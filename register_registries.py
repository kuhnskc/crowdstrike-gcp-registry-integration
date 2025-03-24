from google.cloud import artifactregistry_v1
from google.cloud import resourcemanager_v3
from falconpy import FalconContainer
import os
import json
import subprocess
import argparse

def cleanup_falcon_registries(falcon_client_id, falcon_client_secret):
    """Remove only GAR registries from Falcon"""
    falcon = FalconContainer(
        client_id=falcon_client_id,
        client_secret=falcon_client_secret
    )
    
    print("\nListing existing registry registrations in Falcon...")
    
    # First get list of IDs
    response = falcon.read_registry_entities()
    if response['status_code'] != 200:
        print("Failed to list registries")
        return
    
    registry_ids = response['body']['resources']
    if not registry_ids:
        print("No registries found in Falcon")
        return

    print(f"\nFound {len(registry_ids)} total registries")
    
    # Get details for each registry using read_registry_entities_by_uuid
    gar_registries = []
    for registry_id in registry_ids:
        try:
            details = falcon.read_registry_entities_by_uuid(ids=registry_id)
            print(f"\nDebug: Details for registry {registry_id}:")
            print(json.dumps(details, indent=2))
            
            if details['status_code'] == 200:
                registry = details['body'].get('resources', [{}])[0]
                if registry.get('type') == 'gar':
                    gar_registries.append({
                        'id': registry_id,
                        'alias': registry.get('user_defined_alias', 'Unknown'),
                        'url': registry.get('url', 'Unknown')
                    })
                    print(f"Found GAR registry: {registry.get('user_defined_alias', 'Unknown')}")
            
        except Exception as e:
            print(f"Error processing registry {registry_id}: {str(e)}")
            continue
    
    if not gar_registries:
        print("\nNo Google Artifact Registry registrations found in Falcon")
        return
    
    print(f"\nFound {len(gar_registries)} Google Artifact Registry registrations to remove:")
    for reg in gar_registries:
        print(f"- {reg['alias']} ({reg['url']})")
    
    # Confirm before deletion
    confirm = input("\nDo you want to proceed with removal? (y/N): ")
    if confirm.lower() != 'y':
        print("Aborted registry removal")
        return
    
    print("\nRemoving registries...")
    for reg in gar_registries:
        try:
            print(f"\nRemoving {reg['alias']}...")
            response = falcon.delete_registry_entities(ids=[reg['id']])
            
            if response['status_code'] == 200:
                print(f"Successfully removed {reg['alias']}")
            else:
                print(f"Failed to remove {reg['alias']}: {response.get('body', {}).get('errors', [])}")
        except Exception as e:
            print(f"Error removing {reg['alias']}: {str(e)}")
    
    print("\nCleanup complete. Note: Records will be hard deleted after 48 hours.")

