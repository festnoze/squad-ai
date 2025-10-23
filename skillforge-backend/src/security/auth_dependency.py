"""Authentication Dependencies

This module provides FastAPI dependency functions for JWT authentication.
"""

import jwt
import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Annotated
from security.jwt_skillforge_payload import JWTSkillForgePayload
from security.jwt_helper import JWTHelper
from envvar import EnvHelper


logger = logging.getLogger(__name__)

# Define the security scheme for Swagger UI
security = HTTPBearer(auto_error=False)


async def authentication_required(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None) -> JWTSkillForgePayload:
    """FastAPI dependency to get and verify user authentication from JWT token.

    This dependency requires a valid JWT token in the Authorization header.
    If the token is missing, invalid, or expired, it raises an HTTP 401 error.

    Usage in FastAPI endpoints:
        ```python
        @router.get("/protected")
        async def protected_endpoint(token_payload: JWTPayload = Depends(authentication_required)):
            return {"user_id": token_payload.get_user_id_as_uuid()}
        ```

    Args:
        credentials: HTTPAuthorizationCredentials from Bearer token (automatically injected by FastAPI)

    Returns:
        JWTPayload object containing the decoded token data

    Raises:
        HTTPException: 401 if token is missing, invalid, or expired
    """

    token: str | None = None
    if credentials:
        token = credentials.credentials
    else:
        token = _get_dev_token()

    # If no token (even after checking DEV_TOKEN), raise 401
    if not token:
        logger.warning("Authentication attempt without Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Decode the JWT token (our helper already handles base64 and JWT decoding)
        jwt_payload = JWTHelper.adecode_token(token)

        logger.info(f"User authenticated successfully: {jwt_payload.sid}")
        return jwt_payload

    except ValueError as e:
        # Handle invalid token format or base64 decoding error
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    except jwt.ExpiredSignatureError as e:
        # Handle expired token
        logger.warning(f"Expired JWT token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    except jwt.InvalidTokenError as e:
        # Handle invalid token
        logger.warning(f"Invalid JWT token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Unexpected error during authentication: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed due to server error",
        ) from e


def _get_dev_token() -> str | None:
    token = None
    if EnvHelper.get_environment() == "development":
        dev_token = EnvHelper.get_dev_token()
        if dev_token:
            logger.info("Using DEV_TOKEN from environment (development mode)")
            token = dev_token
    return token


async def authentication_optional(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None) -> JWTSkillForgePayload | None:
    """FastAPI dependency to optionally get the current authenticated user from JWT token.

    This dependency attempts to decode the JWT token if present, but does not
    raise an error if the token is missing. Returns None if no token is provided.
    Raises 401 only if a token is provided but is invalid or expired.

    Usage in FastAPI endpoints:
        ```python
        @router.get("/public-or-private")
        async def flexible_endpoint(token_payload: JWTPayload | None = Depends(authentication_optional)):
            if token_payload:
                return {"message": "Authenticated", "user_id": token_payload.user_id}
            else:
                return {"message": "Anonymous access"}
        ```

    Args:
        credentials: HTTPAuthorizationCredentials from Bearer token (automatically injected by FastAPI)

    Returns:
        JWTPayload object if token is valid, None if no token provided

    Raises:
        HTTPException: 401 if token is provided but invalid or expired
    """
    token: str | None = None
    if credentials:
        token = credentials.credentials
    else:
        token = _get_dev_token()

    # If no token (even after checking DEV_TOKEN), return None for anonymous access
    if not token:
        logger.debug("No authorization header provided - anonymous access")
        return None

    try:
        # Decode the JWT token (our helper already handles base64 and JWT decoding)
        jwt_payload = JWTHelper.adecode_token(token)

        logger.info(f"User authenticated successfully (optional): {jwt_payload.sid}")
        return jwt_payload

    except ValueError as e:
        # Handle invalid token format or base64 decoding error
        logger.warning(f"Invalid token in optional auth: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    except jwt.ExpiredSignatureError as e:
        # Handle expired token
        logger.warning(f"Expired JWT token in optional auth: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    except jwt.InvalidTokenError as e:
        # Handle invalid token
        logger.warning(f"Invalid JWT token in optional auth: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Unexpected error during optional authentication: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed due to server error",
        ) from e


async def arequire_role(token_payload: JWTSkillForgePayload, required_role: str) -> None:
    """Helper function to check if the current user has a specific role.

    This can be used within endpoint functions to enforce role-based access control.

    Usage in FastAPI endpoints:
        ```python
        @router.get("/admin-only")
        async def admin_endpoint(token_payload: JWTPayload = Depends(authentication_required)):
            await arequire_role(token_payload, "admin")
            return {"message": "Admin access granted"}
        ```

    Args:
        token_payload: The authenticated user's JWT token payload
        required_role: The role required to access the resource

    Raises:
        HTTPException: 403 if user does not have the required role
    """
    if not token_payload.has_role(required_role):
        logger.warning(f"User {token_payload.sid} attempted to access resource requiring role '{required_role}' but has roles: {token_payload.roles}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required role: {required_role}",
        )

    logger.info(f"User {token_payload.sid} authorized with role '{required_role}'")
