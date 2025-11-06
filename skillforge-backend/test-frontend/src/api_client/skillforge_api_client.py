"""SkillForge Backend API client for HTTP communication."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from src.config import Config


class SkillForgeAPIClient:
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

    async def aget_user_all_threads_ids_or_create(
        self, course_context: dict[str, Any], max_retries: int = 3
    ) -> list[str]:
        """Get existing thread IDs or create a new one for the given course context.

        Args:
            course_context: Course context dictionary containing resource, theme, module, matiere info
            max_retries: Maximum number of retry attempts for transient errors

        Returns:
            List of thread IDs (UUID strings), most recent first

        Raises:
            httpx.HTTPError: If the request fails after retries
        """
        url = f"{self.base_url}/thread/get-all/ids"

        for attempt in range(max_retries):
            try:
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
                        print(msg)
                        return []

                    return threads_ids

            except (httpx.ConnectError, httpx.TimeoutException, ConnectionResetError) as e:
                # Transient network errors - retry with exponential backoff
                if attempt < max_retries - 1:
                    wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                    print(
                        f"Warning: Network error (attempt {attempt + 1}/{max_retries}): {type(e).__name__}. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    print(f"Error: Failed after {max_retries} attempts: {type(e).__name__}: {e}")
                    raise

            except asyncio.CancelledError:
                # Don't retry on cancellation
                print("Info: Request cancelled by client")
                raise

            except Exception as e:
                # Non-retryable errors
                print(f"Error: {type(e).__name__}: {e}")
                raise

        # Should not reach here
        msg = "Unexpected error: exceeded max retries"
        raise RuntimeError(msg)

    async def aget_thread_messages(
        self, thread_id: str, page_number: int = 1, page_size: int = 20, max_retries: int = 3
    ) -> dict[str, Any]:
        """Get messages for a specific thread with pagination.

        Args:
            thread_id: Thread UUID
            page_number: Page number (1-indexed, most recent messages first)
            page_size: Number of messages per page
            max_retries: Maximum number of retry attempts for transient errors

        Returns:
            Dictionary containing thread messages and pagination info

        Raises:
            httpx.HTTPError: If the request fails after retries
        """
        url = f"{self.base_url}/thread/{thread_id}/messages"
        params = {"page_number": page_number, "page_size": page_size}

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url, params=params, headers=self._get_headers())
                    response.raise_for_status()
                    return response.json()

            except (httpx.ConnectError, httpx.TimeoutException, ConnectionResetError) as e:
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    print(
                        f"Warning: Network error (attempt {attempt + 1}/{max_retries}): {type(e).__name__}. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    print(f"Error: Failed after {max_retries} attempts: {type(e).__name__}: {e}")
                    raise

            except asyncio.CancelledError:
                print("Info: Request cancelled by client")
                raise

            except Exception as e:
                print(f"Error: {type(e).__name__}: {e}")
                raise

        msg = "Unexpected error: exceeded max retries"
        raise RuntimeError(msg)

    async def asend_query_streaming(
        self,
        thread_id: str,
        query_text: str,
        course_context: dict[str, Any],
        selected_text: str = "",
        generated_chunks: list[str] | None = None,
        timeout: float = 200.0,
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

        try:
            async with (
                httpx.AsyncClient(timeout=timeout) as client,
                client.stream("POST", url, json=body, headers=headers) as response,
            ):
                # Handle validation errors before starting stream
                if response.status_code == 422:
                    import json

                    error_detail = await response.aread()
                    print("\n" + "=" * 80)
                    print("VALIDATION ERROR (422) Details:")
                    print("=" * 80)
                    print(f"Request URL: {url}")
                    print("\nRequest Body:")
                    print(json.dumps(body, indent=2))
                    print("\nResponse Body:")
                    print(error_detail.decode())
                    print("=" * 80 + "\n")
                response.raise_for_status()

                # Stream the response line by line with error handling
                try:
                    async for line in response.aiter_lines():
                        # Extract data from SSE format
                        if line.startswith("data: "):
                            chunk = line[6:]  # Remove "data: " prefix
                            if chunk == "[DONE]":
                                break
                            if generated_chunks is not None:
                                generated_chunks.append(chunk)
                            yield chunk

                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
                    # Connection lost during streaming - log but don't crash
                    print(f"Warning: Connection lost during streaming: {type(e).__name__}: {e}")
                    # Yield any partial data we collected
                    return

                except asyncio.CancelledError:
                    # Client cancelled the request (user stopped it)
                    print("Info: Streaming cancelled by client")
                    raise  # Re-raise to properly propagate cancellation

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            # Network errors - provide user-friendly error
            error_msg = f"Network error during streaming: {type(e).__name__}"
            print(f"Error: {error_msg} - {e}")
            raise

        except asyncio.CancelledError:
            # Propagate cancellation
            raise

        except Exception as e:
            # Catch any other exceptions to prevent crash
            print(f"Unexpected error during streaming: {type(e).__name__}: {e}")
            raise

    async def ascrape_parcour_all_courses_streaming(
        self, parcour_data: dict[str, Any]
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Scrape and persist course content for all resources with real-time progress streaming (SSE).

        This endpoint streams progress events in real-time to avoid timeouts on long operations.
        Events are yielded as they arrive, allowing real-time progress tracking.

        For each resource, it:
        1. Checks if content already exists in the database
        2. If not found, scrapes the content based on resource type (opale or pdf)
        3. Persists the scraped content to the database
        4. Yields a progress event

        Args:
            parcour_data: Dictionary containing:
                - parcours_id: ID of the parcours/course
                - parcours_code: Code of the parcours/course
                - name: Name of the parcours/course
                - ressource_objects: List of resources with name, type, and url

        Yields:
            Dictionary events with the following structure:
            - "started" event: {'event': 'started', 'parcours_name': str, 'total_resources': int}
            - "progress" event: {'event': 'progress', 'current': int, 'total': int, 'resource': {...}}
            - "completed" event: {'event': 'completed', 'status': str, 'message': str, ...}
            - "error" event: {'event': 'error', 'message': str, 'parcours_name': str}

        Example:
            async for event in client.ascrape_parcour_all_courses_streaming(data):
                if event['event'] == 'started':
                    print(f"Starting scraping of {event['total_resources']} resources...")
                elif event['event'] == 'progress':
                    print(f"Progress: {event['current']}/{event['total']} - {event['resource']['name']}")
                elif event['event'] == 'completed':
                    print(f"Completed! {event['successful']} successful, {event['failed']} failed")

        Raises:
            httpx.HTTPError: If the request fails
        """
        url = f"{self.base_url}/admin/content/scrape-parcour-courses"

        # Add Accept header for SSE
        headers = self._get_headers()
        headers["Accept"] = "text/event-stream"

        try:
            async with (
                httpx.AsyncClient(timeout=None) as client,  # noqa: S113 - No timeout needed for long-running SSE streaming (can take up to 1 hour)
                client.stream("POST", url, json=parcour_data, headers=headers) as response,
            ):
                # Handle validation errors before starting stream
                if response.status_code == 422:
                    import json

                    error_detail = await response.aread()
                    print("\n" + "=" * 80)
                    print("VALIDATION ERROR (422) Details:")
                    print("=" * 80)
                    print(f"Request URL: {url}")
                    print("\nRequest Body:")
                    print(json.dumps(parcour_data, indent=2))
                    print("\nResponse Body:")
                    print(error_detail.decode())
                    print("=" * 80 + "\n")

                response.raise_for_status()

                # Stream the response line by line with error handling
                try:
                    async for line in response.aiter_lines():
                        # Extract data from SSE format
                        if line.startswith("data: "):
                            import json

                            chunk = line[6:]  # Remove "data: " prefix
                            if chunk.strip():
                                try:
                                    event_data = json.loads(chunk)
                                    yield event_data
                                except json.JSONDecodeError:
                                    # Skip malformed JSON
                                    continue

                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
                    # Connection lost during long-running scraping operation
                    print(f"Warning: Connection lost during scraping operation: {type(e).__name__}: {e}")
                    # Yield error event to notify client
                    yield {
                        "event": "error",
                        "message": f"Connection lost during scraping: {type(e).__name__}",
                        "parcours_name": parcour_data.get("name", "Unknown"),
                    }
                    return

                except asyncio.CancelledError:
                    # User cancelled the long-running operation
                    print("Info: Scraping operation cancelled by client")
                    # Yield cancellation event
                    yield {
                        "event": "cancelled",
                        "message": "Operation cancelled by user",
                        "parcours_name": parcour_data.get("name", "Unknown"),
                    }
                    raise  # Re-raise to properly propagate cancellation

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            # Network errors during scraping
            error_msg = f"Network error during scraping: {type(e).__name__}"
            print(f"Error: {error_msg} - {e}")
            # Yield error event before raising
            yield {
                "event": "error",
                "message": error_msg,
                "parcours_name": parcour_data.get("name", "Unknown"),
            }
            raise

        except asyncio.CancelledError:
            # Propagate cancellation
            raise

        except Exception as e:
            # Catch any other exceptions during scraping
            print(f"Unexpected error during scraping: {type(e).__name__}: {e}")
            # Yield error event before raising
            yield {
                "event": "error",
                "message": f"Unexpected error: {type(e).__name__}",
                "parcours_name": parcour_data.get("name", "Unknown"),
            }
            raise

    async def aget_content_html_by_url(self, ressource_url: str, max_retries: int = 3) -> dict[str, Any]:
        """Get HTML content from database by resource URL.

        This is useful as a fallback when the web URL is not accessible.
        Retrieves the HTML content stored in the database for a given resource URL.

        Args:
            ressource_url: The resource URL to retrieve content for
            max_retries: Maximum number of retry attempts for transient errors

        Returns:
            Dictionary containing:
                - status: "success" or "error"
                - content_html: The HTML content string
                - content_markdown: The markdown content string
                - metadata: Context metadata
                - message: Status message

        Raises:
            httpx.HTTPError: If the request fails (404 if not found, 500 on server error) after retries
        """
        url = f"{self.base_url}/admin/content/html"
        params = {"ressource_url": ressource_url}

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url, params=params, headers=self._get_headers())
                    response.raise_for_status()
                    return response.json()

            except (httpx.ConnectError, httpx.TimeoutException, ConnectionResetError) as e:
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    print(
                        f"Warning: Network error (attempt {attempt + 1}/{max_retries}): {type(e).__name__}. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    print(f"Error: Failed after {max_retries} attempts: {type(e).__name__}: {e}")
                    raise

            except asyncio.CancelledError:
                print("Info: Request cancelled by client")
                raise

            except Exception as e:
                print(f"Error: {type(e).__name__}: {e}")
                raise

        msg = "Unexpected error: exceeded max retries"
        raise RuntimeError(msg)

    async def acreate_course_from_hierarchy(self, parcours_hierarchy: dict[str, Any]) -> tuple[bool, str, str | None]:
        """Create a new course in the database from parcours hierarchy JSON."""
        url = f"{self.base_url}/admin/courses/create"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=parcours_hierarchy, headers=self._get_headers())

                # Handle validation errors
                if response.status_code == 400:
                    error_detail = response.json()
                    error_msg = error_detail.get("detail", "Invalid parcours data")
                    return (False, f"Validation error: {error_msg}", None)

                # Handle server errors
                if response.status_code == 500:
                    error_detail = response.json()
                    error_msg = error_detail.get("detail", "Server error")
                    return (False, f"Server error: {error_msg}", None)

                response.raise_for_status()

                # Parse success response
                data = response.json()
                course_id = data.get("course_id")
                message = data.get("message", "Course created successfully")

                return (True, message, course_id)

        except httpx.TimeoutException:
            return (False, f"Connection timeout to {self.base_url}", None)
        except httpx.ConnectError:
            return (False, f"Cannot connect to API at {self.base_url}", None)
        except httpx.HTTPError as e:
            return (False, f"HTTP error: {e}", None)
        except Exception as e:
            return (False, f"Unexpected error: {e}", None)


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
