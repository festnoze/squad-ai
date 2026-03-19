---
name: endpoint-search-or-create
description: |
  Search existing endpoints in routers, create if not found, including request/response models and converters.
  Handles FastAPI routers with Pydantic models for input validation and output serialization.

  Use when:
  - Need to expose a use-case via HTTP endpoint
  - Want to check if an endpoint already exists
  - Need to create request/response models for an endpoint
  - Need converters between request/model and model/response

  Triggers: "create endpoint", "add route", "new API", "HTTP endpoint",
  "router method", "REST API", "request model", "response model"
---

# Endpoint Search or Create

Find existing endpoints or create new ones with request/response models and converters.

## Output Format

```
RESULT:
  Router: {RouterName}
  Endpoint: {HTTP_METHOD} {path}
  File: {file_path}:{line_number}
  Handler: async def {function_name}({params}) -> {ReturnType}
  Request Model: {RequestModelClass} (if any)
  Response Model: {ResponseModelClass}
  Status: FOUND | CREATED
```

---

## Workflow

```
1. IDENTIFY endpoint needed
       │
       ▼
2. SEARCH for existing endpoint
       │
       ├─ FOUND → Return endpoint details
       │
       └─ NOT FOUND
              │
              ▼
       3. CHECK if router exists for this domain
              │
              ├─ YES → Add endpoint to existing router
              │
              └─ NO → Create new router file
              │
              ▼
       4. CREATE request model (if POST/PATCH/PUT with body)
              │
              ▼
       5. CREATE response model (if not dict/JSONResponse)
              │
              ▼
       6. CREATE converters (request→model, model→response)
              │
              ▼
       7. REGISTER router (if new)
              │
              ▼
       8. Return created endpoint details
```

---

## Phase 1: Identify Endpoint

Determine the required endpoint:

| Question | Examples |
|----------|----------|
| **Domain** | User, Thread, Content, Auth, Admin |
| **HTTP Method** | GET, POST, PATCH, PUT, DELETE |
| **Path** | `/user/profile`, `/thread/{id}/messages` |
| **Auth required?** | `authentication_required`, `authentication_optional`, none |
| **Request body?** | POST/PATCH/PUT usually have request body |
| **Response type** | Pydantic model, dict, StreamingResponse |

**Endpoint naming pattern:** `a{action}_{entity}` (async prefix)

Examples:
- `aget_user_profile` - GET /user/profile
- `acreate_thread` - POST /thread
- `aupdate_user_preferences` - PATCH /user/preferences
- `adelete_message` - DELETE /message/{id}

---

## Phase 2: Search

### Step 1: Find router files

```
Glob: src/facade/*_router.py
```

### Step 2: Search for matching endpoint

```
Grep patterns by HTTP method:
- GET:    @{router}.get\(".*{path}
- POST:   @{router}.post\(".*{path}
- PATCH:  @{router}.patch\(".*{path}
- PUT:    @{router}.put\(".*{path}
- DELETE: @{router}.delete\(".*{path}
```

### Step 3: Search for handler function

```
Grep: async def a{action}_{entity}
```

**If exact match found** → Return RESULT with `Status: FOUND`

**If no match** → Continue to Phase 3

See [references/search-patterns.md](references/search-patterns.md) for patterns.

---

## Phase 3: Create Endpoint

### Router Selection/Creation

**Existing routers:**
| Domain | Router | Prefix |
|--------|--------|--------|
| Base/Health | `baserouter` | `` |
| Auth | `auth_router` | `/auth` |
| User | `user_router` | `/user` |
| Thread | `thread_router` | `/thread` |
| Admin | `admin_router` | `/admin` |
| Database | `database_router` | `/database` |

**If router doesn't exist** → Create new router file

### Endpoint Structure

```python
@{router}.{method}(
    "/{path}",
    description="...",
    response_model={ResponseModel},  # or omit for dict/StreamingResponse
    status_code=200,  # or 201 for POST create
)
async def a{action}_{entity}(
    # Path parameters
    {entity}_id: str,
    # Request body (POST/PATCH/PUT)
    body: {RequestModel},
    # Auth dependency
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    # Service injection
    {entity}_service: {Entity}Service = deps.depends({Entity}Service),
) -> {ResponseModel}:
    """Endpoint description."""
    # Validation
    # Business logic via service
    # Convert and return response
```

