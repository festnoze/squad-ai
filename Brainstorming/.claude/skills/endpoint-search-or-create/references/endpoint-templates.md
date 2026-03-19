# Endpoint Templates

Complete templates for creating FastAPI endpoints.

## Table of Contents

1. [Router File Structure](#router-file-structure)
2. [GET Endpoint Templates](#get-endpoint-templates)
3. [POST Endpoint Templates](#post-endpoint-templates)
4. [PATCH Endpoint Templates](#patch-endpoint-templates)
5. [DELETE Endpoint Templates](#delete-endpoint-templates)
6. [Streaming Endpoint Template](#streaming-endpoint-template)
7. [New Router Creation](#new-router-creation)

---

## Router File Structure

**Location:** `src/facade/{entity}_router.py`

```python
from fastapi import APIRouter, Depends

from API.dependency_injection_config import deps
from application.{entity}_service import {Entity}Service
from common_tools.helpers.validation_helper import Validate  # type: ignore[import-not-found]
from facade.request_models.{entity}_request import {Entity}Request
from facade.response_models.{entity}_response import {Entity}Response
from facade.converters.{entity}_request_converter import {Entity}RequestConverter
from facade.converters.{entity}_response_converter import {Entity}ResponseConverter
from models.{entity} import {Entity}
from security.auth_dependency import authentication_required
from security.jwt_skillforge_payload import JWTSkillForgePayload
from utils.exceptions import ValidationError, AuthenticationError, NotFoundError

{entity}_router = APIRouter(prefix="/{entity}", tags=["{Entity}"])


# Endpoints go here...
```

---

## GET Endpoint Templates

### GET - Single Resource by ID

```python
@{entity}_router.get(
    "/{{{entity}_id}}",
    description="Get {entity} by ID",
    response_model={Entity}Response,
    status_code=200,
)
async def aget_{entity}_by_id(
    {entity}_id: str,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    {entity}_service: {Entity}Service = deps.depends({Entity}Service),
) -> {Entity}Response:
    """Retrieve {entity} by its unique identifier."""
    # Validate UUID
    if not Validate.is_uuid({entity}_id):
        raise ValidationError("VALIDATION_INVALID_UUID", value={entity}_id, field="{entity}_id")

    # Validate authentication
    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id:
        raise AuthenticationError("AUTH_USER_NOT_FOUND_IN_TOKEN", payload=token_payload.to_dict(), token=token_payload.get_original_token())

    # Get entity
    {entity}: {Entity} | None = await {entity}_service.aget_{entity}_by_id(UUID({entity}_id))
    if not {entity}:
        raise NotFoundError("NOT_FOUND_{ENTITY}", {entity}_id={entity}_id)

    return {Entity}ResponseConverter.convert_{entity}_to_response({entity})
```

### GET - Collection with Query Parameters

```python
@{entity}_router.get(
    "/",
    description="Get {entities} with optional filters",
    response_model=list[{Entity}Response],
    status_code=200,
)
async def aget_{entities}(
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    {entity}_service: {Entity}Service = deps.depends({Entity}Service),
) -> list[{Entity}Response]:
    """Retrieve {entities} with optional filtering and pagination."""
    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id:
        raise AuthenticationError("AUTH_USER_NOT_FOUND_IN_TOKEN", payload=token_payload.to_dict(), token=token_payload.get_original_token())

    {entities}: list[{Entity}] = await {entity}_service.aget_{entities}(
        status=status,
        page=page,
        page_size=page_size,
    )

    return [{Entity}ResponseConverter.convert_{entity}_to_response(e) for e in {entities}]
```

### GET - Nested Resource (with parent ID)

```python
@{parent}_router.get(
    "/{{{parent}_id}}/{children}",
    description="Get {children} for the specified {parent}",
    response_model={Children}Response,
    status_code=200,
)
async def aget_{parent}_{children}(
    {parent}_id: str,
    page_number: int | None = None,
    page_size: int | None = None,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    {parent}_service: {Parent}Service = deps.depends({Parent}Service),
) -> {Children}Response:
    """Retrieve {children} for a specific {parent}."""
    if not Validate.is_uuid({parent}_id):
        raise ValidationError("VALIDATION_INVALID_UUID", value={parent}_id, field="{parent}_id")

    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id:
        raise AuthenticationError("AUTH_USER_NOT_FOUND_IN_TOKEN", payload=token_payload.to_dict(), token=token_payload.get_original_token())

    {children} = await {parent}_service.aget_{children}_by_{parent}_id(
        UUID({parent}_id),
        page_number=page_number,
        page_size=page_size,
    )

    return {Children}ResponseConverter.convert_to_response({children})
```

---

## POST Endpoint Templates

### POST - Create Resource

```python
@{entity}_router.post(
    "/",
    description="Create a new {entity}",
    response_model={Entity}Response,
    status_code=201,
)
async def acreate_{entity}(
    body: Create{Entity}Request,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    {entity}_service: {Entity}Service = deps.depends({Entity}Service),
) -> {Entity}Response:
    """Create a new {entity}."""
    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id:
        raise AuthenticationError("AUTH_USER_NOT_FOUND_IN_TOKEN", payload=token_payload.to_dict(), token=token_payload.get_original_token())

    # Convert request to model
    {entity}: {Entity} = {Entity}RequestConverter.convert_request_to_{entity}(body)

    # Create via service
    created_{entity}: {Entity} = await {entity}_service.acreate_{entity}({entity})

    return {Entity}ResponseConverter.convert_{entity}_to_response(created_{entity})
```

### POST - Action Endpoint (not resource creation)

```python
@{entity}_router.post(
    "/action-name",
    description="Perform action on {entity}",
    status_code=200,
)
async def a{action}_{entity}(
    body: {Action}Request,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    {entity}_service: {Entity}Service = deps.depends({Entity}Service),
) -> dict:
    """Perform {action} on {entity}."""
    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id:
        raise AuthenticationError("AUTH_USER_NOT_FOUND_IN_TOKEN", payload=token_payload.to_dict(), token=token_payload.get_original_token())

    result = await {entity}_service.a{action}_{entity}(body, lms_user_id)

    return {"status": "success", "message": "{Action} completed successfully", "result": result}
```

### POST - Search/Filter Endpoint (when GET is not suitable)

```python
@{entity}_router.post(
    "/search",
    description="Search {entities} with complex filters",
    response_model=list[{Entity}Response],
    status_code=200,
)
async def asearch_{entities}(
    body: {Entity}SearchRequest,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    {entity}_service: {Entity}Service = deps.depends({Entity}Service),
) -> list[{Entity}Response]:
    """Search {entities} with complex filter criteria."""
    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id:
        raise AuthenticationError("AUTH_USER_NOT_FOUND_IN_TOKEN", payload=token_payload.to_dict(), token=token_payload.get_original_token())

    {entities} = await {entity}_service.asearch_{entities}(body)

    return [{Entity}ResponseConverter.convert_{entity}_to_response(e) for e in {entities}]
```

---

## PATCH Endpoint Templates

### PATCH - Update Resource

```python
@{entity}_router.patch(
    "/{{{entity}_id}}",
    description="Update {entity} by ID",
    response_model={Entity}Response,
    status_code=200,
)
async def aupdate_{entity}(
    {entity}_id: str,
    body: Update{Entity}Request,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    {entity}_service: {Entity}Service = deps.depends({Entity}Service),
) -> {Entity}Response:
    """Update an existing {entity}."""
    if not Validate.is_uuid({entity}_id):
        raise ValidationError("VALIDATION_INVALID_UUID", value={entity}_id, field="{entity}_id")

    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id:
        raise AuthenticationError("AUTH_USER_NOT_FOUND_IN_TOKEN", payload=token_payload.to_dict(), token=token_payload.get_original_token())

    # Convert request to model
    {entity}: {Entity} = {Entity}RequestConverter.convert_update_request_to_{entity}(body, {entity}_id)

    # Update via service
    updated_{entity}: {Entity} = await {entity}_service.aupdate_{entity}({entity})

    return {Entity}ResponseConverter.convert_{entity}_to_response(updated_{entity})
```

### PATCH - Create or Update (Upsert)

```python
@{entity}_router.patch(
    "/set-infos",
    description="Create or update {entity} information",
    response_model={Entity}Response,
    status_code=200,
)
async def acreate_or_update_{entity}(
    {entity}_infos: {Entity}InfosRequest,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    {entity}_service: {Entity}Service = deps.depends({Entity}Service),
) -> {Entity}Response:
    """Create or update {entity} and its information."""
    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id or not Validate.is_int(lms_user_id):
        raise ValidationError("VALIDATION_INVALID_INTEGER", value=lms_user_id, field="lms_user_id")

    {entity}: {Entity} = {Entity}RequestConverter.convert_{entity}_infos_request_to_{entity}({entity}_infos)
    created_{entity}: {Entity} = await {entity}_service.acreate_or_update_{entity}({entity})

    return {Entity}ResponseConverter.convert_{entity}_to_response(created_{entity})
```

---

## DELETE Endpoint Templates

### DELETE - Soft Delete

```python
@{entity}_router.delete(
    "/{{{entity}_id}}",
    description="Delete {entity} by ID (soft delete)",
    status_code=200,
)
async def adelete_{entity}(
    {entity}_id: str,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    {entity}_service: {Entity}Service = deps.depends({Entity}Service),
) -> dict:
    """Soft delete an {entity} by its ID."""
    if not Validate.is_uuid({entity}_id):
        raise ValidationError("VALIDATION_INVALID_UUID", value={entity}_id, field="{entity}_id")

    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id:
        raise AuthenticationError("AUTH_USER_NOT_FOUND_IN_TOKEN", payload=token_payload.to_dict(), token=token_payload.get_original_token())

    success = await {entity}_service.adelete_{entity}(UUID({entity}_id))

    if not success:
        raise NotFoundError("NOT_FOUND_{ENTITY}", {entity}_id={entity}_id)

    return {"status": "success", "message": "{Entity} deleted successfully"}
```

### DELETE - Hard Delete (Admin only)

```python
@admin_router.delete(
    "/{entity}/{{{entity}_id}}",
    description="Permanently delete {entity} (admin only)",
    status_code=200,
)
async def ahard_delete_{entity}(
    {entity}_id: str,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    {entity}_service: {Entity}Service = deps.depends({Entity}Service),
) -> dict:
    """Permanently delete an {entity} from the database."""
    if not Validate.is_uuid({entity}_id):
        raise ValidationError("VALIDATION_INVALID_UUID", value={entity}_id, field="{entity}_id")

    # Admin check would go here

    await {entity}_service.ahard_delete_{entity}(UUID({entity}_id))

    return {"status": "success", "message": "{Entity} permanently deleted"}
```

---

## Streaming Endpoint Template

### SSE/Streaming Response

```python
from fastapi.responses import StreamingResponse

@{entity}_router.post(
    "/{{{entity}_id}}/stream",
    description="Stream {entity} processing results",
    status_code=200,
)
async def astream_{entity}_processing(
    {entity}_id: str,
    body: {Entity}StreamRequest,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    {entity}_service: {Entity}Service = deps.depends({Entity}Service),
) -> StreamingResponse:
    """Stream {entity} processing results as SSE."""
    if not Validate.is_uuid({entity}_id):
        raise ValidationError("VALIDATION_INVALID_UUID", value={entity}_id, field="{entity}_id")

    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id or not Validate.is_int(lms_user_id):
        raise ValidationError("VALIDATION_INVALID_INTEGER", value=lms_user_id, field="lms_user_id")

    # Prepare data BEFORE creating StreamingResponse
    # This allows exceptions to be raised before streaming starts
    prepared_data = await {entity}_service.aprepare_{entity}_for_streaming(
        UUID({entity}_id),
        lms_user_id,
        body,
    )
    if not prepared_data:
        return StreamingResponse("- No data available -", media_type="application/octet-stream")

    # Create async generator for streaming
    response_generator = {entity}_service.astream_{entity}_response(
        prepared_data,
        lms_user_id,
    )

    # Select streaming mode
    media_type = "text/event-stream"  # or "application/octet-stream"
    return StreamingResponse(response_generator, media_type=media_type)
```

---

## New Router Creation

### Complete New Router File

**File:** `src/facade/{entity}_router.py`

```python
from uuid import UUID
from fastapi import APIRouter, Depends

from API.dependency_injection_config import deps
from application.{entity}_service import {Entity}Service
from common_tools.helpers.validation_helper import Validate  # type: ignore[import-not-found]
from facade.request_models.{entity}_request import Create{Entity}Request, Update{Entity}Request
from facade.response_models.{entity}_response import {Entity}Response
from facade.converters.{entity}_request_converter import {Entity}RequestConverter
from facade.converters.{entity}_response_converter import {Entity}ResponseConverter
from models.{entity} import {Entity}
from security.auth_dependency import authentication_required
from security.jwt_skillforge_payload import JWTSkillForgePayload
from utils.exceptions import ValidationError, AuthenticationError, NotFoundError

{entity}_router = APIRouter(prefix="/{entity}", tags=["{Entity}"])


@{entity}_router.get(
    "/{{{entity}_id}}",
    description="Get {entity} by ID",
    response_model={Entity}Response,
    status_code=200,
)
async def aget_{entity}_by_id(
    {entity}_id: str,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    {entity}_service: {Entity}Service = deps.depends({Entity}Service),
) -> {Entity}Response:
    """Retrieve {entity} by its unique identifier."""
    if not Validate.is_uuid({entity}_id):
        raise ValidationError("VALIDATION_INVALID_UUID", value={entity}_id, field="{entity}_id")

    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id:
        raise AuthenticationError("AUTH_USER_NOT_FOUND_IN_TOKEN", payload=token_payload.to_dict(), token=token_payload.get_original_token())

    {entity}: {Entity} | None = await {entity}_service.aget_{entity}_by_id(UUID({entity}_id))
    if not {entity}:
        raise NotFoundError("NOT_FOUND_{ENTITY}", {entity}_id={entity}_id)

    return {Entity}ResponseConverter.convert_{entity}_to_response({entity})


@{entity}_router.post(
    "/",
    description="Create a new {entity}",
    response_model={Entity}Response,
    status_code=201,
)
async def acreate_{entity}(
    body: Create{Entity}Request,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    {entity}_service: {Entity}Service = deps.depends({Entity}Service),
) -> {Entity}Response:
    """Create a new {entity}."""
    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id:
        raise AuthenticationError("AUTH_USER_NOT_FOUND_IN_TOKEN", payload=token_payload.to_dict(), token=token_payload.get_original_token())

    {entity}: {Entity} = {Entity}RequestConverter.convert_request_to_{entity}(body)
    created_{entity}: {Entity} = await {entity}_service.acreate_{entity}({entity})

    return {Entity}ResponseConverter.convert_{entity}_to_response(created_{entity})


@{entity}_router.patch(
    "/{{{entity}_id}}",
    description="Update {entity} by ID",
    response_model={Entity}Response,
    status_code=200,
)
async def aupdate_{entity}(
    {entity}_id: str,
    body: Update{Entity}Request,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    {entity}_service: {Entity}Service = deps.depends({Entity}Service),
) -> {Entity}Response:
    """Update an existing {entity}."""
    if not Validate.is_uuid({entity}_id):
        raise ValidationError("VALIDATION_INVALID_UUID", value={entity}_id, field="{entity}_id")

    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id:
        raise AuthenticationError("AUTH_USER_NOT_FOUND_IN_TOKEN", payload=token_payload.to_dict(), token=token_payload.get_original_token())

    {entity}: {Entity} = {Entity}RequestConverter.convert_update_request_to_{entity}(body, {entity}_id)
    updated_{entity}: {Entity} = await {entity}_service.aupdate_{entity}({entity})

    return {Entity}ResponseConverter.convert_{entity}_to_response(updated_{entity})


@{entity}_router.delete(
    "/{{{entity}_id}}",
    description="Delete {entity} by ID",
    status_code=200,
)
async def adelete_{entity}(
    {entity}_id: str,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    {entity}_service: {Entity}Service = deps.depends({Entity}Service),
) -> dict:
    """Delete an {entity} by its ID."""
    if not Validate.is_uuid({entity}_id):
        raise ValidationError("VALIDATION_INVALID_UUID", value={entity}_id, field="{entity}_id")

    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id:
        raise AuthenticationError("AUTH_USER_NOT_FOUND_IN_TOKEN", payload=token_payload.to_dict(), token=token_payload.get_original_token())

    success = await {entity}_service.adelete_{entity}(UUID({entity}_id))
    if not success:
        raise NotFoundError("NOT_FOUND_{ENTITY}", {entity}_id={entity}_id)

    return {"status": "success", "message": "{Entity} deleted successfully"}
```

### Router Registration

**Location:** `src/API/api_config.py`

```python
# Add import at top of file
from facade.{entity}_router import {entity}_router

# In create_app() function, add:
app.include_router({entity}_router)
```
