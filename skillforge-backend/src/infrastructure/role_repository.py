import logging
from sqlalchemy import select
from common_tools.database.generic_datacontext import GenericDataContext  # type: ignore[import-untyped]
from infrastructure.entities import Base
from infrastructure.entities.role_entity import RoleEntity
from infrastructure.converters.role_converters import RoleConverters
from models.role import Role
from envvar import EnvHelper
from infrastructure.helpers.database_helper import DatabaseHelper


class RoleRepository:
    def __init__(self, db_path_or_url: str | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        self.db_path_or_url = DatabaseHelper.build_postgres_connection_url(db_path_or_url)
        self.data_context = GenericDataContext(Base, self.db_path_or_url)
        host = EnvHelper.get_postgres_host()
        dbname = EnvHelper.get_postgres_database_name()
        self.logger.debug(f"RoleRepository initialized with database: {host}/{dbname}")

    async def aget_by_name(self, role_name: str) -> Role | None:
        """Get a role by its name.

        Args:
            role_name: The name of the role to retrieve

        Returns:
            Role model if found, None otherwise
        """
        try:
            async with self.data_context.get_session_async() as session:
                stmt = select(RoleEntity).where(RoleEntity.name == role_name)
                result = await session.execute(stmt)
                role_entity = result.scalar_one_or_none()

                # Check if static data exists, if not fill it
                if not role_entity:
                    if not await self.astatic_data_exists():
                        await self.afill_roles()
                        self.logger.info("Static data for 'roles' filled successfully into database.")
                        return await self.aget_by_name(role_name)

                return RoleConverters.convert_role_entity_to_model(role_entity)

        except Exception as e:
            self.logger.error(f"Failed to get role by name '{role_name}': {e}")
            raise

    async def astatic_data_exists(self) -> bool:
        """Check if static role data exists in the database.

        Returns:
            True if at least one role exists in the database, False otherwise
        """
        try:
            async with self.data_context.get_session_async() as session:
                stmt = select(RoleEntity).limit(1)
                result = await session.execute(stmt)
                role_entity = result.scalar_one_or_none()
                return role_entity is not None

        except Exception as e:
            self.logger.error(f"Failed to check if static data exists: {e}")
            raise

    async def afill_roles(self) -> None:
        """Fill default roles (user, assistant) into the database.

        This method is idempotent - it will only create roles that don't already exist.
        """
        default_roles = ["user", "assistant"]
        try:
            async with self.data_context.get_session_async() as session:
                for role_name in default_roles:
                    stmt = select(RoleEntity).where(RoleEntity.name == role_name)
                    result = await session.execute(stmt)
                    existing_role = result.scalar_one_or_none()
                    if not existing_role:
                        new_role = RoleEntity(name=role_name)
                        session.add(new_role)
                        self.logger.info(f"Created role: {role_name}")
                await session.commit()
                self.logger.info("Role static data filled successfully")

        except Exception as e:
            self.logger.error(f"Failed to fill roles: {e}")
            raise
