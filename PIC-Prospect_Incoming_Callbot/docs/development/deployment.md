# Deployment

This document covers various deployment strategies for the PIC Prospect Incoming Callbot, including local development, staging, and production deployments on different platforms.

## Deployment Overview

The application supports multiple deployment methods:
- **Local Development**: Direct Python execution with uvicorn
- **Docker Local**: Containerized local deployment
- **Google Cloud Run**: Serverless production deployment
- **Docker Compose**: Multi-service local deployment
- **Kubernetes**: Scalable container orchestration

## Local Development Deployment

### Direct Python Execution

**Prerequisites**:
- Python 3.11+
- All dependencies installed
- Environment variables configured

**Commands**:
```bash
# Install dependencies
pip install -e .[dev]

# Set environment variables
export TWILIO_ACCOUNT_SID="your_twilio_account_sid"
export TWILIO_AUTH_TOKEN="your_twilio_auth_token"
# ... other environment variables

# Start development server
uvicorn app.api.startup:app --reload --host 0.0.0.0 --port 8080

# Alternative using Python module
python -m app.api.startup
```

**Development Features**:
- Hot reload on code changes
- Debug mode enabled
- Detailed error messages
- API documentation at `/docs`

### Environment Configuration

**File**: `.env` (for local development)
```bash
# Application settings
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
HOST=0.0.0.0
PORT=8080

# Twilio configuration
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number

# Google Cloud settings
GOOGLE_CLOUD_PROJECT=your_gcp_project
GOOGLE_APPLICATION_CREDENTIALS=secrets/google-credentials.json

# Salesforce settings
SALESFORCE_USERNAME=your_salesforce_username
SALESFORCE_PASSWORD=your_salesforce_password
SALESFORCE_SECURITY_TOKEN=your_salesforce_token

# Calendar settings
CALENDAR_PROVIDER=google
GOOGLE_CALENDAR_CREDENTIALS_FILEPATH=secrets/google-calendar-credentials.json
GOOGLE_CALENDAR_ID=primary
GOOGLE_CALENDAR_TIMEZONE=Europe/Paris

# LLM settings
OPENAI_API_KEY=your_openai_api_key
LLM_PROVIDER=openai
LLM_MODEL=gpt-4
```

## Docker Deployment

### Local Docker Build and Run

**Build Image**:
```bash
# Build Docker image
docker build -t prospect-callbot .

# Build with specific tag
docker build -t prospect-callbot:v1.0.0 .
```

**Run Container**:
```bash
# Run with environment file
docker run -p 8080:8080 --env-file .env prospect-callbot

# Run with individual environment variables
docker run -p 8080:8080 \
  -e TWILIO_ACCOUNT_SID=your_sid \
  -e TWILIO_AUTH_TOKEN=your_token \
  prospect-callbot

# Run in detached mode
docker run -d -p 8080:8080 --env-file .env --name callbot prospect-callbot
```

**Container Management**:
```bash
# View running containers
docker ps

# View container logs
docker logs callbot

# Stop container
docker stop callbot

# Remove container
docker rm callbot
```

### Docker Compose Deployment

**File**: `docker-compose.yml`
```yaml
version: '3.8'

services:
  callbot:
    build: .
    ports:
      - "8080:8080"
    environment:
      - ENVIRONMENT=development
      - DEBUG=true
    env_file:
      - .env
    volumes:
      - ./secrets:/app/secrets:ro
      - ./outputs/logs:/app/outputs/logs
      - ./static:/app/static
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - callbot
    restart: unless-stopped
```

**Commands**:
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down

# Rebuild and restart
docker-compose up -d --build
```

## Google Cloud Run Deployment

### Automated Deployment Script

**File**: `docker_gcp_deploy.bat` (see [GCP Deployment Guide](../GCP-deployment.md))

**Manual Deployment Steps**:

1. **Authenticate with Google Cloud**:
```bash
gcloud auth activate-service-account --key-file=secrets/google-credentials-for-GCP-deploiement.json
gcloud config set project studi-com-rag-api
```

2. **Configure Docker for Artifact Registry**:
```bash
gcloud auth configure-docker europe-west1-docker.pkg.dev
```

3. **Build and Push Image**:
```bash
# Build image with Cloud Run tag
docker build -t europe-west1-docker.pkg.dev/studi-com-rag-api/depot-docker/prospect-incoming-callbot .

