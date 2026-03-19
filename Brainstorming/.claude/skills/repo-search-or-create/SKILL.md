---
name: repo-search-or-create
description: |
  Search existing repositories for CRUD methods, create if not found, return method details.
  Ensures DRY principle by reusing existing methods or creating new ones following project patterns.

  Use when:
  - Need a database operation (get/create/update/delete) on an entity
  - Want to ensure no duplicate repository methods exist
  - Need to add CRUD functionality to the data layer
  - Called by services needing repository access

  Triggers: "repository method", "CRUD operation", "database access", "get/create/update/delete",
  "find or create repo method", "DRY repository", "data layer operation"
---

# Repository Search or Create

Find existing repository methods or create new ones. Always returns method details for immediate use.

## Output Format

Regardless of found or created, always return:

```
RESULT:
  Repository: {RepositoryClass}
  Method: {method_name}
  File: {file_path}:{line_number}
  Signature: async def {method_name}({params}) -> {ReturnType}
  Usage: await {repository_instance}.{method_name}({caller_params})
  Status: FOUND | CREATED
```

**Note:** `{caller_params}` excludes `session` - it's auto-injected by the metaclass.

---

## Workflow

```
1. IDENTIFY what operation is needed
       │
       ▼
2. SEARCH for existing method
       │
       ├─ FOUND → Return method details
       │
       └─ NOT FOUND
              │
              ▼
       3. CHECK if repository exists
              │
              ├─ YES → Check if entity has required properties
              │        │
              │        ├─ YES → Add method to existing repository
              │        │
              │        └─ NO → Invoke /db-entity-change to add property
              │                then add method
              │
              └─ NO → Check if entity exists
                     │
                     ├─ YES → Create new repository + method
                     │
                     └─ NO → Invoke /db-entity-change to create entity
                             then create repository + method
              │
              ▼
       4. Return created method details
```

**Important:** When entity or property is missing, invoke `/db-entity-change` skill automatically before continuing.

---

## Integration with /db-entity-change

**Responsibility split:**
- `/db-entity-change`: Entity files + migrations ONLY
- `/repo-search-or-create`: Repository + Model + Converters

This skill automatically invokes `/db-entity-change` when:

| Situation | Action |
|-----------|--------|
| Entity doesn't exist | Invoke `/db-entity-change` to create entity, then create model + converter + repository |
| Entity missing required property | Invoke `/db-entity-change` to add property + migration, then update model/converter if needed |

This skill directly creates (without invoking db-entity-change):

| Situation | Action |
|-----------|--------|
| Model doesn't exist | Create model in `src/models/{entity}.py` |
| Converter doesn't exist | Create converter in `src/infrastructure/converters/{entity}_converters.py` |
| Repository doesn't exist | Create repository in `src/infrastructure/{entity}_repository.py` |

**Example flow - New entity:**

```
Need: aget_category_by_name(name: str) -> Category | None

1. Search for CategoryRepository → NOT FOUND
2. Check CategoryEntity exists → NOT FOUND
3. Invoke /db-entity-change:
   - Create CategoryEntity in entities/category_entity.py
   - Register in entities/__init__.py
4. Create Model: src/models/category.py
5. Create Converter: src/infrastructure/converters/category_converters.py
6. Create Repository: src/infrastructure/category_repository.py
7. Add aget_category_by_name method
8. Return RESULT with Status: CREATED
```

**Example flow - Missing property:**

```
Need: aget_user_by_email(email: str) -> User | None

1. Search UserRepository for aget_user_by_email → NOT FOUND
2. Check UserEntity for 'email' property → NOT FOUND
3. Invoke /db-entity-change:
   - Add 'email: Mapped[str]' to UserEntity
   - Create migration: 20260129-add_email_to_users.sql
4. Update User model if 'email' not present
5. Update UserConverters if needed
6. Add aget_user_by_email method to UserRepository
7. Return RESULT with Status: CREATED
```

---

## Phase 1: Identify Operation

Determine the required operation:

| Question | Examples |
|----------|----------|
| **Entity** | User, Thread, Message, School, Content |
| **Operation** | get, create, update, delete, check, count, list |
| **Parameters** | by_id, by_name, by_user_id, batch, filtered |
| **Return type** | Single (`Model \| None`), List (`list[Model]`), Bool, Int |

**Expected method name pattern:** `a{operation}_{entity}_{details}`

Examples:
- `aget_user_by_id` - Get single user by ID
- `aget_users_by_school_id` - Get list of users by school
- `acreate_thread` - Create a thread
- `aupdate_user` - Update user fields
- `adelete_message_by_id` - Delete a message
- `adoes_user_exist_by_lms_id` - Check if user exists

---

## Phase 2: Search

### Step 1: Find repository file

```
Glob: src/infrastructure/*_repository.py
```

### Step 2: Search for entity repository

```
Grep: class {Entity}Repository
Path: src/infrastructure/
```

### Step 3: Search for matching method

