# Migration Templates

SQL templates for schema changes to EXISTING tables (new entities auto-create, no migration needed).
Each migration should be idempotent and run inside a transaction.

**Naming:** `{YYYYMMDD}-{action}_{target}_{details}.sql` (lowercase, underscores). Migrations run in
alphabetical order. Place them where the app keeps migrations (commonly `infrastructure/migrations/`).

## Contents
1. [Add column](#add-column)
2. [Add non-null column with default](#add-non-null-column-with-default)
3. [Add foreign key](#add-foreign-key)
4. [Change column type](#change-column-type)
5. [Add index / constraint](#add-index--constraint)
6. [Remove / rename column](#remove--rename-column)
7. [JSON column](#json-column)
8. [Checklist](#checklist)

**Postgres type map:** `str`→`VARCHAR(n)`/`TEXT`, `int`→`INTEGER`, `bool`→`BOOLEAN`,
`datetime`→`TIMESTAMP`, `UUID`→`UUID`, `dict`→`JSONB`.

---

## Add column

```sql
-- Add {column} to {table} — {YYYY-MM-DD} — {purpose}
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {TYPE};
```

## Add non-null column with default

```sql
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {TYPE};
UPDATE {table} SET {column} = {default_value} WHERE {column} IS NULL;
ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL;
ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {default_value};
```

## Add foreign key

```sql
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {fk_column} UUID;
-- optional: UPDATE {table} SET {fk_column} = (...) WHERE {fk_column} IS NULL;
ALTER TABLE {table} DROP CONSTRAINT IF EXISTS fk_{table}_{fk_column};
ALTER TABLE {table} ADD CONSTRAINT fk_{table}_{fk_column}
    FOREIGN KEY ({fk_column}) REFERENCES {referenced_table}(id);
CREATE INDEX IF NOT EXISTS idx_{table}_{fk_column} ON {table}({fk_column});
```

## Change column type

```sql
ALTER TABLE {table} ALTER COLUMN {column} TYPE {NEW_TYPE} USING {column}::{NEW_TYPE};
```

## Add index / constraint

```sql
CREATE INDEX IF NOT EXISTS idx_{table}_{column} ON {table}({column});
CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_{column}_unique ON {table}({column});

ALTER TABLE {table} DROP CONSTRAINT IF EXISTS uq_{table}_{column};
ALTER TABLE {table} ADD CONSTRAINT uq_{table}_{column} UNIQUE ({column});

ALTER TABLE {table} DROP CONSTRAINT IF EXISTS chk_{table}_{column};
ALTER TABLE {table} ADD CONSTRAINT chk_{table}_{column} CHECK ({column} IN ('a', 'b', 'c'));
```

## Remove / rename column

```sql
-- Remove (destructive)
ALTER TABLE {table} DROP CONSTRAINT IF EXISTS fk_{table}_{column};
DROP INDEX IF EXISTS idx_{table}_{column};
ALTER TABLE {table} DROP COLUMN IF EXISTS {column};

-- Rename
ALTER TABLE {table} RENAME COLUMN {old_column} TO {new_column};
```

## JSON column

```sql
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} JSONB;
UPDATE {table} SET {column} = '{}'::JSONB WHERE {column} IS NULL;
ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL;
ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{}'::JSONB;
```

## Checklist

- [ ] Filename is `YYYYMMDD-description.sql`
- [ ] Uses `IF NOT EXISTS` / `IF EXISTS` for idempotency
- [ ] Existing data handled (nullable → populate → NOT NULL)
- [ ] Foreign keys have a matching index
- [ ] Entity file updated to match the migration
