# API Connection Check Feature

## Overview

The SkillForge Frontend now includes automatic API connectivity checking on startup to provide immediate feedback about the backend connection status.

## Implementation

### 1. API Client - Ping Method

Added `aping()` method to [src/api/skillforge_client.py](src/api/skillforge_client.py):

```python
async def aping(self) -> tuple[bool, str]:
    """Ping the API to check availability and connectivity.

    Returns:
        Tuple of (success: bool, message: str)
    """
```

**Features:**
- ✅ Calls `/ping` endpoint (no authentication required)
- ✅ 5-second timeout for fast feedback
- ✅ Handles multiple error types:
  - Connection timeout
  - Connection refused
  - HTTP errors
  - Unexpected errors
- ✅ Returns tuple: `(success: bool, message: str)`

### 2. Chatbot Frontend Integration

Updated [chatbot.py](chatbot.py) with two new methods:

#### `check_api_connection()`
```python
@staticmethod
def check_api_connection():
    """Check API connection and store result in session state."""
```

- Called automatically on first app load
- Runs async ping check
- Stores result in session state:
  - `api_connection_status` (bool)
  - `api_connection_message` (str)
  - `api_connection_checked` (bool)

#### `display_api_status()`
```python
@staticmethod
def display_api_status():
    """Display API connection status banner."""
```

- Shows at the top of the page
- **Success case**: Small green success banner
- **Failure case**: Prominent red error with troubleshooting tips + retry button

### 3. Session State

New session state variables:
```python
st.session_state.api_connection_checked = False  # Has check been performed?
st.session_state.api_connection_status = None    # True/False/None
st.session_state.api_connection_message = ""     # Status message
```

## User Experience

### Successful Connection

```
✅ API connection successful - API: http://localhost:8372
```

Small, non-intrusive success message at the top of the page.

### Failed Connection

```
❌ Erreur de connexion API : Cannot connect to API at http://localhost:8372

⚠️ Impossible de se connecter à l'API SkillForge à l'adresse : http://localhost:8372

Veuillez vérifier que :
- L'API backend est démarrée
- L'URL dans le fichier .env est correcte
- Le token JWT est valide

[🔄 Réessayer la connexion]
```

Prominent error message with:
- Clear error description
- Troubleshooting checklist
- Retry button to check again without restarting

## Flow Diagram

```
App Startup
    ↓
init_session()
    ↓
Is api_connection_checked == False?
    ↓ Yes
check_api_connection()
    ↓
Async call to aping()
    ↓
Call GET /ping endpoint (5s timeout)
    ↓
├─ Success → Store (True, "API connection successful")
└─ Failure → Store (False, error_message)
    ↓
Set api_connection_checked = True
    ↓
display_api_status()
    ↓
Render appropriate UI banner
```

## Backend Endpoint

The backend provides `/ping` endpoint in [base_router.py](C:/Dev/IA/AzureDevOps/skillforge-backend/src/facade/base_router.py):

```python
@baserouter.get("/ping", description="Allow to verify API availability")
def ping() -> str:
    return "pong"
```

**Features:**
- No authentication required
- Simple response: `"pong"`
- Fast response time
- No side effects

## Error Scenarios Handled

| Error Type | Message | User Action |
|------------|---------|-------------|
| Connection timeout | `Connection timeout to {url}` | Check API is running |
| Connection refused | `Cannot connect to API at {url}` | Start backend API |
| HTTP error | `HTTP error: {error}` | Check API logs |
| Unexpected error | `Unexpected error: {error}` | Report to developers |

## Configuration

Connection check uses settings from [.env](.env):

```env
SKILLFORGE_API_URL=http://localhost:8372
SKILLFORGE_JWT_TOKEN=your_jwt_token_here
```

**Note:** The ping check does NOT require a valid JWT token - it only checks if the API is reachable.

## Testing

### Manual Test

```bash
# Start the app without backend running
uv run streamlit run startup.py

# Expected: Red error banner with troubleshooting tips

# Start the backend API
# Click "Réessayer la connexion" button

# Expected: Green success banner
```

### Code Test

```python
import asyncio
from src.api.skillforge_api_client import SkillForgeAPIClient

client = SkillForgeAPIClient()
success, message = asyncio.run(client.aping())
print(f"Success: {success}")
print(f"Message: {message}")
```

## Benefits

1. **Immediate Feedback**: Users know instantly if there's a connection problem
2. **Clear Troubleshooting**: Error messages guide users to fix the issue
3. **Retry Without Restart**: One-click retry button
4. **Non-Blocking**: App still loads even if API is down
5. **Fast Check**: 5-second timeout prevents long hangs

## Future Enhancements

Possible improvements:
- Periodic health checks (every 30s)
- More detailed API status (version, features)
- Connection status indicator in sidebar
- Automatic retry with exponential backoff
- Check `/health` endpoint for detailed diagnostics

## Files Modified

1. [src/api/skillforge_client.py](src/api/skillforge_client.py)
   - Added `aping()` method

2. [chatbot.py](chatbot.py)
   - Added `check_api_connection()` method
   - Added `display_api_status()` method
   - Updated `init_session()` to trigger check
   - Updated `run()` to display status

3. Documentation:
   - [API_CONNECTION_CHECK.md](API_CONNECTION_CHECK.md) (this file)

## Related Documentation

- [QUICKSTART.md](QUICKSTART.md) - Setup and usage guide
- [SETUP_COMPLETE.md](SETUP_COMPLETE.md) - Project overview
- [CLAUDE.md](CLAUDE.md) - Development guidelines
