# Repository Method Templates

Per-operation method bodies. All use `self.session` provided by `BaseRepository` auto-wrapping. All
async methods are prefixed with `a`.

## Imports

```python
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update

from infrastructure.database import BaseRepository
from infrastructure.converters.{entity}_converters import {Entity}Converters
from infrastructure.entities.{entity}_entity import {Entity}Entity
from models.{entity} import {Model}
```

## GET

```python
async def aget_{entity}_by_id(self, {entity}_id: UUID) -> {Model} | None:
    stmt = select({Entity}Entity).where({Entity}Entity.id == {entity}_id)
    result = await self.session.execute(stmt)
    entity = result.unique().scalar_one_or_none()
    return {Entity}Converters.convert_entity_to_model(entity) if entity else None

async def aget_{entity}_by_{field}(self, {field}: str) -> {Model} | None:
    stmt = select({Entity}Entity).where({Entity}Entity.{field} == {field})
    result = await self.session.execute(stmt)
    entity = result.unique().scalar_one_or_none()
    return {Entity}Converters.convert_entity_to_model(entity) if entity else None

async def aget_{entities}_by_{filter}(self, {filter_param}: Any) -> list[{Model}]:
    stmt = select({Entity}Entity).where({Entity}Entity.{filter_field} == {filter_param})
    result = await self.session.execute(stmt)
    entities = result.unique().scalars().all()
    return [{Entity}Converters.convert_entity_to_model(e) for e in entities]

async def aget_all_{entities}(self) -> list[{Model}]:
    stmt = select({Entity}Entity).order_by({Entity}Entity.id)
    result = await self.session.execute(stmt)
    entities = result.unique().scalars().all()
    return [{Entity}Converters.convert_entity_to_model(e) for e in entities]

async def aget_{entities}_batch(self, limit: int, offset: int) -> list[{Model}]:
    stmt = select({Entity}Entity).order_by({Entity}Entity.created_at.desc()).limit(limit).offset(offset)
    result = await self.session.execute(stmt)
    return [{Entity}Converters.convert_entity_to_model(e) for e in result.scalars().all()]
```

## CREATE

```python
async def acreate_{entity}(self, {entity}: {Model}) -> {Model}:
    entity_obj = {Entity}Converters.convert_model_to_entity({entity})
    self.session.add(entity_obj)
    await self.session.flush()
    await self.session.refresh(entity_obj)
    return {Entity}Converters.convert_entity_to_model(entity_obj)

async def abulk_create_{entities}(self, {entities}: list[{Model}]) -> None:
    self.session.add_all([{Entity}Converters.convert_model_to_entity(e) for e in {entities}])
    await self.session.flush()
```

## UPDATE

```python
async def aupdate_{entity}(self, {entity}: {Model}) -> {Model} | None:
    stmt = (
        update({Entity}Entity)
        .where({Entity}Entity.id == {entity}.id)
        .values(field1={entity}.field1, field2={entity}.field2, updated_at=datetime.now())
    )
    await self.session.execute(stmt)
    await self.session.flush()
    updated = await self._aget_{entity}_entity_query({entity}.id)
    return {Entity}Converters.convert_entity_to_model(updated) if updated else None
```

## UPSERT

```python
async def acreate_or_update_{entity}(self, {entity}: {Model}) -> {Model}:
    existing = await self._aget_{entity}_by_{field}_query({entity}.{field})
    if existing:
        stmt = (
            update({Entity}Entity).where({Entity}Entity.id == existing.id)
            .values(field1={entity}.field1, updated_at=datetime.now())
        )
        await self.session.execute(stmt)
        await self.session.flush()
        updated = await self._aget_{entity}_entity_query(existing.id)
        return {Entity}Converters.convert_entity_to_model(updated)
    entity_obj = {Entity}Converters.convert_model_to_entity({entity})
    self.session.add(entity_obj)
    await self.session.flush()
    await self.session.refresh(entity_obj)
    return {Entity}Converters.convert_entity_to_model(entity_obj)
```

## DELETE

```python
async def adelete_{entity}(self, {entity}_id: UUID) -> bool:  # hard delete
    result = await self.session.execute(delete({Entity}Entity).where({Entity}Entity.id == {entity}_id))
    await self.session.flush()
    return result.rowcount > 0

async def asoft_delete_{entity}(self, {entity}_id: UUID) -> None:  # soft delete
    stmt = update({Entity}Entity).where({Entity}Entity.id == {entity}_id).values(deleted_at=datetime.now())
    await self.session.execute(stmt)
    await self.session.flush()
```

## CHECK / COUNT

```python
async def adoes_{entity}_exist_by_{field}(self, {field}: str) -> bool:
    stmt = select({Entity}Entity.id).where({Entity}Entity.{field} == {field})
    result = await self.session.execute(stmt)
    return result.scalar_one_or_none() is not None

async def aget_{entity}_count(self) -> int:
    result = await self.session.execute(select(func.count()).select_from({Entity}Entity))
    return result.scalar() or 0
```

## Private helpers (return entities, not models)

```python
async def _aget_{entity}_entity_query(self, {entity}_id: UUID) -> {Entity}Entity | None:
    stmt = select({Entity}Entity).where({Entity}Entity.id == {entity}_id)
    result = await self.session.execute(stmt)
    return result.unique().scalar_one_or_none()

async def _aget_{entity}_by_{field}_query(self, {field}: str) -> {Entity}Entity | None:
    stmt = select({Entity}Entity).where({Entity}Entity.{field} == {field})
    result = await self.session.execute(stmt)
    return result.unique().scalar_one_or_none()
```
