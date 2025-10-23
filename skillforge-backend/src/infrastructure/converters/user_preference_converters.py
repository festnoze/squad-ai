from datetime import timezone
from infrastructure.entities.user_preference_entity import UserPreferenceEntity
from models.user_preference import UserPreference


class UserPreferenceConverters:
    @staticmethod
    def convert_user_preference_entity_to_model(preference_entity: UserPreferenceEntity) -> UserPreference:
        """Convert a UserPreferenceEntity to a UserPreference model.

        Args:
            preference_entity: The database entity to convert

        Returns:
            UserPreference model instance with timezone-aware datetimes
        """
        return UserPreference(
            id=preference_entity.id,
            user_id=preference_entity.user_id,
            language=preference_entity.language,
            theme=preference_entity.theme,
            timezone=preference_entity.timezone,
            notifications_enabled=preference_entity.notifications_enabled,
            email_notifications=preference_entity.email_notifications,
            created_at=preference_entity.created_at.replace(tzinfo=timezone.utc),
            updated_at=preference_entity.updated_at.replace(tzinfo=timezone.utc) if preference_entity.updated_at else None,
            deleted_at=preference_entity.deleted_at.replace(tzinfo=timezone.utc) if preference_entity.deleted_at else None,
        )

    @staticmethod
    def convert_user_preference_model_to_entity(preference: UserPreference) -> UserPreferenceEntity:
        """Convert a UserPreference model to a UserPreferenceEntity.

        Args:
            preference: The UserPreference model to convert

        Returns:
            UserPreferenceEntity instance with timezone-naive datetimes (for database storage)
        """
        return UserPreferenceEntity(
            id=preference.id,
            user_id=preference.user_id,
            language=preference.language,
            theme=preference.theme,
            timezone=preference.timezone,
            notifications_enabled=preference.notifications_enabled,
            email_notifications=preference.email_notifications,
            created_at=preference.created_at.replace(tzinfo=None) if preference.created_at else None,
            updated_at=preference.updated_at.replace(tzinfo=None) if preference.updated_at else None,
            deleted_at=preference.deleted_at.replace(tzinfo=None) if preference.deleted_at else None,
        )
