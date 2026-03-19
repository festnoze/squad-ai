# Repository Architecture

How session management and connection pooling work in SkillForge repositories.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [BaseRepository](#baserepository)
3. [AutoSessionMeta Metaclass](#autosessionmeta-metaclass)
4. [Session Lifecycle](#session-lifecycle)
5. [Connection Pool](#connection-pool)
6. [Key Rules](#key-rules)

---

## Architecture Overview

```
External Call (no session parameter)
    │
    ▼
AutoSessionMeta Wrapper
    │
    ▼
BaseRepository._execute_with_session()
    │
    ▼
SessionManager.session_factory()
    │
    ▼
Connection Pool (AsyncEngine)
    │
    ▼
Database
```

**Key principle:** Sessions are completely hidden from callers. The repository layer manages all database connections internally.

---

## BaseRepository

All repositories must inherit from `BaseRepository`.

**Location:** `src/infrastructure/database/base_repository.py`

**What it provides:**

```python
class BaseRepository:
    def __init__(self):
        # Gets session factory from singleton SessionManager
        self.session_factory = session_manager.session_factory

    async def _execute_with_session(
        self,
        operation: Callable[[AsyncSession], Awaitable[T]]
    ) -> T:
        """
        Executes an operation with automatic session management.

        - Opens a new session from the connection pool
        - Begins transaction
        - Executes operation
        - Commits on success / Rollbacks on error
        - Closes session (returns connection to pool)
        """
```

**Why inherit:**
- Access to `session_factory` for creating sessions
- Access to `_execute_with_session()` for transaction management
- Ensures all repositories use the same connection pool

---

## AutoSessionMeta Metaclass

The metaclass that makes session management automatic.

**Location:** `src/infrastructure/database/repository_metaclass.py`

**What it does:**

1. **Scans** all public async methods with `session: AsyncSession` parameter
2. **Removes** `session` from the external method signature
3. **Wraps** the method to inject session via `_execute_with_session()`
4. **Handles errors** based on return type hints

### Before/After Example

**You write:**
```python
class UserRepository(BaseRepository, metaclass=AutoSessionMeta):
    async def aget_user_by_id(self, session: AsyncSession, user_id: UUID) -> User | None:
        stmt = select(UserEntity).where(UserEntity.id == user_id)
        result = await session.execute(stmt)
        entity = result.unique().scalar_one_or_none()
        return UserConverters.convert_entity_to_model(entity) if entity else None
```

**External callers see:**
```python
# session parameter is HIDDEN - don't pass it!
user = await user_repository.aget_user_by_id(user_id)
```

**Internally, metaclass transforms it to:**
```python
async def aget_user_by_id(self, user_id: UUID) -> User | None:
    async def operation(session: AsyncSession):
        stmt = select(UserEntity).where(UserEntity.id == user_id)
        result = await session.execute(stmt)
        entity = result.unique().scalar_one_or_none()
        return UserConverters.convert_entity_to_model(entity) if entity else None

    return await self._execute_with_session(operation)
```

### Wrapping Rules

| Method Type | Wrapped? | Example |
|-------------|----------|---------|
| Public async with `session` param | Yes | `async def aget_user(self, session, id)` |
| Private (starts with `_`) | No | `async def _aget_user_query(self, session, id)` |
| No `session` parameter | No | `async def validate(self, data)` |
| Decorated with `@no_auto_session` | No | See below |

### Opting Out

Use `@no_auto_session` decorator to prevent wrapping:

```python
from infrastructure.database import no_auto_session

class MyRepository(BaseRepository, metaclass=AutoSessionMeta):
    @no_auto_session
    async def acustom_operation(self, param: str) -> Result:
        # This method is NOT wrapped - manage session manually if needed
        pass
```

---

## Session Lifecycle

### Per-Operation Flow

```
1. Method called (without session)
2. AutoSessionMeta wrapper invoked
3. _execute_with_session() called
4. New session created from pool
5. Transaction begins (implicit)
6. Your method code executes with session
7. On success: commit + close session
   On error: rollback + close session + handle error
8. Connection returned to pool
```

### Transaction Boundaries

Each public repository method = one transaction.

```python
# This is ONE transaction:
user = await user_repo.acreate_user(user_model)

# This is ANOTHER transaction:
thread = await thread_repo.acreate_thread(thread_model)
```

### Calling Multiple Repository Methods

When you need atomicity across multiple operations, use private helpers within the same session:

```python
class OrderRepository(BaseRepository, metaclass=AutoSessionMeta):
    async def acreate_order_with_items(
        self,
        session: AsyncSession,
        order: Order,
        items: list[OrderItem]
    ) -> Order:
        # All operations share the same session = same transaction
        order_entity = OrderConverters.convert_model_to_entity(order)
        session.add(order_entity)
        await session.flush()

        for item in items:
            item_entity = ItemConverters.convert_model_to_entity(item)
            item_entity.order_id = order_entity.id
            session.add(item_entity)

        await session.flush()
        await session.refresh(order_entity)
        return OrderConverters.convert_entity_to_model(order_entity)
```

---

## Connection Pool

### Singleton Pattern

The application uses a single `SessionManager` instance with one `AsyncEngine`.

**Benefits:**
- No connection pool fragmentation
- Efficient connection reuse
- Centralized configuration

### Configuration (Environment Variables)

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_POOL_SIZE` | Persistent connections | Auto by environment |
| `DB_MAX_OVERFLOW` | Temporary overflow | Auto by environment |
| `DB_POOL_RECYCLE` | Recycle stale connections (seconds) | 3600 |
| `DB_POOL_PRE_PING` | Health check connections | true |
| `DB_POOL_TIMEOUT` | Wait timeout (seconds) | 30 |

### Environment Defaults

| Environment | Pool Size | Max Overflow |
|-------------|-----------|--------------|
| local/development | 5 | 10 |
| uat | 10 | 20 |
| production | 20 | 30 |

### LIFO Queue

The pool uses Last-In-First-Out (LIFO) queuing, optimized for async applications where recently used connections are more likely to be healthy.

---

## Key Rules

### DO:

```python
# Inherit from BaseRepository
class MyRepository(BaseRepository, metaclass=AutoSessionMeta):

# Add session as first param after self
async def aget_item(self, session: AsyncSession, item_id: UUID) -> Item | None:

# Use private helpers for internal queries
async def _aget_item_entity(self, session: AsyncSession, item_id: UUID) -> ItemEntity | None:

# Call .unique() with joined relationships on collections
result.unique().scalar_one_or_none()

# Flush after writes
await session.flush()

# Refresh after create to get generated values
await session.refresh(entity)
```

### DON'T:

```python
# Don't pass session from outside
user = await repo.aget_user(session, user_id)  # WRONG - no session param!
user = await repo.aget_user(user_id)  # CORRECT

# Don't create sessions manually in repositories
async with session_factory() as session:  # WRONG - let metaclass handle it

# Don't commit manually (handled by _execute_with_session)
await session.commit()  # WRONG - use flush() instead

# Don't forget metaclass
class MyRepository(BaseRepository):  # WRONG - missing metaclass!
class MyRepository(BaseRepository, metaclass=AutoSessionMeta):  # CORRECT
```

### Error Handling

AutoSessionMeta returns safe defaults based on return type:

| Return Type | On Error |
|-------------|----------|
| `T \| None` | `None` |
| `list[T]` | `[]` |
| `bool` | `False` |
| `int` | `0` |
| `str` | `""` |
| `dict` | `{}` |
| `T` (required) | Re-raises |

This means:
- Optional returns gracefully degrade
- Required returns propagate errors to caller
- All errors are logged automatically
