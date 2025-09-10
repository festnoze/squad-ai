# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Testing
- `pytest` - Run all tests (configured via pytest.ini)
- `pytest tests/agents/` - Run specific test directory
- `pytest tests/test_specific_file.py` - Run specific test file
- Tests are configured to run from the `app` directory as pythonpath

### Linting and Code Quality
- `pylint app/` - Run pylint on the app directory (dev dependency)

### Running the Application
- `uvicorn app.api.startup:app --reload` - Start the FastAPI development server
- `python -m app.api.startup` - Alternative way to start the application

### Docker
- `docker_local_build_run.bat` - Build and run Docker container locally
- `docker_gcp_deploy.bat` - Deploy to Google Cloud Platform

## Architecture Overview

This is a **Prospect Incoming Callbot** - an AI-powered phone conversation system that handles incoming calls using Twilio, performs speech-to-text transcription, processes conversations through AI agents, and responds with text-to-speech.

### Core Components

1. **Agent System (LangGraph-based)**:
   - `app/agents/agents_graph.py` - Main orchestration using LangGraph StateGraph
   - `app/agents/lead_agent.py` - Lead qualification agent
   - `app/agents/calendar_agent.py` - Calendar scheduling agent  
   - `app/agents/sf_agent.py` - Salesforce integration agent
   - State model: `phone_conversation_state_model.py`

2. **Audio Processing Pipeline**:
   - `app/managers/incoming_audio_manager.py` - Handles incoming audio from Twilio WebSocket
   - `app/managers/outgoing_audio_manager.py` - Manages outgoing audio responses
   - `app/speech/speech_to_text.py` - Google Cloud Speech-to-Text integration
   - `app/speech/text_to_speech.py` - Text-to-speech conversion
   - Uses WebRTC VAD for voice activity detection

3. **API Layer**:
   - `app/endpoints.py` - FastAPI routes for Twilio webhooks and WebSocket connections
   - `app/api/startup.py` - Application initialization and cleanup
   - `app/phone_call_websocket_events_handler.py` - WebSocket event handling

4. **Calendar Integration** (Interface-based):
   - `app/api_client/calendar_client_interface.py` - Generic calendar interface
   - `app/api_client/salesforce_api_client.py` - Salesforce calendar implementation
   - `app/api_client/google_calendar_client.py` - Google Calendar implementation
   - `app/utils/google_calendar_auth.py` - Google Calendar authentication helper

5. **External Integrations**:
   - `app/api_client/salesforce_user_client_interface.py` - Salesforce user/CRM interface
   - `app/api_client/salesforce_api_client.py` - Salesforce API integration (CRM + Calendar)
   - `app/api_client/studi_rag_inference_api_client.py` - RAG inference client
   - Twilio for telephony services

5. **LLM Integration**:
   - `llms/langchain_factory.py` - LangChain model factory
   - Support for OpenAI and other LLM providers via LangChain

### Key Technologies
- **FastAPI** - Web framework and API endpoints
- **LangGraph** - Agent orchestration and state management
- **LangChain** - LLM integration and prompt management
- **Twilio** - Phone call handling and WebSocket audio streaming
- **Google Cloud Speech/TTS** - Speech processing services
- **WebRTC VAD** - Voice activity detection
- **asyncio** - Asynchronous processing throughout

### Configuration
- Agent configurations in `app/agents/configs/` (YAML files)
- Environment variables handled via `app/utils/envvar.py`
- Secrets stored in `secrets/` directory (not committed)

#### Calendar Provider Configuration
The system supports multiple calendar providers via the `CalendarClientInterface`:

**Salesforce Calendar (default)**:
- Uses Salesforce Events API or Lightning Scheduler
- Configured via `CALENDAR_PROVIDER=salesforce`
- Requires Salesforce authentication credentials

**Google Calendar**:
- Uses Google Calendar API v3
- Configured via `CALENDAR_PROVIDER=google`
- Requires Google service account credentials

Environment variables for calendar configuration:
- `CALENDAR_PROVIDER` - Choose between "salesforce" or "google"
- `GOOGLE_CALENDAR_CREDENTIALS_FILEPATH` - Path to Google service account JSON file
- `GOOGLE_CALENDAR_ID` - Google Calendar ID (default: "primary")
- `GOOGLE_CALENDAR_TIMEZONE` - Timezone for appointments (default: "Europe/Paris")

### Audio File Management
- Incoming audio stored in `static/incoming_audio/`
- Outgoing audio stored in `static/outgoing_audio/`
- Logs stored in `outputs/logs/`
- These directories are cleared on startup

### Testing Strategy
- Integration tests for agents in `tests/agents/`
- Unit tests for managers in `tests/managers/`
- API client tests in `tests/api_client/`
- Uses pytest-asyncio for async test support
- Parameterized testing with `parameterized` library