# Service Templates

Complete templates for creating application services.

## Table of Contents

1. [Basic Service Structure](#basic-service-structure)
2. [Service with Sub-services](#service-with-sub-services)
3. [Method Templates](#method-templates)
4. [Error Handling Patterns](#error-handling-patterns)
5. [Dependency Injection Registration](#dependency-injection-registration)
6. [Complete Example](#complete-example)

---

## Basic Service Structure

**Location:** `src/application/{entity}_service.py`

```python
import logging

from infrastructure.{entity}_repository import {Entity}Repository
from models.{entity} import {Entity}


class {Entity}Service:
    """
    Service for {Entity} use-cases.

    Orchestrates business logic by coordinating repositories.
    """

    def __init__(
        self,
        {entity}_repository: {Entity}Repository,
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.{entity}_repository = {entity}_repository

    async def aget_{entity}_by_id(self, {entity}_id: UUID) -> {Entity} | None:
        """Retrieve {entity} by ID."""
        return await self.{entity}_repository.aget_{entity}_by_id({entity}_id)  # type: ignore[call-arg]

    async def acreate_{entity}(self, {entity}: {Entity}) -> {Entity}:
        """Create new {entity}."""
        return await self.{entity}_repository.acreate_{entity}({entity})  # type: ignore[call-arg]
```

**Note:** `# type: ignore[call-arg]` is needed because AutoSessionMeta removes the `session` parameter from the repository method signature, but type checkers don't know this.

---

## Service with Sub-services

```python
import logging
from typing import TYPE_CHECKING

from infrastructure.{entity}_repository import {Entity}Repository
from models.{entity} import {Entity}

if TYPE_CHECKING:
    from application.user_service import UserService
    from application.content_service import ContentService


class {Entity}Service:
    """
    Service for {Entity} use-cases.

    Orchestrates business logic by coordinating repositories and other services.
    """

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

    async def acomplex_use_case(self, user_id: UUID, content_id: str) -> {Entity}:
        """
        Complex use-case that orchestrates multiple services.
        """
        # Step 1: Get user via sub-service
        user = await self.user_service.aget_user_by_id(user_id)
        if not user:
            raise NotFoundError("NOT_FOUND_USER")

        # Step 2: Get content via sub-service
        content = await self.content_service.aget_content_by_id(content_id)
        if not content:
            raise NotFoundError("NOT_FOUND_CONTENT")

        # Step 3: Create entity with repository
        entity = {Entity}(user_id=user.id, content_id=content.id)
        return await self.{entity}_repository.acreate_{entity}(entity)  # type: ignore[call-arg]
```

**Note:** Use `TYPE_CHECKING` guard to avoid circular imports when services depend on each other.

---

## Method Templates

### Simple CRUD Wrapper

```python
async def aget_{entity}_by_id(self, {entity}_id: UUID) -> {Entity} | None:
    """Retrieve {entity} by ID."""
    return await self.{entity}_repository.aget_{entity}_by_id({entity}_id)  # type: ignore[call-arg]

async def acreate_{entity}(self, {entity}: {Entity}) -> {Entity}:
    """Create new {entity}."""
    return await self.{entity}_repository.acreate_{entity}({entity})  # type: ignore[call-arg]

async def aupdate_{entity}(self, {entity}: {Entity}) -> {Entity}:
    """Update existing {entity}."""
    return await self.{entity}_repository.aupdate_{entity}({entity})  # type: ignore[call-arg]

async def adelete_{entity}(self, {entity}_id: UUID) -> bool:
    """Delete {entity} by ID."""
    return await self.{entity}_repository.adelete_{entity}({entity}_id)  # type: ignore[call-arg]
```

### Get or Create Pattern

```python
async def aget_or_create_{entity}(
    self,
    identifier: str,
    default_data: dict | None = None
) -> {Entity}:
    """
    Retrieve existing {entity} or create new one.
    """
    # Try to get existing
    entity = await self.{entity}_repository.aget_{entity}_by_identifier(identifier)  # type: ignore[call-arg]
    if entity:
        return entity

    # Create new
    new_entity = {Entity}(
        identifier=identifier,
        **(default_data or {})
    )
    return await self.{entity}_repository.acreate_{entity}(new_entity)  # type: ignore[call-arg]
```

### Create or Update Pattern

```python
async def acreate_or_update_{entity}(self, {entity}: {Entity}) -> {Entity}:
    """
    Create new {entity} or update existing one.
    """
    try:
        return await self.{entity}_repository.acreate_or_update({entity})  # type: ignore[call-arg]
    except Exception as e:
        self.logger.error(f"Failed to create/update {entity}: {e}")
        raise InternalServerException("INTERNAL_{ENTITY}_PERSISTENCE_FAILED", details=str(e)) from e
```

### Orchestration with Multiple Services

```python
async def aprocess_{entity}_with_context(
    self,
    {entity}_id: UUID,
    user_id: UUID,
    context: dict
) -> ProcessResult:
    """
    Process {entity} with full context.

    Orchestrates user verification, content loading, and processing.
    """
    # Step 1: Verify user
    user = await self.user_service.aget_user_by_id(user_id)
    if not user:
        raise NotFoundError("NOT_FOUND_USER")

    # Step 2: Get entity
    entity = await self.{entity}_repository.aget_{entity}_by_id({entity}_id)  # type: ignore[call-arg]
    if not entity:
        raise NotFoundError("NOT_FOUND_{ENTITY}")

    # Step 3: Authorization check
    if entity.user_id != user.id:
        raise AuthorizationError("AUTHZ_{ENTITY}_ACCESS_DENIED")

    # Step 4: Load related content
    content = await self.content_service.aget_content_by_filter(context)

    # Step 5: Process and return
    result = self._process_entity(entity, content, context)
    return result
```

### Streaming Pattern (AsyncGenerator)

```python
from typing import AsyncGenerator

async def astream_{entity}_processing(
    self,
    {entity}_id: UUID,
    options: dict
) -> AsyncGenerator[str, None]:
    """
    Stream {entity} processing results.

    Yields progress updates as SSE-formatted strings.
    """
    import json

    # Yield start event
    yield f"data: {json.dumps({'event': 'started', 'id': str({entity}_id)})}\n\n"

    try:
        # Process in chunks
        entity = await self.{entity}_repository.aget_{entity}_by_id({entity}_id)  # type: ignore[call-arg]

        for i, chunk in enumerate(self._process_chunks(entity, options)):
            # Yield progress
            yield f"data: {json.dumps({'event': 'progress', 'chunk': i, 'data': chunk})}\n\n"

        # Yield completion
        yield f"data: {json.dumps({'event': 'completed'})}\n\n"

    except Exception as e:
        # Yield error
        yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"
        raise
```

### Bulk Operation Pattern

```python
async def aexport_{entities}_to_json(
    self,
    output_dir: str,
    batch_size: int = 100
) -> dict:
    """
    Export all {entities} to JSON files.

    Returns summary with counts and any errors.
    """
    import json
    from pathlib import Path

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    total = 0
    errors = []
    offset = 0

    while True:
        # Fetch batch
        batch = await self.{entity}_repository.aget_{entities}_batch(  # type: ignore[call-arg]
            limit=batch_size,
            offset=offset
        )

        if not batch:
            break

        # Process batch
        for entity in batch:
            try:
                file_path = output_path / f"{entity.id}.json"
                file_path.write_text(json.dumps(entity.model_dump(), default=str))
                total += 1
            except Exception as e:
                errors.append({"id": str(entity.id), "error": str(e)})

        offset += batch_size

    return {
        "exported": total,
        "errors": errors,
        "output_dir": str(output_path)
    }
```

---

## Error Handling Patterns

### Import Error Classes

```python
from errors import (
    ValidationError,
    AuthorizationError,
    NotFoundError,
    ConflictError,
    QuotaExceededException,
    InternalServerException,
    ExternalApiException,
)
```

### Early Validation

```python
async def aprocess_{entity}(self, {entity}_id: UUID | None) -> {Entity}:
    # Validate input early
    if not {entity}_id:
        raise ValidationError("VALIDATION_{ENTITY}_ID_MISSING")

    entity = await self.{entity}_repository.aget_{entity}_by_id({entity}_id)  # type: ignore[call-arg]
    if not entity:
        raise NotFoundError("NOT_FOUND_{ENTITY}", {entity}_id=str({entity}_id))

    return entity
```

### Authorization Check

```python
async def aget_{entity}_for_user(
    self,
    {entity}_id: UUID,
    user_id: UUID
) -> {Entity}:
    entity = await self.{entity}_repository.aget_{entity}_by_id({entity}_id)  # type: ignore[call-arg]

    if not entity:
        raise NotFoundError("NOT_FOUND_{ENTITY}")

    if entity.user_id != user_id:
        raise AuthorizationError(
            "AUTHZ_{ENTITY}_ACCESS_DENIED",
            {entity}_id=str({entity}_id),
            user_id=str(user_id)
        )

    return entity
```

### Wrap External Errors

```python
async def acreate_{entity}(self, {entity}: {Entity}) -> {Entity}:
    try:
        return await self.{entity}_repository.acreate_{entity}({entity})  # type: ignore[call-arg]
    except PydanticValidationError as e:
        raise ValidationError("VALIDATION_INVALID_{ENTITY}_DATA", details=str(e)) from e
    except Exception as e:
        self.logger.error(f"Failed to create {entity}: {e}", exc_info=True)
        raise InternalServerException(
            "INTERNAL_{ENTITY}_PERSISTENCE_FAILED",
            details=str(e)
        ) from e
```

### Quota Check

```python
async def aprocess_with_quota_check(
    self,
    user_id: UUID,
    daily_limit: int,
    monthly_limit: int
) -> None:
    # Check daily quota
    daily_count = await self.{entity}_repository.aget_count_since_start_of_day(user_id)  # type: ignore[call-arg]
    if daily_count >= daily_limit:
        raise QuotaExceededException(
            "QUOTA_DAILY_EXCEEDED",
            current=daily_count,
            limit=daily_limit
        )

    # Check monthly quota
    monthly_count = await self.{entity}_repository.aget_count_since_start_of_month(user_id)  # type: ignore[call-arg]
    if monthly_count >= monthly_limit:
        raise QuotaExceededException(
            "QUOTA_MONTHLY_EXCEEDED",
            current=monthly_count,
            limit=monthly_limit
        )
```

---

## Dependency Injection Registration

**Location:** `src/API/dependency_injection_config.py`

### Basic Registration

```python
from lagom import Container

from application.{entity}_service import {Entity}Service
from infrastructure.{entity}_repository import {Entity}Repository

container = Container()

# Register repository
container[{Entity}Repository] = {Entity}Repository

# Register service
container[{Entity}Service] = {Entity}Service
```

### Service with Dependencies

```python
from lagom import Container

from application.{entity}_service import {Entity}Service
from application.user_service import UserService
from infrastructure.{entity}_repository import {Entity}Repository

container = Container()

# Repositories first
container[{Entity}Repository] = {Entity}Repository

# Services (order matters for dependencies)
container[UserService] = UserService  # No service dependencies
container[{Entity}Service] = {Entity}Service  # Depends on UserService
```

### FastAPI Integration

```python
from lagom.integrations.fast_api import FastApiIntegration

# Create integration
deps = FastApiIntegration(container)

# Use in router
@router.get("/{entity}/{id}")
async def get_{entity}(
    id: UUID,
    {entity}_service: {Entity}Service = deps.depends({Entity}Service)
) -> {Entity}Response:
    entity = await {entity}_service.aget_{entity}_by_id(id)
    return {Entity}ResponseConverter.convert(entity)
```

---

## Complete Example

### New "Notification" Service

**1. Service File** (`src/application/notification_service.py`):

```python
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from errors import NotFoundError, ValidationError, AuthorizationError
from infrastructure.notification_repository import NotificationRepository
from models.notification import Notification

if TYPE_CHECKING:
    from application.user_service import UserService


class NotificationService:
    """
    Service for Notification use-cases.

    Handles notification creation, retrieval, and user-specific operations.
    """

    def __init__(
        self,
        notification_repository: NotificationRepository,
        user_service: "UserService",
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.notification_repository = notification_repository
        self.user_service = user_service

    async def aget_notifications_for_user(
        self,
        user_id: UUID,
        limit: int = 50
    ) -> list[Notification]:
        """
        Get notifications for a user.
        """
        # Verify user exists
        user = await self.user_service.aget_user_by_id(user_id)
        if not user:
            raise NotFoundError("NOT_FOUND_USER", user_id=str(user_id))

        return await self.notification_repository.aget_notifications_by_user_id(  # type: ignore[call-arg]
            user_id=user_id,
            limit=limit
        )

    async def acreate_notification(
        self,
        user_id: UUID,
        title: str,
        message: str
    ) -> Notification:
        """
        Create a new notification for a user.
        """
        if not title or not message:
            raise ValidationError("VALIDATION_NOTIFICATION_CONTENT_MISSING")

        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            is_read=False
        )

        return await self.notification_repository.acreate_notification(  # type: ignore[call-arg]
            notification
        )

    async def amark_as_read(
        self,
        notification_id: UUID,
        user_id: UUID
    ) -> Notification:
        """
        Mark a notification as read.
        """
        notification = await self.notification_repository.aget_notification_by_id(  # type: ignore[call-arg]
            notification_id
        )

        if not notification:
            raise NotFoundError("NOT_FOUND_NOTIFICATION")

        if notification.user_id != user_id:
            raise AuthorizationError("AUTHZ_NOTIFICATION_ACCESS_DENIED")

        return await self.notification_repository.aupdate_notification(  # type: ignore[call-arg]
            notification_id,
            is_read=True
        )
```

**2. DI Registration** (add to `dependency_injection_config.py`):

```python
from application.notification_service import NotificationService
from infrastructure.notification_repository import NotificationRepository

# In container setup
container[NotificationRepository] = NotificationRepository
container[NotificationService] = NotificationService
```
