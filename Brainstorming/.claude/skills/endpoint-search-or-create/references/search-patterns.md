# Search Patterns Reference

## Finding Router Files

```bash
# All router files
Glob: src/facade/*_router.py

# Specific router
Grep: {entity}_router = APIRouter
Path: src/facade/
```

## Endpoint Search Patterns

### By HTTP Method

**GET**
```
Pattern: @{router}\.get\(
Examples:
  - @baserouter.get("/health")
  - @user_router.get("/profile")
  - @thread_router.get("/{thread_id}/messages")
```

**POST**
```
Pattern: @{router}\.post\(
Examples:
  - @thread_router.post("/get-all/ids")
  - @thread_router.post("/{thread_id}/query")
  - @admin_router.post("/scrape-parcour-all-courses")
```

**PATCH**
```
Pattern: @{router}\.patch\(
Examples:
  - @user_router.patch("/set-infos")
  - @user_router.patch("/preferences")
```

**PUT**
```
Pattern: @{router}\.put\(
```

**DELETE**
```
Pattern: @{router}\.delete\(
Examples:
  - @database_router.delete("/clear-database")
```

### By Path Pattern

**Static paths**
```
Pattern: @{router}\.{method}\s*\(\s*["']/path["']
```

**Dynamic paths (with parameters)**
```
Pattern: @{router}\.{method}\s*\(\s*["']/.*\{.*\}
Examples:
  - "/{thread_id}/messages"
  - "/{id}"
```

### By Handler Function

```
Pattern: async def a{action}_{entity}
Examples:
  - async def aget_current_user_info
  - async def acreate_or_update_user
  - async def aget_thread_messages
  - async def aanswer_user_query_into_thread
```

## Request/Response Model Search

### Request Models

```bash
# Location
Glob: src/facade/request_models/*_request.py

# Class pattern
Grep: class.*Request\(BaseModel\)
```

### Response Models

```bash
# Location
Glob: src/facade/response_models/*_response.py

# Class pattern
Grep: class.*Response\(BaseModel\)
```

## Converter Search

```bash
# Location
Glob: src/facade/converters/*_converter.py

# Request converter
Grep: class.*RequestConverter

# Response converter
Grep: class.*ResponseConverter
```

## Router-to-Domain Mapping

| Router File | Router Variable | Prefix | Domain |
|-------------|-----------------|--------|--------|
| `base_router.py` | `baserouter` | `` | Health, Quick Actions |
| `auth_router.py` | `auth_router` | `/auth` | Authentication |
| `user_router.py` | `user_router` | `/user` | User Management |
| `thread_router.py` | `thread_router` | `/thread` | Conversations |
| `admin_router.py` | `admin_router` | `/admin` | Admin Operations |
| `database_router.py` | `database_router` | `/database` | Database Maintenance |

## Request Model Files

| File | Models |
|------|--------|
| `user_infos_request.py` | `UserInfosRequest`, `UserPreferencesRequest` |
| `user_query_request.py` | `QueryRequest`, `UserAskNewQueryRequest` |
| `context_request.py` | `CourseContextRequest`, `CourseContextStudiRequest` |
| `llm_config_update_request.py` | `LlmConfigInfo`, `LlmConfigUpdateRequest` |
| `token_request.py` | Token-related requests |

## Response Model Files

| File | Models |
|------|--------|
| `user_response.py` | `UserResponse`, `SchoolResponse`, `UserPreferenceResponse` |
| `thread_response.py` | `ThreadIdsResponse`, `ThreadMessagesResponse`, `MessageResponse` |
| `token_response.py` | `TokenResponse` |
| `admin_response.py` | `AdminOperationResponse`, `CourseContentScrapingResponse` |

## Converter Files

| File | Class | Direction |
|------|-------|-----------|
| `user_request_converter.py` | `UserRequestConverter` | Request → Model |
| `user_response_converter.py` | `UserResponseConverter` | Model → Response |
| `thread_response_converter.py` | `ThreadResponseConverter` | Model → Response |

## Router Registration

```bash
# Location
File: src/API/api_config.py

# Import pattern
Grep: from facade\..*_router import

# Registration pattern
Grep: app\.include_router\(
```
