from fastapi import APIRouter, Depends

#
from application.user_service import UserService
from models.user import User
from models.user_preference import UserPreference
from facade.request_models.user_infos_request import UserInfosRequest, UserPreferencesRequest
from facade.response_models.user_response import UserResponse
from facade.converters.user_request_converter import UserRequestConverter
from facade.converters.user_response_converter import UserResponseConverter
from dependency_injection_config import deps
from common_tools.helpers.validation_helper import Validate  # type: ignore[import-untyped]
from security.auth_dependency import authentication_required
from security.jwt_skillforge_payload import JWTSkillForgePayload

user_router = APIRouter(prefix="/user", tags=["User"])


@user_router.patch(
    "/set-infos",
    description="Create or update user information (without preferences)",
    response_model=UserResponse,
    status_code=200,
)
async def acreate_or_update_user(user_infos: UserInfosRequest, token_payload: JWTSkillForgePayload = Depends(authentication_required), user_service: UserService = deps.depends(UserService)) -> UserResponse:
    """Create or update user and its information.

    This endpoint handles user's basic information including:
    - Civility, first name, last name, email
    - School name and LMS internal user ID

    User preferences is set apart using '/user/preferences' endpoint.
    """
    lms_user_id = token_payload.get_lms_user_id()
    if not Validate.is_int(lms_user_id):
        raise ValueError(f"Provided user LMS id value: '{lms_user_id}' isn't a valid integer.")
    user: User = UserRequestConverter.convert_user_infos_request_to_user(user_infos)
    created_user: User = await user_service.acreate_or_update_user(user)
    return UserResponseConverter.convert_user_to_response(created_user)


@user_router.patch(
    "/preferences",
    description="Create or update user preferences",
    status_code=200,
)
async def aset_user_preferences(preferences: UserPreferencesRequest, token_payload: JWTSkillForgePayload = Depends(authentication_required), user_service: UserService = deps.depends(UserService)) -> dict:
    """Create or update user preferences.

    The user_id is automatically extracted from the authentication token.

    This endpoint allows users to set their:
    - Language preference
    - Theme preference (light, dark, auto)
    - Timezone
    - Notification settings
    """
    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id:
        raise ValueError("User LMS ID not found in token")

    # Get user ID from LMS ID
    user_id = await user_service.user_repository.aget_user_id_by_lms_user_id(lms_user_id)
    if not user_id:
        raise ValueError(f"User not found from its internal LMS id: {lms_user_id}")

    # Convert request to model
    user_preference: UserPreference = UserRequestConverter.convert_user_preferences_request_to_model(preferences, str(user_id))

    # Create or update preferences
    updated_preference = await user_service.user_repository.acreate_or_update_user_preference(user_id, user_preference)

    return {"status": "success", "message": "User preferences updated successfully", "preference_id": str(updated_preference.id)}


@user_router.post(
    "/activate-service",
    description="Activate the SkillForge service for a user",
    status_code=200,
)
async def aactivate_service(token_payload: JWTSkillForgePayload = Depends(authentication_required), user_service: UserService = deps.depends(UserService)) -> bool:
    """Activate the SkillForge service for a user."""
    lms_user_id = token_payload.get_lms_user_id()
    if not Validate.is_int(lms_user_id):
        raise ValueError(f"Provided user LMS id value: '{lms_user_id}' isn't a valid integer.")
    return await user_service.aservice_activation(lms_user_id)