def cleanup_service_account(project_id, sa_name="crowdstrike-registry-scanner"):
    """Remove the service account if it exists"""
    sa_email = f"{sa_name}@{project_id}.iam.gserviceaccount.com"
    print(f"\nChecking for service account {sa_email}...")
    
    try:
        # List all service accounts and check if our target exists
        list_cmd = f"gcloud iam service-accounts list --project={project_id} --format='value(email)'"
        result = subprocess.run(list_cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Error listing service accounts: {result.stderr}")
            return
            
        service_accounts = result.stdout.splitlines()
        
        if sa_email not in service_accounts:
            print(f"Service account {sa_email} does not exist - no cleanup needed")
            return
            
        # If we get here, the service account exists - try to delete it
        print(f"Service account found - attempting to delete...")
        delete_cmd = f"gcloud iam service-accounts delete {sa_email} --project={project_id} --quiet"
        delete_result = subprocess.run(delete_cmd, shell=True, capture_output=True, text=True)
        
        if delete_result.returncode == 0:
            print(f"Successfully removed service account {sa_email}")
        else:
            print(f"Failed to remove service account: {delete_result.stderr}")
            
    except Exception as e:
        print(f"Error during service account cleanup: {str(e)}")

def get_service_account_key(project_id, sa_name="crowdstrike-registry-scanner"):
    """Create or get service account and return its key"""
    print(f"\nManaging service account in project {project_id}...")
    sa_email = f"{sa_name}@{project_id}.iam.gserviceaccount.com"
    
    try:
        # Check if service account exists
        check_cmd = f"gcloud iam service-accounts describe {sa_email} --project={project_id}"
        subprocess.run(check_cmd, shell=True, check=True, capture_output=True)
        print(f"Found existing service account: {sa_email}")
    except subprocess.CalledProcessError:
        # Create service account if it doesn't exist
        print(f"Creating new service account: {sa_email}")
        create_cmd = [
            'gcloud', 'iam', 'service-accounts', 'create',
            sa_name,
            f'--project={project_id}',
            '--display-name=CrowdStrike Registry Scanner',
            '--description=Service account for CrowdStrike container registry scanning'
        ]
        subprocess.run(create_cmd, check=True)

    # Create new key
    key_file = 'service_account_key.json'
    key_cmd = [
        'gcloud', 'iam', 'service-accounts', 'keys', 'create',
        key_file,
        f'--iam-account={sa_email}',
        f'--project={project_id}'
    ]
    subprocess.run(key_cmd, check=True)
    
    # Read and return the key
    with open(key_file, 'r') as f:
        key_json = json.load(f)
    
    # Clean up key file
    os.remove(key_file)
    return key_json, sa_email

def grant_required_roles(project_id, service_account_email):
    """Grant required roles to service account"""
    required_roles = [
        "roles/artifactregistry.reader",
        "roles/storage.objectViewer"
    ]
    
    print(f"\nGranting roles in project {project_id} to service account...")
    for role in required_roles:
        try:
            cmd = f"gcloud projects add-iam-policy-binding {project_id} " \
                  f"--member=serviceAccount:{service_account_email} " \
                  f"--role={role} " \
                  f"--condition=None " \
                  f"--format='value(bindings.role)' " \
                  f"--quiet"
            
            subprocess.run(cmd, shell=True, check=True, capture_output=True)
            print(f"Granted {role}")
            
        except subprocess.CalledProcessError as e:
            print(f"Failed to grant {role}: {e.stderr}")

def list_gcp_registries():
    """List all Artifact Registries across all accessible projects"""
    client = artifactregistry_v1.ArtifactRegistryClient()
    projects_client = resourcemanager_v3.ProjectsClient()
    
    registries = []
    print("\nDiscovering GCP registries...")
    
    # List all projects
    request = resourcemanager_v3.SearchProjectsRequest()
    projects = projects_client.search_projects(request=request)
    
    for project in projects:
        project_id = project.project_id
        print(f"\nChecking project: {project_id}")
        
        # List repositories in specific locations
        locations = ['us-central1', 'us-east1', 'us-west1', 'europe-west1', 'asia-east1']
        
        for location in locations:
            try:
                parent = f"projects/{project_id}/locations/{location}"
                request = artifactregistry_v1.ListRepositoriesRequest(parent=parent)
                repositories = client.list_repositories(request=request)
                
                for repo in repositories:
                    registry_info = {
                        'name': repo.name,
                        'project_id': project_id,
                        'location': location,
                        'repository_id': repo.name.split('/')[-1]
                    }
                    registries.append(registry_info)
                    print(f"Found registry: {repo.name} in {location}")
                    
            except Exception as e:
                if "SERVICE_DISABLED" in str(e):
                    print(f"Note: Artifact Registry API not enabled in project {project_id}")
                    break  # Skip remaining locations for this project
                elif "PERMISSION_DENIED" in str(e):
                    print(f"Note: No access to Artifact Registry in project {project_id}")
                    break
                else:
                    print(f"Error checking {location} in project {project_id}: {str(e)}")
    
    return registries

def register_with_falcon(registries, service_account_key, falcon_client_id, falcon_client_secret):
    """Register registries with CrowdStrike"""
    falcon = FalconContainer(
        client_id=falcon_client_id,
        client_secret=falcon_client_secret
    )
    
    results = []
    for registry in registries:
        # Create request body matching API documentation
        request_body = {
            "type": "gar",
            "url": f"https://{registry['location']}-docker.pkg.dev/",
            "url_uniqueness_key": f"{registry['project_id']}/{registry['repository_id']}",
            "user_defined_alias": f"GAR-{registry['project_id']}-{registry['repository_id']}",
            "credential": {
                "details": {
                    "project_id": registry['project_id'],
                    "scope_name": registry['repository_id'],
                    "service_account_json": {
                        "type": "service_account",
                        "private_key_id": service_account_key.get('private_key_id'),
                        "private_key": service_account_key.get('private_key'),
                        "client_email": service_account_key.get('client_email'),
                        "client_id": service_account_key.get('client_id'),
                        "project_id": service_account_key.get('project_id')
                    }
                }
            }
        }
        
        print(f"\nRegistering {registry['name']}...")
        response = falcon.create_registry_entities(body=request_body)
        
        results.append({
            'registry': registry['name'],
            'status': response['status_code'],
            'response': response.get('body', {})
        })
        
        if response['status_code'] == 200:
            print(f"Successfully registered {registry['name']}")
        else:
            print(f"Failed to register {registry['name']}: {response['body'].get('errors', [])}")
    
    return results

def provision_registries(host_project, falcon_client_id, falcon_client_secret):
    """Handle the provisioning workflow"""
    # Find all registries
    registries = list_gcp_registries()
    if not registries:
        print("No registries found")
        return
    
    print(f"\nFound {len(registries)} registries")
    
    # Create/get service account and key
    service_account_key, service_account_email = get_service_account_key(host_project)
    
    # Grant permissions in each project that has registries
    projects_processed = set()
    for registry in registries:
        if registry['project_id'] not in projects_processed:
            grant_required_roles(registry['project_id'], service_account_email)
            projects_processed.add(registry['project_id'])
    
    # Register with CrowdStrike
    results = register_with_falcon(registries, service_account_key, falcon_client_id, falcon_client_secret)
    
    # Print summary
    print("\n=== Registration Summary ===")
    success_count = len([r for r in results if r['status'] == 200])
    print(f"Total registries: {len(registries)}")
    print(f"Successfully registered: {success_count}")
    print(f"Failed: {len(registries) - success_count}")
    
    if len(registries) - success_count > 0:
        print("\nFailed registrations:")
        for result in results:
            if result['status'] != 200:
                print(f"\nRegistry: {result['registry']}")
                print(f"Error: {result['response'].get('errors', [])}")

def main():
    # Add command line arguments
    parser = argparse.ArgumentParser(description='Manage GCP Artifact Registry registration with CrowdStrike')
    parser.add_argument('--deprovision', action='store_true', 
                      help='Deprovision registries from CrowdStrike and cleanup service account')
    args = parser.parse_args()

    # Get environment variables
    host_project = os.environ.get('GCP_HOST_PROJECT')
    falcon_client_id = os.environ.get('FALCON_CLIENT_ID')
    falcon_client_secret = os.environ.get('FALCON_CLIENT_SECRET')
    
    if not all([host_project, falcon_client_id, falcon_client_secret]):
        raise ValueError("Missing required environment variables: GCP_HOST_PROJECT, FALCON_CLIENT_ID, FALCON_CLIENT_SECRET")

    if args.deprovision:
        print("\n=== Starting Deprovisioning ===")
        cleanup_falcon_registries(falcon_client_id, falcon_client_secret)
        cleanup_service_account(host_project)
        print("\n=== Deprovisioning Complete ===")
    else:
        print("\n=== Starting Provisioning ===")
        provision_registries(host_project, falcon_client_id, falcon_client_secret)
        print("\n=== Provisioning Complete ===")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Script failed: {str(e)}")
