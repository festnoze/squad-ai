from sqlalchemy import select
from infrastructure.entities.role_entity import RoleEntity
from envvar import EnvHelper
from common_tools.database.generic_datacontext import GenericDataContext  # type: ignore[import-untyped]
from infrastructure.entities import Base


class DatabaseAdministrationRepository:
    """Handles filling of static/reference data into the database."""

    def __init__(self, db_path_or_url: str | None = None) -> None:
        if db_path_or_url:
            self.db_path_or_url = db_path_or_url
        else:
            username = EnvHelper.get_postgres_username()
            password = EnvHelper.get_postgres_password()
            host = EnvHelper.get_postgres_host()
            dbname = EnvHelper.get_postgres_database_name()
            self.db_path_or_url = f"postgresql://{username}:{password}@{host}/{dbname}"
        #
        self.data_context = GenericDataContext(Base, self.db_path_or_url)

    def reset_database(self) -> None:
        self.data_context.drop_all_tables_postgre()
        # self.data_context = GenericDataContext(Base, self.db_path_or_url)

    async def afill_all_static_data(self) -> None:
        """Fill all static/reference data into the database."""
        await self.afill_roles()

    async def afill_roles(self) -> None:
        """Fill default roles (user, assistant) into the database."""
        default_roles = ["user", "assistant"]
        async with self.data_context.get_session_async() as session:
            for role_name in default_roles:
                stmt = select(RoleEntity).where(RoleEntity.name == role_name)
                result = await session.execute(stmt)
                existing_role = result.scalar_one_or_none()
                if not existing_role:
                    new_role = RoleEntity(name=role_name)
                    session.add(new_role)
            await session.commit()
