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
            created_at=user.created_at,
            updated_at=user.updated_at,
            deleted_at=user.deleted_at,
        )

    @staticmethod
    def convert_school_to_response(school: School) -> SchoolResponse:
        """Convert School domain model to SchoolResponse.

        Args:
            school: The domain model containing school information

        Returns:
            SchoolResponse model for API response
        """
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
        """Convert UserPreference domain model to UserPreferenceResponse.

        Args:
            preference: The domain model containing user preference information

        Returns:
            UserPreferenceResponse model for API response
        """
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
