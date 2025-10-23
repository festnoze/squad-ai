from facade.request_models.user_infos_request import UserInfosRequest, UserPreferencesRequest
from models.user import User
from models.school import School
from models.user_preference import UserPreference


class UserRequestConverter:
    """Converter for transforming UserInfosRequest to domain models."""

    # @staticmethod
    # def convert_token_payload_to_user(token_payload: JWTSkillForgePayload) -> User:
    #     """Convert JWT token payload to User model."""
    #     return User(
    #         school=School(name=token_payload.get_school_name()),
    #         preference=None,
    #         school_lms_internal_user_id=token_payload.get_lms_user_id(),
    #         civility=None,
    #         first_name=None,
    #         last_name=None,
    #         email=None,
    #     )

    @staticmethod
    def convert_user_infos_request_to_user(user_infos: UserInfosRequest) -> User:
        """Convert UserInfosRequest to User model (without preferences).

        User preferences are now handled separately via the /user/preferences endpoint.

        Args:
            user_infos: The request model containing user information

        Returns:
            User model with school but no preferences
        """
        # Create School model from request (only name is provided)
        school = School(name=user_infos.school_name) if user_infos.school_name else None

        # Create User model without preferences
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
    def convert_user_preferences_request_to_model(preferences_request: UserPreferencesRequest, user_id: str) -> UserPreference:
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
