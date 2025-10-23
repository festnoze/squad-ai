# AICommonTools Installation Guide

This document explains how the AICommonTools dependency is installed differently based on the environment.

## Overview

The SkillForge API uses a custom internal library called **AICommonTools** that contains shared utilities. The installation method differs based on whether you're in development or production:

- **Development**: Editable install from local repository path
- **Production**: Install from Azure Artifacts private package feed

## How It Works

The installation is handled by `scripts/install_aicommontools.py`, which:

1. Reads the `ENVIRONMENT` variable from your `.env` file
2. Chooses the appropriate installation method
3. Executes the corresponding `uv pip install` command

This script is automatically executed when you run:
```bash
make install
```

Or manually with:
```bash
make install-aicommontools
```

## Development Setup

### Prerequisites

1. Clone the AICommonTools repository locally
2. Ensure it's accessible at a known path (e.g., `C:/Dev/IA/AzureDevOps/ai-commun-tools`)

### Configuration

In your `.env` file:

```bash
ENVIRONMENT=development
AICOMMONTOOLS_LOCAL_PATH=C:/Dev/IA/AzureDevOps/ai-commun-tools
```

### What Happens

The script will execute:
```bash
uv pip install -e "AICommonTools @ C:/Dev/IA/AzureDevOps/ai-commun-tools"
```

This creates an **editable installation**, meaning:
- Changes to AICommonTools are immediately reflected in your API
- No need to reinstall after modifying the library
- Perfect for simultaneous development of both projects

### Troubleshooting

**Error: Local path does not exist**
- Verify the path in `AICOMMONTOOLS_LOCAL_PATH` is correct
- Ensure you've cloned the AICommonTools repository
- Use forward slashes (`/`) or escaped backslashes (`\\`) in the path

## Production Setup (Docker/Azure)

### Prerequisites

1. AICommonTools published to Azure Artifacts
2. Azure DevOps Personal Access Token (PAT) with Packaging Read permissions

### Configuration

The Docker container automatically sets `ENVIRONMENT=production`.

You need to provide these environment variables (via Azure App Service Configuration or Dockerfile):

```bash
ENVIRONMENT=production
AZURE_ARTIFACT_FEED_URL=https://pkgs.dev.azure.com/studi-ai/_packaging/skillforge-packages/pypi/simple/
AZURE_ARTIFACT_FEED_TOKEN=your-pat-token-here
AICOMMONTOOLS_VERSION=1.0.0  # Optional, leave empty for latest
```

### What Happens

The script will execute:
```bash
uv pip install AICommonTools==1.0.0 --index-url https://{token}@pkgs.dev.azure.com/...
```

This installs the specified (or latest) version from your private Azure Artifacts feed.

### Creating a Personal Access Token (PAT)

1. Go to Azure DevOps: `https://dev.azure.com/studi-ai`
2. Click on User Settings (top right) → Personal Access Tokens
3. Click "New Token"
4. Configure:
   - **Name**: SkillForge AICommonTools Access
   - **Organization**: studi-ai
   - **Scopes**: Custom defined → Packaging (Read)
5. Copy the token and store it securely
6. Add it to your Azure App Service configuration as `AZURE_ARTIFACT_FEED_TOKEN`

### Security Notes

- **Never commit PAT tokens to git**
- Use Azure App Service Configuration / Key Vault for token storage
- Tokens should have minimal permissions (Read only)
- Rotate tokens regularly

## Publishing AICommonTools to Azure Artifacts

When you update AICommonTools and want to deploy to production:

### 1. Update Version

In `AICommonTools/pyproject.toml`:
```toml
[project]
version = "1.0.1"  # Increment version
```

### 2. Build Package

```bash
cd /path/to/ai-commun-tools
uv build
```

This creates `dist/AICommonTools-1.0.1-py3-none-any.whl`

### 3. Publish to Azure Artifacts

```bash
# Install twine if needed
uv pip install twine

# Upload to Azure Artifacts
twine upload --repository-url https://pkgs.dev.azure.com/studi-ai/_packaging/skillforge-packages/pypi/upload/ \
  --username studi-ai \
  --password {your-pat-token} \
  dist/AICommonTools-1.0.1-py3-none-any.whl
```

### 4. Update Production

Update `.env` or Azure App Service configuration:
```bash
AICOMMONTOOLS_VERSION=1.0.1
```

Rebuild and redeploy your Docker container.

## CI/CD Integration

### GitHub Actions / Azure Pipelines

For automated deployments, add the PAT token as a secret and reference it in your pipeline:

**Azure Pipelines example:**
```yaml
steps:
  - script: |
      export AZURE_ARTIFACT_FEED_TOKEN=$(AZURE_ARTIFACTS_PAT)
      make install
    displayName: 'Install dependencies'
    env:
      ENVIRONMENT: production
```

**GitHub Actions example:**
```yaml
- name: Install dependencies
  env:
    ENVIRONMENT: production
    AZURE_ARTIFACT_FEED_TOKEN: ${{ secrets.AZURE_ARTIFACTS_PAT }}
  run: make install
```

## Manual Installation

If you need to install AICommonTools manually without using the script:

**Development:**
```bash
.venv\Scripts\activate
uv pip install -e "AICommonTools @ C:/Dev/IA/AzureDevOps/ai-commun-tools"
```

**Production:**
```bash
.venv\Scripts\activate
uv pip install AICommonTools==1.0.0 \
  --index-url https://{token}@pkgs.dev.azure.com/studi-ai/_packaging/skillforge-packages/pypi/simple/
```

## Verifying Installation

After installation, verify AICommonTools is available:

```bash
.venv\Scripts\activate
python -c "import AICommonTools; print(AICommonTools.__version__)"
```

Or check installed packages:
```bash
uv pip list | grep AICommonTools
```

Development mode will show the local path:
```
AICommonTools  1.0.0  C:\Dev\IA\AzureDevOps\ai-commun-tools
```

Production mode will show the installed version:
```
AICommonTools  1.0.0
```
