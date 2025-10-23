from pydantic import BaseModel, EmailStr
from datetime import datetime
from uuid import UUID


class SchoolResponse(BaseModel):
    """Response model for School information.

    Attributes:
        id: Unique identifier (UUID)
        name: Name of the school
        address: Physical address of the school
        city: City where the school is located
        postal_code: Postal/ZIP code of the school
        country: Country where the school is located
        phone: Contact phone number
        email: Contact email address
        created_at: Timestamp when the record was created
        updated_at: Timestamp when the record was last updated
        deleted_at: Timestamp when the record was soft-deleted
    """

    id: UUID | None = None
    name: str
    address: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country: str | None = None
    phone: str | None = None
    email: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class UserPreferenceResponse(BaseModel):
    """Response model for UserPreference information.

    Attributes:
        id: Unique identifier (UUID)
        user_id: Foreign key reference to the User
        language: Preferred language code (e.g., 'en', 'fr', 'es')
        theme: UI theme preference (e.g., 'light', 'dark', 'auto')
        timezone: User's timezone (e.g., 'Europe/Paris', 'America/New_York')
        notifications_enabled: Whether to enable notifications
        email_notifications: Whether to receive email notifications
        created_at: Timestamp when the record was created
        updated_at: Timestamp when the record was last updated
        deleted_at: Timestamp when the record was soft-deleted
    """

    id: UUID | None = None
    user_id: UUID | None = None
    language: str | None = None
    theme: str | None = None
    timezone: str | None = None
    notifications_enabled: bool = True
    email_notifications: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class UserResponse(BaseModel):
    """Response model for User information.

    Attributes:
        id: Unique identifier (UUID)
        lms_user_id: Unique user identifier from LMS
        school: School this user belongs to
        preference: User preferences (one-to-one relationship)
        civility: User's civility/title
        first_name: User's first name
        last_name: User's last name
        email: User's email address
        created_at: Timestamp when the record was created
        updated_at: Timestamp when the record was last updated
        deleted_at: Timestamp when the record was soft-deleted
    """

    id: UUID | None = None
    lms_user_id: str
    school: SchoolResponse | None = None
    preference: UserPreferenceResponse | None = None
    civility: str
    first_name: str
    last_name: str
    email: EmailStr
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
