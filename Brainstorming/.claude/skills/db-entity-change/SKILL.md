---
name: db-entity-change
description: |
  Create new database entities or modify existing ones with automatic migration generation.
  Handles SQLAlchemy ORM entity definitions with PostgreSQL/SQLite JSON compatibility.

  Use when:
  - Creating a new database table/entity
  - Adding a new column/property to an existing entity
  - Modifying an existing column type or constraints
  - Called by /repo-search-or-create when entity changes are needed

  Triggers: "create entity", "add column", "modify entity", "new table",
  "database schema change", "add property to entity", "alter table"
---

# Database Entity Change Skill

Create or modify SQLAlchemy ORM entities with automatic migration generation when needed.

**Scope:** This skill handles ONLY entity files and migrations. Model and Converter creation is handled by `/repo-search-or-create` when creating a new repository.

## Decision Tree

```
Is this a NEW entity or MODIFICATION?
│
├─ NEW ENTITY
│  └─ 1. Determine base class (SimpleBase vs StatefulBase)
│  └─ 2. Create entity file (no migration needed)
│  └─ 3. Register in __init__.py
│  └─ 4. If simple data with predefined values → add static data pattern
│  └─ Table auto-created at startup via CREATE_MISSING_TABLES
│  └─ Model + Converter created by /repo-search-or-create
│
└─ MODIFICATION to existing entity
   └─ 1. Update entity file
   └─ 2. Create migration SQL file
   └─ Model/Converter updates handled by /repo-search-or-create if needed
```

## Workflow: New Entity

### Step 1: Determine Base Class

| Use Case | Base Class | Provides | When to Use |
|----------|-----------|----------|-------------|
| Simple lookup/reference data | `SimpleBase` | id only | Lookup tables (roles, statuses, categories), static data with predefined values |
| Full audit trail needed | `StatefulBase` (or `Base`) | id, created_at, updated_at, deleted_at | User-generated content, transactional data, entities that change over time |

**Rule of thumb:**
- **SimpleBase** → Simple data entities like lookup tables, enums in DB, static reference data
- **StatefulBase** → Everything else (user data, threads, messages, etc.)

### Step 2: Create Entity File

Location: `src/infrastructure/entities/{entity_name}_entity.py`

See [references/entity-templates.md](references/entity-templates.md) for complete templates.

**Naming conventions:**
- File: `{entity_name}_entity.py` (snake_case)
- Class: `{EntityName}Entity` (PascalCase)
- Table: `{entity_names}` (plural snake_case)

### Step 3: Register in `__init__.py`

Add import to `src/infrastructure/entities/__init__.py`

**Note:** Model and Converter will be created by `/repo-search-or-create` when creating the repository.

### Step 4: Static Data Pattern (for SimpleBase entities with predefined values)

If the entity represents simple data with predefined values that should be pre-populated in the database (e.g., roles, statuses, quick actions), implement the **static data fill pattern**:

#### 4.1 Add to Repository

Add these methods to the repository (see `/repo-search-or-create` for full repository creation):

```python
async def astatic_data_exists(self) -> bool:
    """Check if static data exists in database."""
    stmt = select({EntityName}Entity).limit(1)
    result = await self.session.execute(stmt)
    return result.scalar_one_or_none() is not None

async def afill_{entity_names}(self) -> None:
    """Initialize default {entity_names} (idempotent).

    Default values: {list predefined values}
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

#### 4.2 Register in DatabaseAdminRepository

**IMPORTANT:** Add the repository to `DatabaseAdminRepository.afill_all_static_data()` method in `src/infrastructure/database_admin_repository.py`.

1. **Add repository to constructor injection**:

```python
def __init__(
    self,
    role_repository: RoleRepository,
    quick_action_repository: QuickActionRepository,
    task_status_repository: TaskStatusRepository,
    {entity_name}_repository: {EntityName}Repository,  # ADD THIS
) -> None:
    super().__init__()
    self.logger = logging.getLogger(__name__)
    self.role_repository = role_repository
    self.quick_action_repository = quick_action_repository
    self.task_status_repository = task_status_repository
    self.{entity_name}_repository = {entity_name}_repository  # ADD THIS
