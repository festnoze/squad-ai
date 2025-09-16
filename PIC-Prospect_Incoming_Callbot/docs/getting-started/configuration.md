# Configuration

This guide explains how to configure the PIC Prospect Incoming Callbot application.

## Environment Variables

Create a `.env` file in the root directory with the following configuration:

### Core Application Settings
```bash
# Environment (development, production)
ENVIRONMENT=development

# Server configuration
HOST=0.0.0.0
PORT=8080
```

### Twilio Configuration
```bash
# Twilio credentials
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number
```

### Google Cloud Services
```bash
# Google Cloud Speech-to-Text and Text-to-Speech
GOOGLE_CLOUD_PROJECT=your_gcp_project_id
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json

# Speech configuration
SPEECH_LANGUAGE=fr-FR
SPEECH_MODEL=chirp_3_hd
TTS_VOICE_NAME=fr-FR-Chirp3-HD-Zephyr
```

### Calendar Integration
```bash
# Calendar provider (salesforce or google)
CALENDAR_PROVIDER=salesforce

# Google Calendar (if using google provider)
GOOGLE_CALENDAR_CREDENTIALS_FILEPATH=secrets/google-calendar-credentials.json
GOOGLE_CALENDAR_ID=primary
GOOGLE_CALENDAR_TIMEZONE=Europe/Paris
```

### Salesforce Integration
```bash
# Salesforce credentials
SALESFORCE_USERNAME=your_salesforce_username
SALESFORCE_PASSWORD=your_salesforce_password
SALESFORCE_SECURITY_TOKEN=your_salesforce_security_token
SALESFORCE_DOMAIN=your_salesforce_domain
```

### LLM Configuration
```bash
# OpenAI
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4

# Alternative LLM providers
ANTHROPIC_API_KEY=your_anthropic_api_key
```

### RAG System
```bash
# RAG inference endpoint
RAG_INFERENCE_URL=https://your-rag-endpoint.com
RAG_API_KEY=your_rag_api_key
```

## Secrets Management

Store sensitive credentials in the `secrets/` directory:

```
secrets/
├── google-credentials-for-GCP-deploiement.json
├── google-calendar-credentials.json
├── salesforce-credentials.json
└── openai-api-key.txt
```

!!! warning "Security Note"
    Never commit secrets to version control. The `secrets/` directory is included in `.gitignore`.

## Agent Configuration

Agent behaviors are configured via YAML files in `app/agents/configs/`:

- `lead_agent_config.yaml` - Lead qualification settings
- `calendar_agent_config.yaml` - Calendar booking configuration
- `sf_agent_config.yaml` - Salesforce integration settings

## Audio Configuration

### Voice Activity Detection
```bash
# WebRTC VAD sensitivity (0-3, 3 = most aggressive)
VAD_MODE=2

# Audio processing
AUDIO_SAMPLE_RATE=16000
AUDIO_CHUNK_SIZE=1024
```

### Pre-generated Audio
The system uses pre-generated audio files stored in `static/pregenerated_audio/` for common responses to reduce latency.

## Logging Configuration

Configure logging levels and output destinations:

```bash
# Logging
LOG_LEVEL=INFO
LOG_FILE=outputs/logs/app.log
ENABLE_FILE_LOGGING=true
ENABLE_CONSOLE_LOGGING=true
```

## Docker Configuration

For Docker deployment, ensure all environment variables are properly set in your Docker Compose or deployment configuration.

## Validation

Run the configuration validation:

```bash
python -m app.utils.config_validator
```

This will check all required environment variables and validate credentials.