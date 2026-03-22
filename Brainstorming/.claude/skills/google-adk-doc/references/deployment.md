# Deployment Reference

## Table of Contents
- [Cloud Run with adk CLI](#cloud-run-with-adk-cli)
- [Cloud Run with gcloud CLI](#cloud-run-with-gcloud-cli)
- [Vertex AI Agent Engine](#vertex-ai-agent-engine)
- [Local / Custom Infrastructure](#local--custom-infrastructure)
- [API Testing](#api-testing)
- [Evaluation](#evaluation)

## Cloud Run with adk CLI

Recommended approach for Python:

```bash
export GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_CLOUD_LOCATION=us-central1

adk deploy cloud_run \
  --project=$GOOGLE_CLOUD_PROJECT \
  --region=$GOOGLE_CLOUD_LOCATION \
  --service_name=my-agent-service \
  --with_ui \
  ./my_agent
```

Options:
- `--service_name`: Cloud Run service name (default: `adk-default-service-name`)
- `--app_name`: ADK API server application name
- `--with_ui`: Include web interface
- `--port`: Server port (default 8000)

Requirements:
- Agent code in `agent.py` with variable named `root_agent`
- `__init__.py` with `from . import agent`
- `requirements.txt` file
- Google Cloud project with Secret Manager for API keys

## Cloud Run with gcloud CLI

Project structure:
```
your-project/
  my_agent/
    __init__.py
    agent.py
  main.py
  requirements.txt
  Dockerfile
```

`main.py`:
```python
import os
import uvicorn
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri="sqlite+aiosqlite:///./sessions.db",
    allow_origins=["*"],
    web=True,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
```

`requirements.txt`:
```
google-adk
```

`Dockerfile`:
```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
```

Deploy:
```bash
gcloud run deploy my-agent-service \
  --source . \
  --region $GOOGLE_CLOUD_LOCATION \
  --project $GOOGLE_CLOUD_PROJECT \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,GOOGLE_CLOUD_LOCATION=$GOOGLE_CLOUD_LOCATION,GOOGLE_GENAI_USE_VERTEXAI=TRUE"
```

## Vertex AI Agent Engine

Managed scaling on Google Cloud infrastructure. Deploy to Vertex AI for scalable agent hosting integrated with Google Cloud's managed infrastructure.

## Local / Custom Infrastructure

```bash
adk web          # Dev UI at http://localhost:8000
adk run my_agent # Terminal interaction
adk api_server   # RESTful API server
```

## API Testing

```bash
export APP_URL="https://your-service.a.run.app"
export TOKEN=$(gcloud auth print-identity-token)

# List apps
curl -X GET -H "Authorization: Bearer $TOKEN" $APP_URL/list-apps

# Create/update session
curl -X POST -H "Authorization: Bearer $TOKEN" \
  $APP_URL/apps/my_agent/users/user_123/sessions/session_abc \
  -H "Content-Type: application/json" \
  -d '{"preferred_language": "English"}'

# Run agent
curl -X POST -H "Authorization: Bearer $TOKEN" \
  $APP_URL/run_sse \
  -H "Content-Type: application/json" \
  -d '{
    "app_name": "my_agent",
    "user_id": "user_123",
    "session_id": "session_abc",
    "new_message": {
      "role": "user",
      "parts": [{"text": "Hello!"}]
    },
    "streaming": false
  }'
```

## Evaluation

```bash
adk eval \
  my_agent \
  my_agent/eval_set.evalset.json
```
