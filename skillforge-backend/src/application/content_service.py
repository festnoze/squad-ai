"""Content Service

This module provides business logic for content management, including retrieval
from database and scraping from external sources.
"""

import logging
import hashlib
import json
from datetime import datetime
from pathlib import Path
from collections.abc import Callable
from infrastructure.content_repository import ContentRepository
from models.content import Content
from data_ingestion.course_content_scraping_service import CourseContentScrapingService
from helpers.context_helper_studi import ContextHelperStudi
from common_tools.helpers.file_helper import file  # type: ignore[import-untyped]
from envvar import EnvHelper
from utils.text_cleaner import TextCleaner
from api_client.studi_parcours_api_client import StudiParcoursApiClient
from api_client.models.parcours_hierarchy_models import ParcoursHierarchy
from security.jwt_helper import JWTHelper


class ContentService:
    """Service class for managing course content retrieval and caching.

    This service acts as a facade over the content repository, providing
    business logic for content retrieval with database caching and web scraping fallback.
    """

    def __init__(self, content_repository: ContentRepository) -> None:
        self.logger = logging.getLogger(__name__)
        """Initialize the content service.

        Args:
            content_repository: Repository for content data access
        """
        self.content_repository: ContentRepository = content_repository

    async def aget_content_by_filter(self, all_context_info: dict) -> Content:
        """Retrieve content by its JSON content filter."""
        # Extract the content filter from the context info
        filter = ContextHelperStudi.get_content_filter_for_studi(all_context_info)

        # TODO to remove TMP until frontend provide the actual ressource_url
        if all_context_info["ressource"]["ressource_url"] == "https://example.com/chat":
            filter = {"ressource_url": "https://ressources.studi.fr/contenus/opale/eaa694e6dd5ac7ea4244f54e413a8f25de20b8aa/"}

        # First, Search any existing Content from within database by filter
        content = await self.content_repository.aget_content_by_filter(filter)
        if content:
            return content

        # Scrape the content from provided ressource url, if not found in DB and if scraping is enabled
        if EnvHelper.get_allow_on_the_fly_lms_retrieval_of_unknown_lesson_content() and filter.get("ressource_url"):
            scrape_result = await CourseContentScrapingService.scrape_course_content_from_url(
                opale_course_url=str(filter.get("ressource_url")),
                ressource_name=all_context_info["ressource"]["ressource_title"],
                save_html_and_md_as_files=False,
                content_repository=self.content_repository,
            )

            if scrape_result:
                pdf_url, course_content_md, course_content_html = scrape_result
                all_context_info["pdf_url"] = pdf_url

                # Clean content to remove null bytes before database insertion
                cleaned_content_md = TextCleaner.clean_for_postgres(course_content_md)
                cleaned_content_html = TextCleaner.clean_for_postgres(course_content_html)

                content = Content(
                    filter=filter,
                    context_metadata=all_context_info,
                    content_full=cleaned_content_md,
                    content_html=cleaned_content_html,
                    content_media={},
                )
                await self.content_repository.apersist_content(content)
                return content

        if EnvHelper.get_fails_on_not_found_lesson_content():
            raise ValueError(f"Content not found for filter: {filter}. Ensure the filter contains a valid 'ressource_url' for scraping.")
        else:
            self.logger.error(f"Content not found for filter: {filter}. Ensure the filter contains a valid 'ressource_url' for scraping.")
            no_content_str = "- pas de contenu de cours trouvé pour le contexte fourni -"
            no_content = Content(
                filter=filter,
                context_metadata=all_context_info,
                content_full=no_content_str,
                content_html=f"<p>{no_content_str}</p>",
                content_media={},
                content_summary_full=no_content_str,
                content_summary_light=no_content_str,
                content_summary_compact=no_content_str,
            )
            return no_content

    async def ascraping_resource_content(self, resource_name: str, resource_type: str, resource_url: str, metadata_builder: Callable | None = None) -> Content | None:
        """
        Get or scrape content for a single resource.

        Returns:
            Content | None: The scraped and persisted Content object if successful, None if failed or content already exists
        """
        # Create a filter based on resource URL
        filter = {"ressource_url": resource_url}

        # Check if content already exists in database
        existing_content = await self.content_repository.aget_content_by_filter(filter)
        if existing_content:
            return None  # Content already exists, return None

        # Scrape content based on resource type
        try:
            if resource_type == "pdf":
                res = CourseContentScrapingService.build_and_save_html_and_md_from_pdf_url(pdf_url=resource_url, ressource_name=file.build_valid_filename(resource_name), save_html_and_md_as_files=False)
                if res:
                    course_content_md, course_content_html = res
                    pdf_url = resource_url
                else:
                    return None

            elif resource_type == "opale":
                scrape_result = await CourseContentScrapingService.scrape_course_content_from_url(
                    opale_course_url=resource_url,
                    ressource_name=file.build_valid_filename(resource_name),
                    save_html_and_md_as_files=False,
                    content_repository=self.content_repository,
                )

                if not scrape_result:
                    return None  # Failed to scrape

                pdf_url, course_content_md, course_content_html = scrape_result

            else:
                return None  # Unsupported resource type

            # Build enriched metadata right before persistence (now we have the pdf_url)
            if metadata_builder:
                # Use the enriched metadata builder function
                # Builder signature: metadata_builder(pdf_url, scraping_status, scraping_error)
                context_metadata = metadata_builder(pdf_url, "success", None)
            else:
                # Fallback to minimal metadata if no builder provided
                context_metadata = {
                    "ressource": {"ressource_title": resource_name, "ressource_type": resource_type, "ressource_url": resource_url},
                    "pdf_url": pdf_url,
                    "scraping_status": "success",
                }

            # Clean content to remove null bytes before database insertion
            cleaned_content_md = TextCleaner.clean_for_postgres(course_content_md)
            cleaned_content_html = TextCleaner.clean_for_postgres(course_content_html)

            content = Content(filter=filter, context_metadata=context_metadata, content_full=cleaned_content_md, content_html=cleaned_content_html, content_media={})

            await self.content_repository.apersist_content(content)

            return content  # Return the successfully created content

        except Exception:
            return None  # Failed to scrape

    async def aget_parcours_hierarchy_from_studi_api_client(self, parcours_id: int, use_cache: bool = False, jwt_token: str | None = None) -> ParcoursHierarchy:
        """Get the complete hierarchy for a specific parcours from the Studi Parcours API Client"""
        # Forge token first if not provided to get the parcours hierarchy
        if not jwt_token:
            jwt_token = JWTHelper.create_token(client=199520, school_id=1009, issuer="lms-studi.studi.fr", expires_in_hours=24)
        api_client = StudiParcoursApiClient(jwt_token=jwt_token)
        return await api_client.aget_parcours_hierarchy(parcours_id=parcours_id, use_cache=use_cache)

    async def aexport_contents_to_json_files(self, batch_size: int = 25, export_dir: str = "exports") -> dict:
        """Export all contents from database to JSON files with validation.

        Args:
            batch_size: Number of contents per batch file
            output_dir: Directory to save export files

        Returns:
            dict with export summary (total_count, batch_count, output_dir, files)
        """
        # Create output directory
        output_path = Path("outputs/" + export_dir)
        output_path.mkdir(exist_ok=True)

        # Get total count
        total_count = await self.content_repository.aget_total_contents_count()
        self.logger.info(f"Starting export of {total_count} contents with batch size {batch_size}")

        exported_files = []
        batch_num = 0

        # Export in batches
        for offset in range(0, total_count, batch_size):
            contents = await self.content_repository.aget_contents_batch(limit=batch_size, offset=offset)

            if not contents:
                break

            # Convert Content models to dicts for JSON serialization
            contents_data = [content.model_dump() for content in contents]

            # Create batch wrapper with metadata
            batch_data = {
                "batch_id": batch_num,
                "timestamp": datetime.utcnow().isoformat(),
                "record_count": len(contents_data),
                "checksum": hashlib.md5(json.dumps(contents_data, default=str, sort_keys=True).encode()).hexdigest(),
                "data": contents_data,
            }

            # Save to file
            filename = output_path / f"batch_{batch_num:04d}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(batch_data, f, default=str, ensure_ascii=False, indent=2)

            exported_files.append(str(filename))
            self.logger.info(f"Exported batch {batch_num} ({len(contents_data)} records) to {filename}")
            batch_num += 1

        return {
            "status": "success",
            "total_count": total_count,
            "batch_count": batch_num,
            "output_dir": str(output_path.absolute()),
            "files": exported_files,
        }

    async def aimport_contents_from_json_files(self, input_dir: str = "exports", validate_checksums: bool = True) -> dict:
        """Import contents from JSON files into database with validation.

        Args:
            input_dir: Directory containing export JSON files
            validate_checksums: Whether to validate checksums before importing

        Returns:
            dict with import summary (total_imported, failed_batches, errors)
        """
        input_path = Path("outputs/" + input_dir)
        if not input_path.exists():
            raise FileNotFoundError(f"Input directory not found: {input_path}")

        # Find all batch files
        batch_files = sorted(input_path.glob("batch_*.json"))
        if not batch_files:
            raise ValueError(f"No batch files found in {input_dir}")

        self.logger.info(f"Starting import from {len(batch_files)} batch files")

        total_imported = 0
        failed_batches = []
        errors = []

        for batch_file in batch_files:
            try:
                # Load batch data
                with open(batch_file, "r", encoding="utf-8") as f:
                    batch_data = json.load(f)

                # Validate checksum if requested
                if validate_checksums:
                    expected_checksum = batch_data.get("checksum")
                    actual_checksum = hashlib.md5(json.dumps(batch_data["data"], default=str, sort_keys=True).encode()).hexdigest()

                    if expected_checksum != actual_checksum:
                        error_msg = f"Checksum mismatch in {batch_file.name}: expected {expected_checksum}, got {actual_checksum}"
                        self.logger.error(error_msg)
                        failed_batches.append(batch_file.name)
                        errors.append(error_msg)
                        continue

                # Convert dicts back to Content models
                contents = [Content(**content_dict) for content_dict in batch_data["data"]]

                # Bulk insert
                await self.content_repository.abulk_insert_contents(contents)

                total_imported += len(contents)
                self.logger.info(f"Imported batch {batch_file.name} ({len(contents)} records)")

            except Exception as e:
                error_msg = f"Failed to import {batch_file.name}: {str(e)}"
                self.logger.error(error_msg)
                failed_batches.append(batch_file.name)
                errors.append(error_msg)

        status = "success" if not failed_batches else ("partial_success" if total_imported > 0 else "error")

        return {
            "status": status,
            "total_imported": total_imported,
            "total_batches": len(batch_files),
            "failed_batches": failed_batches,
            "errors": errors,
        }
