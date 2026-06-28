# Service Search Patterns

## Find service files / classes

```
Glob: application/*_service.py
Grep: class {Entity}Service
```

## Method search

```
Grep: async def a{action}_{entity}
Grep: async def a{action}_.*{entity}     # action may be qualified, e.g. aget_retrieve_or_create_user
```

## Check sub-services before creating

If the entity's own service has no match, search related services for a reusable operation —
duplicating orchestration logic across services is the main thing this skill prevents.

```
Grep: async def a.*{related_concept}     # across all application/*_service.py
```

## FOUND vs CREATE

A match counts as reuse only if its parameters and return type fit the use-case AND its business
logic does not conflict. Otherwise add a new method (or extend the existing one deliberately).
