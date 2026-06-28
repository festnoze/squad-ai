# Entity Templates

SQLAlchemy ORM entity templates (infrastructure layer). This skill creates ONLY entity files;
models and converters are created by `/repo-search-or-create`.

## Contents
1. [Choosing a base class](#choosing-a-base-class)
2. [Simple entity (SimpleBase)](#simple-entity-simplebase)
3. [Standard entity (StatefulBase)](#standard-entity-statefulbase)
4. [Entity with JSON fields](#entity-with-json-fields)
5. [Entity with relationships](#entity-with-relationships)
6. [Static data fill pattern](#static-data)
7. [Register the entity](#register-the-entity)

---

## Choosing a base class

| Base class | Inherits | Use for |
|------------|----------|---------|
| `SimpleBase` | `id` only | Lookup/reference tables, static data with predefined values |
| `StatefulBase` | `id`, `created_at`, `updated_at`, `deleted_at` | User/transactional data, anything needing an audit trail |

> The generated app may use a simpler persistence layer. Treat these as the canonical pattern; if
> the app has only one base class, use it and keep the field conventions.

---

## Simple entity (SimpleBase)

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.entities import SimpleBase


class {EntityName}Entity(SimpleBase):
    """{Description — typically a lookup table}."""

    __tablename__ = "{entity_names}"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<{EntityName}Entity(id={self.id}, name={self.name})>"
```

---

## Standard entity (StatefulBase)

```python
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.entities import StatefulBase

if TYPE_CHECKING:
    from infrastructure.entities.user_entity import UserEntity


class {EntityName}Entity(StatefulBase):
    """{Description of entity purpose}."""

    __tablename__ = "{entity_names}"  # plural snake_case

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    user: Mapped["UserEntity"] = relationship("UserEntity", back_populates="{entity_names}", lazy="joined")

    def __repr__(self) -> str:
        return f"<{EntityName}Entity(id={self.id}, name={self.name})>"
```

Inherited: `id` (UUID4), `created_at`, `updated_at | None`, `deleted_at | None` (soft delete).

---

## Entity with JSON fields

Always use the variant pattern for Postgres/SQLite compatibility.

```python
from sqlalchemy import JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.entities import StatefulBase


class {EntityName}Entity(StatefulBase):
    __tablename__ = "{entity_names}"

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    config: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    metadata_info: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    settings: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
```

---

## Entity with relationships

```python
# parent_entity.py
class ParentEntity(StatefulBase):
    __tablename__ = "parents"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    children: Mapped[list["ChildEntity"]] = relationship(
        "ChildEntity", back_populates="parent",
        cascade="all, delete-orphan", lazy="noload",
        order_by="ChildEntity.created_at.asc()",
    )

# child_entity.py
class ChildEntity(StatefulBase):
    __tablename__ = "children"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[UUID] = mapped_column(ForeignKey("parents.id"), nullable=False)
    parent: Mapped["ParentEntity"] = relationship("ParentEntity", back_populates="children", lazy="joined")
```

| Lazy strategy | Use case |
|---------------|----------|
| `lazy="joined"` | Small related data, loaded via JOIN |
| `lazy="noload"` | Large collections, loaded explicitly |
| `lazy="select"` | Default, loaded on first access |

---

## Static data

For a `SimpleBase` lookup table with predefined values, add an idempotent fill method to the
repository and call it once at startup where the app seeds reference data.

```python
async def astatic_data_exists(self) -> bool:
    """Check if static data already exists."""
    stmt = select({EntityName}Entity).limit(1)
    result = await self.session.execute(stmt)
    return result.scalar_one_or_none() is not None

async def afill_{entity_names}(self) -> None:
    """Initialize default {entity_names} (idempotent)."""
    default_values = ["value1", "value2", "value3"]
    for value in default_values:
        stmt = select({EntityName}Entity).where({EntityName}Entity.name == value)
        result = await self.session.execute(stmt)
        if result.scalar_one_or_none() is None:
            self.session.add({EntityName}Entity(name=value))
            self.logger.info(f"Created {entity_name}: {value}")
    await self.session.flush()
```

At startup (where the app seeds reference data):

```python
if not await {entity_name}_repository.astatic_data_exists():
    await {entity_name}_repository.afill_{entity_names}()
```

---

## Register the entity

Import the entity where the app collects ORM metadata (commonly
`infrastructure/entities/__init__.py`) so its table is created at startup:

```python
from infrastructure.entities.{entity_name}_entity import {EntityName}Entity

__all__ = [..., "{EntityName}Entity"]
```
