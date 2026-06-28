---
name: repo-search-or-create
description: |
  Search existing repositories for a data-access method, reuse it if present, otherwise create one
  following project patterns. Infrastructure layer of the generated 3-layer backend. Enforces DRY in
  the data layer and creates the domain model + converter when a new repository is needed.

  Use when:
  - Need a database operation (get/create/update/delete/check/count/list) on an entity
  - Want to ensure no duplicate repository methods exist
  - Need to add CRUD functionality to the data layer
  - Called by services needing repository access

  Triggers: "repository method", "CRUD operation", "database access", "get/create/update/delete",
  "find or create repo method", "DRY repository", "data layer operation"
---

# Repository Search or Create

Find an existing repository method or create a new one. Always return the method details so the
caller (a service) can use it immediately.

## Output Format

```
RESULT:
  Repository: {RepositoryClass}
  Method: {method_name}
  File: {file_path}:{line_number}
  Signature: async def {method_name}({params}) -> {ReturnType}
  Usage: await {repository_instance}.{method_name}({caller_params})
  Status: FOUND | CREATED
```

## Workflow

```
1. IDENTIFY the operation needed (entity, operation, params, return type)
2. SEARCH for an existing method
       ├─ FOUND → return details
       └─ NOT FOUND
              3. Repository exists?
                 ├─ YES → entity has required properties?
                 │        ├─ YES → add method
                 │        └─ NO  → invoke /db-entity-change, then add method
                 └─ NO  → entity exists?
                          ├─ YES → create model + converter + repository + method
                          └─ NO  → invoke /db-entity-change, then create model + converter + repository + method
4. Return created method details
```

## Responsibility split

- `/db-entity-change`: entity files + migrations ONLY.
- `/repo-search-or-create`: domain model (`models/`) + converter + repository.

Invoke `/db-entity-change` automatically when the entity is missing or lacks a required property.

## Phase 1 — Identify

Expected method name: `a{operation}_{entity}_{details}`. Examples: `aget_user_by_id`,
`aget_users_by_school_id`, `acreate_thread`, `aupdate_user`, `adelete_message_by_id`,
`adoes_user_exist_by_email`.

## Phase 2 — Search

```
Glob: infrastructure/*_repository.py
Grep: class {Entity}Repository      (path: infrastructure/)
Grep by operation:
  GET    → async def aget_{entity}
  CREATE → async def acreate_{entity}
  UPDATE → async def aupdate_{entity}
  DELETE → async def adelete_{entity}
  CHECK  → async def adoes_{entity}_exist
  COUNT  → async def aget_{entity}_count
  LIST   → async def aget_{entities} / aget_all_{entities}
```

Verify params and return type match the need. Exact match → return `Status: FOUND`. No match →
Phase 3. See [references/search-patterns.md](references/search-patterns.md).

## Phase 3 — Create

**3a. Repository exists → add method.** Confirm the entity has the properties the operation needs
(e.g. `aget_user_by_email` requires an `email` column). If missing → invoke `/db-entity-change`,
then add the method.

**3b. Repository missing → create the stack:**
1. Entity exists? If not → invoke `/db-entity-change`.
2. Create domain model at `models/{entity}.py`.
3. Create converter at `infrastructure/converters/{entity}_converters.py`.
4. Create repository at `infrastructure/{entity}_repository.py` (inherit `BaseRepository`).
5. Add the requested method, return `Status: CREATED`.

See [references/method-templates.md](references/method-templates.md) for per-operation method bodies
and [references/model-converter-templates.md](references/model-converter-templates.md) for model and
converter templates.

### New repository skeleton

```python
import logging
from uuid import UUID

from sqlalchemy import delete, func, select, update

from infrastructure.database import BaseRepository
from infrastructure.converters.{entity}_converters import {Entity}Converters
from infrastructure.entities.{entity}_entity import {Entity}Entity
from models.{entity} import {Entity}


class {Entity}Repository(BaseRepository):
    """Repository for {Entity} CRUD. Public async methods are auto-wrapped with session
    management; access the session via self.session. Callers never pass a session."""

    def __init__(self) -> None:
        super().__init__()
        self.logger = logging.getLogger(__name__)
```

## Architecture Quick Reference

Session management is automatic for repositories inheriting `BaseRepository`:

```python
# Implement using self.session:
async def aget_user_by_id(self, user_id: UUID) -> User | None:
    stmt = select(UserEntity).where(UserEntity.id == user_id)
    result = await self.session.execute(stmt)
    entity = result.unique().scalar_one_or_none()
    return UserConverters.convert_entity_to_model(entity) if entity else None

# Callers (no session):
user = await user_repository.aget_user_by_id(user_id)
```

Rules: inherit `BaseRepository`; call `super().__init__()`; use `self.session`; use `flush()` not
`commit()`; call `.unique()` for queries with joined collections.

> If the generated app uses a simpler persistence layer (no `BaseRepository` auto-wrapping), keep the
> same method naming and converter boundary, and open/manage the session/connection explicitly inside
> each method instead.

## Method Naming

All async methods prefixed with `a`: `aget_`, `acreate_`, `aupdate_`, `adelete_`,
`adoes_*_exist`, `aget_*_count`, `acreate_or_update_`, `abulk_`.

## Error Handling

`BaseRepository` returns safe defaults on error by return type: `T | None`→`None`, `list[T]`→`[]`,
`bool`→`False`, `int`→`0`; required `T` re-raises.
