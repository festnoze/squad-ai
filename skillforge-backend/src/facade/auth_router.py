"""Authentication Router

This module provides authentication-related endpoints including JWT token operations.
"""

from fastapi import APIRouter, Depends
from datetime import datetime

from application.user_service import UserService
from facade.request_models.token_request import CreateTokenRequest
from facade.response_models.user_response import UserResponse
from facade.response_models.token_response import TokenResponse
from facade.converters.user_response_converter import UserResponseConverter
from dependency_injection_config import deps
from security.auth_dependency import authentication_required, authentication_optional
from security.jwt_skillforge_payload import JWTSkillForgePayload
from security.jwt_helper import JWTHelper

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


@auth_router.get(
    "/me",
    description="Get current authenticated user information from database",
    response_model=UserResponse,
    status_code=200,
)
async def get_current_user_info_from_database(token_payload: JWTSkillForgePayload = Depends(authentication_required), user_service: UserService = deps.depends(UserService)) -> UserResponse:
    """Get the current authenticated user's information.

    This endpoint demonstrates JWT authentication usage.
    Requires a valid JWT token in the Authorization header.

    Example:
        Authorization: Bearer ZEJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    """
    # Get user ID from JWT payload
    user_id = token_payload.get_token_uuid()
    if not user_id:
        raise ValueError("User ID not found in JWT token")

    # Fetch user from database
    user = await user_service.aget_user_by_id(user_id)
    if not user:
        raise ValueError(f"User not found with ID: {user_id}")

    return UserResponseConverter.convert_user_to_response(user)


@auth_router.get(
    "/profile",
    description="Get current user information from JWT token if provided, anonymous user information otherwise",
    status_code=200,
)
async def get_current_user_info_from_token(token_payload: JWTSkillForgePayload | None = Depends(authentication_optional)) -> dict:
    """Get user information from JWT token.

    This endpoint demonstrates optional JWT authentication.
    If a valid JWT token is provided, returns authenticated user info.
    Otherwise, returns anonymous user info.

    Example with token:
        Authorization: Bearer EZd9aacad954537f7f421c57...
    """
    if token_payload:
        return {
            "authenticated": True,
            "token_id": str(token_payload.get_token_uuid()),
            "user_id": str(token_payload.get_lms_user_id()),
            "school_id": token_payload.get_school_id(),
            "issuer": token_payload.get_issuer(),
            "expiration": token_payload.get_token_expiration(),
            "not_before": token_payload.get_token_not_before(),
        }
    else:
        return {"authenticated": False, "message": "Anonymous access - no JWT token provided"}


@auth_router.post(
    "/token/new",
    description="Create a JWT token for testing/development purposes",
    response_model=TokenResponse,
    status_code=201,
)
async def forge_new_token(token_request: CreateTokenRequest) -> TokenResponse:
    """Create a new JWT token for testing and development.

    This endpoint generates a JWT token with the specified parameters.
    The token includes a newly generated UUID for the session ID (sid) and
    the current timestamp for the 'not before' (nbf) claim.

    Example request:
        {
            "client": 199520,
            "schoolId": 1009,
            "issuer": "uat-lms-studi.studi.fr",
            "expires_in_hours": 24
        }

    Returns:
        JWT token and its metadata including the generated sid

    WARNING: This endpoint should be disabled or protected in production!
    """
    # Create the JWT token
    token = JWTHelper.acreate_token(client=token_request.client, school_id=token_request.school_id, issuer=token_request.issuer, expires_in_hours=token_request.expires_in_hours)

    # Decode the token to get the generated sid
    decoded = JWTHelper.adecode_token(token, verify_signature=False)

    # Return the response
    return TokenResponse(
        token=token,
        token_type="Bearer",
        expires_in_hours=token_request.expires_in_hours,
        created_at=datetime.now().isoformat(),
        sid=str(decoded.sid),
        client=token_request.client,
        schoolId=token_request.school_id,
        issuer=token_request.issuer,
    )
