# Azure Artifacts Setup for common_tools Library

This document explains how the SkillForge Backend API integrates with Azure Artifacts to install the `common_tools` library with flexible dependency management.

## Overview

The `common_tools` library now supports optional dependency groups (extras) to minimize installation size and avoid platform-specific requirements. The SkillForge backend only installs the `database` extra, excluding unnecessary dependencies like `pinecone` and `ml`.

## Configuration

### Environment Variables

The following environment variables control the `common_tools` installation:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `ENVIRONMENT` | Installation mode (`development`, `built-lib`, `production`) | `development` | Yes |
| `COMMON_TOOLS_INSTALL_MODE` | Comma-separated list of extras to install | `database` | No |
| `AICOMMONTOOLS_LOCAL_PATH` | Local path for development mode | `C:/Dev/IA/AzureDevOps/ai-commun-tools` | Dev only |
| `AZURE_ARTIFACT_FEED_URL` | Azure Artifacts feed URL | - | Prod only |
| `AZURE_ARTIFACT_FEED_TOKEN` | Azure DevOps PAT token | - | Prod only |
| `AICOMMONTOOLS_VERSION` | Specific version to install | (latest) | No |

### Available Dependency Groups

The `common_tools` library supports the following extras:

- **Core dependencies** (always installed): ChromaDB, LangChain, OpenAI, etc.
- `database` - Database support (SQLAlchemy, asyncpg, psycopg2-binary) ✅ **Required for SkillForge**
- `qdrant` - Qdrant vector DB (qdrant-client, langchain-qdrant)
- `pinecone` - Pinecone vector DB (⚠️ requires C++ redistributable) ❌ **Not needed**
- `ml` - ML/scientific computing (scikit-learn, scipy, pandas) ❌ **Not needed**
- `advanced` - Advanced AI features (langgraph, langsmith, ragas)
- `full` - All optional dependencies

**For SkillForge**, we use `COMMON_TOOLS_INSTALL_MODE=database` to install only the database dependencies.

## Local Development Setup

1. **Create `.env` file:**
   ```bash
   cp .env.sample .env
   ```

2. **Configure `.env`:**
   ```bash
   ENVIRONMENT=development
   AICOMMONTOOLS_LOCAL_PATH=C:/Dev/IA/AzureDevOps/ai-commun-tools
   COMMON_TOOLS_INSTALL_MODE=database
   ```

3. **Install dependencies:**
   ```bash
   make install
   ```

This will install `common_tools` as an editable package from the local path with only the `database` extra:
```bash
uv pip install -e "common-tools[database] @ C:/Dev/IA/AzureDevOps/ai-commun-tools"
```

## Azure Pipeline Setup

### Prerequisites

1. **Azure Artifacts Feed**: Create a PyPI feed in Azure Artifacts to host the `common_tools` package
2. **Service Connection**: Ensure the pipeline has access to the Azure Artifacts feed
3. **System.AccessToken**: The pipeline uses the built-in `$(System.AccessToken)` for authentication

### Pipeline Variables

Configure the following variables in `azure-pipelines.yml`:

```yaml
variables:
  ENVIRONMENT: 'production'
  COMMON_TOOLS_INSTALL_MODE: 'database'
  AZURE_ARTIFACTS_FEED_NAME: 'your-feed-name'  # Replace with your feed name
  AZURE_DEVOPS_ORG: 'studi-ai'
  AZURE_ARTIFACTS_PROJECT: 'Skillforge'
```

### Test Stage

The test stage:
1. Authenticates with Azure Artifacts using `PipAuthenticate@1` task
2. Sets environment variables for the feed URL and token
3. Installs dependencies with `uv sync`
4. Runs the `install_aicommontools.py` script to install `common_tools[database]` from Azure Artifacts

### Build Stage (Docker)

The Docker build stage:
1. Authenticates with Azure Artifacts
2. Passes build arguments to the Dockerfile:
   - `AZURE_ARTIFACT_FEED_URL`: Feed URL for pip installation
   - `AZURE_ARTIFACT_FEED_TOKEN`: Authentication token
   - `COMMON_TOOLS_INSTALL_MODE`: Dependency extras to install
