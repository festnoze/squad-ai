# Repository Method Templates

Complete templates for each operation type.

## GET Operations

### Get by ID

```python
async def aget_{entity}_by_id(
    self,
    session: AsyncSession,
    {entity}_id: UUID
) -> {Model} | None:
    stmt = select({Entity}Entity).where({Entity}Entity.id == {entity}_id)
    result = await session.execute(stmt)
    entity = result.unique().scalar_one_or_none()
    return {Entity}Converters.convert_entity_to_model(entity) if entity else None
```

### Get by Field

```python
async def aget_{entity}_by_{field}(
    self,
    session: AsyncSession,
    {field}: str
) -> {Model} | None:
    stmt = select({Entity}Entity).where({Entity}Entity.{field} == {field})
    result = await session.execute(stmt)
    entity = result.unique().scalar_one_or_none()
    return {Entity}Converters.convert_entity_to_model(entity) if entity else None
```

### Get List with Filters

```python
async def aget_{entities}_by_{filter}(
    self,
    session: AsyncSession,
    {filter_param}: {Type}
) -> list[{Model}]:
    stmt = select({Entity}Entity).where({Entity}Entity.{filter_field} == {filter_param})
    result = await session.execute(stmt)
    entities = result.unique().scalars().all()
    return [{Entity}Converters.convert_entity_to_model(e) for e in entities]
```

### Get with Pagination

```python
async def aget_{entities}_batch(
    self,
    session: AsyncSession,
    limit: int,
    offset: int
) -> list[{Model}]:
    stmt = (
        select({Entity}Entity)
        .order_by({Entity}Entity.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    entities = result.scalars().all()
    return [{Entity}Converters.convert_entity_to_model(e) for e in entities]
```

### Get All

```python
async def aget_all_{entities}(
    self,
    session: AsyncSession
) -> list[{Model}]:
    stmt = select({Entity}Entity).order_by({Entity}Entity.id)
    result = await session.execute(stmt)
    entities = result.unique().scalars().all()
    return [{Entity}Converters.convert_entity_to_model(e) for e in entities]
```

## CREATE Operations

### Create Single

```python
async def acreate_{entity}(
    self,
    session: AsyncSession,
    {entity}: {Model}
) -> {Model}:
    entity_obj = {Entity}Converters.convert_model_to_entity({entity})
    session.add(entity_obj)
    await session.flush()
    await session.refresh(entity_obj)
    return {Entity}Converters.convert_entity_to_model(entity_obj)
```

### Create with Validation

```python
async def acreate_{entity}(
    self,
    session: AsyncSession,
    {entity}: {Model}
) -> {Model}:
    # Check for conflicts
    existing = await self._aget_{entity}_by_unique_field_query(
        session, {entity}.unique_field
    )
    if existing:
        raise ValueError(f"{Entity} already exists with this unique_field")

    entity_obj = {Entity}Converters.convert_model_to_entity({entity})
    session.add(entity_obj)
    await session.flush()
    await session.refresh(entity_obj)
    return {Entity}Converters.convert_entity_to_model(entity_obj)
```

### Bulk Create

```python
async def abulk_create_{entities}(
    self,
    session: AsyncSession,
    {entities}: list[{Model}]
) -> None:
    entity_objs = [
        {Entity}Converters.convert_model_to_entity(e) for e in {entities}
    ]
    session.add_all(entity_objs)
    await session.flush()
```

## UPDATE Operations

### Update by ID

```python
async def aupdate_{entity}(
    self,
    session: AsyncSession,
    {entity}_id: UUID,
    **kwargs: Any
) -> {Model} | None:
    stmt = (
        update({Entity}Entity)
        .where({Entity}Entity.id == {entity}_id)
        .values(**kwargs)
    )
    await session.execute(stmt)
    await session.flush()

    # Re-fetch updated entity
    updated = await self._aget_{entity}_entity_query(session, {entity}_id)
    return {Entity}Converters.convert_entity_to_model(updated) if updated else None
```

### Update with Model

```python
async def aupdate_{entity}(
    self,
    session: AsyncSession,
    {entity}: {Model}
) -> {Model}:
    stmt = (
        update({Entity}Entity)
        .where({Entity}Entity.id == {entity}.id)
        .values(
            field1={entity}.field1,
            field2={entity}.field2,
            updated_at=datetime.now()
        )
    )
    await session.execute(stmt)
    await session.flush()

    updated = await self._aget_{entity}_entity_query(session, {entity}.id)
    return {Entity}Converters.convert_entity_to_model(updated)
```