# Push to Artifact Registry
docker push europe-west1-docker.pkg.dev/studi-com-rag-api/depot-docker/prospect-incoming-callbot
```

4. **Deploy to Cloud Run**:
```bash
gcloud run deploy prospect-incoming-callbot \
  --image europe-west1-docker.pkg.dev/studi-com-rag-api/depot-docker/prospect-incoming-callbot \
  --platform managed \
  --region europe-west1 \
  --allow-unauthenticated \
  --port 8080 \
  --memory 2Gi \
  --cpu 2 \
  --timeout 3600 \
  --max-instances 10 \
  --set-env-vars ENVIRONMENT=production
```

### Cloud Run Configuration

**Environment Variables for Production**:
```bash
# Set environment variables in Cloud Run
gcloud run services update prospect-incoming-callbot \
  --set-env-vars ENVIRONMENT=production \
  --set-env-vars LOG_LEVEL=INFO \
  --set-env-vars TWILIO_ACCOUNT_SID=your_production_sid \
  --region europe-west1
```

**Cloud Run Service Settings**:
- **CPU**: 2 vCPU
- **Memory**: 2 GiB
- **Timeout**: 3600 seconds (1 hour)
- **Concurrency**: 100 requests per instance
- **Min Instances**: 0 (scales to zero)
- **Max Instances**: 10

### Secrets Management in Cloud Run

**Using Google Secret Manager**:
```bash
# Create secrets
gcloud secrets create twilio-auth-token --data-file=-
gcloud secrets create salesforce-password --data-file=-

# Grant access to Cloud Run service account
gcloud secrets add-iam-policy-binding twilio-auth-token \
  --member="serviceAccount:your-service-account@project.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Mount secrets in Cloud Run
gcloud run services update prospect-incoming-callbot \
  --set-secrets TWILIO_AUTH_TOKEN=twilio-auth-token:latest \
  --region europe-west1
```

## Kubernetes Deployment

### Kubernetes Manifests

**File**: `k8s/deployment.yaml`
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prospect-callbot
  labels:
    app: prospect-callbot
spec:
  replicas: 3
  selector:
    matchLabels:
      app: prospect-callbot
  template:
    metadata:
      labels:
        app: prospect-callbot
    spec:
      containers:
      - name: callbot
        image: prospect-callbot:latest
        ports:
        - containerPort: 8080
        env:
        - name: ENVIRONMENT
          value: "production"
        - name: LOG_LEVEL
          value: "INFO"
        envFrom:
        - secretRef:
            name: callbot-secrets
        - configMapRef:
            name: callbot-config
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
```

**File**: `k8s/service.yaml`
```yaml
apiVersion: v1
kind: Service
metadata:
  name: prospect-callbot-service
spec:
  selector:
    app: prospect-callbot
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8080
  type: LoadBalancer
```

**File**: `k8s/configmap.yaml`
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: callbot-config
data:
  CALENDAR_PROVIDER: "google"
  GOOGLE_CALENDAR_TIMEZONE: "Europe/Paris"
  LLM_PROVIDER: "openai"
  LLM_MODEL: "gpt-4"
  SPEECH_LANGUAGE: "fr-FR"
  AUDIO_SAMPLE_RATE: "16000"
```

**File**: `k8s/secret.yaml`
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: callbot-secrets
type: Opaque
stringData:
  TWILIO_ACCOUNT_SID: "your_twilio_account_sid"
  TWILIO_AUTH_TOKEN: "your_twilio_auth_token"
  SALESFORCE_USERNAME: "your_salesforce_username"
  SALESFORCE_PASSWORD: "your_salesforce_password"
  OPENAI_API_KEY: "your_openai_api_key"
```

