import logging
from abc import ABC, abstractmethod
from typing import Any
from sqlalchemy import select, func
from common_tools.database.generic_datacontext import GenericDataContext  # type: ignore[import-untyped]
from infrastructure.entities import Base
from infrastructure.entities.content_entity import ContentEntity
from infrastructure.converters.content_converters import ContentConverters
from models.content import Content
from envvar import EnvHelper
from infrastructure.helpers.database_helper import DatabaseHelper
from infrastructure.helpers.json_filter_helper import JsonFilterHelperMixin


class ContentRepository(JsonFilterHelperMixin, ABC):
    """Abstract base class for content repositories."""

    @abstractmethod
    async def aget_content_by_filter(self, filter: dict) -> Content | None:
        """Retrieve a content by its JSON content filter.

        Args:
            filter: Filter JSON dictionary to search Content by

        Returns:
            Content model if found, None otherwise
        """
        pass

    @abstractmethod
    async def aget_content_by_id(self, content_id: str) -> Content | None:
        """Retrieve a content by its ID.

        Args:
            content_id: Content ID (UUID as string)

        Returns:
            Content model if found, None otherwise
        """
        pass

    @abstractmethod
    async def adoes_content_exist_by_filter(self, filter: dict) -> bool:
        """Check if content exists by its JSON content filter.

        Args:
            filter: Filter JSON dictionary to search Content by

        Returns:
            True if content exists, False otherwise
        """
        pass

    @abstractmethod
    async def apersist_content(self, content: Content) -> None:
        """Persist a content in the repository.

        Args:
            content: Content model to persist
        """
        pass

    @abstractmethod
    async def aget_all_content_ids(self) -> list[str]:
        """Retrieve all content IDs from the repository.

        Returns:
            List of content IDs (UUIDs as strings)
        """
        pass

    @abstractmethod
    async def aupdate_content_by_id(self, content_id: str, **kwargs: Any) -> None:
        """Update a content by its ID with the provided fields.

        Args:
            content_id: Content ID (UUID as string)
            **kwargs: Fields to update (e.g., content_summary_full, content_summary_light, content_summary_compact)
        """
        pass

    @abstractmethod
    async def aget_contents_batch(self, limit: int, offset: int) -> list[Content]:
        """Retrieve a batch of contents with pagination.

        Args:
            limit: Number of contents to retrieve
            offset: Number of contents to skip

        Returns:
            List of Content models
        """
        pass

    @abstractmethod
    async def aget_total_contents_count(self) -> int:
        """Get total count of contents in the repository.

        Returns:
            Total number of contents
        """
        pass

    @abstractmethod
    async def abulk_insert_contents(self, contents: list[Content]) -> None:
        """Bulk insert multiple contents into the repository.

        Args:
            contents: List of Content models to persist

        Raises:
            Exception: Re-raises the exception after logging to allow caller to handle
        """
        pass


