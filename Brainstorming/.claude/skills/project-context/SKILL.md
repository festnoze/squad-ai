---
name: project-context
description: |
  Provides comprehensive project architecture overview, naming conventions, codebase map, and registration guide.
  Fuses architecture documentation, codebase exploration, and component registration guidance into one skill.

  Use when:
  - Need to understand the project's 3-layer architecture
  - Want to see existing components (routers, services, repositories, entities)
  - Need to know how to register new components (DI, routers, entities)
  - Starting work on a new feature and need project context

  Triggers: "project context", "architecture", "codebase map", "naming conventions",
  "how to register", "project structure", "what exists", "list components"
---

# Project Context

Comprehensive project overview combining architecture, codebase map, and registration guide.

## Quick Reference

| Need | Location |
|------|----------|
| Architecture overview | [Section 1](#section-1-architecture) |
| Naming conventions | [Section 2](#section-2-naming-conventions) |
| Existing components | [Section 3](#section-3-codebase-map) |
| Registration guide | [Section 4](#section-4-registration-guide) |

---

## Section 1: Architecture

SkillForge follows a **3-Layer Architecture** pattern with clear separation of concerns.

### Layer Overview

```
HTTP Request
     |
     v
+------------------+
|   FACADE LAYER   |  src/facade/
|   (Routers)      |  - HTTP endpoints
|   - Validation   |  - Request/Response models
|   - Auth deps    |  - No business logic
+------------------+
     |
     v
+------------------+
| APPLICATION LAYER|  src/application/
|   (Services)     |  - Business logic
|   - Use cases    |  - Orchestration
|   - Rules        |  - Transaction boundaries
+------------------+
     |
     v
+------------------+
| INFRASTRUCTURE   |  src/infrastructure/
|   (Repositories) |  - Data access
|   - Entities     |  - External services
|   - Converters   |  - Persistence
+------------------+
     |
     v
   Database
```

### Directory Structure

```
src/
  facade/                       # Layer 1: HTTP Interface
    *_router.py                 # FastAPI routers
    request_models/             # Pydantic request models
    response_models/            # Pydantic response models
    converters/                 # Request/Response converters (optional)

  application/                  # Layer 2: Business Logic
    *_service.py                # Service classes

  infrastructure/               # Layer 3: Data Access
    *_repository.py             # Repository classes
    entities/                   # SQLAlchemy ORM entities
    converters/                 # Entity <-> Model converters

  models/                       # Domain Models (shared across layers)
    *.py                        # Dataclasses/Pydantic models
```

### Dependency Flow

```
Router --> Service --> Repository --> Entity
                          |
                          v
                        Model (via Converter)
```

**Rules:**
- Routers depend on Services (never Repositories directly)
- Services depend on Repositories
- Repositories return Models (converted from Entities)
- No circular dependencies between layers

See [references/architecture.md](references/architecture.md) for detailed architecture documentation.

---

## Section 2: Naming Conventions

### Component Naming Patterns

| Component | File Pattern | Class Pattern | Example File | Example Class |
|-----------|--------------|---------------|--------------|---------------|
| Entity | `{name}_entity.py` | `{Name}Entity` | `notification_entity.py` | `NotificationEntity` |
| Repository | `{name}_repository.py` | `{Name}Repository` | `notification_repository.py` | `NotificationRepository` |
| Service | `{name}_service.py` | `{Name}Service` | `notification_service.py` | `NotificationService` |
| Router | `{name}_router.py` | `{name}_router` | `notification_router.py` | `notification_router` |
| Model | `{name}.py` | `{Name}` | `notification.py` | `Notification` |
| Converter | `{name}_converters.py` | `{Name}Converters` | `notification_converters.py` | `NotificationConverters` |
| Request Model | `{name}_request.py` | `{Action}{Name}Request` | `notification_request.py` | `CreateNotificationRequest` |
| Response Model | `{name}_response.py` | `{Name}Response` | `notification_response.py` | `NotificationResponse` |

### Async Method Naming

**CRITICAL:** All async methods MUST be prefixed with `a` (not `_async` suffix).

| Pattern | Example |
|---------|---------|
| `async def a{action}_{entity}()` | `async def acreate_notification()` |
| `async def aget_{entity}_by_{field}()` | `async def aget_user_by_id()` |
| `async def aupdate_{entity}()` | `async def aupdate_thread()` |
| `async def adelete_{entity}()` | `async def adelete_message()` |
| `async def alist_{entities}()` | `async def alist_threads()` |

### Database Naming

| Component | Pattern | Example |
|-----------|---------|---------|
| Table name | `{entities}` (plural snake_case) | `notifications` |
| Primary key | `id` (UUID) | `id: Mapped[UUID]` |
| Foreign key | `{entity}_id` | `user_id: Mapped[UUID]` |
| Timestamps | `created_at`, `updated_at`, `deleted_at` | Auto from `Base` |

See [references/naming-conventions.md](references/naming-conventions.md) for complete naming guide.

---

## Section 3: Codebase Map

**IMPORTANT:** This section requires dynamic scanning. Execute the commands below to get current state.

### Scan Commands

Run these Glob commands to discover existing components:

```
# Routers
Glob: src/facade/*_router.py

# Services
Glob: src/application/*_service.py

# Repositories
Glob: src/infrastructure/*_repository.py

# Entities
Glob: src/infrastructure/entities/*_entity.py

# Domain Models
Glob: src/models/*.py

# Converters (Entity <-> Model)
Glob: src/infrastructure/converters/*_converters.py

# Request Models
Glob: src/facade/request_models/*.py

# Response Models
Glob: src/facade/response_models/*.py
```

### Expected Structure

After scanning, you should see components organized like:

| Layer | Component Type | Location |
|-------|---------------|----------|
| Facade | Routers | `src/facade/*_router.py` |
| Facade | Request Models | `src/facade/request_models/*.py` |
| Facade | Response Models | `src/facade/response_models/*.py` |
| Application | Services | `src/application/*_service.py` |
| Infrastructure | Repositories | `src/infrastructure/*_repository.py` |
| Infrastructure | Entities | `src/infrastructure/entities/*_entity.py` |
| Infrastructure | Converters | `src/infrastructure/converters/*_converters.py` |
| Shared | Domain Models | `src/models/*.py` |

### Component Relationships

To understand relationships between components:

```
# Find what services a router uses
Grep: deps\.depends\( in src/facade/{name}_router.py

# Find what repositories a service uses
Grep: def __init__ in src/application/{name}_service.py

# Find entity relationships
Grep: relationship\( in src/infrastructure/entities/{name}_entity.py
```

---

## Section 4: Registration Guide

### 4.1 Router Registration

**Location:** `src/API/api_config.py`

**Steps:**
1. Import the router
2. Add `app.include_router()` in `create_app()`

```python
# 1. Import at top of file
from facade.{name}_router import {name}_router

# 2. In create_app() method
app.include_router({name}_router)

# For admin-only routers (non-production):
if EnvVar.get_environment() != "production":
    app.include_router({name}_router)
```

### 4.2 Dependency Injection Registration

**Location:** `src/API/dependency_injection_config.py`

**Steps:**
1. Import the class
2. Register with container

```python
# 1. Import
from infrastructure.{name}_repository import {Name}Repository
from application.{name}_service import {Name}Service

# 2. Register repository
container[{Name}Repository] = {Name}Repository

# 3. Register service
container[{Name}Service] = {Name}Service
```

**For abstract classes (interfaces):**
```python
# Abstract -> Concrete mapping
container[ContentRepository] = ContentRepositoryStudi  # type: ignore[type-abstract]
```

### 4.3 Entity Registration

**Location:** `src/infrastructure/entities/__init__.py`

**Steps:**
1. Add import statement
2. Add to `__all__` list

```python
# 1. Import (after base classes)
from infrastructure.entities.{name}_entity import {Name}Entity  # noqa: E402

# 2. Add to __all__
__all__ = [
    # ... existing entities ...
    "{Name}Entity",
]
```

### 4.4 Registration Checklist

When adding a new feature:

```
[ ] Entity created in src/infrastructure/entities/
[ ] Entity registered in src/infrastructure/entities/__init__.py
[ ] Model created in src/models/
[ ] Converter created in src/infrastructure/converters/
[ ] Repository created in src/infrastructure/
[ ] Repository registered in src/API/dependency_injection_config.py
[ ] Service created in src/application/
[ ] Service registered in src/API/dependency_injection_config.py
[ ] Router created in src/facade/
[ ] Router registered in src/API/api_config.py
[ ] Request/Response models created if needed
```

---

## Integration with Other Skills

| Task | Skill to Use |
|------|--------------|
| Create/modify entity | `/db-entity-change` |
| Create/find repository method | `/repo-search-or-create` |
| Create/find service method | `/service-search-or-create` |
| Create/find endpoint | `/endpoint-search-or-create` |

**Typical workflow:**
```
/project-context           # Understand current state
    |
    v
/db-entity-change          # If entity changes needed
    |
    v
/repo-search-or-create     # Create data access
    |
    v
/service-search-or-create  # Create business logic
    |
    v
/endpoint-search-or-create # Expose via HTTP
```