```
Grep patterns by operation:
- GET:    async def aget_{entity}
- CREATE: async def acreate_{entity}
- UPDATE: async def aupdate_{entity}
- DELETE: async def adelete_{entity}
- CHECK:  async def adoes_{entity}_exist
- COUNT:  async def aget_{entity}_count
- LIST:   async def aget_{entities} OR aget_all_{entities}
```

### Step 4: Verify match

If method found, verify:
- Parameters match needed inputs
- Return type matches expected output
- No conflicting business logic

**If exact match found** → Return RESULT with `Status: FOUND`

**If no match** → Continue to Phase 3

See [references/search-patterns.md](references/search-patterns.md) for complete patterns.

---

## Phase 3: Create

### 3a. Repository exists → Add method

1. **Check if entity has required properties** for the operation
   - Example: `aget_user_by_email` requires `email` property on UserEntity
   - If property missing → **Invoke `/db-entity-change`** to add the property
2. Open existing repository file
3. Add new method following project patterns
4. Return RESULT with `Status: CREATED`

### 3b. Repository doesn't exist → Create full stack

**Step 1: Check entity exists:**
```
Glob: src/infrastructure/entities/{entity}_entity.py
```
- If entity missing → **Invoke `/db-entity-change`** to create the entity

**Step 2: Create Model (if missing):**
```
Location: src/models/{entity}.py
```
- Create Pydantic model matching entity fields
- See [references/model-converter-templates.md](references/model-converter-templates.md)

**Step 3: Create Converter (if missing):**
```
Location: src/infrastructure/converters/{entity}_converters.py
```
- Create `{Entity}Converters` class with `convert_entity_to_model` and `convert_model_to_entity`
- Handle timezone conversion for datetime fields
- See [references/model-converter-templates.md](references/model-converter-templates.md)

**Step 4: Create Repository:**
```
Location: src/infrastructure/{entity}_repository.py
```
- Inherit from `BaseRepository` with `metaclass=AutoSessionMeta`
- Add the requested method

### New Repository Structure

```python
import logging
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database import AutoSessionMeta, BaseRepository
from infrastructure.converters.{entity}_converters import {Entity}Converters
from infrastructure.entities.{entity}_entity import {Entity}Entity
from models.{entity} import {Entity}


class {Entity}Repository(BaseRepository, metaclass=AutoSessionMeta):
    """
    Repository for {Entity} CRUD operations.

    All public async methods with 'session: AsyncSession' are auto-wrapped.
    Callers do NOT pass the session parameter.
    """

    def __init__(self) -> None:
        super().__init__()
        self.logger = logging.getLogger(__name__)

    # Add methods here...
```

See [references/method-templates.md](references/method-templates.md) for operation templates.
See [references/repository-architecture.md](references/repository-architecture.md) for session management details.

---

## Architecture Quick Reference

**Session management is automatic:**

```python
# You implement (with session):
async def aget_user_by_id(self, session: AsyncSession, user_id: UUID) -> User | None:
    stmt = select(UserEntity).where(UserEntity.id == user_id)
    result = await session.execute(stmt)
    entity = result.unique().scalar_one_or_none()
    return UserConverters.convert_entity_to_model(entity) if entity else None

# Callers use (without session):
user = await user_repository.aget_user_by_id(user_id)
```

**Critical requirements:**
- Inherit from `BaseRepository`
- Use `metaclass=AutoSessionMeta`
- Call `super().__init__()` in constructor
- Use `flush()` not `commit()` after writes
- Use `.unique()` for queries with joined collection relationships

---

## Repository Locations

| Entity | Repository | File |
|--------|------------|------|
| User | UserRepository | `user_repository.py` |
| UserPreference | UserRepository | `user_repository.py` |
| Thread | ThreadRepository | `thread_repository.py` |
| Message | ThreadRepository | `thread_repository.py` |
| Role | RoleRepository | `role_repository.py` |
| School | SchoolRepository | `school_repository.py` |
| Content | ContentRepository | `content_repository.py` |
| QuickAction | QuickActionRepository | `quick_action_repository.py` |

---

## Method Naming Conventions

All async methods prefixed with `a`:

| Prefix | Operation | Example |
|--------|-----------|---------|
| `aget_` | Retrieve | `aget_user_by_id`, `aget_all_roles` |
| `acreate_` | Create | `acreate_user`, `acreate_thread` |
| `aupdate_` | Update | `aupdate_user`, `aupdate_school` |
| `adelete_` | Delete | `adelete_message`, `aclear_thread_messages` |
| `adoes_*_exist` | Check | `adoes_user_exist_by_id` |
| `aget_*_count` | Count | `aget_thread_messages_count` |
| `acreate_or_update_` | Upsert | `acreate_or_update_user_preference` |
| `abulk_` | Batch | `abulk_create_messages` |

---

## Error Handling

AutoSessionMeta returns safe defaults based on return type:

| Return Type | On Error |
|-------------|----------|
| `T \| None` | `None` |
| `list[T]` | `[]` |
| `bool` | `False` |
| `int` | `0` |
| `T` (required) | Re-raises |
