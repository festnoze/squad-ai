# SkillForge Frontend - Planning Document

## Project Overview

**Project Name:** SkillForge Frontend (Streamlit-based)
**Location:** `C:\Dev\IA\AzureDevOps\test-frontend`
**Technology Stack:** Python 3.12+, Streamlit, UV package manager
**Backend API:** SkillForge Backend API (FastAPI)
**Inspiration:** OpaleCoursesWebscraper chatbot.py

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        STREAMLIT FRONTEND                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │   LEFT SIDEBAR  │  │  MAIN CONTENT    │  │  CHAT WINDOW   │ │
│  │                 │  │                  │  │                │ │
│  │  - Course       │  │  - Web Browser   │  │  - Messages    │ │
│  │    Selection    │  │    (iframe)      │  │  - Input       │ │
│  │  - Hierarchical │  │  - Display       │  │  - Streaming   │ │
│  │    Dropdowns    │  │    Resource URL  │  │    Response    │ │
│  │    • Matiere    │  │                  │  │                │ │
│  │    • Module     │  │                  │  │                │ │
│  │    • Theme      │  │                  │  │                │ │
│  │    • Resource   │  │                  │  │                │ │
│  └─────────────────┘  └──────────────────┘  └────────────────┘ │
│                                                                   │
└───────────────────────────────┬───────────────────────────────────┘
                                │
                                │ HTTP Requests
                                │
                        ┌───────▼────────┐
                        │  API CLIENT    │
                        │  - Auth (JWT)  │
                        │  - Thread Mgmt │
                        │  - Streaming   │
                        └───────┬────────┘
                                │
                                │ REST API
                                │
                ┌───────────────▼────────────────┐
                │   SKILLFORGE BACKEND API       │
                │   - /thread/{id}/query         │
                │   - /thread/get-all/ids        │
                │   - /thread/{id}/messages      │
                └────────────────────────────────┘
```

## Component Breakdown

### 1. API Client (`src/api/skillforge_client.py`)

**Responsibilities:**
- Authenticate with backend API using JWT tokens
- Manage HTTP requests to backend endpoints
- Handle streaming responses for chat
- Thread management (create, get messages, send queries)

**Key Methods:**
```python
class SkillForgeClient:
    def __init__(self, base_url: str, jwt_token: str)
    async def get_or_create_thread(self, course_context: dict) -> str  # Returns thread_id
    async def get_thread_messages(self, thread_id: str, page: int, page_size: int) -> list
    async def send_query_streaming(self, thread_id: str, query: str, context: dict) -> AsyncGenerator
```

**API Endpoints to Integrate:**
- `POST /thread/get-all/ids` - Get or create thread for user/context
- `GET /thread/{thread_id}/messages` - Retrieve thread messages (paginated)
- `POST /thread/{thread_id}/query` - Send query and stream response

### 2. Course Loader (`src/utils/course_loader.py`)

**Responsibilities:**
- Load course structure from JSON files in `outputs/` folder
- Parse CourseContent hierarchy
- Provide navigation structure for UI

**Key Methods:**
```python
class CourseLoader:
    @staticmethod
    def load_available_courses(outputs_dir: str = "outputs/") -> list[str]

    @staticmethod
    def load_course_structure(course_name: str) -> CourseContent

    @staticmethod
    def get_hierarchical_structure(course: CourseContent) -> dict
```

**Course Hierarchy:**
```
CourseContent
├── Matieres (subjects)
│   └── Modules
│       └── Themes
│           └── Ressources
│               └── RessourceObjects (PDF/Opale)
```

### 3. Sidebar Component (`src/components/sidebar.py`)

**Responsibilities:**
- Display course selection dropdown
- Display hierarchical navigation (Matiere → Module → Theme → Resource)
- Trigger course loading and selection events
- Display action buttons (clear conversation, etc.)

**UI Elements:**
- **Course Selector:** Dropdown of available courses from `outputs/` folder
- **Hierarchical Dropdowns:**
  - Matiere dropdown (filtered by selected course)
  - Module dropdown (filtered by selected matiere)
  - Theme dropdown (filtered by selected module)
  - Resource dropdown (filtered by selected theme)
- **Action Buttons:**
  - Clear conversation
  - Load selected resource

### 4. Web Browser Component (`src/components/web_browser.py`)

**Responsibilities:**
- Display resource URL in iframe
- Handle resource type (PDF, Opale, etc.)
- Update when resource selection changes

**UI Elements:**
- Streamlit `st.components.v1.iframe()` for web content display
- Height: 600px, scrolling enabled

### 5. Chat Component (`src/components/chat.py`)

**Responsibilities:**
- Display conversation history
- Handle user input
- Stream AI responses from backend
- Manage session state for messages

**UI Elements:**
- Message history display (`st.chat_message()`)
- Chat input (`st.chat_input()`)
- Streaming response display (`st.write_stream()`)

**Session State:**
```python
st.session_state.messages = [
    {'role': 'user', 'content': '...'},
    {'role': 'assistant', 'content': '...'}
]
st.session_state.current_thread_id = "uuid"
st.session_state.selected_course = {...}
st.session_state.selected_resource = {...}
```

### 6. Main Application (`src/main.py`)

**Responsibilities:**
- Initialize Streamlit page configuration
- Orchestrate all components
- Manage session state
- Handle authentication

**Structure:**
```python
def main():
    # Initialize session state
    init_session()

    # Page configuration
    st.set_page_config(...)

    # Custom CSS
    apply_custom_styles()

    # Sidebar
    with st.sidebar:
        render_sidebar()

    # Main content area
    render_web_browser()

    # Chat interface
    render_chat()
