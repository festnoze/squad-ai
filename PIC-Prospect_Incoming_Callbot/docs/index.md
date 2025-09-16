# PIC Prospect Incoming Callbot

Welcome to the **PIC Prospect Incoming Callbot** documentation! 

This is an AI-powered phone conversation system that handles incoming calls using Twilio, performs speech-to-text transcription, processes conversations through AI agents, and responds with text-to-speech.

## Features

- 🤖 **AI Agent System** - LangGraph-based orchestration with specialized agents
- 📞 **Twilio Integration** - Handles incoming calls and SMS messages
- 🗣️ **Speech Processing** - Google Cloud Speech-to-Text and Text-to-Speech
- 📅 **Calendar Management** - Automated appointment scheduling
- 💼 **Salesforce Integration** - CRM data management
- 🔄 **RAG System** - Retrieval-augmented generation for intelligent responses

## Quick Start

```bash
# Install dependencies
uv pip install -e .[dev]

# Run the application
uvicorn app.api.startup:app --reload

# Run tests with coverage
pytest --cov=app tests/

# Lint and format code
ruff check app/
ruff format app/

# Serve documentation
mkdocs serve
```

## Architecture Overview

The system is built with:

- **FastAPI** - Web framework and API endpoints
- **LangGraph** - Agent orchestration and state management
- **LangChain** - LLM integration and prompt management
- **Twilio** - Phone call handling and WebSocket audio streaming
- **Google Cloud** - Speech processing services
- **asyncio** - Asynchronous processing throughout

## Getting Started

- [Installation](getting-started/installation.md) - Set up your development environment
- [Configuration](getting-started/configuration.md) - Configure environment variables and secrets
- [Running the Application](getting-started/running.md) - Start the application and test it
- [Google Calendar Setup](getting-started/google-calendar-setup.md) - Configure Google Calendar integration

## Architecture

- [Overview](architecture/overview.md) - System architecture and components
- [Agent System](architecture/agents.md) - LangGraph agents and workflow
- [Audio Processing](architecture/audio.md) - Real-time audio pipeline
- [External Integrations](architecture/integrations.md) - Third-party service integrations

## API Reference

- [Endpoints](api/endpoints.md) - FastAPI endpoints and WebSocket handlers
- [Agents](api/agents.md) - LangGraph agents and workflow
- [Managers](api/managers.md) - Audio and conversation managers
- [Utils](api/utils.md) - Utility functions and helpers

## Development

- [Contributing](development/contributing.md) - How to contribute to the project
- [Coding Standards](development/coding-standards.md) - Code style and standards
- [Testing](development/testing.md) - Testing strategies and frameworks
- [Deployment](development/deployment.md) - Deployment procedures and environments

## Deployment

- [GCP Deployment (English)](GCP-deployment.md) - Deploy to Google Cloud Platform
- [GCP Deployment (Français)](GCP-deployment.fr.md) - Déploiement sur Google Cloud Platform