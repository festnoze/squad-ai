"""Content Service

This module provides business logic for content management, including retrieval
from database and scraping from external sources.
"""

from infrastructure.content_repository import ContentRepository
from models.content import Content
from data_ingestion.course_content_scraping_service import CourseContentScrapingService
from context.context_helper_studi import ContextHelperStudi


class ContentService:
    """Service class for managing course content retrieval and caching.

    This service acts as a facade over the content repository, providing
    business logic for content retrieval with database caching and web scraping fallback.
    """

    def __init__(self, content_repository: ContentRepository) -> None:
        """Initialize the content service.

        Args:
            content_repository: Repository for content data access
        """
        self.content_repository: ContentRepository = content_repository

    async def aget_content_by_filter(self, all_context_info: dict) -> Content:
        """Retrieve content by its JSON content filter.

        This method first attempts to retrieve content from the database cache.
        If not found and a course_url is provided in the filter, it scrapes
        the content from the URL and returns it (without persisting to database).

        Args:
            all_context_info: Content filter JSON dictionary containing:
                - course_url: URL to scrape if not found in database
                - resource_name: Name of the resource being retrieved
                - parcours_name: Name of the course/parcours (optional)
            look_in_db_first: Whether to check database first before scraping (default: True)

        Returns:
            Content model with filter and content_full populated

        Raises:
            ValueError: If content cannot be found in database and no course_url is provided,
                       or if scraping fails
        """
        # Extract the content filter from the context info
        filter = ContextHelperStudi.get_content_filter_for_studi(all_context_info)

        # First, Search any existing Content from within database by filter
        content = await self.content_repository.aget_content_by_filter(filter)
        if content:
            return content

        # If not found in DB, Scrape the content from the provided ressource url
        if filter.get("ressource_url"):
            scrape_result = CourseContentScrapingService.scrape_course_content_from_url(
                opale_course_url=filter.get("ressource_url"),
                ressource_name=all_context_info["ressource"]["ressource_title"],
                save_html_and_md_as_files=False,
            )

            if scrape_result:
                pdf_url, course_content_md, course_content_html = scrape_result
                all_context_info["pdf_url"] = pdf_url
                content = Content(
                    filter=filter,
                    context_metadata=all_context_info,
                    content_full=course_content_md,
                    content_html=course_content_html,
                    content_media={},
                )
                await self.content_repository.apersist_content(content)
                return content

        raise ValueError(f"Content not found for filter: {filter}. Ensure the filter contains a valid 'course_url' for scraping.")
