# Installation

This guide will help you set up the development environment for the PIC Prospect Incoming Callbot.

## Prerequisites

- Python 3.12 or higher
- Git
- Google Cloud account (for speech services)
- Twilio account (for phone services)
- Salesforce account (for CRM integration)

## Development Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd PIC-Prospect_Incoming_Callbot
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies

```bash
# Install main dependencies
pip install -e .

# Install development dependencies
pip install -e .[dev]
```

### 4. Set up Environment Variables

Copy the example environment file and configure your settings:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```env
# Twilio Configuration
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token

# Google Cloud Configuration
GOOGLE_CLOUD_PROJECT=your_project_id
GOOGLE_APPLICATION_CREDENTIALS=path/to/credentials.json

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key

# Salesforce Configuration
SALESFORCE_USERNAME=your_username
SALESFORCE_PASSWORD=your_password
SALESFORCE_SECURITY_TOKEN=your_token
```

### 5. Verify Installation

```bash
# Run tests
pytest

# Check linting
ruff check app/

# Start the application
uvicorn app.api.startup:app --reload
```

## IDE Setup

### VS Code

Install the recommended extensions:

- Python
- Ruff
- MkDocs

The project includes VS Code settings that will automatically configure Ruff for linting and formatting.

## Next Steps

- [Configuration](configuration.md) - Set up your environment variables
- [Running the Application](running.md) - Start the application and test it