See [references/endpoint-templates.md](references/endpoint-templates.md) for complete templates.

---

## Phase 4: Create Request Model

**Location:** `src/facade/request_models/{entity}_request.py`

**When needed:**
- POST, PATCH, PUT methods with request body
- Complex query parameters

**Structure:**
```python
from pydantic import BaseModel, Field

class {Action}{Entity}Request(BaseModel):
    """Request model for {action} {entity}."""
    field1: str
    field2: int | None = None
```

See [references/model-templates.md](references/model-templates.md) for templates.

---

## Phase 5: Create Response Model

**Location:** `src/facade/response_models/{entity}_response.py`

**When needed:**
- Structured response (not raw dict)
- API documentation clarity
- Type safety

**Structure:**
```python
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class {Entity}Response(BaseModel):
    """Response model for {entity}."""
    id: UUID | None = None
    name: str
    created_at: datetime | None = None
```

---

## Phase 6: Create Converters

**Location:** `src/facade/converters/`

### Request → Model Converter

**File:** `{entity}_request_converter.py`

```python
class {Entity}RequestConverter:
    @staticmethod
    def convert_{request}_to_{model}(request: {Request}) -> {Model}:
        return {Model}(
            field1=request.field1,
            field2=request.field2,
        )
```

### Model → Response Converter

**File:** `{entity}_response_converter.py`

```python
class {Entity}ResponseConverter:
    @staticmethod
    def convert_{model}_to_response({model}: {Model}) -> {Response}:
        return {Response}(
            id={model}.id,
            name={model}.name,
            created_at={model}.created_at,
        )
```

---

## Phase 7: Register Router

**Location:** `src/API/api_config.py`

If new router created, add:

```python
from facade.{entity}_router import {entity}_router

# In create_app():
app.include_router({entity}_router)
```

---

## Authentication Patterns

### Required Authentication

```python
from security.auth_dependency import authentication_required

@router.get("/protected")
async def aprotected_endpoint(
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
) -> dict:
    lms_user_id = token_payload.get_lms_user_id()
```

### Optional Authentication

```python
from security.auth_dependency import authentication_optional

@router.get("/public-or-private")
async def amixed_endpoint(
    token_payload: JWTSkillForgePayload | None = Depends(authentication_optional),
) -> dict:
    if token_payload:
        # Authenticated
    else:
        # Anonymous
```

### No Authentication

```python
@router.get("/public")
async def apublic_endpoint() -> dict:
    # No auth dependency
```

---

## Error Handling

```python
from errors import ValidationError, NotFoundError, AuthenticationError
from common_tools.helpers.validation_helper import Validate

@router.get("/{id}")
async def aget_by_id(
    id: str,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    service: Service = deps.depends(Service),
) -> Response:
    # Validate input
    if not Validate.is_uuid(id):
        raise ValidationError("VALIDATION_INVALID_UUID", value=id, field="id")

    # Check auth
    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id:
        raise AuthenticationError("AUTH_USER_NOT_FOUND_IN_TOKEN")

    # Call service
    result = await service.aget_by_id(UUID(id))
    if not result:
        raise NotFoundError("NOT_FOUND_ENTITY", id=id)

    return Converter.convert_to_response(result)
```

---

## Integration with Other Skills

| Situation | Action |
|-----------|--------|
| Service method missing | Invoke `/service-search-or-create` |
| Repository method missing | `/service-search-or-create` invokes `/repo-search-or-create` |
| Entity missing | Chain: `/repo-search-or-create` → `/db-entity-change` |

**Flow:**
```
Endpoint needed
    │
    ▼
/endpoint-search-or-create
    │
    ├─ Need service method? → /service-search-or-create
    │                              │
    │                              └─ Need repo? → /repo-search-or-create
    │                                                   │
    │                                                   └─ Need entity? → /db-entity-change
    │
    ├─ Create request/response models
    ├─ Create converters
    ├─ Create endpoint
    │
    └─ Return endpoint details
```
