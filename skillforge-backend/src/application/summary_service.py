"""Summary Service

This module provides business logic for generating and managing content summaries
using LLM to create summaries at different levels of detail.
"""

import logging
from typing import Any
from infrastructure.content_repository import ContentRepository
from infrastructure.llm_service import LlmService


class SummaryService:
    """Service class for managing content summarization.

    This service orchestrates the summarization of content using LLM
    and persists the generated summaries to the database.
    """

    def __init__(self, content_repository: ContentRepository, llm_service: LlmService) -> None:
        self.logger = logging.getLogger(__name__)
        """Initialize the summary service.

        Args:
            content_repository: Repository for content data access
            llm_repository: Repository for LLM operations
        """
        self.content_repository = content_repository
        self.llm_service = llm_service

    async def asummarize_content_by_id(self, content_id: str, skip_existing_summaries: bool = True, llm_index: int = -1) -> dict[str, Any]:
        """Generate summaries for a single content item and save to database.

        This method creates a chain of summaries:
        1. Full summary: from original content (reduces to ~1/3 size)
        2. Light summary: from full summary (high-level overview)
        3. Compact summary: from light summary (1-2 sentences)

        Args:
            content_id: Content ID (UUID as string)

        Returns:
            Dictionary with summary results:
                - status: "success" or "error"
                - message: Status message
                - summaries: Dict with "full", "light", "compact" summaries (if successful)

        Raises:
            ValueError: If content is not found
        """
        # Load content by ID
        content = await self.content_repository.aget_content_by_id(content_id)
        if not content:
            raise ValueError(f"Content not found with ID: {content_id}")

        if skip_existing_summaries and content.content_summary_full and content.content_summary_light and content.content_summary_compact:
            return {"status": "skipped", "message": "Content already has summaries"}

        # Generate summaries in chain: full → light → compact
        try:
            ressource_title = "Titre du cours : " + content.context_metadata.get("ressource", {}).get("ressource_name", "") + "\n\n"

            # Step 1: Generate full summary from original content
            summary_full = await self.llm_service.asummarize_content(ressource_title + content.content_full, "full", llm_index)

            # Step 2: Generate light summary from full summary (not from original content)
            summary_light = await self.llm_service.asummarize_content(ressource_title + summary_full, "light", llm_index)

            # Step 3: Generate compact summary from light summary (not from full or original)
            summary_compact = await self.llm_service.asummarize_content(ressource_title + summary_light, "compact", llm_index)

            # Update content with generated summaries
            await self.content_repository.aupdate_content_by_id(content_id, content_summary_full=summary_full, content_summary_light=summary_light, content_summary_compact=summary_compact)

            return {"status": "success", "message": f"Successfully generated summaries for content {content_id}", "summaries": {"full": summary_full, "light": summary_light, "compact": summary_compact}}

        except Exception as e:
            return {"status": "error", "message": f"Failed to generate summaries for content {content_id}: {str(e)}"}

    async def asummarize_all_contents(self, skip_existing_summaries: bool = True, llm_index: int = -1) -> dict[str, Any]:
        """Generate summaries for all contents in the database.

        This method retrieves all content IDs, then processes each one
        to generate and save summaries at three levels: full, light, and compact.
        """

        # Get all content IDs
        content_ids = await self.content_repository.aget_all_content_ids()

        if not content_ids:
            return {"status": "success", "message": "No contents found in database", "total_contents": 0, "successful": 0, "skipped": 0, "failed": 0, "results": []}

        results = []
        successful_count = 0
        skipped_count = 0
        failed_count = 0

        # Process each content
        for content_id in content_ids:
            try:
                result = await self.asummarize_content_by_id(content_id, skip_existing_summaries, llm_index)
                if result["status"] == "success":
                    successful_count += 1
                elif result["status"] == "skipped":
                    skipped_count += 1
                else:
                    failed_count += 1
                results.append({"content_id": content_id, **result})

            except Exception as e:
                failed_count += 1
                results.append({"content_id": content_id, "status": "error", "message": f"Unexpected error: {str(e)}"})

        # Determine overall status
        total_contents = len(content_ids)
        if failed_count == 0:
            overall_status = "success"
            overall_message = f"Successfully generated summaries for all {total_contents} contents"
        elif successful_count == 0:
            overall_status = "error"
            overall_message = f"Failed to generate summaries for all {total_contents} contents"
        else:
            overall_status = "partial_success"
            overall_message = f"Generated summaries for {successful_count}/{total_contents} contents ({skipped_count} skipped, {failed_count} failed)"

        return {"status": overall_status, "message": overall_message, "total_contents": total_contents, "successful": successful_count, "skipped": skipped_count, "failed": failed_count, "results": results}
