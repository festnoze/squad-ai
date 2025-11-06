import logging
from uuid import UUID
from sqlalchemy import select
from common_tools.database.generic_datacontext import GenericDataContext  # type: ignore[import-untyped]
from infrastructure.entities import Base
from infrastructure.entities.context_entity import ContextEntity
from infrastructure.converters.context_converters import ContextConverters
from models.context import Context
from infrastructure.helpers.database_helper import DatabaseHelper
from infrastructure.helpers.json_filter_helper import JsonFilterHelperMixin


class ContextRepository(JsonFilterHelperMixin):
    def __init__(self, db_path_or_url: str | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        self.db_path_or_url = DatabaseHelper.build_postgres_connection_url(db_path_or_url)
        self.data_context = GenericDataContext(Base, self.db_path_or_url)

    async def acreate_context(self, context: Context) -> Context:
        """Create a new context in the database.

        Args:
            context: Context model containing context data

        Returns:
            Created Context model

        Raises:
            Exception: If context creation fails
        """
        try:
            context_entity = ContextConverters.convert_context_model_to_entity(context)
            context_entity = await self.data_context.add_entity_async(context_entity)
            return ContextConverters.convert_context_entity_to_model(context_entity)
        except Exception as e:
            self.logger.error(f"Failed to create context: {e}")
            raise

    async def aget_context_by_id(self, context_id: UUID) -> Context | None:
        """Retrieve a context by its UUID.

        Args:
            context_id: Context's UUID

        Returns:
            Context model if found, None otherwise
        """
        try:
            context_entity: ContextEntity = await self.data_context.get_entity_by_id_async(ContextEntity, context_id)
            return ContextConverters.convert_context_entity_to_model(context_entity) if context_entity else None
        except Exception as e:
            self.logger.error(f"Failed to get context by id: {e}")
            return None

    async def aget_context_by_filter(self, context_filter: dict) -> Context | None:
        """Retrieve a context by its JSON content (searches context_filter field).

        Works with both PostgreSQL (JSONB @> operator) and SQLite (json_extract function).

        Args:
            context_filter: Context to filter by - JSON dictionary

        Returns:
            Context model if found, None otherwise
        """
        try:
            async with self.data_context.get_session_async() as session:
                # Use database-agnostic JSON containment filter on context_filter field
                filter_condition = self._build_json_containment_filter(ContextEntity.context_filter, context_filter)
                stmt = select(ContextEntity).where(filter_condition)
                result = await session.execute(stmt)
                context_entity = result.unique().scalar_one_or_none()
                return ContextConverters.convert_context_entity_to_model(context_entity) if context_entity else None
        except Exception as e:
            self.logger.error(f"Failed to get the context filter prop: {e}")
            return None

    async def aget_context_by_full_content(self, full_content_filter: dict) -> Context | None:
        """Retrieve a context by its full JSON content (searches context_full field).

        Works with both PostgreSQL (JSONB @> operator) and SQLite (json_extract function).

        Args:
            full_content_filter: Full content to filter by - JSON dictionary

        Returns:
            Context model if found, None otherwise
        """
        try:
            async with self.data_context.get_session_async() as session:
                # Use database-agnostic JSON containment filter on context_full field
                filter_condition = self._build_json_containment_filter(ContextEntity.context_full, full_content_filter)
                stmt = select(ContextEntity).where(filter_condition)
                result = await session.execute(stmt)
                context_entity = result.unique().scalar_one_or_none()
                return ContextConverters.convert_context_entity_to_model(context_entity) if context_entity else None
        except Exception as e:
            self.logger.error(f"Failed to get context by full content: {e}")
            return None

    async def aget_all_contexts(self) -> list[Context]:
        """Retrieve all contexts from the database.

        Returns:
            List of all Context models in the database
        """
        try:
            async with self.data_context.get_session_async() as session:
                stmt = select(ContextEntity)
                result = await session.execute(stmt)
                context_entities = result.scalars().all()
                return [ContextConverters.convert_context_entity_to_model(entity) for entity in context_entities]
        except Exception as e:
            self.logger.error(f"Failed to get all contexts: {e}")
            return []

    async def aget_or_create_context(self, context: Context) -> Context:
        """Get or create a context based on JSON content.

        Args:
            context_filter: Context JSON dictionary
            context_full: Full context JSON dictionary

        Returns:
            Existing or newly created Context model
        """
        try:
            # Check if context already exists
            existing_context = await self.aget_context_by_filter(context.context_filter)
            if existing_context:
                return existing_context

            # Else Create new context and get it back to ensure its persistence
            await self.acreate_context(context)
            return await self.aget_context_by_filter(context.context_filter)
        except Exception as e:
            self.logger.error(f"Failed to get or create context: {e}")
            raise

    async def aupdate_context(self, context_id: UUID, context_filter: dict, context_full: dict) -> Context:
        """Update an existing context.

        Args:
            context_id: Context's UUID
            context_filter: New context filter JSON dictionary
            context_full: New full context JSON dictionary

        Returns:
            Updated Context model

        Raises:
            ValueError: If context does not exist
        """
        try:
            # Check if context exists
            existing_context = await self.aget_context_by_id(context_id)
            if not existing_context:
                raise ValueError(f"Context with id {context_id} does not exist")

            # Update context
            await self.data_context.update_entity_async(ContextEntity, context_id, context_filter=context_filter, context_full=context_full)

            # Re-fetch the updated context
            updated_context = await self.aget_context_by_id(context_id)
            if not updated_context:
                raise ValueError(f"Failed to retrieve updated context with id {context_id}")

            return updated_context
        except Exception as e:
            self.logger.error(f"Failed to update context: {e}")
            raise

    async def adelete_context(self, context_id: UUID) -> bool:
        """Delete a context (soft delete).

        Args:
            context_id: Context's UUID

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            await self.data_context.delete_entity_async(ContextEntity, context_id)
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete context: {e}")
            return False
