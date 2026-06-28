---
name: architecture
description: |
  Default 3-layer backend architecture for generated apps: facade → application →
  infrastructure, with domain models shared across layers. Encodes folder layout,
  naming conventions (every async method is `a`-prefixed), where each class lives,
  and how to register a new component.

  Use when:
  - Deciding which layer a new class/function belongs to
  - Naming a router/service/repository/entity or an async method
  - Wiring a new component into the app (router include, dependency wiring)
  - Reviewing whether code respects separation of concerns

  Triggers: architecture, 3-layer, layer, couche, où placer, naming, convention,
  register, router, service, repository, entity, facade, application, infrastructure
---

# 3-layer backend architecture

Generated Python apps (managed by `uv`, FastAPI for HTTP) follow three layers plus
shared domain models. Dependencies point INWARD only: facade → application →
infrastructure. Never call a repository from a router; never import FastAPI in a
service or repository.

```
<package>/
  facade/            # HTTP boundary
    *_router.py            # FastAPI routers (one per resource)
    request_models/        # Pydantic input models  {Action}{Name}Request
    response_models/       # Pydantic output models  {Name}Response
  application/         # business logic / use-cases
    *_service.py           # {Name}Service — orchestrates repos + other services
  infrastructure/     # persistence + external systems
    *_repository.py        # {Name}Repository — data access (CRUD)
    entities/              # {Name}Entity — persistence shape (ORM/row/record)
    converters/            # entity <-> domain model mapping
  models/             # domain dataclasses shared by all layers ({Name})
  main.py             # executable entry point (starts the server / CLI)
```

## Rules
- **A facade method** validates input, calls ONE service, serializes the result,
  maps domain errors to HTTP status codes. No business logic.
- **A service method** is one use-case. It orchestrates repositories and other
  services; it holds the business rules. No HTTP, no SQL.
- **A repository method** does data access only (get/create/update/delete). No
  business rules.
- **Domain models** (`models/`) are plain dataclasses/Pydantic — the language the
  layers speak to each other. Entities (`infrastructure/entities/`) are the
  storage shape; convert at the infrastructure boundary.

## Naming
- Files: `user_router.py`, `user_service.py`, `user_repository.py`,
  `user_entity.py`. Classes: `UserService`, `UserRepository`, `UserEntity`.
- **Every async method starts with `a`** (never an `_async` suffix):
  `async def acreate_user(...)`, `async def aget_user_by_id(...)`,
  `async def adoes_user_exist_by_email(...)`. This applies in EVERY layer.

## Registering a new component
1. Entity → make it importable from `infrastructure/entities/`.
2. Repository / Service → construct them where the app wires its dependencies
   (the composition root / DI setup), so a service receives its repository.
3. Router → `app.include_router(user_router)` where the app assembles routers.

## Adding a feature, layer by layer (inside-out build order)
entity (`db-entity-change`) → repository (`repo-search-or-create`) → service
(`service-search-or-create`) → endpoint (`endpoint-search-or-create`) → tests
(`test-generator`). Reuse before creating: each `*-search-or-create` skill checks
for an existing method first (DRY). For a trivial pure-logic feature, skip the
persistence layers — a single service function may be enough.
