# Exception Class Hierarchy

A single base exception (`AppException` / whatever the app names it) with typed subclasses. Naming:
**"Error" suffix → 4xx** (client made a bad request); **"Exception" suffix → 5xx** (server failed).

```
AppException (base)
├── ValidationError          (400)
├── AuthenticationError      (401)
├── AuthorizationError       (403)
├── NotFoundError            (404)
├── ConflictError            (409)
├── QuotaExceededError       (429)
├── ExternalApiException     (502)
├── ServiceException         (503/504)
└── InternalServerException  (500)
```

| Class | Default HTTP | Typical codes |
|-------|-------------|---------------|
| `ValidationError` | 400 | `VALIDATION_INVALID_UUID`, `VALIDATION_MISSING_FIELD` |
| `AuthenticationError` | 401 | `AUTH_USER_NOT_AUTHENTICATED`, `AUTH_INVALID_TOKEN` |
| `AuthorizationError` | 403 | `AUTHZ_ACCESS_DENIED` |
| `NotFoundError` | 404 | `NOT_FOUND_USER`, `NOT_FOUND_{ENTITY}` |
| `ConflictError` | 409 | `CONFLICT_RESOURCE_ALREADY_EXISTS` |
| `QuotaExceededError` | 429 | `QUOTA_DAILY_EXCEEDED` |
| `ExternalApiException` | 502 | `EXTERNAL_API_ERROR` |
| `ServiceException` | 503 | `SERVICE_TIMEOUT`, `SERVICE_TEMPORARILY_UNAVAILABLE` |
| `InternalServerException` | 500 | `INTERNAL_SERVER_ERROR`, `INTERNAL_{ENTITY}_PERSISTENCE_FAILED` |

## Base class API

```python
class AppException(Exception):
    def __init__(self, error_code: str, custom_message: str | None = None,
                 http_status: int | None = None, **kwargs):
        self.error_code = error_code     # "VALIDATION_INVALID_UUID"
        self.message = "..."             # user-facing, from catalog or custom_message
        self.log_message = "..."         # technical, from catalog
        self.http_status = 400           # from catalog or http_status param
        self.details = kwargs            # all extra kwargs

    def to_dict(self) -> dict:
        return {"code": self.error_code, "message": self.message,
                "http_status": self.http_status, "details": self.details}
```

## Key behaviors

- `str(exception)` returns `self.message` (user-facing), NOT the details. Use `exception.details`,
  `exception.error_code`, `exception.log_message`, or `exception.to_dict()` for the rest.
- Override the catalog status per-raise: `raise ExternalApiException("EXTERNAL_API_ERROR", http_status=504)`.
- Bypass the catalog entirely: `raise AppException("CUSTOM", custom_message="...", http_status=400)`.

## Middleware

The centralized middleware (app factory) catches every `AppException` subclass: builds the body from
`to_dict()`, returns a `JSONResponse` with `http_status`, logs `log_message`. Non-`AppException`
errors become a generic 500.
