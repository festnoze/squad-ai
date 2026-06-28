# Endpoint Templates

FastAPI endpoint templates (facade layer). Handlers stay thin: validate → call service → convert.
All handlers are `async` and prefixed with `a`. Replace `Depends(get_{entity}_service)` and the auth
dependency with whatever the generated app provides.

## Contents
1. [Router file](#router-file)
2. [GET](#get)
3. [POST](#post)
4. [PATCH](#patch)
5. [DELETE](#delete)
6. [Streaming](#streaming)
7. [Register](#register)

---

## Router file

**Location:** `facade/{entity}_router.py`

```python
from uuid import UUID

from fastapi import APIRouter, Depends

from application.{entity}_service import {Entity}Service
from facade.request_models.{entity}_request import Create{Entity}Request, Update{Entity}Request
from facade.response_models.{entity}_response import {Entity}Response
from facade.converters.{entity}_request_converter import {Entity}RequestConverter
from facade.converters.{entity}_response_converter import {Entity}ResponseConverter
from models.{entity} import {Entity}
from errors import ValidationError, NotFoundError
# from <app>.dependencies import get_{entity}_service, authentication_required, Validate

{entity}_router = APIRouter(prefix="/{entity}", tags=["{Entity}"])
```

---

## GET

```python
@{entity}_router.get("/{{{entity}_id}}", description="Get {entity} by ID",
                     response_model={Entity}Response, status_code=200)
async def aget_{entity}_by_id(
    {entity}_id: str,
    {entity}_service: {Entity}Service = Depends(get_{entity}_service),
) -> {Entity}Response:
    if not Validate.is_uuid({entity}_id):
        raise ValidationError("VALIDATION_INVALID_UUID", value={entity}_id, field="{entity}_id")
    {entity}: {Entity} | None = await {entity}_service.aget_{entity}_by_id(UUID({entity}_id))
    if not {entity}:
        raise NotFoundError("NOT_FOUND_{ENTITY}", {entity}_id={entity}_id)
    return {Entity}ResponseConverter.convert_{entity}_to_response({entity})


@{entity}_router.get("/", description="List {entities}",
                     response_model=list[{Entity}Response], status_code=200)
async def aget_{entities}(
    page: int = 1, page_size: int = 20,
    {entity}_service: {Entity}Service = Depends(get_{entity}_service),
) -> list[{Entity}Response]:
    {entities} = await {entity}_service.aget_{entities}(page=page, page_size=page_size)
    return [{Entity}ResponseConverter.convert_{entity}_to_response(e) for e in {entities}]
```

---

## POST

```python
@{entity}_router.post("/", description="Create a {entity}",
                      response_model={Entity}Response, status_code=201)
async def acreate_{entity}(
    body: Create{Entity}Request,
    {entity}_service: {Entity}Service = Depends(get_{entity}_service),
) -> {Entity}Response:
    {entity}: {Entity} = {Entity}RequestConverter.convert_request_to_{entity}(body)
    created = await {entity}_service.acreate_{entity}({entity})
    return {Entity}ResponseConverter.convert_{entity}_to_response(created)
```

---

## PATCH

```python
@{entity}_router.patch("/{{{entity}_id}}", description="Update {entity}",
                       response_model={Entity}Response, status_code=200)
async def aupdate_{entity}(
    {entity}_id: str, body: Update{Entity}Request,
    {entity}_service: {Entity}Service = Depends(get_{entity}_service),
) -> {Entity}Response:
    if not Validate.is_uuid({entity}_id):
        raise ValidationError("VALIDATION_INVALID_UUID", value={entity}_id, field="{entity}_id")
    {entity}: {Entity} = {Entity}RequestConverter.convert_update_request_to_{entity}(body, {entity}_id)
    updated = await {entity}_service.aupdate_{entity}({entity})
    return {Entity}ResponseConverter.convert_{entity}_to_response(updated)
```

---

## DELETE

```python
@{entity}_router.delete("/{{{entity}_id}}", description="Delete {entity}", status_code=200)
async def adelete_{entity}(
    {entity}_id: str,
    {entity}_service: {Entity}Service = Depends(get_{entity}_service),
) -> dict:
    if not Validate.is_uuid({entity}_id):
        raise ValidationError("VALIDATION_INVALID_UUID", value={entity}_id, field="{entity}_id")
    success = await {entity}_service.adelete_{entity}(UUID({entity}_id))
    if not success:
        raise NotFoundError("NOT_FOUND_{ENTITY}", {entity}_id={entity}_id)
    return {"status": "success", "message": "{Entity} deleted"}
```

---

## Streaming

```python
from fastapi.responses import StreamingResponse

@{entity}_router.post("/{{{entity}_id}}/stream", status_code=200)
async def astream_{entity}_processing(
    {entity}_id: str, body: {Entity}StreamRequest,
    {entity}_service: {Entity}Service = Depends(get_{entity}_service),
) -> StreamingResponse:
    if not Validate.is_uuid({entity}_id):
        raise ValidationError("VALIDATION_INVALID_UUID", value={entity}_id, field="{entity}_id")
    # Prepare BEFORE streaming so exceptions surface as normal HTTP errors
    prepared = await {entity}_service.aprepare_{entity}_for_streaming(UUID({entity}_id), body)
    if not prepared:
        return StreamingResponse("- no data -", media_type="application/octet-stream")
    generator = {entity}_service.astream_{entity}_response(prepared)
    return StreamingResponse(generator, media_type="text/event-stream")
```

---

## Register

**Location:** the app factory (`create_app()` / wherever routers are included).

```python
from facade.{entity}_router import {entity}_router
app.include_router({entity}_router)
```