class ContentRepositoryStudi(ContentRepository):
    def __init__(self, db_path_or_url: str | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        self.db_path_or_url = DatabaseHelper.build_postgres_connection_url(db_path_or_url)
        self.data_context = GenericDataContext(Base, self.db_path_or_url)
        host = EnvHelper.get_postgres_host()
        dbname = EnvHelper.get_postgres_database_name()
        self.logger.debug(f"ContentRepositoryStudi initialized with database: {host}/{dbname}")

    async def aget_content_by_filter(self, filter: dict) -> Content | None:
        """Retrieve a content by its JSON content filter using database-agnostic filtering.

        Uses JSONB @> operator for PostgreSQL and json_extract for SQLite.

        Args:
            filter: Filter JSON dictionary to search Content by

        Returns:
            Content model if found, None otherwise
        """
        try:
            async with self.data_context.get_session_async() as session:
                # Use generalized JSON containment filter
                filter_condition = self._build_json_containment_filter(ContentEntity.filter, filter)
                stmt = select(ContentEntity).where(filter_condition)
                result = await session.execute(stmt)
                content_entity = result.unique().scalar_one_or_none()
                if content_entity:
                    return ContentConverters.convert_content_entity_to_model(content_entity)
            return None
        except Exception as e:
            self.logger.error(f"Failed to get content by filter: {e}")
            return None

    async def adoes_content_exist_by_filter(self, filter: dict) -> bool:
        """Check if content exists by its JSON content filter using database-agnostic filtering.

        Uses JSONB @> operator for PostgreSQL and json_extract for SQLite.

        Args:
            filter: Filter JSON dictionary to search Content by

        Returns:
            True if content exists, False otherwise
        """
        try:
            async with self.data_context.get_session_async() as session:
                # Use generalized JSON containment filter
                filter_condition = self._build_json_containment_filter(ContentEntity.filter, filter)
                stmt = select(ContentEntity.id).where(filter_condition)
                result = await session.execute(stmt)
                return result.scalar_one_or_none() is not None
        except Exception as e:
            self.logger.error(f"Failed to check content existence by filter: {e}")
            return False

    async def apersist_content(self, content: Content) -> None:
        """Persist a content in the repository.

        Args:
            content: Content model to persist

        Raises:
            Exception: Re-raises the exception after logging to allow caller to handle
        """
        try:
            content_entity: ContentEntity = ContentConverters.convert_content_model_to_entity(content)
            async with self.data_context.get_session_async() as session:
                session.add(content_entity)
                await session.commit()
        except Exception as e:
            self.logger.error(f"Failed to persist content: {e}")
            # Re-raise to allow service layer to handle and return proper status
            raise

    async def aget_all_content_ids(self) -> list[str]:
        """Retrieve all content IDs from the repository.

        Returns:
            List of content IDs (UUIDs as strings)
        """
        try:
            async with self.data_context.get_session_async() as session:
                stmt = select(ContentEntity.id)
                result = await session.execute(stmt)
                content_ids = [str(row[0]) for row in result.all()]
                return content_ids
        except Exception as e:
            self.logger.error(f"Failed to get all content IDs: {e}")
            return []

    async def aget_content_by_id(self, content_id: str) -> Content | None:
        """Retrieve a content by its ID.

        Args:
            content_id: Content ID (UUID as string)

        Returns:
            Content model if found, None otherwise
        """
        try:
            content_entity: ContentEntity = await self.data_context.get_entity_by_id_async(ContentEntity, content_id)
            return ContentConverters.convert_content_entity_to_model(content_entity) if content_entity else None
        except Exception as e:
            self.logger.error(f"Failed to get content by ID: {e}")
            return None

    async def aupdate_content_by_id(self, content_id: str, **kwargs: Any) -> None:
        """Update a content by its ID with the provided fields.

        Args:
            content_id: Content ID (UUID as string)
            **kwargs: Fields to update (e.g., content_summary_full, content_summary_light, content_summary_compact)

        Raises:
            Exception: Re-raises the exception after logging to allow caller to handle
        """
        try:
            await self.data_context.update_entity_async(ContentEntity, content_id, **kwargs)
        except Exception as e:
            self.logger.error(f"Failed to update content by ID {content_id}: {e}")
            raise

    async def aget_contents_batch(self, limit: int, offset: int) -> list[Content]:
        """Retrieve a batch of contents with pagination.

        Args:
            limit: Number of contents to retrieve
            offset: Number of contents to skip

        Returns:
            List of Content models
        """
        try:
            async with self.data_context.get_session_async() as session:
                stmt = select(ContentEntity).order_by(ContentEntity.id).limit(limit).offset(offset)
                result = await session.execute(stmt)
                content_entities = result.scalars().all()
                return [ContentConverters.convert_content_entity_to_model(entity) for entity in content_entities]
        except Exception as e:
            self.logger.error(f"Failed to get contents batch (limit={limit}, offset={offset}): {e}")
            return []

    async def aget_total_contents_count(self) -> int:
        """Get total count of contents in the repository.

        Returns:
            Total number of contents
        """
        try:
            async with self.data_context.get_session_async() as session:
                stmt = select(func.count()).select_from(ContentEntity)
                result = await session.execute(stmt)
                return result.scalar() or 0
        except Exception as e:
            self.logger.error(f"Failed to get total contents count: {e}")
            return 0

    async def abulk_insert_contents(self, contents: list[Content]) -> None:
        """Bulk insert multiple contents into the repository.

        Args:
            contents: List of Content models to persist

        Raises:
            Exception: Re-raises the exception after logging to allow caller to handle
        """
        try:
            content_entities = [ContentConverters.convert_content_model_to_entity(content) for content in contents]
            async with self.data_context.get_session_async() as session:
                session.add_all(content_entities)
                await session.commit()
        except Exception as e:
            self.logger.error(f"Failed to bulk insert {len(contents)} contents: {e}")
            raise


class ContentRepositoryBlackboard(ContentRepository):
    def __init__(self, db_path_or_url: str | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        self.db_path_or_url = DatabaseHelper.build_postgres_connection_url(db_path_or_url)
        self.data_context = GenericDataContext(Base, self.db_path_or_url)
        host = EnvHelper.get_postgres_host()
        dbname = EnvHelper.get_postgres_database_name()
        self.logger.debug(f"ContentRepositoryBlackboard initialized with database: {host}/{dbname}")

    async def aget_content_by_filter(self, filter: dict) -> Content | None:
        """Retrieve a content by its JSON content filter.

        Args:
            filter: Filter JSON dictionary to search Content by

        Returns:
            None (blackboard implementation returns no content)
        """
        self.logger.debug(f"aget_content_by_filter called with filter: {filter}")
        return None

    async def aget_content_by_id(self, content_id: str) -> Content | None:
        """Retrieve a content by its ID.

        Args:
            content_id: Content ID (UUID as string)

        Returns:
            None (blackboard implementation returns no content)
        """
        self.logger.debug(f"aget_content_by_id called with content_id: {content_id}")
        return None

    async def adoes_content_exist_by_filter(self, filter: dict) -> bool:
        """Check if content exists by its JSON content filter.

        Args:
            filter: Filter JSON dictionary to search Content by

        Returns:
            False (blackboard implementation has no content)
        """
        self.logger.debug(f"adoes_content_exist_by_filter called with filter: {filter}")
        return False

    async def apersist_content(self, content: Content) -> None:
        """Persist a content in the repository.

        Args:
            content: Content model to persist

        Note:
            Blackboard implementation does nothing - content is not persisted
        """
        self.logger.debug(f"apersist_content called with content_id: {content.id}")
        # Do nothing - blackboard doesn't persist

    async def aget_all_content_ids(self) -> list[str]:
        """Retrieve all content IDs from the repository.

        Returns:
            Empty list (blackboard implementation has no content)
        """
        self.logger.debug("aget_all_content_ids called")
        return []

    async def aupdate_content_by_id(self, content_id: str, **kwargs: Any) -> None:
        """Update a content by its ID with the provided fields.

        Args:
            content_id: Content ID (UUID as string)
            **kwargs: Fields to update

        Note:
            Blackboard implementation does nothing - content is not updated
        """
        self.logger.debug(f"aupdate_content_by_id called with content_id: {content_id}, kwargs: {kwargs}")
        # Do nothing - blackboard doesn't update

    async def aget_contents_batch(self, limit: int, offset: int) -> list[Content]:
        """Retrieve a batch of contents with pagination.

        Args:
            limit: Number of contents to retrieve
            offset: Number of contents to skip

        Returns:
            Empty list (blackboard implementation has no content)
        """
        self.logger.debug(f"aget_contents_batch called with limit={limit}, offset={offset}")
        return []

    async def aget_total_contents_count(self) -> int:
        """Get total count of contents in the repository.

        Returns:
            0 (blackboard implementation has no content)
        """
        self.logger.debug("aget_total_contents_count called")
        return 0

    async def abulk_insert_contents(self, contents: list[Content]) -> None:
        """Bulk insert multiple contents into the repository.

        Args:
            contents: List of Content models to persist

        Note:
            Blackboard implementation does nothing - content is not persisted
        """
        self.logger.debug(f"abulk_insert_contents called with {len(contents)} contents")
        # Do nothing - blackboard doesn't persist