```

## Project Structure

```
test-frontend/
├── pyproject.toml              # UV project config
├── README.md
├── PLANNING.md                 # This file
├── TODO.md                     # Task tracking
├── .env.sample                 # Environment variables template
├── .env                        # Local environment (gitignored)
├── outputs/                    # Course JSON files (symlink or copy)
│   ├── *.json                 # Analyzed course structures
│   └── [course_name]/         # Course content folders
│       └── *.md               # Markdown course content
├── src/
│   ├── main.py                # Streamlit entry point
│   ├── config.py              # Configuration management
│   ├── api/
│   │   ├── __init__.py
│   │   └── skillforge_client.py  # Backend API client
│   ├── models/
│   │   ├── __init__.py
│   │   ├── course_content.py     # CourseContent model
│   │   ├── matiere.py            # Matiere model
│   │   ├── module.py             # Module model
│   │   ├── theme.py              # Theme model
│   │   ├── ressource.py          # Ressource model
│   │   └── ressource_object.py   # RessourceObject model
│   ├── utils/
│   │   ├── __init__.py
│   │   └── course_loader.py      # Course loading utilities
│   ├── components/
│   │   ├── __init__.py
│   │   ├── sidebar.py            # Sidebar component
│   │   ├── web_browser.py        # Web browser component
│   │   └── chat.py               # Chat component
│   └── styles/
│       └── custom.css            # Custom CSS styles
└── tests/
    ├── __init__.py
    └── test_api_client.py        # API client tests
```

## Environment Variables

```env
# Backend API Configuration
SKILLFORGE_API_URL=http://localhost:8372
SKILLFORGE_JWT_TOKEN=your_jwt_token_here

# Frontend Configuration
OUTPUTS_DIR=outputs/
STREAMLIT_SERVER_PORT=8577
STREAMLIT_SERVER_ADDRESS=localhost

# Optional: Development mode
DEBUG=true
```

## Data Flow

### 1. Course Selection Flow
```
User selects course from dropdown
    ↓
CourseLoader loads course JSON
    ↓
Parse CourseContent hierarchy
    ↓
Populate Matiere dropdown
    ↓
User selects Matiere → Populate Module dropdown
    ↓
User selects Module → Populate Theme dropdown
    ↓
User selects Theme → Populate Resource dropdown
    ↓
User selects Resource → Update web browser with URL
```

### 2. Chat Query Flow
```
User types query in chat input
    ↓
Display user message in chat
    ↓
Prepare course context from selected resource
    ↓
API Client: Get or create thread for context
    ↓
API Client: Send query to /thread/{id}/query endpoint
    ↓
Stream response from backend (SSE)
    ↓
Display streaming response in chat
    ↓
Save complete message to session state
```

### 3. Thread Management Flow
```
User selects new resource
    ↓
Create course_context from selection
    ↓
Call API: POST /thread/get-all/ids with context
    ↓
Backend returns thread_id (existing or new)
    ↓
Call API: GET /thread/{id}/messages
    ↓
Load existing conversation history
    ↓
