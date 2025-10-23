# SkillForge Frontend - TODO List

## Phase 1: Project Setup & API Client

### 1.1 Project Initialization
- [ ] Initialize project with cookiecutter-uv template
  - Run: `uv tool run cookiecutter gh:fpgmaas/cookiecutter-uv`
  - Project name: `test-frontend`
  - Python version: `3.12`
- [ ] Create project directory structure
  - Create `src/api/`, `src/models/`, `src/utils/`, `src/components/`, `src/styles/`
  - Create `tests/` directory
- [ ] Set up `.gitignore` for Python/Streamlit projects
- [ ] Create `.env.sample` with required environment variables
- [ ] Create `.env` with local configuration
- [ ] Copy or symlink `outputs/` folder from OpaleCoursesWebscraper

### 1.2 Dependency Management
- [ ] Add Streamlit to dependencies (`streamlit>=1.40.0`)
- [ ] Add httpx for async HTTP (`httpx>=0.27.0`)
- [ ] Add pydantic for data validation (`pydantic>=2.10.0`)
- [ ] Add python-dotenv for env management (`python-dotenv>=1.0.0`)
- [ ] Add dev dependencies (pytest, ruff, mypy)
- [ ] Run `uv sync` to install dependencies

### 1.3 Configuration Module
- [ ] Create `src/config.py` for environment variable management
  - Load from `.env` file
  - Define `SKILLFORGE_API_URL`
  - Define `SKILLFORGE_JWT_TOKEN`
  - Define `OUTPUTS_DIR`
  - Validation for required variables

### 1.4 API Client Implementation
- [ ] Create `src/api/skillforge_client.py`
  - [ ] Implement `__init__(self, base_url, jwt_token)`
  - [ ] Implement `_get_headers()` method for auth headers
  - [ ] Implement `aget_or_create_thread(course_context)` → thread_id
  - [ ] Implement `aget_thread_messages(thread_id, page, page_size)` → messages
  - [ ] Implement `asend_query_streaming(thread_id, query, context)` → AsyncGenerator
  - [ ] Add error handling for HTTP errors
  - [ ] Add logging for debugging

### 1.5 API Client Testing
- [ ] Create `tests/test_api_client.py`
- [ ] Test authentication headers
- [ ] Test get/create thread endpoint (mock)
- [ ] Test get messages endpoint (mock)
- [ ] Manual test against running backend API

---

## Phase 2: Data Models & Course Loader

### 2.1 Course Content Models
- [ ] Create `src/models/matiere.py` (copy from OpaleCoursesWebscraper)
- [ ] Create `src/models/module.py` (copy from OpaleCoursesWebscraper)
- [ ] Create `src/models/theme.py` (copy from OpaleCoursesWebscraper)
- [ ] Create `src/models/ressource.py` (copy from OpaleCoursesWebscraper)
- [ ] Create `src/models/ressource_object.py` (copy from OpaleCoursesWebscraper)
- [ ] Create `src/models/course_content.py` (copy from OpaleCoursesWebscraper)
- [ ] Adapt models to use Pydantic if needed (optional)

### 2.2 Course Loader Utility
- [ ] Create `src/utils/course_loader.py`
  - [ ] Implement `load_available_courses(outputs_dir)` → list[str]
  - [ ] Implement `load_course_structure(course_name)` → CourseContent
  - [ ] Implement `get_matieres(course)` → list[Matiere]
  - [ ] Implement `get_modules(matiere)` → list[Module]
  - [ ] Implement `get_themes(module)` → list[Theme]
  - [ ] Implement `get_ressources(theme)` → list[RessourceObject]
  - [ ] Add error handling for missing files

### 2.3 Course Loader Testing
- [ ] Create `tests/test_course_loader.py`
- [ ] Test loading available courses
- [ ] Test loading course structure from JSON
- [ ] Test hierarchical navigation methods
- [ ] Manual test with real course JSON files

---

## Phase 3: Sidebar Component

### 3.1 Sidebar Layout
- [ ] Create `src/components/sidebar.py`
- [ ] Implement `render_sidebar()` function
- [ ] Add title/header section
- [ ] Add action buttons section (clear conversation)
- [ ] Add course selection section

