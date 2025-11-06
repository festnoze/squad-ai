"""
Studi LMS API Client.

This client provides access to the Studi LMS API, specifically the user profile endpoint
that returns user information including personal details, addresses, phone numbers, and active promotions.
"""

import httpx
from typing import Optional
from api_client.models.studi_lms_user_models import StudiLmsUserInfoResponse
from envvar import EnvHelper


class StudiLmsApiClientException(Exception):
    """Base exception for Studi LMS API Client errors."""

    pass


class StudiLmsApiClient:
    """
    Client for interacting with the Studi LMS API.

    This client follows the project's architecture patterns:
    - Async methods are prefixed with 'a' (e.g., aget_user_infos)
    - Uses JWT token authentication (from frontend or JWTHelper.create_token)
    - Uses environment variables for configuration
    - Provides proper error handling and timeout management
    """

    def __init__(self, jwt_token: Optional[str] = None, base_url: Optional[str] = None, timeout: float = 30.0) -> None:
        """
        Initialize the Studi LMS API client.

        Args:
            jwt_token: JWT token for authentication. Can be provided from frontend or created using JWTHelper.create_token.
            base_url: Base URL for the LMS API. If not provided, uses LMS_API_BASE_URL from environment.
            timeout: Request timeout in seconds (default: 30.0)
        """
        self.jwt_token = jwt_token
        self.base_url = base_url or EnvHelper.get_lms_api_base_url()
        self.timeout = timeout

        # Remove trailing slash from base_url if present
        if self.base_url.endswith("/"):
            self.base_url = self.base_url[:-1]

    def _get_headers(self, jwt_token: Optional[str] = None) -> dict[str, str]:
        """
        Get headers for API requests.

        Args:
            jwt_token: Optional JWT token to use for this request. If not provided, uses the instance token.

        Returns:
            Dictionary of HTTP headers including authentication if JWT token is provided.
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        # Use provided token or fall back to instance token
        token = jwt_token or self.jwt_token
        if token:
            if not token.startswith("Bearer "):
                token = f"Bearer {token}"
            headers["Authorization"] = token

        return headers

    async def aget_user_infos(self, jwt_token: Optional[str] = None) -> StudiLmsUserInfoResponse:
        """
        Get the current user profile information.

        This method calls the /v2/profile/me endpoint and returns the user's complete profile
        including personal details, addresses, phone numbers, and active promotions.

        Args:
            jwt_token: Optional JWT token for this request. If not provided, uses the instance token.

        Returns:
            StudiLmsUserInfoResponse: Complete user profile information from /me endpoint

        Raises:
            StudiLmsApiClientException: If the API request fails or returns invalid data
        """
        url = f"{self.base_url}/v2/profile/me"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = self._get_headers(jwt_token)
                response = await client.get(url, headers=headers)

                # Raise an exception for HTTP error responses
                response.raise_for_status()

                # Parse JSON response
                data = response.json()

                # Validate and parse using Pydantic model
                return StudiLmsUserInfoResponse.model_validate(data)

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error occurred while fetching user infos: {e.response.status_code} - {e.response.text}"
            raise StudiLmsApiClientException(error_msg) from e

        except httpx.RequestError as e:
            error_msg = f"Request error occurred while fetching user infos: {str(e)}"
            raise StudiLmsApiClientException(error_msg) from e

        except ValueError as e:
            error_msg = f"Failed to parse API response: {str(e)}"
            raise StudiLmsApiClientException(error_msg) from e

        except Exception as e:
            error_msg = f"Unexpected error occurred: {str(e)}"
            raise StudiLmsApiClientException(error_msg) from e

    async def aget_user_infos_json(self, jwt_token: Optional[str] = None) -> str:
        """
        Get the raw JSON response for the current user profile.

        This method is useful for debugging or when you need the raw API response.

        Args:
            jwt_token: Optional JWT token for this request. If not provided, uses the instance token.

        Returns:
            str: Raw JSON string from the API response

        Raises:
            StudiLmsApiClientException: If the API request fails
        """
        url = f"{self.base_url}/v2/profile/me"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = self._get_headers(jwt_token)
                response = await client.get(url, headers=headers)

                # Raise an exception for HTTP error responses
                response.raise_for_status()

                return response.text

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error occurred while fetching user infos: {e.response.status_code} - {e.response.text}"
            raise StudiLmsApiClientException(error_msg) from e

        except httpx.RequestError as e:
            error_msg = f"Request error occurred while fetching user infos: {str(e)}"
            raise StudiLmsApiClientException(error_msg) from e

        except Exception as e:
            error_msg = f"Unexpected error occurred: {str(e)}"
            raise StudiLmsApiClientException(error_msg) from e
