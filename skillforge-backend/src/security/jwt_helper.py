"""JWT Helper Module

This module provides utilities for encoding, decoding and validating JWT tokens.
"""

import jwt
import logging
import base64
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4
from security.jwt_skillforge_payload import JWTSkillForgePayload
from envvar import EnvHelper


logger = logging.getLogger(__name__)


class JWTHelper:
    """Helper class for JWT token operations."""

    @staticmethod
    def adecode_token(token: str, verify_signature: bool | None = None) -> JWTSkillForgePayload:
        """Decode and validate a JWT token.

        The token processing steps:
        1. Remove "Bearer " prefix if present
        2. Decode from base64
        3. Decode and validate the JWT

        Args:
            token: The base64-encoded JWT token string to decode (may have "Bearer " prefix)
            verify_signature: Whether to verify the token signature.
                            If None, uses the value from environment variables.

        Returns:
            JWTPayload object containing the decoded token data

        Raises:
            jwt.ExpiredSignatureError: If the token has expired
            jwt.InvalidTokenError: If the token is invalid
            ValueError: If required configuration is missing or base64 decoding fails
        """
        # Get JWT configuration from environment
        secret_key = EnvHelper.get_jwt_secret_key()
        algorithm = EnvHelper.get_jwt_algorithm()

        if verify_signature is None:
            verify_signature = EnvHelper.get_jwt_verify_signature()

        # Decode options
        decode_options: dict[str, Any] = {
            "verify_signature": verify_signature,
            "verify_exp": True,  # Always verify expiration if present
            "verify_aud": False,  # Don't verify audience by default
        }

        try:
            # Step 0: Remove "Bearer " prefix if present
            clean_token = token.strip() if token else token
            if clean_token and clean_token.lower().startswith("bearer "):
                clean_token = clean_token[7:]  # Remove "Bearer " (7 characters)
                logger.debug("Removed 'Bearer ' prefix from token")

            # Step 1: Decode from base64
            try:
                jwt_token = base64.b64decode(clean_token).decode("utf-8")
            except Exception as base64_error:
                logger.error(f"Failed to decode base64 token: {base64_error}")
                raise ValueError(f"Invalid base64-encoded token: {base64_error}") from base64_error

            # Step 2: Decode the JWT token
            if verify_signature and secret_key:
                # Decode with signature verification
                payload = jwt.decode(
                    jwt_token,
                    secret_key,
                    algorithms=[algorithm],
                    options=decode_options,
                )
            else:
                # Decode without signature verification (for development/testing)
                logger.warning("JWT signature verification is disabled. This should only be used in development!")
                payload = jwt.decode(
                    jwt_token,
                    options={**decode_options, "verify_signature": False},
                    algorithms=[algorithm],
                )

            # Create and return JWTPayload model
            return JWTSkillForgePayload(**payload)

        except jwt.ExpiredSignatureError as e:
            logger.warning(f"JWT token has expired: {e}")
            raise jwt.ExpiredSignatureError("Token has expired") from e

        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid JWT token: {e}")
            raise jwt.InvalidTokenError("Invalid token") from e

        except ValueError:
            # Re-raise ValueError from base64 decoding
            raise

        except Exception as e:
            logger.error(f"Unexpected error decoding JWT: {e}")
            raise ValueError(f"Failed to decode token: {e}") from e

    @staticmethod
    def aextract_token_from_header(authorization_header: str | None) -> str:
        """Extract the JWT token from the Authorization header.

        Args:
            authorization_header: The Authorization header value (e.g., "Bearer eyJ...")

        Returns:
            The extracted JWT token string

        Raises:
            ValueError: If the header format is invalid or token is missing
        """
        if not authorization_header:
            raise ValueError("Authorization header is missing")

        # Check for Bearer scheme
        parts = authorization_header.split()
        if len(parts) != 2:
            raise ValueError("Invalid authorization header format. Expected: 'Bearer <token>'")

        scheme, token = parts
        if scheme.lower() != "bearer":
            raise ValueError(f"Unsupported authorization scheme: '{scheme}'. Expected: 'Bearer'")

        if not token:
            raise ValueError("Token is missing in authorization header")

        return token

    @staticmethod
    def adecode_from_header(authorization_header: str | None, verify_signature: bool | None = None) -> JWTSkillForgePayload:
        """Extract and decode a JWT token from the Authorization header.

        This is a convenience method that combines extract_token_from_header and decode_token.

        Args:
            authorization_header: The Authorization header value (e.g., "Bearer eyJ...")
            verify_signature: Whether to verify the token signature.
                            If None, uses the value from environment variables.

        Returns:
            JWTPayload object containing the decoded token data

        Raises:
            ValueError: If the header format is invalid or token is missing
            jwt.ExpiredSignatureError: If the token has expired
            jwt.InvalidTokenError: If the token is invalid
        """
        token = JWTHelper.aextract_token_from_header(authorization_header)
        return JWTHelper.adecode_token(token, verify_signature)

    @staticmethod
    def acreate_token(client: int, school_id: int, issuer: str, expires_in_hours: int = 24) -> str:
        """Create a new JWT token for testing/development purposes.

        The JWT token is created and then encoded in base64.

        Args:
            client: Client ID (integer)
            school_id: School ID (integer)
            issuer: Issuer string (e.g., "uat-lms-studi.studi.fr")
            expires_in_hours: Token expiration time in hours (default: 24)

        Returns:
            Base64-encoded JWT token string

        Raises:
            ValueError: If token creation fails
        """
        try:
            # Get JWT configuration from environment
            secret_key = EnvHelper.get_jwt_secret_key()
            algorithm = EnvHelper.get_jwt_algorithm()

            # Generate current timestamp
            now = datetime.now()
            nbf = int(now.timestamp())
            exp = int((now + timedelta(hours=expires_in_hours)).timestamp())

            # Generate a new UUID for sid
            sid = str(uuid4())

            # Build the payload
            payload = {
                "sid": sid,
                "client": client,
                "schoolId": school_id,
                "iss": issuer,
                "exp": exp,
                "nbf": nbf,
            }

            # Step 1: Encode the JWT token
            jwt_token = jwt.encode(payload, secret_key, algorithm=algorithm)

            # Step 2: Encode to base64
            base64_token = base64.b64encode(jwt_token.encode("utf-8")).decode("utf-8")

            logger.info(f"JWT token created successfully for client {client}, school {school_id}, sid: {sid}")
            return base64_token

        except Exception as e:
            logger.error(f"Failed to create JWT token: {e}")
            raise ValueError(f"Token creation failed: {e}") from e
