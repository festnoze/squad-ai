from datetime import timezone
from infrastructure.entities.user_entity import UserEntity
from infrastructure.converters.school_converters import SchoolConverters
from infrastructure.converters.user_preference_converters import UserPreferenceConverters
from models.user import User


class UserConverters:
    @staticmethod
    def convert_user_entity_to_model(user_entity: UserEntity) -> User:
        """Convert a UserEntity to a User model.

        Args:
            user_entity: The database entity to convert

        Returns:
            User model instance with timezone-aware datetimes
        """
        return User(
            id=user_entity.id,
            lms_user_id=user_entity.lms_user_id,
            school=SchoolConverters.convert_school_entity_to_model(user_entity.school) if user_entity.school else None,
            preference=UserPreferenceConverters.convert_user_preference_entity_to_model(user_entity.preference) if user_entity.preference else None,
            civility=user_entity.civility,
            first_name=user_entity.first_name,
            last_name=user_entity.last_name,
            email=user_entity.email,
            created_at=user_entity.created_at.replace(tzinfo=timezone.utc),
            updated_at=user_entity.updated_at.replace(tzinfo=timezone.utc) if user_entity.updated_at else None,
            deleted_at=user_entity.deleted_at.replace(tzinfo=timezone.utc) if user_entity.deleted_at else None,
        )

    @staticmethod
    def convert_user_model_to_entity(user: User) -> UserEntity:
        """Convert a User model to a UserEntity.

        IMPORTANT: This only sets foreign key IDs, not relationship objects.
        Relationships are loaded automatically by SQLAlchemy when reading.

        Args:
            user: The User model to convert

        Returns:
            UserEntity instance with timezone-naive datetimes (for database storage)
        """
        return UserEntity(
            id=user.id,
            lms_user_id=user.lms_user_id,
            school_id=user.school.id if user.school else None,
            # NOTE: Do NOT set 'school' or 'preference' relationship objects here
            # Only set the foreign key IDs. SQLAlchemy will load relationships on read.
            civility=user.civility,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            created_at=user.created_at.replace(tzinfo=None) if user.created_at else None,
            updated_at=user.updated_at.replace(tzinfo=None) if user.updated_at else None,
            deleted_at=user.deleted_at.replace(tzinfo=None) if user.deleted_at else None,
        )
