# GCP Artifact Registry Integration with CrowdStrike

**DISCLAIMER:** This is not an officially supported CrowdStrike project. This script was generated with the assistance of AI and should be used at your own risk. Please review and test thoroughly before using in any production environment.

This script automates the registration and management of Google Cloud Platform (GCP) Artifact Registries with CrowdStrike's Image Assessment feature.

## Description

This script performs the following functions:
- Discovers all Artifact Registries across accessible GCP projects
- Creates a service account with necessary permissions
- Registers discovered registries with CrowdStrike
- Provides cleanup functionality to remove registrations and service accounts

## Prerequisites

### Python Requirements
- Python 3.x
- Virtual Environment recommended

### Required Python Packages
```bash
pip install google-cloud-artifact-registry
pip install google-cloud-resource-manager
pip install google-cloud-iam
pip install crowdstrike-falconpy
```

### Required Credentials
1. GCP Authentication:
   - Authenticated gcloud CLI
   - Appropriate permissions to create service accounts and manage IAM roles

2. CrowdStrike API Credentials:
   - API Client ID with the following scopes:
     - `Falcon Container Image: Write`
     - `Falcon Container Image: Read`
   - API Client Secret
   - Created at https://falcon.crowdstrike.com/support/api-clients-and-keys

### Environment Variables
```bash
# To get your project name:
gcloud config get-value project

# Set environment variables:
export GCP_HOST_PROJECT='your-project-name'  # Example: 'my-project-dev'
export FALCON_CLIENT_ID='your-falcon-client-id'
export FALCON_CLIENT_SECRET='your-falcon-client-secret'
```

## Installation

1. Clone the repository:
```bash
git clone [repository-url]
cd [repository-directory]
```

2. Create and activate virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Registering Registries

```bash
python3 register_registries.py
```

This will:
1. Discover all Artifact Registries across your GCP organization
2. Create a service account in your host project
3. Grant the service account necessary permissions in each project with registries
4. Register each registry with CrowdStrike

### Deprovisioning

To remove registrations and cleanup:

```bash
python3 register_registries.py --deprovision
```

This will:
1. Remove all GAR (Google Artifact Registry) registrations from CrowdStrike
2. Remove the created service account
3. Note: This will not affect the actual registries in GCP

## Permissions Required

### GCP Permissions
- Service Account Creator
- IAM Role Administrator
- Artifact Registry Reader
- Storage Object Viewer

### CrowdStrike Permissions
- Image Assessment Administrator
- Registry Management permissions

## Error Handling

The script handles various scenarios:
- Projects without Artifact Registry API enabled
- Missing permissions
- Already registered registries
- Service account management errors

## Notes

- Only affects Google Artifact Registry registrations (does not impact other registry types)
- Service account cleanup only removes the account created by this script
- Registry registrations are soft-deleted in CrowdStrike for 48 hours before hard deletion

## Troubleshooting

Common issues and solutions:
1. "API not enabled" messages: These are normal for projects not using Artifact Registry
2. Permission denied: Verify your GCP roles and CrowdStrike API permissions
3. Service account issues: Ensure you have appropriate IAM permissions in the host project