"""
Studi Parcours API Client.

This client provides access to the Studi Parcours API, specifically the hierarchy endpoint
that returns the complete parcours structure with all nested elements (blocs, matieres, modules, themes, resources, etc.).
"""

import httpx
from typing import Optional
from api_client.models.parcours_hierarchy_models import ParcoursHierarchy
from envvar import EnvHelper


class StudiParcoursApiClientException(Exception):
    """Base exception for Studi Parcours API Client errors."""

    pass


class StudiParcoursApiClient:
    """
    Client for interacting with the Studi Parcours API.

    This client follows the project's architecture patterns:
    - Async methods are prefixed with 'a' (e.g., aget_parcours_hierarchy)
    - Uses JWT token authentication (from frontend or JWTHelper.create_token)
    - Uses environment variables for configuration
    - Provides proper error handling and timeout management
    """

    def __init__(self, jwt_token: Optional[str] = None, base_url: Optional[str] = None, timeout: float = 30.0) -> None:
        """
        Initialize the Studi Parcours API client.

        Args:
            jwt_token: JWT token for authentication. Can be provided from frontend or created using JWTHelper.create_token.
            base_url: Base URL for the Parcours API. If not provided, uses OTHERS_API_BASE_URL from environment.
            timeout: Request timeout in seconds (default: 30.0)
        """
        self.jwt_token = jwt_token
        self.base_url = base_url or (EnvHelper.get_other_api_base_url() + "/parcours")
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
            headers["Authorization"] = f"Bearer {token}"

        return headers

    async def aget_parcours_hierarchy(self, parcours_id: int, use_cache: bool = False, jwt_token: Optional[str] = None) -> ParcoursHierarchy:
        """
        Get the complete hierarchy for a specific parcours.

        This method calls the /{parcoursId}/hierarchy endpoint and returns the full
        structure including all blocs, matieres, modules, themes, resources, evaluations, and exams.

        Args:
            parcours_id: The ID of the parcours to retrieve
            use_cache: Whether to use cached data (default: False)
            jwt_token: Optional JWT token for this request. If not provided, uses the instance token.

        Returns:
            ParcoursHierarchy: Complete parcours hierarchy with all nested elements

        Raises:
            StudiParcoursApiClientException: If the API request fails or returns invalid data
        """
        url = f"{self.base_url}/{parcours_id}/hierarchy"
        params = {"useCache": str(use_cache).lower()}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_headers(jwt_token), params=params)

                # Raise an exception for HTTP error responses
                response.raise_for_status()

                # Parse JSON response
                data = response.json()

                # Validate and parse using Pydantic model
                return ParcoursHierarchy.model_validate(data)

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error occurred while fetching parcours hierarchy: {e.response.status_code} - {e.response.text}"
            raise StudiParcoursApiClientException(error_msg) from e

        except httpx.RequestError as e:
            error_msg = f"Request error occurred while fetching parcours hierarchy: {str(e)}"
            raise StudiParcoursApiClientException(error_msg) from e

        except ValueError as e:
            error_msg = f"Failed to parse API response: {str(e)}"
            raise StudiParcoursApiClientException(error_msg) from e

        except Exception as e:
            error_msg = f"Unexpected error occurred: {str(e)}"
            raise StudiParcoursApiClientException(error_msg) from e

    async def aget_parcours_hierarchy_json(self, parcours_id: int, use_cache: bool = False, jwt_token: Optional[str] = None) -> str:
        """
        Get the raw JSON response for a specific parcours hierarchy.

        This method is useful for debugging or when you need the raw API response.

        Args:
            parcours_id: The ID of the parcours to retrieve
            use_cache: Whether to use cached data (default: False)
            jwt_token: Optional JWT token for this request. If not provided, uses the instance token.

        Returns:
            str: Raw JSON string from the API response

        Raises:
            StudiParcoursApiClientException: If the API request fails
        """
        url = f"{self.base_url}/{parcours_id}/hierarchy"
        params = {"useCache": str(use_cache).lower()}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_headers(jwt_token), params=params)

                # Raise an exception for HTTP error responses
                response.raise_for_status()

                return response.text

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error occurred while fetching parcours hierarchy: {e.response.status_code} - {e.response.text}"
            raise StudiParcoursApiClientException(error_msg) from e

        except httpx.RequestError as e:
            error_msg = f"Request error occurred while fetching parcours hierarchy: {str(e)}"
            raise StudiParcoursApiClientException(error_msg) from e

        except Exception as e:
            error_msg = f"Unexpected error occurred: {str(e)}"
            raise StudiParcoursApiClientException(error_msg) from e
