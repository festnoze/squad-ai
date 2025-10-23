# SkillForge Frontend - Quick Start Guide

## Project Status

✅ **All Phases Complete!**
- Project structure based on OpaleCoursesWebscraper
- Single-file chatbot implementation ([chatbot.py](chatbot.py))
- VSCode debugging configuration
- Complete API integration with streaming responses
- Hierarchical course navigation
- Resource viewer with iframe
- AI chat assistant

## Prerequisites

Before running the application, ensure you have:

1. **Python 3.12+** installed
2. **UV package manager** installed
3. **SkillForge Backend API** running (default: `http://localhost:8372`)
4. **JWT token** for authentication
5. **Course data** (outputs folder from OpaleCoursesWebscraper)

## Setup Instructions

### 1. Configure Environment Variables

Edit the `.env` file and update the following values:

```env
# Backend API Configuration
SKILLFORGE_API_URL=http://localhost:8372
SKILLFORGE_JWT_TOKEN=<your_actual_jwt_token_here>

# Frontend Configuration
OUTPUTS_DIR=outputs/
STREAMLIT_SERVER_PORT=8577
STREAMLIT_SERVER_ADDRESS=localhost

# Optional
DEBUG=true
```

**Important:** Replace `<your_actual_jwt_token_here>` with a valid JWT token from the SkillForge backend.

### 2. Add Course Data

You need to add course JSON files to the `outputs/` directory. You have two options:

**Option A: Create Symbolic Link (Recommended)**

```bash
# On Windows (requires admin privileges)
mklink /D outputs "C:\Dev\squad-ai\OpaleCoursesWebscraper\outputs"

# On Linux/Mac
ln -s /path/to/OpaleCoursesWebscraper/outputs outputs
```

**Option B: Copy Files**

```bash
# Copy the entire outputs folder
cp -r /path/to/OpaleCoursesWebscraper/outputs ./outputs
```

The `outputs/` folder should contain files like:
- `Bachelor Développeur Python 2023-2029.json`
- etc.

### 3. Verify Setup

Check that everything is configured correctly:

```bash
# Verify UV is installed
uv --version

# Verify dependencies are installed
uv sync

# Check that outputs folder exists and has files
ls outputs/*.json
```

## Running the Application

### Method 1: Command Line

```bash
# Using startup.py (recommended)
uv run streamlit run startup.py

# Or using chatbot.py directly
uv run streamlit run chatbot.py
```

The application will start and open in your browser at `http://localhost:8577`

### Method 2: VSCode Debugger (Recommended for Development)

1. Open the project in VSCode
2. Press `F5` or go to **Run → Start Debugging**
3. The debugger will launch Streamlit with breakpoints enabled

The VSCode configuration is in [.vscode/launch.json](.vscode/launch.json)

### Alternative: Specify Custom Port

```bash
uv run streamlit run startup.py --server.port 8502
```

## Using the Application

### 1. Navigate to a Resource

1. Open the sidebar (should be expanded by default)
2. Select a **Course** from the dropdown
3. Navigate through the hierarchy:
   - Select a **Matiere** (Subject)
   - Select a **Module**
   - Select a **Theme**
   - Select a **Resource**

### 2. View the Resource

Once you select a resource, it will appear in the **Resource Viewer** panel (left side).

### 3. Chat with AI Assistant

1. The **AI Assistant** panel is on the right side
2. Type your question in the chat input
3. The AI will respond based on the selected resource context
4. Your conversation history is preserved for each resource

### 4. Switch Resources

- When you select a different resource, the conversation history is cleared
- A new thread is created for the new resource context

## Troubleshooting

### Issue: "JWT token not configured"

**Solution:** Update your `.env` file with a valid JWT token from the backend.

### Issue: "No courses found in outputs/ directory"

**Solution:** Ensure the `outputs/` directory exists and contains `*.json` files.

### Issue: "Failed to initialize API client"

**Solution:**
1. Verify the backend API is running at the specified URL
2. Check that the JWT token is valid
3. Test the API manually: `curl -H "Authorization: Bearer <token>" http://localhost:8372/health`

### Issue: Module Import Errors

**Solution:** Run `uv sync` to ensure all dependencies are installed correctly.

### Issue: "Connection refused" when sending queries

**Solution:**
1. Ensure the SkillForge backend is running
2. Check the API URL in `.env` matches your backend
3. Verify CORS settings on the backend allow your frontend origin

## Development

### Run Tests

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

### Adding New Features

See [PLANNING.md](PLANNING.md) and [TODO.md](TODO.md) for the development roadmap and future enhancements.

## Project Structure

```
test-frontend/
├── src/
│   ├── main.py                    # Streamlit entry point
│   ├── config.py                  # Environment configuration
│   ├── api/                       # Backend API client
│   │   ├── skillforge_client.py
│   │   └── __init__.py
│   ├── models/                    # Data models
│   │   ├── course_content.py
│   │   ├── matiere.py
│   │   ├── module.py
│   │   ├── theme.py
│   │   ├── ressource.py
│   │   ├── ressource_object.py
│   │   └── __init__.py
│   ├── utils/                     # Utilities
│   │   ├── course_loader.py
│   │   └── __init__.py
│   └── components/                # UI components
│       ├── sidebar.py
│       ├── web_browser.py
│       ├── chat.py
│       └── __init__.py
├── outputs/                       # Course JSON files (not in repo)
├── .env                           # Local config (not in repo)
├── .env.sample                    # Environment template
├── pyproject.toml                 # Project configuration
├── README.md                      # Project overview
├── PLANNING.md                    # Architecture documentation
├── TODO.md                        # Task tracking
├── QUICKSTART.md                  # This file
└── CLAUDE.md                      # Claude Code instructions

```

## Next Steps

1. **Test with Real Data**: Try loading different courses and asking questions
2. **Customize UI**: Modify the CSS in `src/main.py` to match your preferences
3. **Add Features**: Implement bonus features from [TODO.md](TODO.md) like:
   - Quick action buttons (reformulate, explain, summarize)
   - Dark mode toggle
   - Conversation export
   - File upload for attachments

## Support

For issues or questions:
- Check [PLANNING.md](PLANNING.md) for architecture details
- Review [TODO.md](TODO.md) for known limitations
- Check [CLAUDE.md](CLAUDE.md) for development guidelines

---

**Happy Learning! 🎓**
