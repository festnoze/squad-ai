# Repository Search Patterns

## Find repository files / classes

```
Glob: infrastructure/*_repository.py
Grep: class {Entity}Repository
```

## Method search by operation

| Operation | Grep pattern | Examples |
|-----------|--------------|----------|
| GET single | `async def aget_{entity}_by_` | `aget_user_by_id`, `aget_user_by_email` |
| GET many | `async def aget_{entities}` / `aget_all_` | `aget_all_roles`, `aget_users_by_school_id` |
| CREATE | `async def acreate_{entity}` | `acreate_user`, `acreate_thread` |
| UPDATE | `async def aupdate_{entity}` | `aupdate_user` |
| DELETE | `async def adelete_{entity}` | `adelete_message_by_id` |
| UPSERT | `async def acreate_or_update_` / `acreate_or_get_` | `acreate_or_update_user_preference` |
| CHECK | `async def adoes_{entity}_exist` / `_exists` | `adoes_user_exist_by_email` |
| COUNT | `async def aget_{entity}_count` / `func.count` | `aget_thread_messages_count` |

## Search by parameter or helper

```
Grep: async def a.*\(self, {param_name}:     # methods taking a given param
Grep: async def _a.*_query\(                  # private entity-returning helpers
```

## Before deciding FOUND vs CREATE

Verify the candidate method's parameters match the needed inputs and its return type matches the
expected output. A name match with the wrong signature is NOT a reuse — add a new method instead.