3. Builds the Docker image with `common_tools[database]` installed

## Docker Build

### Dockerfile Changes

The Dockerfile accepts build arguments for Azure Artifacts authentication:

```dockerfile
ARG AZURE_ARTIFACT_FEED_URL
ARG AZURE_ARTIFACT_FEED_TOKEN
ARG COMMON_TOOLS_INSTALL_MODE=database

ENV AZURE_ARTIFACT_FEED_URL=${AZURE_ARTIFACT_FEED_URL}
ENV AZURE_ARTIFACT_FEED_TOKEN=${AZURE_ARTIFACT_FEED_TOKEN}
ENV COMMON_TOOLS_INSTALL_MODE=${COMMON_TOOLS_INSTALL_MODE}

RUN uv run python scripts/install_aicommontools.py
```

### Local Docker Build

To build the Docker image locally with Azure Artifacts:

```bash
# Set your Azure DevOps PAT token
export AZURE_TOKEN="your-pat-token"

# Build the image
docker build \
  --build-arg AZURE_ARTIFACT_FEED_URL=https://pkgs.dev.azure.com/studi-ai/Skillforge/_packaging/your-feed-name/pypi/simple/ \
  --build-arg AZURE_ARTIFACT_FEED_TOKEN=$AZURE_TOKEN \
  --build-arg COMMON_TOOLS_INSTALL_MODE=database \
  -t skillforge-api:local .
```

## Installation Script

The `scripts/install_aicommontools.py` script handles all three installation modes:

### Development Mode
```bash
uv pip install -e "common-tools[database] @ /path/to/local/repo"
```

### Built-lib Mode
```bash
uv pip install wheels/common_tools-{version}-py3-none-any.whl[database]
```

### Production Mode
```bash
uv pip install common-tools[database]=={version} --index-url https://pkgs.dev.azure.com/.../pypi/simple/
```

## Troubleshooting

### Authentication Issues

If you encounter authentication errors:

1. **Pipeline**: Ensure the pipeline has the "Project Collection Build Service" contributor access to the feed
2. **Local Docker**: Verify your PAT token has "Packaging (Read)" permissions
3. **Feed URL**: Ensure the feed URL format is correct with `/pypi/simple/` suffix

### Missing Dependencies

If you get import errors:

1. Check that `COMMON_TOOLS_INSTALL_MODE=database` is set
2. Verify the `common_tools` package version supports the extras system
3. Ensure `scripts/install_aicommontools.py` is using the updated version

### Docker Build Failures

If Docker build fails:

1. Check that build arguments are passed correctly in the pipeline
2. Verify the Azure Artifacts feed is accessible
3. Review the Docker build logs for authentication errors
4. Ensure `.dockerignore` excludes unnecessary files

## Publishing common_tools to Azure Artifacts

To publish a new version of `common_tools` to Azure Artifacts:

1. **Build the wheel** in the `ai-commun-tools` repository:
   ```bash
   python -m build
   ```

2. **Upload to Azure Artifacts**:
   ```bash
   # Install twine
   pip install twine

   # Upload to Azure Artifacts
   twine upload --repository-url https://pkgs.dev.azure.com/studi-ai/Skillforge/_packaging/your-feed-name/pypi/upload/ \
                --username studi-ai \
                --password YOUR_PAT_TOKEN \
                dist/*
   ```

3. **Update the version** in SkillForge's `.env` if needed:
   ```bash
   AICOMMONTOOLS_VERSION=1.0.0
   ```

## References

- [Azure Artifacts Python Feeds](https://docs.microsoft.com/en-us/azure/devops/artifacts/quickstarts/python-packages)
- [UV Package Manager](https://github.com/astral-sh/uv)
- [Python Package Extras](https://packaging.python.org/en/latest/specifications/dependency-specifiers/#extras)
