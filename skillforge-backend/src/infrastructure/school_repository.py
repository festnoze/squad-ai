from typing import Any
from uuid import UUID
from sqlalchemy import select
from common_tools.database.generic_datacontext import GenericDataContext  # type: ignore[import-untyped]
from infrastructure.entities import Base
from infrastructure.entities.school_entity import SchoolEntity
from infrastructure.converters.school_converters import SchoolConverters
from models.school import School
from envvar import EnvHelper


class SchoolRepository:
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

    async def acreate_or_get_by_name(self, school_name: str) -> School:
        """Get existing school by name or create a new one if it doesn't exist."""
        try:
            # Try to get existing school by name
            existing_school = await self.aget_school_by_name(school_name)
            if existing_school:
                return existing_school

            # Create new school as it doesn't exist
            new_school = School(name=school_name)
            school_entity = SchoolConverters.convert_school_model_to_entity(new_school)
            school_entity = await self.data_context.add_entity_async(school_entity)

            created_school = await self.aget_school_by_name(school_name)
            if not created_school:
                raise ValueError(f"Failed to retrieve created school with name '{school_name}'")
            return created_school

        except Exception as e:
            print(f"Failed to create or get school: {e}")
            raise

    async def aget_school_by_name(self, school_name: str) -> School | None:
        """Retrieve school by name."""
        try:
            async with self.data_context.get_session_async() as session:
                stmt = select(SchoolEntity).where(SchoolEntity.name == school_name)
                result = await session.execute(stmt)
                school_entity = result.unique().scalar_one_or_none()
                return SchoolConverters.convert_school_entity_to_model(school_entity) if school_entity else None
        except Exception as e:
            print(f"Failed to get school by name: {e}")
            return None

    async def aget_school_by_id(self, school_id: UUID) -> School | None:
        """Retrieve school by UUID."""
        try:
            school_entity: SchoolEntity = await self.data_context.get_entity_by_id_async(SchoolEntity, school_id)
            return SchoolConverters.convert_school_entity_to_model(school_entity) if school_entity else None
        except Exception as e:
            print(f"Failed to get school by id: {e}")
            return None

    async def acreate_school(self, school: School) -> School:
        """Create a new school in the database."""
        try:
            # Check if school already exists
            existing_school = await self.aget_school_by_name(school.name)
            if existing_school:
                raise ValueError(f"School with name '{school.name}' already exists")

            # Create new school - use converter
            school_entity = SchoolConverters.convert_school_model_to_entity(school)
            school_entity = await self.data_context.add_entity_async(school_entity)

            # Re-fetch to ensure relationships are properly loaded
            created_school = await self.aget_school_by_name(school.name)
            if not created_school:
                raise ValueError(f"Failed to retrieve created school with name '{school.name}'")
            return created_school

        except Exception as e:
            print(f"Failed to create school: {e}")
            raise

    async def aupdate_school(self, school_id: UUID, **kwargs: Any) -> School:
        """Update an existing school in the database."""
        try:
            await self.data_context.update_entity_async(SchoolEntity, school_id, **kwargs)
            updated_school = await self.aget_school_by_id(school_id)
            if not updated_school:
                raise ValueError(f"Failed to retrieve updated school with id {school_id}")
            return updated_school
        except Exception as e:
            print(f"Failed to update school: {e}")
            raise
