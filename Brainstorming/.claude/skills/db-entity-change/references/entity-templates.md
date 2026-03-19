# Entity Templates

Complete templates for creating SQLAlchemy ORM entities.

**Note:** This skill creates ONLY entity files. Model and Converter creation is handled by `/repo-search-or-create`.

## Table of Contents

1. [Choosing the Right Base Class](#choosing-the-right-base-class)
2. [Simple Entity (SimpleBase)](#simple-entity-simplebase)
3. [Simple Entity with Static Data](#simple-entity-with-static-data)
4. [Standard Entity (StatefulBase)](#standard-entity-statefulbase)
5. [Entity with JSON Fields](#entity-with-json-fields)
6. [Entity with Relationships](#entity-with-relationships)
7. [Register in __init__.py](#register-in-__init__py)

---

## Choosing the Right Base Class

**ALWAYS determine the base class first before creating an entity.**

| Base Class | Inherits | Use Case | Examples |
|------------|----------|----------|----------|
| `SimpleBase` | `id` only | Lookup/reference tables, static data with predefined values | roles, statuses, quick_actions, categories, priorities |
| `StatefulBase` (or `Base`) | `id`, `created_at`, `updated_at`, `deleted_at` | User-generated data, transactional entities, data that changes over time | users, threads, messages, tasks, preferences |

**Decision Rule:**
- If the entity is a **lookup table** or has **predefined static values** → Use `SimpleBase`
- If the entity needs **audit trail** or represents **user/transactional data** → Use `StatefulBase`

---

## Simple Entity (SimpleBase)

Use for lookup tables or entities that don't need timestamps.

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.entities import SimpleBase


class {EntityName}Entity(SimpleBase):
    """
    {Description - typically a lookup table}
    """

    __tablename__ = "{entity_names}"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<{EntityName}Entity(id={self.id}, name={self.name})>"
```

**Inherited from SimpleBase:**
- `id: Mapped[UUID]` - Primary key only

---

## Simple Entity with Static Data

When a SimpleBase entity has **predefined values** that should be populated at startup (e.g., roles, statuses), follow this complete pattern:

### Entity File

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.entities import SimpleBase


class {EntityName}Entity(SimpleBase):
    """Lookup table for {description}."""

    __tablename__ = "{entity_names}"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<{EntityName}Entity(id={self.id}, name={self.name})>"
```

### Repository Methods (add to repository)

```python
async def astatic_data_exists(self) -> bool:
    """Check if static data exists in database."""
    stmt = select({EntityName}Entity).limit(1)
    result = await self.session.execute(stmt)
    return result.scalar_one_or_none() is not None

async def afill_{entity_names}(self) -> None:
    """Initialize default {entity_names} (idempotent).

    Default values: value1, value2, value3
    """
    default_values = ["value1", "value2", "value3"]

    for value in default_values:
        stmt = select({EntityName}Entity).where({EntityName}Entity.name == value)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        if not existing:
            entity = {EntityName}Entity(name=value)
            self.session.add(entity)
            self.logger.info(f"Created {entity_name}: {value}")

    await self.session.flush()
```

### Register in DatabaseAdminRepository

**CRITICAL:** Add the fill method call to `DatabaseAdminRepository.afill_all_static_data()` in `src/infrastructure/database_admin_repository.py`:

1. Add repository injection to `__init__`:
```python
self.{entity_name}_repository = {entity_name}_repository
```

2. Add fill call in `afill_all_static_data()`:
```python
# Fill {entity_names} if not exists
if not await self.{entity_name}_repository.astatic_data_exists():
    await self.{entity_name}_repository.afill_{entity_names}()
else:
    self.logger.info("{EntityName}s static data already exists, skipping fill")
```

3. Update DI container to inject the repository.

**Existing examples:** See `RoleRepository`, `QuickActionRepository`, `TaskStatusRepository` for complete implementations.

---

## Standard Entity (StatefulBase)

Use for entities requiring full audit trail (created_at, updated_at, deleted_at).

```python
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.entities import StatefulBase

if TYPE_CHECKING:
    from infrastructure.entities.related_entity import RelatedEntity


class {EntityName}Entity(Base):
    """
    {Description of entity purpose}
    """

    __tablename__ = "{entity_names}"  # plural snake_case

    # Required fields
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Optional fields
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Foreign keys
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Relationships
    user: Mapped["UserEntity"] = relationship("UserEntity", back_populates="{entity_names}", lazy="joined")

    def __repr__(self) -> str:
        return f"<{EntityName}Entity(id={self.id}, name={self.name})>"
```

**Inherited from Base (StatefulBase):**
- `id: Mapped[UUID]` - Primary key, auto-generated UUID4
- `created_at: Mapped[datetime]` - Auto-set on insert
- `updated_at: Mapped[datetime | None]` - Auto-set on update
- `deleted_at: Mapped[datetime | None]` - For soft deletes

---

## Entity with JSON Fields

For PostgreSQL/SQLite compatibility, always use the variant pattern.

```python
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.entities import StatefulBase


class {EntityName}Entity(Base):
    __tablename__ = "{entity_names}"

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # JSON field - required
    config: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False
    )

    # JSON field - optional
    metadata_info: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True
    )

    # JSON field with default
    settings: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict  # Empty dict as default
    )
```

**Key points:**
- Type hint: `Mapped[dict]` or `Mapped[dict | None]`
- Always use `.with_variant(JSONB, "postgresql")`
- PostgreSQL uses JSONB (indexed, efficient)
- SQLite uses JSON (text-based)

---

## Entity with Relationships

### One-to-Many Relationship

```python
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.entities import StatefulBase

if TYPE_CHECKING:
    from infrastructure.entities.child_entity import ChildEntity


class ParentEntity(StatefulBase):
    __tablename__ = "parents"

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # One-to-many: parent has many children
    children: Mapped[list["ChildEntity"]] = relationship(
        "ChildEntity",
        back_populates="parent",
        cascade="all, delete-orphan",
        lazy="noload",  # Load explicitly when needed
        order_by="ChildEntity.created_at.asc()"
    )
```

```python
# child_entity.py
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.entities import StatefulBase

if TYPE_CHECKING:
    from infrastructure.entities.parent_entity import ParentEntity


class ChildEntity(StatefulBase):
    __tablename__ = "children"

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Foreign key to parent
    parent_id: Mapped[UUID] = mapped_column(ForeignKey("parents.id"), nullable=False)

    # Many-to-one: child belongs to parent
    parent: Mapped["ParentEntity"] = relationship("ParentEntity", back_populates="children", lazy="joined")
```

### Lazy Loading Strategies

| Strategy | Use Case | Behavior |
|----------|----------|----------|
| `lazy="joined"` | Small related data | Loaded with parent query (JOIN) |
| `lazy="noload"` | Large collections | Never auto-loaded |
| `lazy="select"` | Default | Loaded on first access (new query) |

---

## Register in __init__.py

Add import to `src/infrastructure/entities/__init__.py`:

```python
from infrastructure.entities.{entity_name}_entity import {EntityName}Entity

__all__ = [
    # ... existing exports
    "{EntityName}Entity",
]
```

---

## Complete Example: New "Category" Entity

**Note:** This example shows ONLY the entity file. Model and Converter are created by `/repo-search-or-create`.

`src/infrastructure/entities/category_entity.py`:

```python
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.entities import StatefulBase

if TYPE_CHECKING:
    from infrastructure.entities.content_entity import ContentEntity


class CategoryEntity(StatefulBase):
    """Category for organizing content."""

    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # One-to-many relationship
    contents: Mapped[list["ContentEntity"]] = relationship(
        "ContentEntity",
        back_populates="category",
        lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<CategoryEntity(id={self.id}, name={self.name})>"
```

Then register in `__init__.py`:

```python
from infrastructure.entities.category_entity import CategoryEntity
```
