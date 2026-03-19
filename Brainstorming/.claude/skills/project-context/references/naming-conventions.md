# Naming Conventions Reference

Comprehensive naming guide for all SkillForge components.

## File Naming

### By Component Type

| Component | Pattern | Example |
|-----------|---------|---------|
| Entity | `{name}_entity.py` | `notification_entity.py` |
| Repository | `{name}_repository.py` | `notification_repository.py` |
| Service | `{name}_service.py` | `notification_service.py` |
| Router | `{name}_router.py` | `notification_router.py` |
| Model | `{name}.py` | `notification.py` |
| Converter | `{name}_converters.py` | `notification_converters.py` |
| Request Model | `{name}_request.py` | `notification_request.py` |
| Response Model | `{name}_response.py` | `notification_response.py` |

**Rules:**
- Use `snake_case` for all file names
- Use singular form for component name (`user`, not `users`)
- Suffix indicates component type

---

## Class Naming

### By Component Type

| Component | Pattern | Example |
|-----------|---------|---------|
| Entity | `{Name}Entity` | `NotificationEntity` |
| Repository | `{Name}Repository` | `NotificationRepository` |
| Service | `{Name}Service` | `NotificationService` |
| Router | `{name}_router` | `notification_router` |
| Model | `{Name}` | `Notification` |
| Converter | `{Name}Converters` | `NotificationConverters` |
| Request Model | `{Action}{Name}Request` | `CreateNotificationRequest` |
| Response Model | `{Name}Response` | `NotificationResponse` |

**Rules:**
- Use `PascalCase` for class names
- Use `snake_case` for router variable names
- Request models include action verb (Create, Update, Delete)

---

## Method Naming

### Async Method Prefix

**CRITICAL RULE:** All async methods MUST use `a` prefix, NOT `_async` suffix.

```python
# CORRECT
async def acreate_user(...)
async def aget_by_id(...)
async def aupdate_notification(...)

# WRONG - DO NOT USE
async def create_user_async(...)  # Wrong: _async suffix
async def async_get_by_id(...)    # Wrong: async_ prefix
```

### Standard CRUD Patterns

| Operation | Method Pattern | Example |
|-----------|---------------|---------|
| Create | `async def acreate_{name}()` | `acreate_notification()` |
| Read (single) | `async def aget_{name}_by_{field}()` | `aget_user_by_id()` |
| Read (list) | `async def alist_{names}()` | `alist_notifications()` |
| Update | `async def aupdate_{name}()` | `aupdate_notification()` |
| Delete | `async def adelete_{name}()` | `adelete_notification()` |

### Query Patterns

| Query Type | Method Pattern | Example |
|------------|---------------|---------|
| By ID | `aget_{name}_by_id()` | `aget_user_by_id()` |
| By field | `aget_{name}_by_{field}()` | `aget_user_by_email()` |
| By FK | `aget_{names}_by_{parent}_id()` | `aget_messages_by_thread_id()` |
| With filter | `alist_{names}_with_{filter}()` | `alist_threads_with_status()` |
| Exists check | `aexists_{name}()` | `aexists_notification()` |
| Count | `acount_{names}()` | `acount_messages()` |

### Converter Method Patterns

```python
class NotificationConverters:
    @staticmethod
    def convert_entity_to_model(entity: NotificationEntity) -> Notification:
        ...

    @staticmethod
    def convert_model_to_entity(model: Notification) -> NotificationEntity:
        ...

    @staticmethod
    def convert_request_to_model(request: CreateNotificationRequest) -> Notification:
        ...

    @staticmethod
    def convert_model_to_response(model: Notification) -> NotificationResponse:
        ...
```

---

## Database Naming

### Table Names

| Pattern | Example |
|---------|---------|
| `{entities}` (plural snake_case) | `notifications` |

```python
class NotificationEntity(StatefulBase):
    __tablename__ = "notifications"  # plural
```

### Column Names

