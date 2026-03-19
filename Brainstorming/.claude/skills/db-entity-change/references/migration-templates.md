# Migration Templates

SQL templates for database migrations. All migrations are executed within a transaction (atomic).

## Table of Contents

1. [Naming Convention](#naming-convention)
2. [Add Column](#add-column)
3. [Add Column with Default](#add-column-with-default)
4. [Add Foreign Key Column](#add-foreign-key-column)
5. [Change Column Type](#change-column-type)
6. [Add Index](#add-index)
7. [Add Constraint](#add-constraint)
8. [Remove Column](#remove-column)
9. [Rename Column](#rename-column)
10. [Complex Migration Example](#complex-migration-example)

---

## Naming Convention

**Format:** `{YYYYMMDD}-{action}_{target}_{details}.sql`

**Location:** `src/utils/database/migration_scripts/`

**Examples:**
```
20260129-add_status_column_to_users.sql
20260129-add_category_id_to_contents.sql
20260129-change_content_type_to_text.sql
20260129-add_index_on_messages_user_id.sql
20260129-remove_deprecated_field_from_users.sql
```

**Rules:**
- Use today's date as prefix (YYYYMMDD)
- Use lowercase with underscores
- Be descriptive about the change
- Migrations execute in alphabetical order

---

## Add Column

### Simple Column (Nullable)

```sql
-- Migration: Add {column} column to {table} table
-- Date: {YYYY-MM-DD}
-- Purpose: {Reason for adding this column}

ALTER TABLE {table}
ADD COLUMN IF NOT EXISTS {column} {TYPE};
```

**Type Reference:**
| Python Type | PostgreSQL Type |
|-------------|-----------------|
| `str` | `VARCHAR(n)` or `TEXT` |
| `int` | `INTEGER` |
| `bool` | `BOOLEAN` |
| `datetime` | `TIMESTAMP` |
| `UUID` | `UUID` |
| `dict` | `JSONB` |

### Example: Add status column

```sql
-- Migration: Add status column to users table
-- Date: 2026-01-29
-- Purpose: Track user account status

ALTER TABLE users
ADD COLUMN IF NOT EXISTS status VARCHAR(50);
```

---

## Add Column with Default

### Non-Nullable Column (requires default or data migration)

```sql
-- Migration: Add {column} column to {table} table
-- Date: {YYYY-MM-DD}
-- Purpose: {Reason}

-- Step 1: Add column as nullable
ALTER TABLE {table}
ADD COLUMN IF NOT EXISTS {column} {TYPE};

-- Step 2: Set default value for existing rows
UPDATE {table}
SET {column} = {default_value}
WHERE {column} IS NULL;

-- Step 3: Make column NOT NULL
ALTER TABLE {table}
ALTER COLUMN {column} SET NOT NULL;

-- Step 4: Set default for future inserts (optional)
ALTER TABLE {table}
ALTER COLUMN {column} SET DEFAULT {default_value};
```

### Example: Add is_active boolean

```sql
-- Migration: Add is_active column to categories table
-- Date: 2026-01-29
-- Purpose: Allow soft-disabling categories

-- Step 1: Add column as nullable
ALTER TABLE categories
ADD COLUMN IF NOT EXISTS is_active BOOLEAN;

-- Step 2: Set default for existing rows
UPDATE categories
SET is_active = TRUE
WHERE is_active IS NULL;

-- Step 3: Make NOT NULL
ALTER TABLE categories
ALTER COLUMN is_active SET NOT NULL;

-- Step 4: Set default for future inserts
ALTER TABLE categories
ALTER COLUMN is_active SET DEFAULT TRUE;
```

---

## Add Foreign Key Column

```sql
-- Migration: Add {fk_column} foreign key to {table} table
-- Date: {YYYY-MM-DD}
-- Purpose: Link {table} to {referenced_table}

-- Step 1: Add the column (nullable initially if existing data)
ALTER TABLE {table}
ADD COLUMN IF NOT EXISTS {fk_column} UUID;

-- Step 2: Populate if needed (optional)
-- UPDATE {table} SET {fk_column} = (SELECT id FROM {referenced_table} WHERE ...) WHERE {fk_column} IS NULL;

-- Step 3: Add foreign key constraint
ALTER TABLE {table}
DROP CONSTRAINT IF EXISTS fk_{table}_{fk_column};

ALTER TABLE {table}
ADD CONSTRAINT fk_{table}_{fk_column}
FOREIGN KEY ({fk_column}) REFERENCES {referenced_table}(id);

-- Step 4: Create index for FK performance
CREATE INDEX IF NOT EXISTS idx_{table}_{fk_column} ON {table}({fk_column});
```

### Example: Add category_id to contents

```sql
-- Migration: Add category_id foreign key to contents table
-- Date: 2026-01-29
-- Purpose: Categorize content items

-- Step 1: Add column
ALTER TABLE contents
ADD COLUMN IF NOT EXISTS category_id UUID;

-- Step 2: Add FK constraint
ALTER TABLE contents
DROP CONSTRAINT IF EXISTS fk_contents_category_id;

ALTER TABLE contents
ADD CONSTRAINT fk_contents_category_id
FOREIGN KEY (category_id) REFERENCES categories(id);

-- Step 3: Index for performance
CREATE INDEX IF NOT EXISTS idx_contents_category_id ON contents(category_id);
```

---

## Change Column Type

```sql
-- Migration: Change {column} type from {old_type} to {new_type} in {table}
-- Date: {YYYY-MM-DD}
-- Purpose: {Reason for type change}

ALTER TABLE {table}
ALTER COLUMN {column} TYPE {NEW_TYPE} USING {column}::{NEW_TYPE};
```

### Example: Change content from VARCHAR to TEXT

```sql
-- Migration: Change content column type to TEXT in messages table
-- Date: 2026-01-29
-- Purpose: Support longer message content

ALTER TABLE messages
ALTER COLUMN content TYPE TEXT USING content::TEXT;
```

### Example: Change string to integer

```sql
-- Migration: Change priority column from VARCHAR to INTEGER
-- Date: 2026-01-29
-- Purpose: Enable numeric sorting

ALTER TABLE tasks
ALTER COLUMN priority TYPE INTEGER USING priority::INTEGER;
```

---

## Add Index

```sql
-- Migration: Add index on {column}(s) in {table}
-- Date: {YYYY-MM-DD}
-- Purpose: Improve query performance for {use_case}

-- Single column index
CREATE INDEX IF NOT EXISTS idx_{table}_{column} ON {table}({column});

-- Composite index
CREATE INDEX IF NOT EXISTS idx_{table}_{col1}_{col2} ON {table}({col1}, {col2});

-- Unique index
CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_{column}_unique ON {table}({column});
```

### Example: Add composite index for quota queries

```sql
-- Migration: Add composite index for user quota queries
-- Date: 2026-01-29
-- Purpose: Optimize daily/monthly quota counting

CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_user_id_created_at ON messages(user_id, created_at);
```

---

## Add Constraint

### Unique Constraint

```sql
-- Migration: Add unique constraint on {column} in {table}
-- Date: {YYYY-MM-DD}

ALTER TABLE {table}
DROP CONSTRAINT IF EXISTS uq_{table}_{column};

ALTER TABLE {table}
ADD CONSTRAINT uq_{table}_{column} UNIQUE ({column});
```

### Check Constraint

```sql
-- Migration: Add check constraint on {column} in {table}
-- Date: {YYYY-MM-DD}

ALTER TABLE {table}
DROP CONSTRAINT IF EXISTS chk_{table}_{column};

ALTER TABLE {table}
ADD CONSTRAINT chk_{table}_{column} CHECK ({column} IN ('value1', 'value2', 'value3'));
```

---

## Remove Column

```sql
-- Migration: Remove {column} column from {table}
-- Date: {YYYY-MM-DD}
-- Purpose: {Reason - column deprecated/moved/etc}
-- WARNING: This is destructive - data will be lost

-- Step 1: Drop any constraints on the column
ALTER TABLE {table}
DROP CONSTRAINT IF EXISTS fk_{table}_{column};

ALTER TABLE {table}
DROP CONSTRAINT IF EXISTS uq_{table}_{column};

-- Step 2: Drop index if exists
DROP INDEX IF EXISTS idx_{table}_{column};

-- Step 3: Drop the column
ALTER TABLE {table}
DROP COLUMN IF EXISTS {column};
```

---

## Rename Column

```sql
-- Migration: Rename {old_column} to {new_column} in {table}
-- Date: {YYYY-MM-DD}
-- Purpose: {Reason for rename}

ALTER TABLE {table}
RENAME COLUMN {old_column} TO {new_column};
```

---

## Complex Migration Example

Full example with multiple steps and data migration.

**File:** `20260129-add_user_id_to_messages.sql`

```sql
-- Migration: Add user_id column to messages table for quota performance optimization
-- Date: 2026-01-29
-- Purpose: Denormalize user_id into messages table to optimize quota verification queries
--          Previously required JOIN through threads table for every quota check

-- Step 1: Add the column if it doesn't exist (nullable initially)
ALTER TABLE messages
ADD COLUMN IF NOT EXISTS user_id UUID;

-- Step 2: Populate with actual user IDs from the threads table
UPDATE messages m
SET user_id = (
    SELECT t.user_id
    FROM threads t
    WHERE t.id = m.thread_id
)
WHERE user_id IS NULL;

-- Step 3: Make the column NOT NULL after population
ALTER TABLE messages
ALTER COLUMN user_id SET NOT NULL;

-- Step 4: Add foreign key constraint
ALTER TABLE messages
DROP CONSTRAINT IF EXISTS fk_messages_user_id;

ALTER TABLE messages
ADD CONSTRAINT fk_messages_user_id
FOREIGN KEY (user_id) REFERENCES users(id);

-- Step 5: Create indexes for performance optimization
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_user_id_created_at ON messages(user_id, created_at);
```

---

## JSON/JSONB Column

```sql
-- Migration: Add {column} JSON column to {table}
-- Date: {YYYY-MM-DD}
-- Purpose: Store structured {data_description}

-- For PostgreSQL (JSONB for indexing and efficiency)
ALTER TABLE {table}
ADD COLUMN IF NOT EXISTS {column} JSONB;

-- Set default empty object for existing rows
UPDATE {table}
SET {column} = '{}'::JSONB
WHERE {column} IS NULL;

-- Make NOT NULL if required
ALTER TABLE {table}
ALTER COLUMN {column} SET NOT NULL;

-- Set default for future inserts
ALTER TABLE {table}
ALTER COLUMN {column} SET DEFAULT '{}'::JSONB;
```

### Example: Add settings JSON column

```sql
-- Migration: Add settings JSON column to users table
-- Date: 2026-01-29
-- Purpose: Store user preferences as structured data

ALTER TABLE users
ADD COLUMN IF NOT EXISTS settings JSONB;

UPDATE users
SET settings = '{}'::JSONB
WHERE settings IS NULL;

ALTER TABLE users
ALTER COLUMN settings SET NOT NULL;

ALTER TABLE users
ALTER COLUMN settings SET DEFAULT '{}'::JSONB;
```

---

## Migration Checklist

Before committing a migration:

- [ ] Filename follows `YYYYMMDD-description.sql` format
- [ ] SQL comments explain purpose and date
- [ ] Uses `IF NOT EXISTS` / `IF EXISTS` for idempotency
- [ ] Handles existing data (nullable first, then populate, then NOT NULL)
- [ ] Foreign keys have corresponding indexes
- [ ] Tested locally with both PostgreSQL and SQLite (if applicable)
- [ ] Entity file updated to match migration
- [ ] Converter updated if new fields affect model
