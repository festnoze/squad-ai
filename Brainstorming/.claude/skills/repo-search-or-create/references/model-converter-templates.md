# Model and Converter Templates

Templates for creating Pydantic models and entity converters.

## Table of Contents

1. [Model Template](#model-template)
2. [Converter Template](#converter-template)
3. [Complete Example](#complete-example)

---

## Model Template

**Location:** `src/models/{entity_name}.py`

### Standard Model (matching StatefulBase entity)

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class {EntityName}(BaseModel):
    """
    {Description of the business model}
    """

    id: UUID
    # Add entity-specific fields here
    name: str
    description: str | None = None

    # Timestamps from StatefulBase
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True  # Enable ORM mode
```

### Model with Relationships

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class {EntityName}(BaseModel):
    id: UUID
    name: str

    # Foreign key as ID only (not full object)
    user_id: UUID

    # Or include related object (if needed)
    user: "User | None" = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
```

### Model with JSON fields

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class {EntityName}(BaseModel):
    id: UUID
    name: str

    # JSON field with default empty dict
    config: dict = Field(default_factory=dict)

    # Optional JSON field
    metadata_info: dict | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
```

### Simple Model (matching SimpleBase entity)

```python
from uuid import UUID

from pydantic import BaseModel


class {EntityName}(BaseModel):
    """
    Simple lookup model (no timestamps)
    """

    id: UUID
    name: str
    description: str | None = None

    class Config:
        from_attributes = True
```

---

## Converter Template

**Location:** `src/infrastructure/converters/{entity_name}_converters.py`

### Standard Converter

```python
from datetime import timezone

from infrastructure.entities.{entity_name}_entity import {EntityName}Entity
from models.{entity_name} import {EntityName}


class {EntityName}Converters:
    """
    Converters between {EntityName}Entity (database) and {EntityName} (business model).
    """

    @staticmethod
    def convert_entity_to_model(entity: {EntityName}Entity) -> {EntityName}:
        """Convert database entity to business model."""
        return {EntityName}(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            # Add timezone for datetime fields (entity stores UTC without tzinfo)
            created_at=entity.created_at.replace(tzinfo=timezone.utc) if entity.created_at else None,
            updated_at=entity.updated_at.replace(tzinfo=timezone.utc) if entity.updated_at else None,
        )

    @staticmethod
    def convert_model_to_entity(model: {EntityName}) -> {EntityName}Entity:
        """Convert business model to database entity."""
        return {EntityName}Entity(
            id=model.id,
            name=model.name,
            description=model.description,
            # Remove timezone for database storage (store as UTC without tzinfo)
            created_at=model.created_at.replace(tzinfo=None) if model.created_at else None,
            updated_at=model.updated_at.replace(tzinfo=None) if model.updated_at else None,
        )
```

### Converter with Relationships

```python
from datetime import timezone

from infrastructure.entities.{entity_name}_entity import {EntityName}Entity
from infrastructure.converters.user_converters import UserConverters
from models.{entity_name} import {EntityName}


class {EntityName}Converters:
    @staticmethod
    def convert_entity_to_model(entity: {EntityName}Entity) -> {EntityName}:
        return {EntityName}(
            id=entity.id,
            name=entity.name,
            # Foreign key ID
            user_id=entity.user_id,
            # Convert related entity if loaded (check for None)
            user=UserConverters.convert_entity_to_model(entity.user) if entity.user else None,
            created_at=entity.created_at.replace(tzinfo=timezone.utc) if entity.created_at else None,
            updated_at=entity.updated_at.replace(tzinfo=timezone.utc) if entity.updated_at else None,
        )

    @staticmethod
    def convert_model_to_entity(model: {EntityName}) -> {EntityName}Entity:
        return {EntityName}Entity(
            id=model.id,
            name=model.name,
            # Only set FK ID, NOT the relationship object
            user_id=model.user_id,
            created_at=model.created_at.replace(tzinfo=None) if model.created_at else None,
            updated_at=model.updated_at.replace(tzinfo=None) if model.updated_at else None,
        )
```

### Converter for SimpleBase entity (no timestamps)

```python
from infrastructure.entities.{entity_name}_entity import {EntityName}Entity
from models.{entity_name} import {EntityName}


class {EntityName}Converters:
    @staticmethod
    def convert_entity_to_model(entity: {EntityName}Entity) -> {EntityName}:
        return {EntityName}(
            id=entity.id,
            name=entity.name,
            description=entity.description,
        )

    @staticmethod
    def convert_model_to_entity(model: {EntityName}) -> {EntityName}Entity:
        return {EntityName}Entity(
            id=model.id,
            name=model.name,
            description=model.description,
        )
```

---

## Complete Example

### Entity (created by /db-entity-change)

`src/infrastructure/entities/category_entity.py`:
```python
from sqlalchemy import String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.entities import StatefulBase


class CategoryEntity(StatefulBase):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

### Model (created by /repo-search-or-create)

`src/models/category.py`:
```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class Category(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
```

### Converter (created by /repo-search-or-create)

`src/infrastructure/converters/category_converters.py`:
```python
from datetime import timezone

from infrastructure.entities.category_entity import CategoryEntity
from models.category import Category


class CategoryConverters:
    @staticmethod
    def convert_entity_to_model(entity: CategoryEntity) -> Category:
        return Category(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            is_active=entity.is_active,
            created_at=entity.created_at.replace(tzinfo=timezone.utc) if entity.created_at else None,
            updated_at=entity.updated_at.replace(tzinfo=timezone.utc) if entity.updated_at else None,
        )

    @staticmethod
    def convert_model_to_entity(model: Category) -> CategoryEntity:
        return CategoryEntity(
            id=model.id,
            name=model.name,
            description=model.description,
            is_active=model.is_active,
        )
```

### Repository (created by /repo-search-or-create)

`src/infrastructure/category_repository.py`:
```python
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database import AutoSessionMeta, BaseRepository
from infrastructure.converters.category_converters import CategoryConverters
from infrastructure.entities.category_entity import CategoryEntity
from models.category import Category


class CategoryRepository(BaseRepository, metaclass=AutoSessionMeta):
    def __init__(self) -> None:
        super().__init__()
        self.logger = logging.getLogger(__name__)

    async def aget_category_by_name(
        self,
        session: AsyncSession,
        name: str
    ) -> Category | None:
        stmt = select(CategoryEntity).where(CategoryEntity.name == name)
        result = await session.execute(stmt)
        entity = result.unique().scalar_one_or_none()
        return CategoryConverters.convert_entity_to_model(entity) if entity else None
```

---

## Key Conversion Rules

### Entity → Model (database to business):
- Add `tzinfo=timezone.utc` to datetime fields
- Convert nested entities recursively if loaded
- Check for `None` before converting relationships

### Model → Entity (business to database):
- Remove timezone with `replace(tzinfo=None)` for datetime fields
- Only set FK IDs, never relationship objects
- Don't set `created_at`/`updated_at` on create (handled by database defaults)

### When Model differs from Entity:
Create a model with only the fields needed by the business layer. Not all entity fields need to be in the model. Add computed or derived fields to the model as needed.
