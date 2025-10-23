from uuid import UUID
from models.base_model import IdStatefulBaseModel


class UserPreference(IdStatefulBaseModel):
    """UserPreference model representing user preferences and settings.

    Inherits common fields (id, created_at, updated_at, deleted_at) from IdStatefulBaseModel.

    Attributes:
        user_id: Foreign key reference to the User these preferences belong to
        language: Preferred language code (e.g., 'en', 'fr', 'es')
        theme: UI theme preference (e.g., 'light', 'dark', 'auto')
        timezone: User's timezone (e.g., 'Europe/Paris', 'America/New_York')
        notifications_enabled: Whether to enable notifications
        email_notifications: Whether to receive email notifications
    """

    user_id: UUID | None = None
    language: str | None = None
    theme: str | None = None
    timezone: str | None = None
    notifications_enabled: bool = True
    email_notifications: bool = True
