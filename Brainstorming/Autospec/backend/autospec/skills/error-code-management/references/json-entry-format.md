# JSON Catalog Entry Format

## File selection

Use the app's existing layout: a single `errors/error_messages/errors.json`, or a user-facing vs
internal split (e.g. `front_office.json` / `back_office.json`).

**Rule:** if an end user can trigger the error → user-facing file; if only admin/internal/cron
triggers it → internal file.

## Entry structure

```json
{
  "category_name": {
    "ERROR_CODE": {
      "message": "User-facing message",
      "log_message": "Technical English message with {variable} placeholders",
      "http_status": 400
    }
  }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `message` | No | User-facing text. If omitted, uses the global default. |
| `log_message` | Yes | Technical log line. Supports `{variable}` substitution. |
| `http_status` | Yes | 400, 401, 403, 404, 409, 429, 500, 502, 503, 504. |

## Variable substitution

```python
# "log_message": "Not found: user with id '{user_id}' does not exist"
raise NotFoundError("NOT_FOUND_USER", user_id="12345")
# → "Not found: user with id '12345' does not exist"
```

A missing variable leaves the template as-is (no crash).

## Categories

| Category | HTTP | Usage |
|----------|------|-------|
| `validation` | 400 | Input validation |
| `authentication` | 401 | Auth failures |
| `authorization` | 403 | Permission denied |
| `not_found` | 404 | Resource not found |
| `conflict` | 409 | Duplicate resources |
| `quota` | 429 | Rate limiting |
| `business` | 400 | Business-rule violations |
| `service` | 503/504 | Service unavailable / timeout |
| `external_api` | 502/504 | External API failures |
| `internal` | 500 | Unexpected server / config / persistence errors |

## Naming convention

`CATEGORY_DESCRIPTION` in SCREAMING_SNAKE_CASE: `VALIDATION_INVALID_UUID`, `AUTH_INVALID_TOKEN`,
`AUTHZ_ACCESS_DENIED`, `NOT_FOUND_USER`, `CONFLICT_RESOURCE_ALREADY_EXISTS`, `QUOTA_DAILY_EXCEEDED`,
`EXTERNAL_API_ERROR`, `SERVICE_TIMEOUT`, `INTERNAL_SERVER_ERROR`.

## Full example

**1. Add the entry** (under `external_api`):

```json
"EXTERNAL_API_ERROR": {
  "message": "Error communicating with the external service",
  "log_message": "External API error: {service} call failed - {details}",
  "http_status": 502
}
```

**2. Raise it:**

```python
from errors import ExternalApiException

try:
    response = await client.post(url, json=body)
    response.raise_for_status()
except httpx.HTTPStatusError as e:
    raise ExternalApiException(
        "EXTERNAL_API_ERROR",
        service="payments",
        details=f"HTTP {e.response.status_code}: {e.response.text}",
    ) from e
```

**3. Result:** user sees the `message`; logs show the formatted `log_message`; HTTP 502;
`exception.details == {"service": "payments", "details": "HTTP 401: Unauthorized"}`.