## UPSERT Operations

### Create or Update

```python
async def acreate_or_update_{entity}(
    self,
    session: AsyncSession,
    {entity}: {Model}
) -> {Model}:
    existing = await self._aget_{entity}_by_unique_field_query(
        session, {entity}.unique_field
    )

    if existing:
        stmt = (
            update({Entity}Entity)
            .where({Entity}Entity.id == existing.id)
            .values(
                field1={entity}.field1,
                field2={entity}.field2,
                updated_at=datetime.now()
            )
        )
        await session.execute(stmt)
        await session.flush()
        updated = await self._aget_{entity}_entity_query(session, existing.id)
        return {Entity}Converters.convert_entity_to_model(updated)
    else:
        entity_obj = {Entity}Converters.convert_model_to_entity({entity})
        session.add(entity_obj)
        await session.flush()
        await session.refresh(entity_obj)
        return {Entity}Converters.convert_entity_to_model(entity_obj)
```

### Create or Get

```python
async def acreate_or_get_{entity}_by_{field}(
    self,
    session: AsyncSession,
    {field}: str
) -> {Model}:
    existing = await self._aget_{entity}_by_{field}_query(session, {field})
    if existing:
        return {Entity}Converters.convert_entity_to_model(existing)

    entity_obj = {Entity}Entity({field}={field})
    session.add(entity_obj)
    await session.flush()
    await session.refresh(entity_obj)
    return {Entity}Converters.convert_entity_to_model(entity_obj)
```

## DELETE Operations

### Hard Delete

```python
async def adelete_{entity}(
    self,
    session: AsyncSession,
    {entity}_id: UUID
) -> bool:
    stmt = delete({Entity}Entity).where({Entity}Entity.id == {entity}_id)
    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount > 0
```

### Soft Delete

```python
async def adelete_{entity}(
    self,
    session: AsyncSession,
    {entity}_id: UUID
) -> None:
    stmt = (
        update({Entity}Entity)
        .where({Entity}Entity.id == {entity}_id)
        .values(deleted_at=datetime.now())
    )
    await session.execute(stmt)
    await session.flush()
```

### Bulk Delete

```python
async def adelete_{entities}_by_{field}(
    self,
    session: AsyncSession,
    {field}: {Type}
) -> int:
    stmt = delete({Entity}Entity).where({Entity}Entity.{field} == {field})
    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount
```

## CHECK/EXISTS Operations

### Check Exists

```python
async def adoes_{entity}_exist(
    self,
    session: AsyncSession,
    {entity}_id: UUID
) -> bool:
    stmt = select({Entity}Entity.id).where({Entity}Entity.id == {entity}_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
```

### Check Exists by Field

```python
async def adoes_{entity}_exist_by_{field}(
    self,
    session: AsyncSession,
    {field}: str
) -> bool:
    stmt = select({Entity}Entity.id).where({Entity}Entity.{field} == {field})
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
```

## COUNT Operations

### Count All

```python
async def aget_{entity}_count(
    self,
    session: AsyncSession
) -> int:
    stmt = select(func.count()).select_from({Entity}Entity)
    result = await session.execute(stmt)
    return result.scalar() or 0
```

### Count with Filter

```python
async def aget_{entity}_count_by_{field}(
    self,
    session: AsyncSession,
    {field}: {Type}
) -> int:
    stmt = (
        select(func.count())
        .select_from({Entity}Entity)
        .where({Entity}Entity.{field} == {field})
    )
    result = await session.execute(stmt)
    return result.scalar() or 0
```

## PRIVATE HELPER PATTERNS

### Entity Query Helper

```python
async def _aget_{entity}_entity_query(
    self,
    session: AsyncSession,
    {entity}_id: UUID
) -> {Entity}Entity | None:
    stmt = select({Entity}Entity).where({Entity}Entity.id == {entity}_id)
    result = await session.execute(stmt)
    return result.unique().scalar_one_or_none()
```

### Field Query Helper

```python
async def _aget_{entity}_by_{field}_query(
    self,
    session: AsyncSession,
    {field}: str
) -> {Entity}Entity | None:
    stmt = select({Entity}Entity).where({Entity}Entity.{field} == {field})
    result = await session.execute(stmt)
    return result.unique().scalar_one_or_none()
```

## IMPORTS TEMPLATE

```python
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database import AutoSessionMeta, BaseRepository
from infrastructure.converters.{entity}_converters import {Entity}Converters
from infrastructure.entities.{entity}_entity import {Entity}Entity
from models.{entity} import {Model}
```
