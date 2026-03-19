---
name: service-search-or-create
description: |
  Search existing services for use-case methods, create if not found, reuse sub-services.
  Services orchestrate business logic by coordinating repositories and other services.
  A service = a use-case implementation.

  Use when:
  - Need to implement a business use-case
  - Want to check if a service method already exists
  - Need to create a new service or add methods to existing ones
  - Called after /repo-search-or-create when data access is ready

  Triggers: "service method", "use-case", "business logic", "application layer",
  "create service", "orchestration", "service layer"
---

# Service Search or Create

Find existing service methods or create new ones. Services orchestrate business logic by coordinating repositories and other services.

**Principle:** A service method = A use-case. Reuse existing sub-services whenever possible.

## Output Format

```
RESULT:
  Service: {ServiceClass}
  Method: {method_name}
  File: {file_path}:{line_number}
  Signature: async def {method_name}({params}) -> {ReturnType}
  Dependencies: {list of injected services/repositories}
  Usage: await {service_instance}.{method_name}({params})
  Status: FOUND | CREATED
```

---

## Workflow

```
1. IDENTIFY use-case needed
       │
       ▼
2. SEARCH for existing method in services
       │
       ├─ FOUND → Return method details
       │
       └─ NOT FOUND
              │
              ▼
       3. IDENTIFY required dependencies
          (repositories, other services)
              │
              ▼
       4. CHECK if service exists for this entity
              │
              ├─ YES → Add method, inject new dependencies if needed
              │
              └─ NO → Create new service file
              │
              ▼
       5. REGISTER in dependency injection (if new service)
              │
              ▼
       6. Return created method details
```

---

## Phase 1: Identify Use-Case

Determine the required use-case:

| Question | Examples |
|----------|----------|
| **Domain** | User, Thread, Content, Course |
| **Action** | create, retrieve, update, delete, process, stream |
| **Complexity** | Simple CRUD wrapper? Multi-step orchestration? |
| **Dependencies** | Which repositories? Which other services? |

**Method naming pattern:** `a{action}_{entity}_{details}`

Examples:
- `acreate_or_update_user` - Create/update user with school handling
- `aget_retrieve_or_create_user` - Get from DB or create from LMS
- `astream_llm_response_and_persist` - Complex streaming orchestration
- `ascrape_parcours_all_contents` - Batch scraping with SSE progress

---

## Phase 2: Search

### Step 1: Find service files

```
Glob: src/application/*_service.py
```

### Step 2: Search for entity service

```
Grep: class {Entity}Service
Path: src/application/
```

### Step 3: Search for matching method

```
Grep patterns:
- async def a{action}_{entity}
- async def a{action}_.*{entity}
```

### Step 4: Check sub-service methods

If main service not found, check if the operation exists in a related service:
- UserService for user-related operations
- ContentService for content operations
- ThreadService for conversation operations
- CourseHierarchyService for course structure

**If exact match found** → Return RESULT with `Status: FOUND`

**If no match** → Continue to Phase 3

See [references/search-patterns.md](references/search-patterns.md) for patterns.

---

## Phase 3: Identify Dependencies

Before creating, identify what the use-case needs:

### Repository Dependencies

Use `/repo-search-or-create` to ensure required repository methods exist:

```
Need: aget_user_by_email in UserService
  └─ Requires: UserRepository.aget_user_by_email
  └─ Invoke /repo-search-or-create if missing
```

### Service Dependencies (Sub-services)

Check if other services provide reusable operations:

| Need | Check Service | Method |
|------|---------------|--------|
| User retrieval | UserService | `aget_retrieve_or_create_user` |
| Content fetching | ContentService | `aget_content_by_filter` |
| Course hierarchy | CourseHierarchyService | `aget_or_retrieve_course_hierarchy_by_partial_filter` |
| LLM operations | LlmService | `astream_response` |

**Reuse existing service methods** instead of duplicating logic.

---

## Phase 4: Create Service Method

### 4a. Service exists → Add method

1. Open existing service file
2. Add new dependency to `__init__` if needed
3. Add new method following patterns
4. Update DI registration if new dependencies added

