from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException, Query, Header, Body
from fastapi.responses import StreamingResponse
from application.content_service import ContentService
from application.summary_service import SummaryService
from application.course_service import CourseService
from API.dependency_injection_config import deps
from facade.request_models.course_content_request import CourseContentScrapingRequest
from facade.response_models.admin_response import CourseCreationResponse
from api_client.models.parcours_hierarchy_models import ParcoursHierarchy
import json

admin_router = APIRouter(prefix="/admin", tags=["Admin"])


@admin_router.post(
    "/content/scrape-parcour-courses",
    description="Scrape and persist course content from a list of resources with real-time progress streaming (SSE)",
    status_code=200,
)
async def ascrape_parcour_all_courses(request: CourseContentScrapingRequest, content_service: ContentService = deps.depends(ContentService)) -> StreamingResponse:
    """Scrape and persist course content for all resources in a course with Server-Sent Events.

    This endpoint streams progress events in real-time to avoid timeouts on long operations.
    For each resource, it:
    1. Checks if content already exists in the database
    2. If not found, scrapes the content based on resource type (opale or pdf)
    3. Persists the scraped content to the database
    4. Sends a progress event to the client
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate Server-Sent Events for scraping progress."""
        results: list[dict] = []
        successful_count = 0
        skipped_count = 0
        failed_count = 0
        total_resources = len(request.ressource_objects)

        try:
            # Send "started" event with total count
            yield f"data: {json.dumps({'event': 'started', 'parcours_name': request.name, 'total_resources': total_resources})}\n\n"

            # Process each resource
            for index, resource in enumerate(request.ressource_objects, start=1):
                # Skip resources without URL
                if not resource.url:
                    result = {
                        "name": resource.name,
                        "type": resource.type,
                        "url": "",
                        "status": "skipped",
                        "message": f"Skipped '{resource.name}': No URL provided",
                    }
                    results.append(result)
                    skipped_count += 1

                    # Send progress event
                    yield f"data: {json.dumps({'event': 'progress', 'current': index, 'total': total_resources, 'resource': result})}\n\n"
                    continue

                try:
                    # Create metadata builder function that will be called after scraping
                    def build_metadata(pdf_url: str | None, scraping_status: str, scraping_error: str | None) -> dict:
                        return request.build_enriched_context_metadata(resource, pdf_url, scraping_status, scraping_error)

                    # Scrape content with metadata builder
                    existing = await content_service.content_repository.aget_content_by_filter({"ressource_url": resource.url})
                    if existing:
                        status = "skipped"
                        message = f"Skipped '{resource.name}': Content already exists in database"
                        skipped_count += 1
                    else:
                        content = await content_service.ascraping_resource_content(resource_name=resource.name, resource_type=resource.type, resource_url=resource.url, metadata_builder=build_metadata)
                        if content is not None:
                            status = "success"
                            message = f"Successfully scraped and persisted content for: '{resource.name}'"
                            successful_count += 1
                        else:
                            status = "failed"
                            message = f"Failed to scrape content for: '{resource.name}'"
                            failed_count += 1

                    result = {"name": resource.name, "type": resource.type, "url": resource.url, "status": status, "message": message}
                    results.append(result)

                    # Send progress event
                    yield f"data: {json.dumps({'event': 'progress', 'current': index, 'total': total_resources, 'resource': result})}\n\n"

                except Exception as e:
                    failed_count += 1
                    result = {
                        "name": resource.name,
                        "type": resource.type,
                        "url": resource.url or "",
                        "status": "failed",
                        "message": f"Unexpected error: {str(e)}",
                    }
                    results.append(result)

                    # Send progress event
                    yield f"data: {json.dumps({'event': 'progress', 'current': index, 'total': total_resources, 'resource': result})}\n\n"

            # Determine overall status
            if failed_count == 0 and successful_count > 0:
                overall_status = "success"
                overall_message = f"All resources processed successfully for '{request.name}'"
            elif failed_count == total_resources:
                overall_status = "error"
                overall_message = f"All resources failed to process for '{request.name}'"
            elif successful_count > 0 or skipped_count > 0:
                overall_status = "partial_success"
                overall_message = f"Partial success for '{request.name}': {successful_count} succeeded, {skipped_count} skipped, {failed_count} failed"
            else:
                overall_status = "success"
                overall_message = f"All resources were already present (skipped) for '{request.name}'"

            # Send "completed" event with summary
            summary = {
                "event": "completed",
                "status": overall_status,
                "message": overall_message,
                "parcours_name": request.name,
                "total_resources": total_resources,
                "successful": successful_count,
                "skipped": skipped_count,
                "failed": failed_count,
                "results": results,
            }
            yield f"data: {json.dumps(summary)}\n\n"

        except Exception as e:
            # Send "error" event for critical errors
            error_event = {"event": "error", "message": f"Critical error during scraping: {str(e)}", "parcours_name": request.name}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@admin_router.get(
    "/content/html",
    description="Get HTML content from database by resource URL",
    response_model=dict,
    status_code=200,
)
async def aget_content_html_by_url(ressource_url: str = Query(..., description="The resource URL to retrieve content for"), content_service: ContentService = deps.depends(ContentService)) -> dict:
    """Retrieve HTML content from database by resource URL.

    This endpoint retrieves the HTML content stored in the database for a given resource URL.
    It's useful as a fallback when the web URL is not accessible.

    Args:
        ressource_url: The resource URL to search for in the database
        content_service: Injected ContentService for handling content operations

    Returns:
        dict with keys:
            - status: "success" or "error"
            - content_html: The HTML content string (if found)
            - message: Status message
            - metadata: Context metadata (if found)

    Raises:
        HTTPException: 404 if content not found
    """
    try:
        # Create filter to search by resource URL
        filter = {"ressource_url": ressource_url}

        # Retrieve content from database
        content = await content_service.content_repository.aget_content_by_filter(filter)

        if not content:
            raise HTTPException(status_code=404, detail=f"Content not found for resource URL: {ressource_url}")

        return {
            "status": "success",
            "content_html": content.content_html,
            "content_markdown": content.content_full,
            "metadata": content.context_metadata,
            "message": f"Content retrieved successfully for: {ressource_url}",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve content: {str(e)}")


@admin_router.get(
    "/parcours/{parcours_id}/hierarchy",
    description="Get the complete hierarchy for a specific parcours from the Studi Parcours API",
    response_model=ParcoursHierarchy,
    status_code=200,
)
async def aget_parcours_hierarchy(
    parcours_id: int,
    use_cache: bool = Query(False, description="Whether to use cached data from the API"),
    authorization: str | None = Header(None, description="Bearer token for authentication"),
    content_service: ContentService = deps.depends(ContentService),
) -> ParcoursHierarchy:
    """Retrieve the complete parcours hierarchy from the Studi Parcours API."""
    try:
        # Extract JWT token from Authorization header if present
        jwt_token = None
        if authorization and authorization.startswith("Bearer "):
            jwt_token = authorization.replace("Bearer ", "")

        # Call the API through ContentService
        hierarchy = await content_service.aget_parcours_hierarchy_from_studi_api_client(parcours_id=parcours_id, use_cache=use_cache, jwt_token=jwt_token)

        return hierarchy

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve parcours hierarchy: {str(e)}")


@admin_router.post(
    "/content/summarize-all",
    description="Generate summaries for all contents in the database using LLM",
    response_model=dict,
    status_code=200,
)
async def asummarize_all_contents(summary_service: SummaryService = deps.depends(SummaryService)) -> dict:
    """Generate summaries for all contents in the database.

    This endpoint processes each content in the database and generates three levels
    of summaries using LLM:
    - Full summary (detailed, 500-800 words)
    - Light summary (concise, 200-300 words)
    - Compact summary (very short, 50-100 words)

    The generated summaries are automatically saved to the database for each content.

    Args:
        summary_service: Injected SummaryService for handling summarization operations

    Returns:
        dict with keys:
            - status: Overall status ("success", "partial_success", or "error")
            - message: Overall status message
            - total_contents: Total number of contents processed
            - successful: Number of successful summarizations
            - failed: Number of failed summarizations
            - results: List of individual results per content

    Raises:
        HTTPException: 500 if a critical error occurs
    """
    try:
        result = await summary_service.asummarize_all_contents(skip_existing_summaries=True, llm_index=1)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate summaries: {str(e)}")


@admin_router.post(
    "/courses/create",
    description="Create a new course from parcours hierarchy JSON",
    response_model=CourseCreationResponse,
    status_code=201,
)
async def acreate_course(
    body: dict = Body(..., description="Untyped JSON containing the parcours hierarchy"),
    course_service: CourseService = deps.depends(CourseService),
) -> CourseCreationResponse:
    """Persist a parcours hierarchy through an untyped JSON body"""
    created_course = await course_service.acreate_or_update_course_hierarchy(body)
    return CourseCreationResponse(status="success", message="Course hierarchy successfully persisted", course_id=str(created_course.id), course_filter=created_course.course_filter)
