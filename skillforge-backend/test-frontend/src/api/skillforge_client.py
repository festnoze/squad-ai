"""SkillForge Backend API client for HTTP communication."""

from collections.abc import AsyncGenerator
from typing import Any

import httpx

from src.config import Config


class SkillForgeClient:
    """Async HTTP client for SkillForge Backend API."""

    def __init__(self, base_url: str | None = None, jwt_token: str | None = None) -> None:
        """Initialize the API client.

        Args:
            base_url: Base URL of the SkillForge API (defaults to Config.SKILLFORGE_API_URL)
            jwt_token: JWT token for authentication (defaults to Config.SKILLFORGE_JWT_TOKEN)
        """
        self.base_url = base_url or Config.SKILLFORGE_API_URL
        self.jwt_token = jwt_token or Config.SKILLFORGE_JWT_TOKEN

        # Validate configuration
        if not self.jwt_token:
            msg = "JWT token not configured. Please set SKILLFORGE_JWT_TOKEN in .env file"
            raise ValueError(msg)

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for API requests."""
        return {"Authorization": f"Bearer {self.jwt_token}", "Content-Type": "application/json"}

    async def aping(self) -> tuple[bool, str]:
        """Ping the API to check availability and connectivity.

        Returns:
            Tuple of (success: bool, message: str)
        """
        url = f"{self.base_url}/ping"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                if response.text == "pong" or response.text == '"pong"':
                    return (True, "Successfully connected to API")
                return (False, f"Unexpected response: {response.text}")

        except httpx.TimeoutException:
            return (False, f"Connection timeout to {self.base_url}")
        except httpx.ConnectError:
            return (False, f"Cannot connect to API at {self.base_url}")
        except httpx.HTTPError as e:
            return (False, f"HTTP error: {e}")
        except Exception as e:
            return (False, f"Unexpected error: {e}")

    async def aget_user_all_threads_ids_or_create(self, course_context: dict[str, Any]) -> list[str]:
        """Get existing thread IDs or create a new one for the given course context.

        Args:
            course_context: Course context dictionary containing resource, theme, module, matiere info

        Returns:
            List of thread IDs (UUID strings), most recent first

        Raises:
            httpx.HTTPError: If the request fails
        """
        url = f"{self.base_url}/thread/get-all/ids"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=course_context, headers=self._get_headers())

            # If validation error (422), print detailed error info
            if response.status_code == 422:
                import json

                error_detail = response.json()
                print("\n" + "=" * 80)
                print("VALIDATION ERROR (422) Details:")
                print("=" * 80)
                print(f"Request URL: {url}")
                print("\nRequest Body:")
                print(json.dumps(course_context, indent=2))
                print("\nResponse Body:")
                print(json.dumps(error_detail, indent=2))
                print("=" * 80 + "\n")

            response.raise_for_status()

            data = response.json()
            threads_ids = data.get("threads_ids", [])

            if not threads_ids:
                msg = "No thread IDs returned from API"
                raise ValueError(msg)

            return threads_ids

    async def aget_thread_messages(self, thread_id: str, page_number: int = 1, page_size: int = 20) -> dict[str, Any]:
        """Get messages for a specific thread with pagination.

        Args:
            thread_id: Thread UUID
            page_number: Page number (1-indexed, most recent messages first)
            page_size: Number of messages per page

        Returns:
            Dictionary containing thread messages and pagination info

        Raises:
            httpx.HTTPError: If the request fails
        """
        url = f"{self.base_url}/thread/{thread_id}/messages"
        params = {"page_number": page_number, "page_size": page_size}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params, headers=self._get_headers())
            response.raise_for_status()

            return response.json()

    async def asend_query_streaming(
        self, thread_id: str, query_text: str, course_context: dict[str, Any], selected_text: str = ""
    ) -> AsyncGenerator[str, None]:
        """Send a query and stream the AI response.

        Args:
            thread_id: Thread UUID
            query_text: User's question/query
            course_context: Course context dictionary
            selected_text: Selected text from the resource (optional)

        Yields:
            Chunks of the AI response as they arrive

        Raises:
            httpx.HTTPError: If the request fails
        """
        url = f"{self.base_url}/thread/{thread_id}/query"

        # Prepare request body
        body = {
            "query": {
                "query_text_content": query_text,
                "query_selected_text": selected_text,
                "query_quick_action": None,
                "query_attachments": None,
            },
            "course_context": course_context,
        }

        # Add Accept header for SSE
        headers = self._get_headers()
        headers["Accept"] = "text/event-stream"

        async with (
            httpx.AsyncClient(timeout=120.0) as client,
            client.stream("POST", url, json=body, headers=headers) as response,
        ):
            response.raise_for_status()

            # Stream the response line by line
            async for line in response.aiter_lines():
                # Extract data from SSE format
                if line.startswith("data: "):
                    chunk = line[6:]  # Remove "data: " prefix
                    if chunk.strip():
                        yield chunk


def build_course_context(
    ressource_id: str | None = None,
    ressource_type: str | None = None,
    ressource_code: str | None = None,
    ressource_title: str | None = None,
    ressource_url: str | None = None,
    theme_id: str | None = None,
    module_id: str | None = None,
    matiere_id: str | None = None,
    parcour_id: str | None = None,
    parcours_name: str | None = None,
) -> dict[str, Any]:
    """Build a course context dictionary for API requests.

    Args:
        ressource_id: Resource ID
        ressource_type: Resource type (pdf, opale, etc.)
        ressource_code: Resource code
        ressource_title: Resource title
        ressource_url: Resource URL
        theme_id: Theme ID
        module_id: Module ID
        matiere_id: Matiere ID
        parcour_id: Parcours/Course ID
        parcours_name: Parcours/Course name

    Returns:
        Dictionary formatted for CourseContextStudiRequest
    """
    context: dict[str, Any] = {
        "context_type": "studi"  # Required discriminator field for CourseContextStudiRequest
    }

    # Build ressource object if any resource info provided
    if any([ressource_id, ressource_type, ressource_code, ressource_title, ressource_url]):
        context["ressource"] = {
            "ressource_id": ressource_id,
            "ressource_type": ressource_type,
            "ressource_code": ressource_code,
            "ressource_title": ressource_title,
            "ressource_url": ressource_url,
            "ressource_path": None,
        }

    # Add hierarchy IDs
    if theme_id:
        context["theme_id"] = theme_id
    if module_id:
        context["module_id"] = module_id
    if matiere_id:
        context["matiere_id"] = matiere_id
    if parcour_id:
        context["parcour_id"] = parcour_id
    if parcours_name:
        context["parcours_name"] = parcours_name

    return context