Display messages in chat interface
```

## API Request/Response Formats

### 1. Get or Create Thread
**Request:**
```json
POST /thread/get-all/ids
Headers: { "Authorization": "Bearer {jwt_token}" }
Body: {
  "ressource": {
    "ressource_id": "...",
    "ressource_type": "pdf",
    "ressource_code": "...",
    "ressource_title": "...",
    "ressource_url": "https://..."
  },
  "theme_id": "...",
  "module_id": "...",
  "matiere_id": "...",
  "parcour_id": "...",
  "parcours_name": "..."
}
```

**Response:**
```json
{
  "threads_ids": ["uuid-1", "uuid-2"]
}
```

### 2. Get Thread Messages
**Request:**
```
GET /thread/{thread_id}/messages?page_number=1&page_size=20
Headers: { "Authorization": "Bearer {jwt_token}" }
```

**Response:**
```json
{
  "thread_id": "uuid",
  "messages": [
    {
      "role": "user",
      "content": "What is Python?",
      "timestamp": "2025-01-15T10:30:00Z"
    },
    {
      "role": "assistant",
      "content": "Python is...",
      "timestamp": "2025-01-15T10:30:05Z"
    }
  ],
  "total_messages": 42,
  "page_number": 1,
  "page_size": 20
}
```

### 3. Send Query (Streaming)
**Request:**
```json
POST /thread/{thread_id}/query
Headers: {
  "Authorization": "Bearer {jwt_token}",
  "Accept": "text/event-stream"
}
Body: {
  "query": {
    "query_text_content": "What is Python?",
    "query_selected_text": "",
    "query_quick_action": null
  },
  "course_context": {
    "ressource": { ... },
    "theme_id": "...",
    ...
  }
}
```

**Response (Server-Sent Events):**
```
data: Python
data:  is
data:  a
data:  programming
data:  language
...
```

## UI/UX Design

### Color Scheme (inspired by chatbot.py)
- Primary: `#3498db` (blue)
- Background: `#f9f9f9` (light gray)
- Border: `#ddd` (gray)
- Shadow: `rgba(0,0,0,0.1)`

### Layout
- **Sidebar:** 500px width, expanded by default
- **Main Content:** Dynamic width
- **Web Browser:** 600px height, scrollable
- **Chat:** Below browser, full width

### Custom CSS Features
- Hidden Streamlit menu/footer/header
- Rounded frames for sections
- Custom scrollbar styling
- Responsive padding

## Authentication Strategy

**Options:**

1. **Environment Variable (Simple - Phase 1):**
   - Store JWT token in `.env` file
   - Load token on startup
   - Use for all API requests

2. **Login Form (Future - Phase 2):**
   - Add login page before main app
   - Store token in session state
   - Implement token refresh logic

**Phase 1 Implementation:**
- Use hardcoded or env-based JWT token
- Focus on functionality over security
- Document authentication requirements

## Dependencies

```toml
[project]
name = "test-frontend"
version = "0.1.0"
description = "SkillForge Streamlit Frontend"
requires-python = ">=3.12"

dependencies = [
    "streamlit>=1.40.0",
    "httpx>=0.27.0",          # Async HTTP client
    "pydantic>=2.10.0",       # Data validation
    "python-dotenv>=1.0.0",   # Environment variables
]

[project.optional-dependencies]
dev = [
    "pytest>=8.4.0",
    "pytest-asyncio>=0.25.0",
    "ruff>=0.9.0",
]
```

## Testing Strategy

1. **Unit Tests:**
   - API client methods
   - Course loader utilities
   - Data model validation

2. **Integration Tests:**
   - API client → Backend communication
   - Course loading from files
   - Session state management

3. **Manual Testing:**
   - UI/UX flow
   - Streaming response display
   - Navigation between resources

## Development Phases

### Phase 1: Project Setup & API Client
- Initialize project with cookiecutter-uv
- Set up project structure
- Implement API client with authentication
- Test API client against backend

### Phase 2: Data Models & Course Loader
- Implement CourseContent models (copy from OpaleCoursesWebscraper)
- Implement course loader utility
- Test loading course JSON files

### Phase 3: Sidebar Component
- Course selection dropdown
- Hierarchical navigation dropdowns (Matiere/Module/Theme/Resource)
- Session state management

### Phase 4: Web Browser Component
- Iframe for resource display
- URL update on resource selection
- Handle different resource types

### Phase 5: Chat Component
- Message display
- User input handling
- Streaming response integration
- Thread management

### Phase 6: Main Application Integration
- Integrate all components
- Apply custom styling
- Session state orchestration
- Error handling

### Phase 7: Testing & Polish
- Write tests
- Bug fixes
- UI/UX improvements
- Documentation

## Risk Mitigation

### Risk 1: CORS Issues
- **Mitigation:** Ensure backend CORS settings allow frontend origin
- **Fallback:** Run frontend on same domain or configure proxy

### Risk 2: JWT Token Management
- **Mitigation:** Use environment variables initially
- **Future:** Implement proper login flow

### Risk 3: Streaming Response Handling
- **Mitigation:** Use `httpx` with SSE support
- **Testing:** Test streaming with backend before integration

### Risk 4: Course JSON Format Changes
- **Mitigation:** Version check on course JSON files
- **Fallback:** Error handling for missing fields

## Success Criteria

1. ✅ User can select a course from available courses
2. ✅ User can navigate course hierarchy (Matiere → Module → Theme → Resource)
3. ✅ Selected resource URL displays in web browser
4. ✅ User can ask questions in chat
5. ✅ AI responses stream in real-time from backend
6. ✅ Conversation history persists for each resource context
7. ✅ UI is responsive and visually appealing

## Next Steps

See [TODO.md](TODO.md) for detailed task list and progress tracking.