### 3.2 Course Selection
- [ ] Implement course dropdown
  - [ ] Load available courses using CourseLoader
  - [ ] Display course names in selectbox
  - [ ] Store selected course in session state
  - [ ] Trigger course loading on selection change

### 3.3 Hierarchical Navigation
- [ ] Implement Matiere dropdown
  - [ ] Filter by selected course
  - [ ] Update on course selection change
  - [ ] Store selection in session state
- [ ] Implement Module dropdown
  - [ ] Filter by selected Matiere
  - [ ] Update on Matiere selection change
  - [ ] Store selection in session state
- [ ] Implement Theme dropdown
  - [ ] Filter by selected Module
  - [ ] Update on Module selection change
  - [ ] Store selection in session state
- [ ] Implement Resource dropdown
  - [ ] Filter by selected Theme
  - [ ] Display resource name and type
  - [ ] Store selection in session state
  - [ ] Trigger web browser update on selection

### 3.4 Session State Management
- [ ] Define session state keys
  - `selected_course_name`
  - `selected_course_content`
  - `selected_matiere_id`
  - `selected_module_id`
  - `selected_theme_id`
  - `selected_resource_id`
  - `selected_resource_url`
- [ ] Implement state initialization
- [ ] Implement state reset on course change

---

## Phase 4: Web Browser Component

### 4.1 Web Browser Implementation
- [ ] Create `src/components/web_browser.py`
- [ ] Implement `render_web_browser()` function
- [ ] Display iframe with selected resource URL
  - [ ] Height: 600px
  - [ ] Scrolling: enabled
  - [ ] Border styling
- [ ] Handle empty/no resource selected state
- [ ] Add resource type badge (PDF, Opale, etc.)

### 4.2 Resource URL Management
- [ ] Get resource URL from session state
- [ ] Update iframe when resource changes
- [ ] Handle different resource types (PDF vs Opale)
- [ ] Add error handling for invalid URLs

---

## Phase 5: Chat Component

### 5.1 Chat Layout
- [ ] Create `src/components/chat.py`
- [ ] Implement `render_chat()` function
- [ ] Display message history from session state
- [ ] Add chat input field
- [ ] Style chat messages (user vs assistant)

### 5.2 Message Display
- [ ] Implement message history rendering
  - [ ] Use `st.chat_message()` for each message
  - [ ] Display user messages with 'user' role
  - [ ] Display assistant messages with 'assistant' role
  - [ ] Add timestamps (optional)

### 5.3 Thread Management Integration
- [ ] Implement `get_or_create_thread_for_resource()`
  - [ ] Build course_context from selected resource
  - [ ] Call API client to get/create thread
  - [ ] Store thread_id in session state
- [ ] Implement `load_thread_messages()`
  - [ ] Call API client to get messages
  - [ ] Populate session state with messages
  - [ ] Display in chat interface

### 5.4 User Query Handling
- [ ] Capture user input from `st.chat_input()`
- [ ] Validate input (non-empty)
- [ ] Display user message immediately
- [ ] Add user message to session state
- [ ] Prepare query request payload

### 5.5 Streaming Response Integration
- [ ] Implement `stream_assistant_response(query)`
  - [ ] Call API client streaming method
  - [ ] Use `st.write_stream()` to display response
  - [ ] Collect full response text
  - [ ] Add assistant message to session state
- [ ] Add loading spinner during response generation
- [ ] Handle streaming errors gracefully

### 5.6 Conversation Management
- [ ] Implement clear conversation button
  - [ ] Clear session state messages
  - [ ] Reset chat display
  - [ ] Keep thread_id (or create new)
- [ ] Add welcome message on first load
- [ ] Handle empty resource state (prompt to select resource)

---

## Phase 6: Main Application Integration

### 6.1 Main App Structure
- [ ] Create `src/main.py` as Streamlit entry point
- [ ] Implement `main()` function
- [ ] Set up page configuration
  - [ ] Page title: "SkillForge - AI Learning Assistant"
  - [ ] Page icon: 🎓
  - [ ] Layout: wide
  - [ ] Sidebar: expanded
- [ ] Initialize session state

