# Endpoint Search Patterns

## Find router files

```
Glob: facade/*_router.py
```

## Search by HTTP method + path

```
Grep: @{router}\.get\(".*{path}
Grep: @{router}\.post\(".*{path}
Grep: @{router}\.patch\(".*{path}
Grep: @{router}\.put\(".*{path}
Grep: @{router}\.delete\(".*{path}
```

## Search by handler name

```
Grep: async def a{action}_{entity}
```

## FOUND vs CREATE

Reuse only when the method, path, and response shape match the need. A handler with the same name but
a different HTTP method or response model is not a match — add a new endpoint.

## Where models / converters / registration live

| Artifact | Location |
|----------|----------|
| Router | `facade/{entity}_router.py` |
| Request model | `facade/request_models/{entity}_request.py` |
| Response model | `facade/response_models/{entity}_response.py` |
| Converters | `facade/converters/{entity}_request_converter.py`, `{entity}_response_converter.py` |
| Router registration | app factory (`create_app()` / where routers are included) |