**Deployment Commands**:
```bash
# Apply Kubernetes manifests
kubectl apply -f k8s/

# Check deployment status
kubectl get deployments

# View pods
kubectl get pods

# Check service
kubectl get services

# View logs
kubectl logs -l app=prospect-callbot

# Scale deployment
kubectl scale deployment prospect-callbot --replicas=5
```

## Production Deployment Checklist

### Pre-Deployment Checklist

- [ ] **Environment Variables**: All production environment variables configured
- [ ] **Secrets Management**: Sensitive data stored securely (not in code)
- [ ] **SSL/TLS**: HTTPS configured for all endpoints
- [ ] **Domain Configuration**: Production domain configured and DNS updated
- [ ] **Monitoring**: Application monitoring and alerting configured
- [ ] **Logging**: Centralized logging configured
- [ ] **Backup**: Database and file backups configured
- [ ] **Load Testing**: Application tested under expected load
- [ ] **Security**: Security scanning completed
- [ ] **Documentation**: Deployment documentation updated

### Production Environment Variables

```bash
# Production settings
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# Security settings
SECRET_KEY=your-secure-secret-key
CORS_ALLOWED_ORIGINS=https://your-domain.com

# External service production URLs
TWILIO_WEBHOOK_BASE_URL=https://your-domain.com
RAG_INFERENCE_URL=https://your-production-rag-api.com

# Performance settings
MAX_CONCURRENT_CALLS=50
AUDIO_BUFFER_SIZE=4096
ENABLE_CACHING=true
```

### Health Checks and Monitoring

**Health Check Endpoint**:
```python
@app.get("/health")
async def health_check():
    """Comprehensive health check"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "services": {}
    }

    # Check external services
    health_status["services"]["twilio"] = await check_twilio_connection()
    health_status["services"]["google_cloud"] = await check_google_cloud_services()
    health_status["services"]["salesforce"] = await check_salesforce_connection()

    return health_status
```

**Monitoring Metrics**:
- Response time percentiles (p50, p95, p99)
- Error rates by endpoint
- Active WebSocket connections
- Audio processing latency
- External API response times
- Resource utilization (CPU, memory)

### SSL/TLS Configuration

**Nginx Configuration for SSL**:
```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    ssl_session_cache shared:SSL:1m;
    ssl_session_timeout 5m;

    location / {
        proxy_pass http://callbot:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

## Rollback Procedures

### Docker Rollback

```bash
# Tag current version before deployment
docker tag prospect-callbot:latest prospect-callbot:backup

# If rollback needed
docker stop callbot
docker rm callbot
docker run -d -p 8080:8080 --env-file .env --name callbot prospect-callbot:backup
```

### Cloud Run Rollback

```bash
# List revisions
gcloud run revisions list --service=prospect-incoming-callbot --region=europe-west1

# Rollback to previous revision
gcloud run services update-traffic prospect-incoming-callbot \
  --to-revisions=prospect-incoming-callbot-00001-abc=100 \
  --region=europe-west1
```

### Kubernetes Rollback

```bash
# Check rollout status
kubectl rollout status deployment/prospect-callbot

# Rollback to previous version
kubectl rollout undo deployment/prospect-callbot

# Rollback to specific revision
kubectl rollout undo deployment/prospect-callbot --to-revision=2
```

## Performance Optimization

### Production Optimizations

**Docker Image Optimization**:
```dockerfile
# Multi-stage build for smaller production image
FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

RUN pip install --no-cache /wheels/*
COPY . .

CMD ["uvicorn", "app.api.startup:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Application Performance**:
- Enable HTTP/2 for better performance
- Use connection pooling for external APIs
- Implement caching for frequently accessed data
- Configure appropriate worker processes
- Enable gzip compression
- Optimize audio buffer sizes

This comprehensive deployment guide covers all aspects of deploying the PIC Prospect Incoming Callbot from development to production environments with proper security, monitoring, and maintenance procedures.