| Type | Pattern | Example |
|------|---------|---------|
| Primary key | `id` | `id: Mapped[UUID]` |
| Foreign key | `{entity}_id` | `user_id: Mapped[UUID]` |
| Boolean | `is_{property}` | `is_read: Mapped[bool]` |
| Status | `{name}_status` | `processing_status: Mapped[str]` |
| Timestamps | `{action}_at` | `created_at`, `sent_at` |

### Index Names

| Type | Pattern | Example |
|------|---------|---------|
| Single column | `ix_{table}_{column}` | `ix_notifications_user_id` |
| Composite | `ix_{table}_{col1}_{col2}` | `ix_messages_thread_user` |
| Unique | `uq_{table}_{column}` | `uq_users_email` |

---

## API Naming

### Endpoint Paths

| Pattern | Example |
|---------|---------|
| Resource collection | `GET /{resources}` | `GET /notifications` |
| Resource by ID | `GET /{resources}/{id}` | `GET /notifications/{id}` |
| Create resource | `POST /{resources}` | `POST /notifications` |
| Update resource | `PATCH /{resources}/{id}` | `PATCH /notifications/{id}` |
| Delete resource | `DELETE /{resources}/{id}` | `DELETE /notifications/{id}` |
| Nested resource | `GET /{parent}/{id}/{children}` | `GET /threads/{id}/messages` |

### Router Handler Names

| HTTP Method | Pattern | Example |
|-------------|---------|---------|
| GET (list) | `alist_{resources}` | `alist_notifications` |
| GET (single) | `aget_{resource}` | `aget_notification` |
| POST | `acreate_{resource}` | `acreate_notification` |
| PATCH | `aupdate_{resource}` | `aupdate_notification` |
| DELETE | `adelete_{resource}` | `adelete_notification` |

---

## Request/Response Model Naming

### Request Models

| Action | Pattern | Example |
|--------|---------|---------|
| Create | `Create{Name}Request` | `CreateNotificationRequest` |
| Update | `Update{Name}Request` | `UpdateNotificationRequest` |
| Query | `Query{Name}Request` | `QueryNotificationsRequest` |
| Bulk | `Bulk{Action}{Name}Request` | `BulkCreateNotificationsRequest` |

### Response Models

| Type | Pattern | Example |
|------|---------|---------|
| Single | `{Name}Response` | `NotificationResponse` |
| List | `{Name}ListResponse` | `NotificationListResponse` |
| Summary | `{Name}SummaryResponse` | `NotificationSummaryResponse` |

---

## Common Abbreviations

Avoid abbreviations except for these commonly accepted ones:

| Abbreviation | Full Form | Usage |
|--------------|-----------|-------|
| `id` | identifier | Primary/foreign keys |
| `repo` | repository | Variable names only |
| `db` | database | Variable names only |
| `config` | configuration | Class names OK |
| `auth` | authentication | Class names OK |
| `admin` | administrator | Class names OK |

**Rule:** In class names, spell it out. In variable names, abbreviations are OK.

```python
# Class names - spell out
class AuthenticationService:  # Not AuthService

# Variable names - abbreviations OK
auth_service = AuthenticationService()
user_repo = UserRepository()
```

---

## Examples Summary

### Complete Feature Example: Notification

```
Files:
  src/infrastructure/entities/notification_entity.py
  src/infrastructure/converters/notification_converters.py
  src/infrastructure/notification_repository.py
  src/models/notification.py
  src/application/notification_service.py
  src/facade/notification_router.py
  src/facade/request_models/notification_request.py
  src/facade/response_models/notification_response.py

Classes:
  NotificationEntity
  NotificationConverters
  NotificationRepository
  Notification
  NotificationService
  notification_router (variable)
  CreateNotificationRequest
  UpdateNotificationRequest
  NotificationResponse

Methods:
  async def acreate_notification(...)
  async def aget_notification_by_id(...)
  async def alist_notifications_by_user_id(...)
  async def aupdate_notification(...)
  async def adelete_notification(...)

Table:
  notifications (plural)

Endpoints:
  POST   /notifications
  GET    /notifications/{id}
  GET    /user/{user_id}/notifications
  PATCH  /notifications/{id}
  DELETE /notifications/{id}
```
