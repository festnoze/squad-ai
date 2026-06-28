# Model & Converter Templates

Domain models (`models/`) are plain Pydantic. Converters (`infrastructure/converters/`) translate
between the ORM entity and the domain model and handle datetime timezone normalization.

## Contents
1. [Model template](#model-template)
2. [Converter template](#converter-template)
3. [Conversion rules](#conversion-rules)

---

## Model template

**Location:** `models/{entity_name}.py`

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class {EntityName}(BaseModel):
    """{Description of the business model}."""

    id: UUID
    name: str
    description: str | None = None

    # JSON fields (if any)
    config: dict = Field(default_factory=dict)

    # FK as ID only (never embed the related object on write paths)
    user_id: UUID | None = None

    # Timestamps from StatefulBase entities
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
```

For a `SimpleBase` lookup model, drop the timestamp fields.

---

## Converter template

**Location:** `infrastructure/converters/{entity_name}_converters.py`

```python
from datetime import timezone

from infrastructure.entities.{entity_name}_entity import {EntityName}Entity
from models.{entity_name} import {EntityName}


class {EntityName}Converters:
    """Convert between {EntityName}Entity (DB) and {EntityName} (domain model)."""

    @staticmethod
    def convert_entity_to_model(entity: {EntityName}Entity) -> {EntityName}:
        return {EntityName}(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            user_id=entity.user_id,
            # entity stores UTC without tzinfo → add it for the domain model
            created_at=entity.created_at.replace(tzinfo=timezone.utc) if entity.created_at else None,
            updated_at=entity.updated_at.replace(tzinfo=timezone.utc) if entity.updated_at else None,
        )

    @staticmethod
    def convert_model_to_entity(model: {EntityName}) -> {EntityName}Entity:
        return {EntityName}Entity(
            id=model.id,
            name=model.name,
            description=model.description,
            user_id=model.user_id,  # FK id only, never the relationship object
        )
```

For a converter that includes a loaded relationship:

```python
from infrastructure.converters.user_converters import UserConverters

user=UserConverters.convert_entity_to_model(entity.user) if entity.user else None,
```

---

## Conversion rules

**Entity → Model:** add `tzinfo=timezone.utc` to datetimes; convert nested entities only if loaded
(check for `None`).

**Model → Entity:** set FK IDs only, never relationship objects; don't set `created_at`/`updated_at`
on create (DB defaults handle them). If you must persist a model-supplied timestamp, strip tz with
`.replace(tzinfo=None)`.

**Divergence is fine:** the domain model need not mirror every entity column — include only the
fields the business layer uses, plus any computed/derived fields.
