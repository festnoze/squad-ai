from pydantic import BaseModel, EmailStr
from typing import Literal


class UserPreferencesRequest(BaseModel):
    """Request model for user preferences (separate from user info)"""

    language: Literal["fr", "en", "es", "de", "it", "pt"] | None = None
    theme: Literal["light", "dark", "auto"] | None = None
    timezone: str | None = None
    notifications_enabled: bool = True
    email_notifications: bool = True


class UserInfosRequest(BaseModel):
    """Request model for user information"""

    civility: str
    first_name: str
    last_name: str
    email: EmailStr
    school_name: str
    lms_user_id: str
