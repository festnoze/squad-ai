---
name: endpoint-search-or-create
description: |
  Search existing FastAPI endpoints in routers, reuse if present, otherwise create the endpoint plus
  its request/response models and converters. Facade layer of the generated 3-layer backend. Routers
  stay thin: validate input, call a service, convert the result — no business logic in the router.

  Use when:
  - Need to expose a use-case via an HTTP endpoint
  - Want to check if an endpoint already exists
  - Need to create request/response models for an endpoint
  - Need converters between request/model and model/response

  Triggers: "create endpoint", "add route", "new API", "HTTP endpoint",
  "router method", "REST API", "request model", "response model"
---

# Endpoint Search or Create

Find an existing endpoint or create one with request/response models and converters (facade layer).

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

## Workflow

```
1. IDENTIFY the endpoint (domain, method, path, auth, body, response type)
2. SEARCH for an existing endpoint
       ├─ FOUND → return details
       └─ NOT FOUND
              3. Router for this domain exists?  YES → add to it / NO → create a router file
              4. CREATE request model (if POST/PATCH/PUT with a body)
              5. CREATE response model (unless returning a raw dict / streaming)
              6. CREATE converters (request→model, model→response)
              7. REGISTER the router where the app includes its routers (if new)
8. Return endpoint details
```

## Phase 1 — Identify

Handler name: `a{action}_{entity}`. Examples: `aget_user_by_id` (GET), `acreate_thread` (POST),
`aupdate_user_preferences` (PATCH), `adelete_message` (DELETE). Decide: auth required / optional /
none; request body present; response is a model, dict, or streaming.

## Phase 2 — Search

```
Glob: facade/*_router.py
Grep by method: @{router}\.(get|post|patch|put|delete)\(".*{path}
Grep handler:   async def a{action}_{entity}
```

Exact match → `Status: FOUND`. See [references/search-patterns.md](references/search-patterns.md).

## Phase 3 — Create the endpoint

Add to the domain router if it exists, otherwise create `facade/{entity}_router.py`. Keep the handler
thin. See [references/endpoint-templates.md](references/endpoint-templates.md) for full templates.

```python
@{entity}_router.{method}(
    "/{path}",
    description="...",
    response_model={ResponseModel},   # omit for dict / StreamingResponse
    status_code=200,                  # 201 for resource creation
)
async def a{action}_{entity}(
    {entity}_id: str,                 # path params
    body: {RequestModel},             # for POST/PATCH/PUT
    {entity}_service: {Entity}Service = Depends(get_{entity}_service),  # service injection
) -> {ResponseModel}:
    # 1. validate input  2. call service  3. convert and return
    ...
```

## Phase 4 — Request model

`facade/request_models/{entity}_request.py` — needed for bodies on POST/PATCH/PUT.

```python
from pydantic import BaseModel

class {Action}{Entity}Request(BaseModel):
    """Request model for {action} {entity}."""
    field1: str
    field2: int | None = None
```

## Phase 5 — Response model

`facade/response_models/{entity}_response.py` — for structured (non-raw-dict) responses.

```python
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

class {Entity}Response(BaseModel):
    id: UUID | None = None
    name: str
    created_at: datetime | None = None
```

## Phase 6 — Converters

`facade/converters/` — keep request/model/response translation out of the handler.

```python
class {Entity}RequestConverter:
    @staticmethod
    def convert_request_to_{entity}(request: {Request}) -> {Model}:
        return {Model}(field1=request.field1, field2=request.field2)

class {Entity}ResponseConverter:
    @staticmethod
    def convert_{entity}_to_response({entity}: {Model}) -> {Response}:
        return {Response}(id={entity}.id, name={entity}.name, created_at={entity}.created_at)
```

## Phase 7 — Register the router

If a new router was created, include it where the app wires its routers (the app factory /
`create_app()`):

```python
from facade.{entity}_router import {entity}_router
app.include_router({entity}_router)
```

## Authentication patterns

Use whatever auth dependency the generated app defines. Generic shapes:

```python
# Required
async def aprotected(user=Depends(authentication_required)) -> dict: ...
# Optional
async def amixed(user=Depends(authentication_optional)) -> dict:
    if user: ...   # authenticated
    else: ...      # anonymous
# None — no auth dependency
async def apublic() -> dict: ...
```

## Error handling

Validate at the boundary; raise domain errors (managed by `/error-code-management`); let centralized
exception middleware map them to HTTP responses.

```python
if not Validate.is_uuid(id):
    raise ValidationError("VALIDATION_INVALID_UUID", value=id, field="id")
result = await service.aget_by_id(UUID(id))
if not result:
    raise NotFoundError("NOT_FOUND_{ENTITY}", id=id)
return {Entity}ResponseConverter.convert_{entity}_to_response(result)
```

## Integration with other skills

| Situation | Action |
|-----------|--------|
| Service method missing | Invoke `/service-search-or-create` |
| Repository method missing | `/service-search-or-create` chains to `/repo-search-or-create` |
| Entity missing | chain: `/repo-search-or-create` → `/db-entity-change` |
| New error code needed | Invoke `/error-code-management` |
