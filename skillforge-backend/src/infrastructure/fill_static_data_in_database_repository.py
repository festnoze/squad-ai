import logging
from common_tools.database.generic_datacontext import GenericDataContext  # type: ignore[import-untyped]
from infrastructure.entities import Base
from infrastructure.role_repository import RoleRepository
from infrastructure.helpers.database_helper import DatabaseHelper


class DatabaseAdministrationRepository:
    """Handles filling of static/reference data into the database."""

    def __init__(self, role_repository: RoleRepository, db_path_or_url: str | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        # Override env. variables if db_path_or_url is provided
        self.db_path_or_url = DatabaseHelper.build_postgres_connection_url(db_path_or_url)
        self.data_context = GenericDataContext(Base, self.db_path_or_url)
        self.role_repository = role_repository

    def reset_database(self) -> None:
        self.data_context.drop_all_tables_postgre()
        # self.data_context = GenericDataContext(Base, self.db_path_or_url)

    async def afill_all_static_data(self) -> None:
        """Fill all static/reference data into the database."""
        # Check if static data already exists before filling
        if not await self.role_repository.astatic_data_exists():
            await self.role_repository.afill_roles()
            self.logger.info("Static data filled successfully")
        else:
            self.logger.info("Static data already exists, skipping fill")

        # Create database indexes for better query performance
        await self.acreate_database_indexes()

    async def acreate_database_indexes(self) -> None:
        """Create indexes on frequently queried columns for performance optimization."""
        try:
            async with self.data_context.get_session_async() as session:
                # Index on threads table for user_id and context_id lookups
                await session.execute("CREATE INDEX IF NOT EXISTS idx_threads_user_context ON threads(user_id, context_id) WHERE deleted_at IS NULL;")

                # Index on contexts table for JSONB containment queries
                # GIN index is optimal for JSONB containment operators
                await session.execute("CREATE INDEX IF NOT EXISTS idx_contexts_filter_gin ON contexts USING GIN(context_filter) WHERE deleted_at IS NULL;")

                # Index on messages table for thread_id lookups
                await session.execute("CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id) WHERE deleted_at IS NULL;")

                # Index on users table for lms_user_id lookups (commonly used for authentication)
                await session.execute("CREATE INDEX IF NOT EXISTS idx_users_lms_id ON users(lms_user_id) WHERE deleted_at IS NULL;")

                await session.commit()
                self.logger.info("Database indexes created successfully")
        except Exception as e:
            # Indexes might already exist - this is not a critical error
            self.logger.warning(f"Note when creating indexes (this is usually harmless): {e}")