### 6.2 Custom Styling
- [ ] Create `src/styles/custom.css` (copy from chatbot.py)
- [ ] Implement `apply_custom_styles()` function
  - [ ] Hide Streamlit menu/footer/header
  - [ ] Set sidebar width (500px)
  - [ ] Add rounded frames
  - [ ] Custom scrollbar styling
  - [ ] Responsive padding
- [ ] Load and apply CSS in main app

### 6.3 Component Integration
- [ ] Import all components (sidebar, web_browser, chat)
- [ ] Render sidebar in `with st.sidebar:` block
- [ ] Render web browser in main content area
- [ ] Render chat below web browser
- [ ] Ensure proper layout flow

### 6.4 Session State Initialization
- [ ] Create `init_session()` function
- [ ] Initialize all required session state keys
  - `messages = []`
  - `current_thread_id = None`
  - `selected_course_name = None`
  - `selected_course_content = None`
  - `selected_matiere_id = None`
  - `selected_module_id = None`
  - `selected_theme_id = None`
  - `selected_resource_id = None`
  - `selected_resource_url = None`
- [ ] Add default welcome message

### 6.5 Error Handling
- [ ] Add try-except blocks for API calls
- [ ] Display user-friendly error messages
- [ ] Log errors for debugging
- [ ] Handle connection errors
- [ ] Handle authentication errors
- [ ] Handle invalid course data

### 6.6 Authentication
- [ ] Load JWT token from environment
- [ ] Initialize API client with token
- [ ] Add token validation check
- [ ] Display authentication status (optional)

---

## Phase 7: Testing & Polish

### 7.1 Unit Tests
- [ ] Test API client methods
- [ ] Test course loader utilities
- [ ] Test data model parsing
- [ ] Test configuration loading
- [ ] Achieve >80% code coverage

### 7.2 Integration Tests
- [ ] Test end-to-end flow with mock backend
- [ ] Test session state management
- [ ] Test component interactions
- [ ] Test streaming response handling

### 7.3 Manual Testing
- [ ] Test course selection flow
- [ ] Test hierarchical navigation
- [ ] Test web browser display
- [ ] Test chat functionality
- [ ] Test streaming responses
- [ ] Test conversation history
- [ ] Test clear conversation
- [ ] Test error scenarios
- [ ] Test with multiple courses

### 7.4 UI/UX Improvements
- [ ] Responsive design testing
- [ ] Mobile compatibility (optional)
- [ ] Loading indicators
- [ ] Empty states messaging
- [ ] Tooltips for unclear elements
- [ ] Keyboard shortcuts (optional)

### 7.5 Documentation
- [ ] Update README.md with:
  - [ ] Project description
  - [ ] Installation instructions
  - [ ] Configuration guide
  - [ ] Usage guide
  - [ ] Screenshots
  - [ ] Troubleshooting
- [ ] Add inline code comments
- [ ] Add docstrings to all functions
- [ ] Update PLANNING.md with any changes

### 7.6 Bug Fixes
- [ ] Fix any discovered bugs
- [ ] Address edge cases
- [ ] Performance optimization
- [ ] Memory leak checks

### 7.7 Deployment Preparation
- [ ] Create requirements.txt for deployment
- [ ] Add deployment instructions
- [ ] Environment variable documentation
- [ ] Docker configuration (optional)

---

## Bonus Features (Optional - Future Enhancements)

- [ ] Add user authentication UI (login form)
- [ ] Add markdown/HTML content display below iframe
- [ ] Add file upload for attachments
- [ ] Add quick action buttons (reformulate, explain, summarize, translate)
- [ ] Add conversation export (PDF, TXT)
- [ ] Add dark mode toggle
- [ ] Add multi-language support
- [ ] Add voice input/output
- [ ] Add code highlighting in responses
- [ ] Add LaTeX math rendering
- [ ] Add conversation search
- [ ] Add favorites/bookmarks

---

## Progress Tracking

**Legend:**
- [ ] Not started
- [🔄] In progress
- [✅] Completed
- [⚠️] Blocked/Issues

**Current Phase:** Phase 1 - Project Setup & API Client

**Overall Progress:** 0/100 tasks completed (0%)

**Last Updated:** 2025-10-22
