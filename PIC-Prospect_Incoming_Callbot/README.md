# PIC Prospect Incoming Callbot

![Python](https://img.shields.io/badge/python-v3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![LangGraph](https://img.shields.io/badge/LangGraph-latest-orange.svg)

An **AI-powered phone conversation system** that handles incoming calls using Twilio, performs speech-to-text transcription, processes conversations through AI agents, and responds with text-to-speech.

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Google Cloud account (for speech services)
- Twilio account (for phone services)
- Salesforce account (for CRM integration)

### Installation
```bash
# Clone the repository
git clone <repository-url>
cd PIC-Prospect_Incoming_Callbot

# Install dependencies
pip install -e .[dev]

# Set up environment variables
cp .env.example .env
# Edit .env with your credentials
```

### Running the Application

#### Development Server
```bash
# Start the API server
uvicorn app.api.startup:app --reload --port 8344

# Or use VS Code debugger (F5)
```

#### With Documentation
```bash
# Start both API and live documentation
python scripts/dev_with_docs.py
```

### 🌐 Access Points

Once the server is running, access these URLs:

- **API Root**: http://localhost:8344/
- **API Documentation**: http://localhost:8344/docs
- **Site Documentation**: http://localhost:8344/docs-site/
- **ReDoc**: http://localhost:8344/redoc

## 🏗️ Architecture Overview

### Core Components
- 🤖 **AI Agent System** - LangGraph-based orchestration with specialized agents
- 📞 **Twilio Integration** - Handles incoming calls and SMS messages
- 🗣️ **Speech Processing** - Google Cloud Speech-to-Text and Text-to-Speech
- 📅 **Calendar Management** - Automated appointment scheduling
- 💼 **Salesforce Integration** - CRM data management
- 🔄 **RAG System** - Retrieval-augmented generation for intelligent responses

### Technology Stack
- **FastAPI** - Web framework and API endpoints
- **LangGraph** - Agent orchestration and state management
- **LangChain** - LLM integration and prompt management
- **Twilio** - Phone call handling and WebSocket audio streaming
- **Google Cloud** - Speech processing services
- **asyncio** - Asynchronous processing throughout

## 🛠️ Development

### Essential Commands
```bash
# Run tests
pytest

# Lint code
pylint app/

# Start development server
uvicorn app.api.startup:app --reload --port 8344

# Build documentation
python scripts/build_docs.py

# Start both API and docs
python scripts/dev_with_docs.py
```

### Environment Variables
Key environment variables (see [Configuration Guide](docs/getting-started/configuration.md)):

```bash
# Application
ENVIRONMENT=development
PORT=8344
SERVE_DOCUMENTATION=true

# Twilio
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token

# Google Cloud
GOOGLE_CLOUD_PROJECT=your_gcp_project
GOOGLE_APPLICATION_CREDENTIALS=path/to/credentials.json

# Salesforce
SALESFORCE_USERNAME=your_username
SALESFORCE_PASSWORD=your_password

# LLM
OPENAI_API_KEY=your_openai_key
```

## 🐳 Docker Deployment

### Local Docker
```bash
# Build and run locally
docker build -t prospect-callbot .
docker run -p 8080:8080 --env-file .env prospect-callbot
```

### Production (GCP)
```bash
# Deploy to Google Cloud Run
.\docker_gcp_deploy.bat
```

## 📚 Documentation

### Browse Documentation
- **Live Documentation**: Run `mkdocs serve` and visit http://127.0.0.1:8000
- **Built Documentation**: Start the API and visit http://localhost:8344/docs-site/
- **API Reference**: Visit http://localhost:8344/docs

### Key Documentation Sections
- [Getting Started](docs/getting-started/) - Installation, configuration, and running
- [Architecture](docs/architecture/) - System design and components
- [API Reference](docs/api/) - Detailed API documentation
- [Development](docs/development/) - Testing, deployment, and contributing
- [GCP Deployment](docs/GCP-deployment.md) - Production deployment guide

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/agents/test_lead_agent.py

# Run integration tests
pytest tests/ -m integration
```

## 🔧 Configuration

### Calendar Integration
Supports multiple calendar providers:
- **Salesforce Calendar** (default)
- **Google Calendar**

Configure via `CALENDAR_PROVIDER` environment variable.

### Audio Processing
- **WebRTC VAD** for voice activity detection
- **Google Cloud Speech** for real-time transcription
- **Pre-generated audio** for common responses

## 📁 Project Structure

```
├── app/                      # Main application code
│   ├── agents/              # LangGraph agents
│   ├── api/                 # FastAPI application
│   ├── managers/            # Audio and conversation managers
│   ├── routers/             # API route handlers
│   ├── speech/              # Speech processing
│   └── utils/               # Utility functions
├── docs/                    # Documentation source
├── scripts/                 # Development scripts
├── static/                  # Static files and documentation
├── tests/                   # Test suite
└── secrets/                 # Credentials (not committed)
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and test them
4. Run linting: `pylint app/`
5. Run tests: `pytest`
6. Submit a pull request

See [Contributing Guide](docs/development/contributing.md) for detailed guidelines.

## 📄 License

This project is proprietary software. All rights reserved.

## 🆘 Support

- **Documentation**: Browse the `/docs` folder or visit http://localhost:8344/docs-site/
- **API Reference**: http://localhost:8344/docs
- **Issues**: Contact the development team

---

**Happy Coding!** 🎉