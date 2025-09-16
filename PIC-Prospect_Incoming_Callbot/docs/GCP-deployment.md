# GCP (Google Cloud Platform) Deployment

This document describes the deployment procedure for the **PIC Prospect Incoming Callbot** application on Google Cloud Platform.

## Prerequisites

- Docker installed and configured
- Google Cloud SDK (gcloud) installed
- Service account credentials file: `secrets/google-credentials-for-GCP-deploiement.json`
- Administrator rights on the GCP project

## Automated Deployment

To deploy the application, use the deployment script:

```bash
.\docker_gcp_deploy.bat
```

### Partial Deployment

You can start the process from a specific step by passing the step number as a parameter:

```bash
# Start from step 5 (image build)
.\docker_gcp_deploy.bat 5

# Start from step 7 (Cloud Run deployment)
.\docker_gcp_deploy.bat 7
```

## Deployment Process Steps

The `docker_gcp_deploy.bat` script executes the following steps:

### 1. Service Account Activation
```bash
gcloud auth activate-service-account --key-file=secrets/google-credentials-for-GCP-deploiement.json
```
- Activates authentication with the configured service account
- Uses credentials stored in the `secrets/google-credentials-for-GCP-deploiement.json` file

### 2. Cloud Resource Manager API Activation
```bash
gcloud services enable cloudresourcemanager.googleapis.com --project=studi-com-rag-api --quiet
```
- Enables the Cloud Resource Manager API required for resource management
- Silent operation with the `--quiet` option

### 3. Project Configuration
```bash
gcloud config set project studi-com-rag-api --quiet
```
- Sets the current GCP project to: `studi-com-rag-api`
- Configures the gcloud context for this project

### 4. Docker Configuration for Artifact Registry
```bash
gcloud auth configure-docker europe-west1-docker.pkg.dev --quiet
```
- Configures Docker to authenticate with Artifact Registry
- Region used: `europe-west1`

### 5. Docker Image Build
```bash
docker build -f Dockerfile -t europe-west1-docker.pkg.dev/studi-com-rag-api/depot-docker/prospect-incoming-callbot .
```
- Builds the Docker image from the Dockerfile
- Tags the image with the complete Artifact Registry URL
- Final image: `prospect-incoming-callbot`

### 6. Push to Artifact Registry
```bash
docker push europe-west1-docker.pkg.dev/studi-com-rag-api/depot-docker/prospect-incoming-callbot
```
- Pushes the built image to GCP's Docker registry
- Storage in the `depot-docker` repository

### 7. Cloud Run Deployment
```bash
gcloud run deploy prospect-incoming-callbot --image europe-west1-docker.pkg.dev/studi-com-rag-api/depot-docker/prospect-incoming-callbot --platform managed --region europe-west1 --allow-unauthenticated --port 8080
```
- Deploys the service to Cloud Run
- Configuration:
  - **Service name**: `prospect-incoming-callbot`
  - **Platform**: `managed` (fully managed by Google)
  - **Region**: `europe-west1`
  - **Access**: `--allow-unauthenticated` (public access)
  - **Port**: `8080`

## Project Configuration

The script uses the following variables:

| Variable | Value | Description |
|----------|-------|-------------|
| `PROJECT_ID` | `studi-com-rag-api` | GCP project identifier |
| `REGION` | `europe-west1` | Deployment region |
| `REPO` | `depot-docker` | Artifact Registry repository name |
| `IMAGE_NAME` | `prospect-incoming-callbot` | Image and service name |

## Optional Steps

The script also includes optional steps for post-deployment management:

- **Step 8**: Displays deployed service details
- **Step 9**: Retrieves the service's public URL
- **Step 10**: Displays service logs
- **Step 11**: Removes the local image to free disk space

## Error Handling

The script automatically stops on error (`if errorlevel 1 pause`) allowing you to:
- Identify the failed step
- Fix the issue
- Resume deployment from that step

## Accessing the Deployed Service

Once deployment is complete, the service is accessible via the URL provided by Cloud Run, typically in the format:
```
https://prospect-incoming-callbot-[hash]-ew.a.run.app
```

## Security

- Service account credentials are stored in `secrets/` (not committed)
- Service is configured for public access (`--allow-unauthenticated`)
- The `europe-west1` region ensures GDPR compliance