# Service Templates

Application-layer service templates. A service method = one use-case. All async methods prefixed
with `a`.

## Contents
1. [Service with sub-services](#service-with-sub-services)
2. [Method patterns](#method-patterns)
3. [Error handling patterns](#error-handling-patterns)
4. [Registration](#registration)

---

## Service with sub-services

```python
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from errors import NotFoundError, AuthorizationError
from infrastructure.{entity}_repository import {Entity}Repository
from models.{entity} import {Entity}

if TYPE_CHECKING:
    from application.user_service import UserService
    from application.content_service import ContentService


class {Entity}Service:
    """Service for {Entity} use-cases. Orchestrates repositories and other services."""

    def __init__(
        self,
        {entity}_repository: {Entity}Repository,
        user_service: "UserService",
        content_service: "ContentService",
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.{entity}_repository = {entity}_repository
        self.user_service = user_service
        self.content_service = content_service

    async def aprocess_{entity}_with_context(self, {entity}_id: UUID, user_id: UUID, context: dict) -> {Entity}:
        user = await self.user_service.aget_user_by_id(user_id)
        if not user:
            raise NotFoundError("NOT_FOUND_USER")
        entity = await self.{entity}_repository.aget_{entity}_by_id({entity}_id)  # type: ignore[call-arg]
        if not entity:
            raise NotFoundError("NOT_FOUND_{ENTITY}")
        if entity.user_id != user.id:
            raise AuthorizationError("AUTHZ_{ENTITY}_ACCESS_DENIED")
        content = await self.content_service.aget_content_by_filter(context)
        return self._process(entity, content, context)
```

Use the `TYPE_CHECKING` guard for sub-service imports to avoid circular imports.

---

## Method patterns

### Simple CRUD wrapper

```python
async def aget_{entity}_by_id(self, {entity}_id: UUID) -> {Entity} | None:
    return await self.{entity}_repository.aget_{entity}_by_id({entity}_id)  # type: ignore[call-arg]

async def acreate_{entity}(self, {entity}: {Entity}) -> {Entity}:
    return await self.{entity}_repository.acreate_{entity}({entity})  # type: ignore[call-arg]
```

### Get or create

```python
async def aget_or_create_{entity}(self, identifier: str, default_data: dict | None = None) -> {Entity}:
    entity = await self.{entity}_repository.aget_{entity}_by_identifier(identifier)  # type: ignore[call-arg]
    if entity:
        return entity
    return await self.{entity}_repository.acreate_{entity}(
        {Entity}(identifier=identifier, **(default_data or {}))
    )  # type: ignore[call-arg]
```

### Streaming (AsyncGenerator → SSE)

```python
from typing import AsyncGenerator
import json

async def astream_{entity}_processing(self, {entity}_id: UUID, options: dict) -> AsyncGenerator[str, None]:
    yield f"data: {json.dumps({'event': 'started', 'id': str({entity}_id)})}\n\n"
    try:
        entity = await self.{entity}_repository.aget_{entity}_by_id({entity}_id)  # type: ignore[call-arg]
        for i, chunk in enumerate(self._process_chunks(entity, options)):
            yield f"data: {json.dumps({'event': 'progress', 'chunk': i, 'data': chunk})}\n\n"
        yield f"data: {json.dumps({'event': 'completed'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"
        raise
```

### Bulk export

```python
async def aexport_{entities}_to_json(self, output_dir: str, batch_size: int = 100) -> dict:
    import json
    from pathlib import Path
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    total, errors, offset = 0, [], 0
    while True:
        batch = await self.{entity}_repository.aget_{entities}_batch(limit=batch_size, offset=offset)  # type: ignore[call-arg]
        if not batch:
            break
        for entity in batch:
            try:
                (out / f"{entity.id}.json").write_text(json.dumps(entity.model_dump(), default=str))
                total += 1
            except Exception as e:
                errors.append({"id": str(entity.id), "error": str(e)})
        offset += batch_size
    return {"exported": total, "errors": errors, "output_dir": str(out)}
```

---

## Error handling patterns

```python
from errors import (
    ValidationError, AuthorizationError, NotFoundError,
    ConflictError, QuotaExceededError, InternalServerException,
)

# Early validation
if not {entity}_id:
    raise ValidationError("VALIDATION_{ENTITY}_ID_MISSING")

# Authorization
if entity.user_id != user_id:
    raise AuthorizationError("AUTHZ_{ENTITY}_ACCESS_DENIED", {entity}_id=str({entity}_id))

# Wrap unexpected errors
try:
    return await self.{entity}_repository.acreate_{entity}({entity})  # type: ignore[call-arg]
except Exception as e:
    self.logger.error(f"Failed to create {entity}: {e}", exc_info=True)
    raise InternalServerException("INTERNAL_{ENTITY}_PERSISTENCE_FAILED", details=str(e)) from e
```

New error codes are added via `/error-code-management`.

---

## Registration

Register the repository and service where the app wires its dependencies (DI container / provider
module / app factory). Register repositories before the services that consume them. Example shape:

```python
# wherever the app registers components
register({Entity}Repository)
register({Entity}Service)  # depends on {Entity}Repository (+ any sub-services)
```
