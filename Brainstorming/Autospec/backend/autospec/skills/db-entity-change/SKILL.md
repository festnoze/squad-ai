---
name: db-entity-change
description: |
  Create new persistence entities or modify existing ones with a matching migration. Lives in the
  infrastructure layer of the generated 3-layer backend. Handles SQLAlchemy ORM entity definitions
  with PostgreSQL/SQLite JSON compatibility (frame entities as a pattern; simpler persistence is fine).

  Use when:
  - Creating a new database table/entity
  - Adding a new column/property to an existing entity
  - Modifying an existing column type or constraints
  - Called by /repo-search-or-create when entity changes are needed

  Triggers: "create entity", "add column", "modify entity", "new table",
  "database schema change", "add property to entity", "alter table"
---

# Database Entity Change

Create or modify persistence entities (infrastructure layer) and write a migration when an existing
table changes.

**Scope:** This skill handles ONLY entity files and migrations. Domain models (`models/`) and
converters are created by `/repo-search-or-create` when a repository is created.

## Decision Tree

```
NEW entity or MODIFICATION?
│
├─ NEW ENTITY
│  1. Pick base class (SimpleBase vs StatefulBase)
│  2. Create entity file (no migration — table auto-created at startup)
│  3. Register the entity where the app collects its tables (entities/__init__.py or metadata)
│  4. If lookup data with predefined values → add the static-data fill pattern
│  └─ Model + converter handled by /repo-search-or-create
│
└─ MODIFICATION to existing entity
   1. Update the entity file
   2. Write a migration SQL file (existing tables do NOT auto-update)
   └─ Model/converter updates handled by /repo-search-or-create if needed
```

## Workflow: New Entity

1. **Choose base class**

   | Use case | Base class | Provides |
   |----------|-----------|----------|
   | Lookup / reference / static data (roles, statuses, categories) | `SimpleBase` | `id` only |
   | User-generated / transactional data needing an audit trail | `StatefulBase` | `id`, `created_at`, `updated_at`, `deleted_at` |

2. **Create the entity file** at `infrastructure/entities/{entity_name}_entity.py`. See
   [references/entity-templates.md](references/entity-templates.md).

   - File: `{entity_name}_entity.py` (snake_case)
   - Class: `{EntityName}Entity` (PascalCase)
   - Table: `{entity_names}` (plural snake_case)

3. **Register the entity** by importing it where the app collects ORM metadata (commonly
   `infrastructure/entities/__init__.py`). The table is auto-created at startup.

4. **Static-data fill pattern** (only for `SimpleBase` lookup tables with predefined values): add an
   idempotent `afill_{entity_names}()` to the repository and call it once at startup where the app
   seeds reference data. See [references/entity-templates.md](references/entity-templates.md#static-data).

## Workflow: Modify Existing Entity

1. Edit the entity file in `infrastructure/entities/`.
2. Write a migration SQL file at `infrastructure/migrations/` (or wherever the app keeps migrations).
   See [references/migration-templates.md](references/migration-templates.md).

**Migration naming:** `{YYYYMMDD}-{action}_{target}_{details}.sql`, e.g.
`20260627-add_status_to_users.sql`. Migrations run in alphabetical order.

## Field Type Reference

| Python type | SQLAlchemy | Example |
|-------------|------------|---------|
| `str` | `String(n)` | `mapped_column(String(255), nullable=False)` |
| `str` (long) | `Text` | `mapped_column(Text, nullable=False)` |
| `int` | `Integer` | `mapped_column(Integer, default=0)` |
| `bool` | `Boolean` | `mapped_column(Boolean, default=False)` |
| `datetime` | `DateTime` | `mapped_column(DateTime, nullable=True)` |
| `UUID` (FK) | `ForeignKey` | `mapped_column(ForeignKey("table.id"))` |

**JSON fields (Postgres/SQLite compatible):**

```python
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

config: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
```

## Key Rules

1. New entities need NO migration (auto-created); modifications ALWAYS need one.
2. Always use `JSON().with_variant(JSONB, "postgresql")` for JSON columns.
3. Store timestamps as timezone-naive UTC.
4. Type hints use `Mapped[T]`; nullable fields use `Mapped[T | None]`.
5. Guard relationship imports with `TYPE_CHECKING` to avoid circular imports.
6. All async methods are prefixed with `a` (e.g. `afill_roles`, `astatic_data_exists`).
