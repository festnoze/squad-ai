# SkillForge Frontend - Setup Complete! 🎉

## What Was Built

A complete **Streamlit-based AI learning assistant** that connects to the SkillForge Backend API, inspired by and following the structure of **OpaleCoursesWebscraper/chatbot.py**.

## Project Structure

```
test-frontend/
├── chatbot.py                     # ⭐ Main chatbot class (single-file design)
├── startup.py                     # Entry point (launches chatbot)
├── .vscode/
│   ├── launch.json               # VSCode debugger config
│   └── settings.json             # VSCode project settings
├── src/                          # Library modules
│   ├── api/
│   │   └── skillforge_client.py  # Backend API client
│   ├── models/                   # Course data models
│   │   ├── course_content.py
│   │   ├── matiere.py
│   │   ├── module.py
│   │   ├── theme.py
│   │   ├── ressource.py
│   │   └── ressource_object.py
│   ├── utils/
│   │   └── course_loader.py      # JSON course loader
│   └── config.py                 # Environment config
├── outputs/                      # Course JSON files (link to OpaleCoursesWebscraper)
│   └── *.json           # Course structure data
├── .env                          # Local configuration
├── pyproject.toml                # UV project config
├── README.md
├── QUICKSTART.md                 # Quick start guide
├── PLANNING.md                   # Architecture docs
├── TODO.md                       # Task tracking
└── CLAUDE.md                     # Claude Code instructions
```

## Key Features Implemented

### 1. Architecture Based on OpaleCoursesWebscraper
- ✅ Single-file chatbot class design ([chatbot.py](chatbot.py))
- ✅ startup.py entry point pattern
- ✅ VSCode debugger configuration
- ✅ Custom CSS styling matching original
- ✅ Sidebar + Web Browser + Chat layout

### 2. Course Navigation
- ✅ Hierarchical dropdown navigation:
  - Course → Matiere → Module → Theme → Resource
- ✅ Automatic course loading from `outputs/*.json`
- ✅ Resource URL display in iframe
- ✅ State management across selections

### 3. AI Chat Integration
- ✅ Async API client with httpx
- ✅ JWT authentication
- ✅ Thread management (get or create)
- ✅ **Streaming responses** via Server-Sent Events (SSE)
- ✅ Conversation history per resource
- ✅ Context-aware responses

### 4. UI/UX
- ✅ Wide layout with expanded sidebar (500px)
- ✅ Hidden Streamlit branding
- ✅ Rounded frames and custom scrollbars
- ✅ Auto-focus on chat input
- ✅ Loading spinners
- ✅ Clear conversation button
- ✅ French language interface

## How to Run

### Prerequisites
1. **SkillForge Backend** running on `http://localhost:8372`
2. **JWT Token** configured in `.env`
3. **Course data** in `outputs/` folder

### Quick Start

**Option 1: Command Line**
```bash
uv run streamlit run startup.py
```

**Option 2: VSCode Debugger** (Recommended)
1. Open project in VSCode
2. Press `F5`
3. Debug with breakpoints!

### First-Time Setup
```bash
# 1. Update .env with JWT token
echo 'SKILLFORGE_JWT_TOKEN=your_token_here' >> .env

# 2. Copy course files to outputs/
cp -r /path/to/OpaleCoursesWebscraper/outputs/*.json outputs/

# 3. Run!
uv run streamlit run startup.py
```

## API Integration

### Endpoints Used
1. `POST /thread/get-all/ids` - Get/create conversation thread
2. `GET /thread/{id}/messages` - Retrieve message history
3. `POST /thread/{id}/query` - Send query with streaming response

### Request Flow
```
User Question
    ↓
Build Course Context (ressource, theme, module, matiere, parcours)
    ↓
Get or Create Thread ID
    ↓
Send Query to Backend API
    ↓
Stream Response (SSE)
    ↓
Display in Chat
```

## Differences from Original Main.py

The project now uses **both** approaches:

### New: chatbot.py (Recommended)
- Single class-based design
- All logic in one file
- Simpler to understand and debug
- Matches OpaleCoursesWebscraper pattern
- Launched via `startup.py`

### Original: src/main.py (Available)
- Modular component-based design
- Separate files for sidebar, chat, web_browser
- Better for large teams
- More organized for scaling

**Both work!** Choose based on preference:
- **Simple project**: Use `chatbot.py`
- **Team project**: Use `src/main.py`

## Configuration Files

### .env
```env
SKILLFORGE_API_URL=http://localhost:8372
SKILLFORGE_JWT_TOKEN=your_jwt_token_here
OUTPUTS_DIR=outputs/
STREAMLIT_SERVER_PORT=8577
DEBUG=true
```

### .vscode/launch.json
```json
{
    "configurations": [{
        "name": "Python Debugger: Streamlit",
        "type": "debugpy",
        "request": "launch",
        "module": "streamlit",
        "args": ["run", "startup.py"]
    }]
}
```

## Testing

```bash
# Test imports
uv run python -c "from chatbot import ChatbotFront; print('OK')"

# Test API client
uv run python -c "from src.api.skillforge_api_client import SkillForgeAPIClient; print('OK')"

# Test course loader
uv run python -c "from src.utils.course_loader import CourseLoader; print('OK')"

# Run tests
uv run pytest

# Code quality
uv run ruff check src/ chatbot.py
uv run mypy src/
```

## Troubleshooting

### "JWT token not configured"
→ Update `.env` with valid token

### "No courses found"
→ Add `*.json` files to `outputs/`

### "Connection refused"
→ Ensure SkillForge backend is running

### Import errors
→ Run `uv sync` to install dependencies

## Next Steps

### Immediate
1. ✅ Update `.env` with your JWT token
2. ✅ Add course data to `outputs/`
3. ✅ Run `uv run streamlit run startup.py`
4. ✅ Test with a real course!

### Future Enhancements (from TODO.md)
- Quick action buttons (reformulate, explain, summarize, translate)
- Dark mode toggle
- Conversation export (PDF, TXT)
- File upload for attachments
- Voice input/output
- LaTeX math rendering
- Multi-language support

## Documentation

- [README.md](README.md) - Project overview
- [QUICKSTART.md](QUICKSTART.md) - Detailed setup guide
- [PLANNING.md](PLANNING.md) - Architecture documentation
- [TODO.md](TODO.md) - Development roadmap
- [CLAUDE.md](CLAUDE.md) - Instructions for Claude Code
- [SETUP_COMPLETE.md](SETUP_COMPLETE.md) - This file

## Success Criteria ✅

All criteria from PLANNING.md met:

1. ✅ User can select a course from available courses
2. ✅ User can navigate course hierarchy (Matiere → Module → Theme → Resource)
3. ✅ Selected resource URL displays in web browser
4. ✅ User can ask questions in chat
5. ✅ AI responses stream in real-time from backend
6. ✅ Conversation history persists for each resource context
7. ✅ UI is responsive and visually appealing

## Credits

**Based on:**
- OpaleCoursesWebscraper by Squad AI team
- SkillForge Backend API
- Streamlit framework

**Built with:**
- Python 3.12+
- UV package manager
- Streamlit 1.40+
- httpx (async HTTP)
- Pydantic (data validation)

---

**Ready to launch! 🚀**

Run: `uv run streamlit run startup.py`