### 4b. Service doesn't exist → Create service

**Step 1: Create service file**
```
Location: src/application/{entity}_service.py
```

**Step 2: Register in dependency injection**
```
Location: src/API/dependency_injection_config.py
```

See [references/service-templates.md](references/service-templates.md) for templates.

---

## Service Structure

```python
import logging
from typing import TYPE_CHECKING

from infrastructure.{entity}_repository import {Entity}Repository
from models.{entity} import {Entity}

if TYPE_CHECKING:
    from application.other_service import OtherService


class {Entity}Service:
    """
    Service for {Entity} use-cases.

    Orchestrates business logic by coordinating repositories and other services.
    """

    def __init__(
        self,
        {entity}_repository: {Entity}Repository,
        # other_service: "OtherService",  # Sub-service if needed
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.{entity}_repository = {entity}_repository
        # self.other_service = other_service

    async def a{action}_{entity}(self, ...) -> {ReturnType}:
        """
        {Use-case description}
        """
        # Implementation
```

---

## Dependency Injection Registration

After creating a new service, register in `src/API/dependency_injection_config.py`:

```python
from lagom import Container
from application.{entity}_service import {Entity}Service
from infrastructure.{entity}_repository import {Entity}Repository

container = Container()

# Repository (if new)
container[{Entity}Repository] = {Entity}Repository

# Service
container[{Entity}Service] = {Entity}Service
```

---

## Service Locations

| Service | Domain | File |
|---------|--------|------|
| UserService | User, School | `user_service.py` |
| ThreadService | Thread, Message, Conversation | `thread_service.py` |
| ContentService | Content, Scraping | `content_service.py` |
| CourseHierarchyService | Course structure | `course_hierarchy_service.py` |
| SummaryService | Content summarization | `summary_service.py` |

---

## Method Naming Conventions

All async methods prefixed with `a`:

| Prefix | Use-Case | Example |
|--------|----------|---------|
| `acreate_` | Create entity | `acreate_new_thread` |
| `aget_` | Retrieve entity | `aget_user_by_lms_user_id` |
| `aget_*_or_create_` | Get or create | `aget_retrieve_or_create_user` |
| `aupdate_` | Update entity | `aupdate_context_metadata` |
| `adelete_` | Delete entity | `adelete_course_by_id` |
| `astream_` | Streaming operation | `astream_llm_response_and_persist` |
| `ascrape_` | External fetching | `ascrape_parcours_all_contents` |
| `aexport_/aimport_` | Bulk operations | `aexport_contents_to_json_files` |

Private methods: `_a{action}_{details}` or `_{sync_method}`

---

## Error Handling

Services use domain-specific exceptions:

```python
from errors import (
    ValidationError,      # VALIDATION_*
    AuthorizationError,   # AUTHZ_*
    NotFoundError,        # NOT_FOUND_*
    ConflictError,        # CONFLICT_*
    QuotaExceededException,  # QUOTA_*
    InternalServerException, # INTERNAL_*
)

# Pattern: Early validation
if not thread.id:
    raise ValidationError("VALIDATION_THREAD_ID_MISSING")

# Pattern: Authorization check
if thread.user_id != user_id:
    raise AuthorizationError("AUTHZ_THREAD_ACCESS_DENIED")

# Pattern: Wrap repository errors
try:
    user = await self.user_repository.acreate_or_update(user)
except Exception as e:
    raise InternalServerException("INTERNAL_USER_PERSISTENCE_FAILED", details=str(e)) from e
```

---

## Integration with Other Skills

| Situation | Action |
|-----------|--------|
| Repository method missing | Invoke `/repo-search-or-create` |
| Entity missing | `/repo-search-or-create` will invoke `/db-entity-change` |
| New service needs new repository | Create repository first via `/repo-search-or-create` |

**Flow:**
```
Use-case needed
    │
    ▼
/service-search-or-create
    │
    ├─ Need repo method? → /repo-search-or-create
    │                          │
    │                          └─ Need entity? → /db-entity-change
    │
    └─ Create/return service method
```
