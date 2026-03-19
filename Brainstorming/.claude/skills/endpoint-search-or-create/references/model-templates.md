# Request/Response Model Templates

Complete templates for creating request models, response models, and converters for the facade layer.

## Table of Contents

1. [Request Models](#request-models)
2. [Response Models](#response-models)
3. [Request Converters](#request-converters)
4. [Response Converters](#response-converters)
5. [Complete Example](#complete-example)

---

## Request Models

**Location:** `src/facade/request_models/{entity}_request.py`

### Basic Request Model

```python
from pydantic import BaseModel, Field


class Create{Entity}Request(BaseModel):
    """Request model for creating a new {entity}."""

    name: str = Field(..., description="Name of the {entity}")
    description: str | None = Field(None, description="Optional description")
    is_active: bool = Field(True, description="Whether the {entity} is active")
```

### Request with Validation

```python
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Literal


class {Entity}InfosRequest(BaseModel):
    """Request model for {entity} information."""

    civility: str = Field(..., description="User's civility (Mr., Mrs., etc.)")
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr = Field(..., description="Valid email address")
    language: Literal["fr", "en", "es", "de", "it", "pt"] | None = None
    theme: Literal["light", "dark", "auto"] | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()
```

### Request with Nested Objects

```python
from pydantic import BaseModel, Field
from typing import Optional


class AddressRequest(BaseModel):
    """Nested address request model."""

    street: str
    city: str
    postal_code: str
    country: str = "France"


class {Entity}WithAddressRequest(BaseModel):
    """Request model with nested address."""

    name: str
    address: AddressRequest | None = None
    tags: list[str] = Field(default_factory=list)
```

### Update Request (Partial)

```python
from pydantic import BaseModel


class Update{Entity}Request(BaseModel):
    """Request model for updating {entity} (all fields optional)."""

    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    metadata: dict | None = None
```

### Search/Filter Request

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal


class {Entity}SearchRequest(BaseModel):
    """Request model for searching {entities}."""

    query: str | None = Field(None, description="Text search query")
    status: Literal["active", "inactive", "pending"] | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    sort_by: Literal["created_at", "name", "updated_at"] = "created_at"
    sort_order: Literal["asc", "desc"] = "desc"
```

### Complex Nested Request

```python
from pydantic import BaseModel
from typing import Optional


class QueryContentRequest(BaseModel):
    """Content of a query."""

    query_text_content: str | None = None
    query_selected_text: str | None = None
    query_quick_action: str | None = None


class CourseContextRequest(BaseModel):
    """Course context information."""

    course_id: str
    section_id: str | None = None
    module_name: str | None = None


class UserAskNewQueryRequest(BaseModel):
    """Complete request for a new user query."""

    query: QueryContentRequest
    course_context: CourseContextRequest
```

---

## Response Models

**Location:** `src/facade/response_models/{entity}_response.py`

### Basic Response Model

```python
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class {Entity}Response(BaseModel):
    """Response model for {entity}.

    Attributes:
        id: Unique identifier (UUID)
        name: Name of the {entity}
        description: Description of the {entity}
        is_active: Whether the {entity} is active
        created_at: Creation timestamp
        updated_at: Last update timestamp
        deleted_at: Soft deletion timestamp
    """

    id: UUID | None = None
    name: str
    description: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
```

### Response with Nested Models

```python
from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime


class SchoolResponse(BaseModel):
    """Response model for School information."""

    id: UUID | None = None
    name: str
    address: str | None = None
    city: str | None = None
    country: str | None = None
    created_at: datetime | None = None


class UserPreferenceResponse(BaseModel):
    """Response model for UserPreference information."""

    id: UUID | None = None
    language: str | None = None
    theme: str | None = None
    timezone: str | None = None
    notifications_enabled: bool = True


class UserResponse(BaseModel):
    """Response model for User information."""

    id: UUID | None = None
    lms_user_id: str
    school: SchoolResponse | None = None
    preference: UserPreferenceResponse | None = None
    civility: str
    first_name: str
    last_name: str
    email: EmailStr
    extra_info: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
```

### Collection Response with Pagination

```python
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class {Entity}ItemResponse(BaseModel):
    """Single {entity} item in a list response."""

    id: UUID
    name: str
    status: str
    created_at: datetime | None = None


class {Entity}ListResponse(BaseModel):
    """Paginated list response for {entities}."""

    items: list[{Entity}ItemResponse]
    total_count: int
    page: int
    page_size: int
    has_next: bool
    has_previous: bool
```

### Response with Computed Fields

```python
from pydantic import BaseModel, computed_field
from uuid import UUID


class MessageResponse(BaseModel):
    """Response model for Message."""

    id: UUID | None = None
    thread_id: UUID | None = None
    role: str  # Converted from enum to string
    content: str
    selected_text: str | None = None
    quick_action: str | None = None  # Converted from enum to string
    elapsed_seconds: float | None = None
    created_at: datetime | None = None


class ThreadMessagesResponse(BaseModel):
    """Response model for thread with messages."""

    thread_id: str
    total_messages_count: int
    messages: list[MessageResponse]

    @computed_field
    @property
    def has_messages(self) -> bool:
        return len(self.messages) > 0
```

### Simple ID List Response

```python
from pydantic import BaseModel


class ThreadIdsResponse(BaseModel):
    """Response model for list of thread IDs."""

    threads_ids: list[str]
```

---

## Request Converters

**Location:** `src/facade/converters/{entity}_request_converter.py`

### Basic Request Converter

```python
from facade.request_models.{entity}_request import Create{Entity}Request, Update{Entity}Request
from models.{entity} import {Entity}


class {Entity}RequestConverter:
    """Converter for transforming {entity} requests to domain models."""

    @staticmethod
    def convert_request_to_{entity}(request: Create{Entity}Request) -> {Entity}:
        """Convert Create{Entity}Request to {Entity} model.

        Args:
            request: The request model containing {entity} information

        Returns:
            {Entity} domain model
        """
        return {Entity}(
            name=request.name,
            description=request.description,
            is_active=request.is_active,
        )

    @staticmethod
    def convert_update_request_to_{entity}(request: Update{Entity}Request, {entity}_id: str) -> {Entity}:
        """Convert Update{Entity}Request to {Entity} model.

        Args:
            request: The request model containing updated {entity} information
            {entity}_id: The ID of the {entity} to update

        Returns:
            {Entity} domain model with updated fields
        """
        from uuid import UUID

        return {Entity}(
            id=UUID({entity}_id),
            name=request.name,
            description=request.description,
            is_active=request.is_active,
        )
```

### Converter with Nested Models

```python
from facade.request_models.user_infos_request import UserInfosRequest, UserPreferencesRequest
from models.user import User
from models.school import School
from models.user_preference import UserPreference


class UserRequestConverter:
    """Converter for transforming user requests to domain models."""

    @staticmethod
    def convert_user_infos_request_to_user(user_infos: UserInfosRequest) -> User:
        """Convert UserInfosRequest to User model.

        Args:
            user_infos: The request model containing user information

        Returns:
            User model with school but no preferences
        """
        # Create nested School model from request
        school = School(name=user_infos.school_name) if user_infos.school_name else None

        # Create User model
        return User(
            school=school,
            preference=None,  # Preferences are set separately
            lms_user_id=user_infos.lms_user_id,
            civility=user_infos.civility,
            first_name=user_infos.first_name,
            last_name=user_infos.last_name,
            email=user_infos.email,
        )

    @staticmethod
    def convert_user_preferences_request_to_model(
        preferences_request: UserPreferencesRequest,
        user_id: str
    ) -> UserPreference:
        """Convert UserPreferencesRequest to UserPreference model.

        Args:
            preferences_request: The request model containing user preferences
            user_id: The UUID of the user these preferences belong to

        Returns:
            UserPreference model
        """
        from uuid import UUID

        return UserPreference(
            user_id=UUID(user_id),
            language=preferences_request.language,
            theme=preferences_request.theme,
            timezone=preferences_request.timezone,
            notifications_enabled=preferences_request.notifications_enabled,
            email_notifications=preferences_request.email_notifications,
        )
```

---

## Response Converters

**Location:** `src/facade/converters/{entity}_response_converter.py`

### Basic Response Converter

```python
from models.{entity} import {Entity}
from facade.response_models.{entity}_response import {Entity}Response


class {Entity}ResponseConverter:
    """Converter for transforming domain models to response models."""

    @staticmethod
    def convert_{entity}_to_response({entity}: {Entity}) -> {Entity}Response:
        """Convert {Entity} domain model to {Entity}Response.

        Args:
            {entity}: The domain model containing {entity} information

        Returns:
            {Entity}Response model for API response
        """
        return {Entity}Response(
            id={entity}.id,
            name={entity}.name,
            description={entity}.description,
            is_active={entity}.is_active,
            created_at={entity}.created_at,
            updated_at={entity}.updated_at,
            deleted_at={entity}.deleted_at,
        )
```

### Converter with Nested Models

```python
from models.user import User
from models.school import School
from models.user_preference import UserPreference
from facade.response_models.user_response import UserResponse, SchoolResponse, UserPreferenceResponse


class UserResponseConverter:
    """Converter for transforming domain models to response models."""

    @staticmethod
    def convert_user_to_response(user: User) -> UserResponse:
        """Convert User domain model to UserResponse.

        Args:
            user: The domain model containing user information

        Returns:
            UserResponse model for API response
        """
        # Convert nested School if present
        school_response = None
        if user.school:
            school_response = UserResponseConverter.convert_school_to_response(user.school)

        # Convert nested UserPreference if present
        preference_response = None
        if user.preference:
            preference_response = UserResponseConverter.convert_user_preference_to_response(user.preference)

        # Create UserResponse
        return UserResponse(
            id=user.id,
            lms_user_id=user.lms_user_id,
            school=school_response,
            preference=preference_response,
            civility=user.civility,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            date_of_birth=user.date_of_birth,
            extra_info=user.extra_info,
            created_at=user.created_at,
            updated_at=user.updated_at,
            deleted_at=user.deleted_at,
        )

    @staticmethod
    def convert_school_to_response(school: School) -> SchoolResponse:
        """Convert School domain model to SchoolResponse."""
        return SchoolResponse(
            id=school.id,
            name=school.name,
            address=school.address,
            city=school.city,
            postal_code=school.postal_code,
            country=school.country,
            phone=school.phone,
            email=school.email,
            created_at=school.created_at,
            updated_at=school.updated_at,
            deleted_at=school.deleted_at,
        )

    @staticmethod
    def convert_user_preference_to_response(preference: UserPreference) -> UserPreferenceResponse:
        """Convert UserPreference domain model to UserPreferenceResponse."""
        return UserPreferenceResponse(
            id=preference.id,
            user_id=preference.user_id,
            language=preference.language,
            theme=preference.theme,
            timezone=preference.timezone,
            notifications_enabled=preference.notifications_enabled,
            email_notifications=preference.email_notifications,
            created_at=preference.created_at,
            updated_at=preference.updated_at,
            deleted_at=preference.deleted_at,
        )
```

### Converter with Enum Handling

```python
from models.thread import Thread
from models.message import Message
from facade.response_models.thread_response import MessageResponse, ThreadIdsResponse, ThreadMessagesResponse


class ThreadResponseConverter:
    """Converter for transforming domain models to thread response models."""

    @staticmethod
    def convert_thread_ids_to_response(thread_ids: list) -> ThreadIdsResponse:
        """Convert list of thread IDs to ThreadIdsResponse."""
        return ThreadIdsResponse(threads_ids=[str(thread_id) for thread_id in thread_ids])

    @staticmethod
    def convert_message_to_response(message: Message) -> MessageResponse:
        """Convert Message domain model to MessageResponse.

        Note: Enum values are converted to their string representation.
        """
        return MessageResponse(
            id=message.id,
            thread_id=message.thread_id,
            role=message.role.name,  # Enum → string
            content=message.content,
            selected_text=message.selected_text,
            quick_action=message.quick_action.name if message.quick_action else None,  # Optional enum → string
            elapsed_seconds=message.elapsed_seconds,
            created_at=message.created_at,
            updated_at=message.updated_at,
            deleted_at=message.deleted_at,
        )

    @staticmethod
    def convert_thread_to_messages_response(
        thread: Thread,
        total_messages_count: int | None = None
    ) -> ThreadMessagesResponse:
        """Convert Thread to ThreadMessagesResponse with pagination."""
        messages_response = [
            ThreadResponseConverter.convert_message_to_response(msg)
            for msg in thread.messages
        ]

        if total_messages_count is None:
            total_messages_count = len(thread.messages)

        return ThreadMessagesResponse(
            thread_id=str(thread.id),
            total_messages_count=total_messages_count,
            messages=messages_response,
        )
```

### Converter for List Responses

```python
from models.{entity} import {Entity}
from facade.response_models.{entity}_response import {Entity}Response


class {Entity}ResponseConverter:
    """Converter for transforming domain models to response models."""

    @staticmethod
    def convert_{entity}_to_response({entity}: {Entity}) -> {Entity}Response:
        """Convert single {entity} to response."""
        return {Entity}Response(
            id={entity}.id,
            name={entity}.name,
            # ... other fields
        )

    @staticmethod
    def convert_list_to_response({entities}: list[{Entity}]) -> list[{Entity}Response]:
        """Convert list of {entities} to list of responses."""
        return [
            {Entity}ResponseConverter.convert_{entity}_to_response(e)
            for e in {entities}
        ]
```

---

## Complete Example

### New "Notification" Feature

**1. Request Model** (`src/facade/request_models/notification_request.py`):

```python
from pydantic import BaseModel, Field


class CreateNotificationRequest(BaseModel):
    """Request model for creating a notification."""

    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=2000)
    notification_type: str = "info"


class MarkNotificationReadRequest(BaseModel):
    """Request model for marking notification as read."""

    notification_ids: list[str]
```

**2. Response Model** (`src/facade/response_models/notification_response.py`):

```python
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class NotificationResponse(BaseModel):
    """Response model for Notification."""

    id: UUID | None = None
    user_id: UUID | None = None
    title: str
    message: str
    notification_type: str
    is_read: bool = False
    created_at: datetime | None = None


class NotificationListResponse(BaseModel):
    """Response model for list of notifications."""

    notifications: list[NotificationResponse]
    unread_count: int
    total_count: int
```

**3. Request Converter** (`src/facade/converters/notification_request_converter.py`):

```python
from uuid import UUID
from facade.request_models.notification_request import CreateNotificationRequest
from models.notification import Notification


class NotificationRequestConverter:
    """Converter for notification requests."""

    @staticmethod
    def convert_request_to_notification(
        request: CreateNotificationRequest,
        user_id: UUID
    ) -> Notification:
        """Convert CreateNotificationRequest to Notification model."""
        return Notification(
            user_id=user_id,
            title=request.title,
            message=request.message,
            notification_type=request.notification_type,
            is_read=False,
        )
```

**4. Response Converter** (`src/facade/converters/notification_response_converter.py`):

```python
from models.notification import Notification
from facade.response_models.notification_response import NotificationResponse, NotificationListResponse


class NotificationResponseConverter:
    """Converter for notification responses."""

    @staticmethod
    def convert_notification_to_response(notification: Notification) -> NotificationResponse:
        """Convert Notification model to response."""
        return NotificationResponse(
            id=notification.id,
            user_id=notification.user_id,
            title=notification.title,
            message=notification.message,
            notification_type=notification.notification_type,
            is_read=notification.is_read,
            created_at=notification.created_at,
        )

    @staticmethod
    def convert_list_to_response(
        notifications: list[Notification],
        unread_count: int
    ) -> NotificationListResponse:
        """Convert notification list to response with counts."""
        return NotificationListResponse(
            notifications=[
                NotificationResponseConverter.convert_notification_to_response(n)
                for n in notifications
            ],
            unread_count=unread_count,
            total_count=len(notifications),
        )
```