```

2. **Add call in `afill_all_static_data()`**:

```python
async def afill_all_static_data(self) -> None:
    """Fill all static/reference data into the database."""
    # ... existing fills ...

    # Fill {entity_names} if not exists
    if not await self.{entity_name}_repository.astatic_data_exists():
        await self.{entity_name}_repository.afill_{entity_names}()
    else:
        self.logger.info("{EntityName}s static data already exists, skipping fill")
```

3. **Update DI container** to inject the new repository into `DatabaseAdminRepository`.

**Existing examples:** See `RoleRepository`, `QuickActionRepository`, `TaskStatusRepository` for complete implementations.

## Workflow: Modify Existing Entity

### Step 1: Update Entity File

Edit the existing entity in `src/infrastructure/entities/`

### Step 2: Create Migration File

**Location:** `src/utils/database/migration_scripts/`

**Naming format:** `{YYYYMMDD}-{description}.sql`

Example: `20260129-add_status_to_users.sql`

See [references/migration-templates.md](references/migration-templates.md) for SQL templates.

**Note:** If the modification requires model/converter updates, `/repo-search-or-create` will handle them when creating or updating repository methods.

## Field Type Reference

### Standard Fields

| Python Type | SQLAlchemy Type | Example |
|-------------|-----------------|---------|
| `str` | `String(n)` | `mapped_column(String(255), nullable=False)` |
| `str` (long) | `Text` | `mapped_column(Text, nullable=False)` |
| `int` | `Integer` | `mapped_column(Integer, default=0)` |
| `bool` | `Boolean` | `mapped_column(Boolean, default=False)` |
| `datetime` | `DateTime` | `mapped_column(DateTime, nullable=True)` |
| `UUID` | (auto from FK) | `mapped_column(ForeignKey("table.id"))` |

### JSON Fields (PostgreSQL/SQLite Compatible)

```python
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

field: Mapped[dict] = mapped_column(
    JSON().with_variant(JSONB, "postgresql"),
    nullable=False
)
```

### Foreign Keys

```python
# Required FK
user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

# Optional FK
school_id: Mapped[UUID | None] = mapped_column(ForeignKey("schools.id"), nullable=True)
```

### Relationships

```python
# Many-to-one (eager load)
user: Mapped["UserEntity"] = relationship("UserEntity", back_populates="items", lazy="joined")

# One-to-many (lazy load for large collections)
messages: Mapped[list["MessageEntity"]] = relationship(
    "MessageEntity",
    back_populates="thread",
    cascade="all, delete-orphan",
    lazy="noload"
)
```

## Migration Naming Convention

Format: `{YYYYMMDD}-{action}_{target}_{details}.sql`

**Examples:**
- `20260129-add_status_to_users.sql`
- `20260129-add_foreign_key_school_to_users.sql`
- `20260129-change_content_type_to_text.sql`
- `20260129-create_index_on_messages_user_id.sql`

## Important Notes

1. **New entities do NOT need migrations** - tables are auto-created at startup
2. **Modifications ALWAYS need migrations** - existing tables won't auto-update
3. **JSON fields** - Always use `JSON().with_variant(JSONB, "postgresql")` pattern
4. **Timestamps** - Store as timezone-naive UTC (no tzinfo)
5. **Type hints** - Use `Mapped[T]` with `| None` for nullable fields
6. **Relationships** - Use `TYPE_CHECKING` guard to avoid circular imports
7. **SimpleBase vs StatefulBase** - Use `SimpleBase` for lookup/reference data, `StatefulBase` for everything else
8. **Static data** - For `SimpleBase` entities with predefined values, implement `afill_{entity_names}()` in repository and register in `DatabaseAdminRepository.afill_all_static_data()`
