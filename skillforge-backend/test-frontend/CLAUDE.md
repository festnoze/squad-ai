# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SkillForge Frontend** is a Streamlit-based web application for an AI-powered learning assistant. It provides an interactive interface for browsing educational course content and chatting with an AI tutor about course materials.

**Tech Stack:**
- Python 3.12+
- Streamlit (UI framework)
- UV (package manager)
- httpx (async HTTP client for API communication)
- Pydantic (data validation)

**Backend Dependency:** This frontend communicates with the SkillForge Backend API (FastAPI) running on `http://localhost:8372` (configurable via environment variables).

## Project Status

**IMPORTANT:** As of the last update, this project is in the planning phase. Only PLANNING.md and TODO.md exist. No code has been implemented yet. The project structure and components described below are planned but not yet created.

## Architecture

The application follows a three-panel layout:
1. **Left Sidebar:** Course navigation with hierarchical dropdowns (Course → Matiere → Module → Theme → Resource)
2. **Main Content:** Web browser (iframe) displaying selected course resource (PDFs, Opale content)
3. **Chat Interface:** AI assistant chat with streaming responses, positioned below the web browser

**Data Flow:**
- User selects a course resource through hierarchical navigation
- Selected resource URL displays in iframe
- User can chat about the resource with AI assistant
- Chat conversations are tied to specific resource contexts (threads)
- Backend API handles AI responses via Server-Sent Events (SSE)

## Development Commands

### Package Management
```bash
# Sync dependencies
uv sync

# Add a new dependency
uv add <package-name>

# Add a dev dependency
uv add --dev <package-name>
```

### Running the Application
```bash
# Run Streamlit app
uv run streamlit run src/main.py

# Or with specific port
uv run streamlit run src/main.py --server.port 8577
```

### Testing
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_api_client.py

# Run with coverage
uv run pytest --cov=src --cov-report=html
```

### Code Quality
```bash
# Lint and format with ruff
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Type checking (if mypy is added)
uv run mypy src/
```

## Environment Configuration

Create a `.env` file in the project root with these variables:

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

**IMPORTANT:** The JWT token is required for authentication with the backend API. Store it in `.env`, never commit it to version control.

## Project Structure

```
test-frontend/
├── src/
│   ├── main.py                    # Streamlit entry point
│   ├── config.py                  # Environment variable management
│   ├── api/
│   │   └── skillforge_client.py   # Backend API client (async HTTP)
│   ├── models/                    # Pydantic data models
│   │   ├── course_content.py      # Root course structure
│   │   ├── matiere.py             # Subject model
│   │   ├── module.py              # Module model
│   │   ├── theme.py               # Theme model
│   │   ├── ressource.py           # Resource model
│   │   └── ressource_object.py    # Resource object model
│   ├── utils/
│   │   └── course_loader.py       # Course JSON loading utilities
│   ├── components/                # Streamlit UI components
│   │   ├── sidebar.py             # Course navigation sidebar
│   │   ├── web_browser.py         # Resource display (iframe)
│   │   └── chat.py                # Chat interface
│   └── styles/
│       └── custom.css             # Custom CSS styles
├── outputs/                       # Course JSON files (symlink/copy from OpaleCoursesWebscraper)
│   └── *.json            # Course structure data
├── tests/
│   ├── test_api_client.py
│   └── test_course_loader.py
├── pyproject.toml                 # UV project configuration
├── .env                           # Local environment (gitignored)
├── .env.sample                    # Environment template
├── PLANNING.md                    # Detailed architecture planning
└── TODO.md                        # Task tracking
```

## Course Data Structure

Courses are loaded from JSON files in `outputs/` directory. The hierarchy is:

```
CourseContent
└── Matieres (subjects)
    └── Modules
        └── Themes
            └── Ressources
                └── RessourceObjects (PDF/Opale content with URLs)
```

**Course Loading:**
- `CourseLoader.load_available_courses()` scans `outputs/` for `*.json` files
- `CourseLoader.load_course_structure(course_name)` parses JSON into CourseContent model
- Navigation dropdowns filter down the hierarchy based on user selection

## API Integration

### Backend Endpoints Used

1. **Get/Create Thread:** `POST /thread/get-all/ids`
   - Creates or retrieves conversation thread for a specific resource context
   - Returns thread IDs for the current user and resource

2. **Get Thread Messages:** `GET /thread/{thread_id}/messages`
   - Retrieves paginated conversation history
   - Used to restore chat when switching between resources

3. **Send Query (Streaming):** `POST /thread/{thread_id}/query`
   - Sends user query to AI assistant
   - Returns streaming response via Server-Sent Events (SSE)
   - Requires `Accept: text/event-stream` header

### Authentication

All API requests require JWT token in `Authorization: Bearer {token}` header. Token is loaded from environment variables via `src/config.py`.

## Async Method Naming Convention

**CRITICAL:** All async methods MUST be prefixed with "a" (not suffixed with "_async"):
- ✅ `async def aget_thread_messages(...)`
- ✅ `async def asend_query_streaming(...)`
- ❌ `async def get_thread_messages_async(...)`

## Session State Management

Streamlit session state stores:
- `messages`: List of chat messages (user/assistant)
- `current_thread_id`: Active conversation thread ID
- `selected_course_name`: Currently selected course
- `selected_course_content`: Parsed CourseContent object
- `selected_matiere_id`, `selected_module_id`, `selected_theme_id`, `selected_resource_id`: Navigation state
- `selected_resource_url`: URL for iframe display

**State Lifecycle:**
- Initialized in `init_session()` on app startup
- Updated on user navigation through course hierarchy
- Thread ID changes when resource context changes
- Messages loaded from backend when thread changes

## Testing Strategy

- **Unit Tests:** API client methods, course loader, data model validation
- **Integration Tests:** API communication with backend, course loading from files
- **Manual Testing:** UI flow, streaming responses, navigation, error handling

## Common Development Workflows

### Adding a New Component

1. Create component file in `src/components/`
2. Implement `render_<component_name>()` function
3. Import and call in `src/main.py`
4. Update session state if needed
5. Add tests in `tests/`

### Modifying API Client

1. Update method in `src/api/skillforge_client.py`
2. Prefix async methods with "a"
3. Add error handling for HTTP errors
4. Update corresponding tests in `tests/test_api_client.py`
5. Test against running backend API

### Changing Course Data Models

1. Update model in `src/models/`
2. Ensure Pydantic validation is correct
3. Update `CourseLoader` if parsing logic changes
4. Test with actual course JSON files from `outputs/`

## Dependencies on External Projects

- **OpaleCoursesWebscraper:** Provides course JSON files in `outputs/` directory and data model definitions
- **SkillForge Backend API:** Must be running for chat functionality to work

## Known Constraints

- JWT authentication is environment-based (no login UI in Phase 1)
- CORS must be configured on backend to allow frontend origin
- Course JSON files must follow the expected CourseContent schema
- Streaming responses require SSE support in httpx client
