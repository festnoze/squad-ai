# SkillForge Frontend

AI-powered learning assistant with Streamlit-based web interface.

## Overview

SkillForge Frontend is a Streamlit web application that provides an interactive interface for browsing educational course content and chatting with an AI tutor about course materials.

## Features

- **Course Navigation**: Hierarchical browsing through courses (Matiere → Module → Theme → Resource)
- **Resource Viewer**: Display course content (PDFs, Opale content) in an embedded iframe
- **AI Chat Assistant**: Real-time streaming chat with AI tutor about course materials
- **Context-Aware**: Conversations are tied to specific resources for relevant responses

## Installation

### Requirements

- Python 3.12+
- UV package manager
- Access to SkillForge Backend API

### Setup

1. Clone the repository:
```bash
cd test-frontend
```

2. Install dependencies:
```bash
uv sync
```

3. Configure environment variables:
```bash
cp .env.sample .env
# Edit .env with your configuration
```

4. Add course data:
```bash
# Copy or symlink the outputs/ folder from OpaleCoursesWebscraper
# The outputs/ folder should contain *.json course files
```

## Configuration

Edit the `.env` file with your settings:

```env
# Backend API Configuration
SKILLFORGE_API_URL=http://localhost:8372
SKILLFORGE_JWT_TOKEN=your_jwt_token_here

# Frontend Configuration
OUTPUTS_DIR=outputs/
STREAMLIT_SERVER_PORT=8577
STREAMLIT_SERVER_ADDRESS=localhost

# Optional
DEBUG=true
```

## Usage

Run the Streamlit application:

```bash
uv run streamlit run src/main.py
```

The application will be available at `http://localhost:8577`

## Development

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html
```

### Code Quality

```bash
# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Type checking
uv run mypy src/
```

## Project Structure

```
test-frontend/
├── src/
│   ├── main.py                    # Streamlit entry point
│   ├── config.py                  # Environment configuration
│   ├── api/                       # Backend API client
│   ├── models/                    # Data models
│   ├── utils/                     # Utilities
│   ├── components/                # UI components
│   └── styles/                    # CSS styles
├── tests/                         # Test suite
├── outputs/                       # Course data (not in repo)
├── pyproject.toml                 # Project configuration
└── .env                           # Local config (not in repo)
```

## License

MIT

## Contributing

See [PLANNING.md](PLANNING.md) and [TODO.md](TODO.md) for development roadmap.
