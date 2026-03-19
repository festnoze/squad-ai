# Architecture Reference

Detailed documentation of SkillForge's 3-layer architecture pattern.

## Layer 1: Facade (Presentation)

**Location:** `src/facade/`

**Purpose:** Handle HTTP interface, request/response serialization, authentication.

### Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| Routers | `src/facade/*_router.py` | HTTP endpoint definitions |
| Request Models | `src/facade/request_models/*.py` | Input validation (Pydantic) |
| Response Models | `src/facade/response_models/*.py` | Output serialization (Pydantic) |

### Router Structure

```python
from fastapi import APIRouter, Depends
from API.dependency_injection_config import deps
from security.auth_dependency import authentication_required
from security.jwt_payload import JWTSkillForgePayload
from application.{name}_service import {Name}Service

{name}_router = APIRouter(prefix="/{name}", tags=["{Name}"])

@{name}_router.get("/{id}")
async def aget_{name}(
    id: str,
    token_payload: JWTSkillForgePayload = Depends(authentication_required),
    service: {Name}Service = deps.depends({Name}Service),
) -> {Name}Response:
    """Get {name} by ID."""
    result = await service.aget_by_id(UUID(id))
    return {Name}ResponseConverter.convert(result)
```

### Request Model Structure

```python
from pydantic import BaseModel, Field

class Create{Name}Request(BaseModel):
    """Request to create a new {name}."""
    field1: str = Field(..., min_length=1, max_length=255)
    field2: int | None = None
```

### Response Model Structure

```python
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class {Name}Response(BaseModel):
    """Response containing {name} data."""
    id: UUID
    field1: str
    created_at: datetime | None = None
```

---

## Layer 2: Application (Business Logic)

**Location:** `src/application/`

**Purpose:** Implement business rules, orchestrate repositories, handle transactions.

### Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| Services | `src/application/*_service.py` | Business logic, orchestration |

### Service Structure

```python
from uuid import UUID
from infrastructure.{name}_repository import {Name}Repository
from models.{name} import {Name}

class {Name}Service:
    def __init__(
        self,
        repository: {Name}Repository,
    ):
        self.repository = repository

    async def aget_by_id(self, id: UUID) -> {Name} | None:
        """Get {name} by ID."""
        return await self.repository.aget_by_id(id)

    async def acreate(self, data: {Name}) -> {Name}:
        """Create a new {name}."""
        # Business rules here
        return await self.repository.acreate(data)
```

### Service Patterns

**Orchestration:** Services coordinate multiple repositories
```python
async def acreate_with_related(self, data: CreateData) -> Result:
    # Create main entity
    main = await self.main_repository.acreate(data.main)

    # Create related entities
    for item in data.related:
        await self.related_repository.acreate(item, parent_id=main.id)

    return main
```

**Validation:** Business rules before persistence
```python
async def aupdate(self, id: UUID, data: UpdateData) -> Result:
    existing = await self.repository.aget_by_id(id)
    if not existing:
        raise NotFoundError("NOT_FOUND_ENTITY", id=str(id))

    # Business validation
    if not self._can_update(existing, data):
        raise ValidationError("VALIDATION_CANNOT_UPDATE")

    return await self.repository.aupdate(id, data)
```

---

## Layer 3: Infrastructure (Data Access)

**Location:** `src/infrastructure/`

**Purpose:** Handle data persistence, external service integration, entity mapping.

### Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| Repositories | `src/infrastructure/*_repository.py` | Database operations |
| Entities | `src/infrastructure/entities/*.py` | ORM definitions |
| Converters | `src/infrastructure/converters/*.py` | Entity <-> Model mapping |

### Repository Structure (with AutoSessionMeta)

```python
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database import BaseRepository, AutoSessionMeta
from infrastructure.entities.{name}_entity import {Name}Entity
from infrastructure.converters.{name}_converters import {Name}Converters
from models.{name} import {Name}

class {Name}Repository(BaseRepository, metaclass=AutoSessionMeta):

    async def aget_by_id(self, session: AsyncSession, id: UUID) -> {Name} | None:
        stmt = select({Name}Entity).where({Name}Entity.id == id)
        result = await session.execute(stmt)
        entity = result.scalar_one_or_none()
        return {Name}Converters.convert_entity_to_model(entity) if entity else None

    async def acreate(self, session: AsyncSession, model: {Name}) -> {Name}:
        entity = {Name}Converters.convert_model_to_entity(model)
        session.add(entity)
        await session.flush()
        await session.refresh(entity)
        return {Name}Converters.convert_entity_to_model(entity)
```

### Entity Structure

```python
from uuid import UUID
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from infrastructure.entities import StatefulBase

class {Name}Entity(StatefulBase):
    __tablename__ = "{names}"  # plural

    # Fields
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Foreign keys
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Relationships
    user: Mapped["UserEntity"] = relationship("UserEntity", lazy="joined")
```

### Converter Structure

```python
from models.{name} import {Name}
from infrastructure.entities.{name}_entity import {Name}Entity

class {Name}Converters:
    @staticmethod
    def convert_entity_to_model(entity: {Name}Entity) -> {Name}:
        return {Name}(
            id=entity.id,
            name=entity.name,
            created_at=entity.created_at,
        )

    @staticmethod
    def convert_model_to_entity(model: {Name}) -> {Name}Entity:
        return {Name}Entity(
            id=model.id,
            name=model.name,
        )
```

---

## Domain Models

**Location:** `src/models/`

**Purpose:** Shared data structures used across all layers.

### Model Structure

```python
from dataclasses import dataclass, field
from uuid import UUID
from datetime import datetime

@dataclass
class {Name}:
    """Domain model for {name}."""
    id: UUID | None = None
    name: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

---

## Dependency Flow Diagram

```
                    +-----------------------+
                    |     HTTP Request      |
                    +-----------------------+
                              |
                              v
+----------------+   +------------------+   +-------------------+
|  Request Model | > |     Router       | < |  Response Model   |
|   (Pydantic)   |   |   (FastAPI)      |   |    (Pydantic)     |
+----------------+   +------------------+   +-------------------+
                              |
                              | deps.depends(Service)
                              v
                    +------------------+
                    |     Service      |
                    |  (Business Logic)|
                    +------------------+
                              |
                              | self.repository
                              v
                    +------------------+
                    |   Repository     |
                    |  (Data Access)   |
                    +------------------+
                         |         |
            Converter    |         |    Converter
             to Model    v         v    to Entity
                    +------------------+
                    |     Entity       |
                    |   (SQLAlchemy)   |
                    +------------------+
                              |
                              v
                    +------------------+
                    |    Database      |
                    +------------------+
```

---

## Key Principles

1. **No circular dependencies** - Layers only depend on layers below them
2. **Repositories return Models** - Never expose Entities outside Infrastructure
3. **Services handle business logic** - Routers are thin, just HTTP
4. **Converters isolate mapping** - Changes to Entities don't ripple through codebase
5. **Domain Models are shared** - Used across all layers for consistency
