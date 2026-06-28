---
name: error-code-management
description: |
  Manage centralized error codes for the generated app: typed exception classes, a JSON message
  catalog, and a singleton handler that resolves codes to messages + HTTP status. Use when: creating
  a new error code, raising a typed exception (ValidationError, NotFoundError, ConflictError,
  ExternalApiException, ...), debugging "Unknown error code" warnings, or adding messages to the JSON
  catalog. Triggers: error code, add error, new exception, unknown error code, error message, error
  catalog, raise error, error handling.
---

# Error Code Management

The app uses a **centralized error system**: a JSON message catalog + a singleton handler +
typed exception classes. Every error code raised in code MUST exist in the catalog, or the user gets
a generic message and a WARNING is logged.

```
raise SomeError("ERROR_CODE", **kwargs)
        │  base Exception.__init__ → ErrorMessageHandler.get_error(code, **kwargs)
        ▼
Lookup code in the catalog (loaded from JSON)
   ├─ Found     → format message + log_message with kwargs, set http_status
   └─ Not found → WARNING "Unknown error code: XXX", generic message, http_status 500
```

## Add a new error code

1. Pick the catalog file. Use a single `errors.json` if the app has one, or split user-facing vs
   internal (e.g. `front_office.json` / `back_office.json`) if it already does. Rule: if an end user
   can trigger it → user-facing file; if only admin/internal/cron triggers it → internal file.
2. Pick the category: `validation`, `authentication`, `authorization`, `not_found`, `conflict`,
   `quota`, `service`, `external_api`, `business`, `internal`.
3. Add the entry (format below).
4. Raise the matching typed exception with kwargs that fill the `{variable}` placeholders.

### Entry format

```json
{
  "category_name": {
    "YOUR_ERROR_CODE": {
      "message": "User-facing message (omit to use the global default)",
      "log_message": "Technical English message with {variable} substitution",
      "http_status": 400
    }
  }
}
```

- `message` (optional): user-facing text; if omitted, falls back to a global default.
- `log_message` (required): technical log line; supports `{variable}` substitution from kwargs.
- `http_status` (required): HTTP status returned to the client.

See [references/json-entry-format.md](references/json-entry-format.md) for categories, naming, and a
full example.

## Raise an exception

```python
from errors import ValidationError, NotFoundError, ConflictError, ExternalApiException

raise ValidationError("VALIDATION_INVALID_UUID", value="abc123", field="thread_id")  # 400
raise NotFoundError("NOT_FOUND_USER", user_id=user_id)                               # 404
raise ConflictError("CONFLICT_RESOURCE_ALREADY_EXISTS")                              # 409
raise ExternalApiException("EXTERNAL_API_ERROR", details=error_msg)                  # 502
```

kwargs are (1) substituted into `{variable}` placeholders in `message`/`log_message`, and (2) stored
in `exception.details` for programmatic access. See
[references/exception-classes.md](references/exception-classes.md) for the full hierarchy and
HTTP-status mapping.

## Common mistake: losing details

`str(exception)` returns the user-facing `message`, NOT the kwargs/details. To capture full info in
logs or an `error_message` field:

```python
if hasattr(e, "details") and e.details:
    error_message = f"{e.error_code}: {e.details}"
else:
    error_message = str(e)
```

## File map (adapt to the app's actual layout)

| File | Purpose |
|------|---------|
| `errors/error_messages/*.json` | Error catalog (one file, or user-facing vs internal split) |
| `errors/error_message_handler.py` | Singleton: loads JSON, resolves codes to message + status |
| `errors/base_exception.py` | Base exception class (`error_code`, `message`, `log_message`, `http_status`, `details`, `to_dict()`) |
| `errors/__init__.py` | Exports all exception classes |

The centralized exception middleware (registered in the app factory) catches every base-exception
subclass, calls `to_dict()`, returns a `JSONResponse` with its `http_status`, and logs `log_message`.
Non-typed errors become a generic 500.
