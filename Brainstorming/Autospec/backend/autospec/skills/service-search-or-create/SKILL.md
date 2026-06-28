---
name: service-search-or-create
description: |
  Search existing services for a use-case method, reuse it if present, otherwise create a service or
  add a method, reusing sub-services. Application layer of the generated 3-layer backend. A service
  method = one use-case; it orchestrates repositories and other services. Business logic lives here,
  never in routers or repositories.

  Use when:
  - Need to implement a business use-case
  - Want to check if a service method already exists
  - Need to create a new service or add methods to existing ones
  - Called after /repo-search-or-create when data access is ready

  Triggers: "service method", "use-case", "business logic", "application layer",
  "create service", "orchestration", "service layer"
---

# Service Search or Create

Find an existing service method or create a new one. Services (application layer) orchestrate
business logic by coordinating repositories and other services.

**Principle:** one service method = one use-case. Reuse existing sub-services instead of duplicating.

## Output Format

```
RESULT:
  Service: {ServiceClass}
  Method: {method_name}
  File: {file_path}:{line_number}
  Signature: async def {method_name}({params}) -> {ReturnType}
  Dependencies: {injected repositories / services}
  Usage: await {service_instance}.{method_name}({params})
  Status: FOUND | CREATED
```

## Workflow

```
1. IDENTIFY the use-case
2. SEARCH services for a matching method
       ├─ FOUND → return details
       └─ NOT FOUND
              3. IDENTIFY dependencies (which repositories? which sub-services?)
              4. Service for this domain exists?
                 ├─ YES → add method, inject new deps if needed
                 └─ NO  → create the service file
              5. REGISTER the service where the app wires dependencies (if new)
6. Return method details
```

## Phase 1 — Identify

Method name: `a{action}_{entity}_{details}`. Examples: `acreate_or_update_user`,
`aget_retrieve_or_create_user`, `astream_response_and_persist`, `aprocess_order_with_context`.

## Phase 2 — Search

```
Glob: application/*_service.py
Grep: class {Entity}Service           (path: application/)
Grep: async def a{action}_{entity}
```

If the main service has no match, check related services for a reusable operation before creating
anything. Exact match → `Status: FOUND`. See
[references/search-patterns.md](references/search-patterns.md).

## Phase 3 — Identify dependencies

**Repository methods:** ensure they exist via `/repo-search-or-create` (invoke it if missing).

**Sub-services:** reuse existing service methods rather than re-implementing logic (e.g. a user
lookup, a content fetch). Pass sub-services in via the constructor.

## Phase 4 — Create

**4a. Service exists → add method.** Add any new dependency to `__init__`, add the method, update DI
registration if new dependencies were introduced.

**4b. Service missing → create** at `application/{entity}_service.py`, then register it where the app
wires its dependencies. See [references/service-templates.md](references/service-templates.md).

### Service skeleton

```python
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from errors import NotFoundError, ValidationError, AuthorizationError
from infrastructure.{entity}_repository import {Entity}Repository
from models.{entity} import {Entity}

if TYPE_CHECKING:
    from application.user_service import UserService  # sub-service, guard circular imports


class {Entity}Service:
    """Service for {Entity} use-cases. Orchestrates repositories and other services."""

    def __init__(
        self,
        {entity}_repository: {Entity}Repository,
        # user_service: "UserService",  # sub-service if needed
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.{entity}_repository = {entity}_repository

    async def a{action}_{entity}(self, ...) -> {ReturnType}:
        """{Use-case description}."""
        ...
```

> Calls into repository methods may carry `# type: ignore[call-arg]` when the repository's
> `BaseRepository` auto-wrapping changes the runtime signature (the injected session is hidden from
> type checkers). Omit it if the app's persistence layer doesn't auto-wrap.

## Dependency Registration

Register the new repository and service where the app wires its dependencies (its DI container /
provider module / app factory). Register repositories before the services that depend on them.

## Method Naming

All async prefixed with `a`: `acreate_`, `aget_`, `aget_*_or_create_`, `aupdate_`, `adelete_`,
`astream_`, `aexport_/aimport_`. Private helpers: `_a{action}_{details}`.

## Error Handling

Raise domain exceptions early. Use the error codes managed by `/error-code-management`.

```python
if not {entity}_id:
    raise ValidationError("VALIDATION_{ENTITY}_ID_MISSING")
entity = await self.{entity}_repository.aget_{entity}_by_id({entity}_id)
if not entity:
    raise NotFoundError("NOT_FOUND_{ENTITY}", {entity}_id=str({entity}_id))
if entity.user_id != user_id:
    raise AuthorizationError("AUTHZ_{ENTITY}_ACCESS_DENIED")
```

Wrap unexpected repository errors in `InternalServerException("INTERNAL_{ENTITY}_PERSISTENCE_FAILED", details=str(e))`.

## Integration with other skills

| Situation | Action |
|-----------|--------|
| Repository method missing | Invoke `/repo-search-or-create` |
| Entity missing | `/repo-search-or-create` chains to `/db-entity-change` |
| New error code needed | Invoke `/error-code-management` |
