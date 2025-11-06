import logging
from uuid import UUID
from sqlalchemy import select
from common_tools.database.generic_datacontext import GenericDataContext  # type: ignore[import-untyped]
from infrastructure.entities import Base
from infrastructure.entities.course_hierarchy_entity import CourseHierarchyEntity
from infrastructure.converters.course_converters import CourseConverters
from models.course_hierarchy import CourseHierarchy
from infrastructure.helpers.database_helper import DatabaseHelper
from infrastructure.helpers.json_filter_helper import JsonFilterHelperMixin


class CourseHierarchyRepository(JsonFilterHelperMixin):
    def __init__(self, db_path_or_url: str | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        self.db_path_or_url = DatabaseHelper.build_postgres_connection_url(db_path_or_url)
        self.data_context = GenericDataContext(Base, self.db_path_or_url)

    async def aget_course_by_id(self, course_id: UUID) -> CourseHierarchy | None:
        """Retrieve a course by its UUID.

        Args:
            course_id: Course's UUID

        Returns:
            Course model if found, None otherwise
        """
        try:
            course_entity: CourseHierarchyEntity = await self.data_context.get_entity_by_id_async(CourseHierarchyEntity, course_id)
            return CourseConverters.convert_course_entity_to_model(course_entity) if course_entity else None
        except Exception as e:
            self.logger.error(f"Failed to get course by id: {e}")
            return None

    async def aget_course_by_exact_filter(self, course_filter: dict) -> CourseHierarchy | None:
        """Retrieve a course by exact match of its JSON content.

        Args:
            course_filter: Course to filter by - JSON dictionary (exact match)

        Returns:
            Course model if found, None otherwise
        """
        try:
            async with self.data_context.get_session_async() as session:
                # JSONB type supports direct equality comparison in PostgreSQL
                stmt = select(CourseHierarchyEntity).where(CourseHierarchyEntity.course_filter == course_filter)
                result = await session.execute(stmt)
                course_entity = result.unique().scalar_one_or_none()
                return CourseConverters.convert_course_entity_to_model(course_entity) if course_entity else None
        except Exception as e:
            self.logger.error(f"Failed to get the course filter prop: {e}")
            return None

    async def aget_course_hierarchy_by_partial_filter(self, partial_filter: dict) -> CourseHierarchy | None:
        """Retrieve a course by partial match within its JSONB course_filter field.

        Uses database-agnostic JSON containment filtering (JSONB @> for PostgreSQL,
        json_extract for SQLite).

        Args:
            partial_filter: Partial course filter dictionary to match

        Returns:
            CourseHierarchy model if found, None otherwise
        """
        try:
            async with self.data_context.get_session_async() as session:
                # Use generalized JSON containment filter
                filter_condition = self._build_json_containment_filter(CourseHierarchyEntity.course_filter, partial_filter)
                stmt = select(CourseHierarchyEntity).where(filter_condition)

                result = await session.execute(stmt)
                course_entity = result.unique().scalar_one_or_none()
                return CourseConverters.convert_course_entity_to_model(course_entity) if course_entity else None
        except Exception as e:
            self.logger.error(f"Failed to get course by partial filter: {e}")
            return None

    async def acreate_or_update_course(self, course: CourseHierarchy) -> CourseHierarchy:
        """Create or update a course based on the course hierarchy model."""
        try:
            # Check if course already exists
            existing_course = await self.aget_course_by_exact_filter(course.course_filter)
            if existing_course and existing_course.id:
                return await self.aupdate_course(existing_course.id, course.course_filter, course.course_hierarchy)

            # Else Create new course
            return await self.acreate_course(course)
        except Exception as e:
            self.logger.error(f"Failed to get or create course: {e}")
            raise

    async def acreate_course(self, course: CourseHierarchy) -> CourseHierarchy:
        """Create a new course in the database."""
        try:
            course_entity = CourseConverters.convert_course_model_to_entity(course)
            course_entity = await self.data_context.add_entity_async(course_entity)
            return CourseConverters.convert_course_entity_to_model(course_entity)
        except Exception as e:
            self.logger.error(f"Failed to create course: {e}")
            raise

    async def aupdate_course(self, course_id: UUID, course_filter: dict, course_hierarchy: dict) -> CourseHierarchy:
        """Update an existing course."""
        try:
            # Check if course exists
            existing_course = await self.aget_course_by_id(course_id)
            if not existing_course:
                raise ValueError(f"Course with id {course_id} does not exist")

            # Update course
            await self.data_context.update_entity_async(CourseHierarchyEntity, course_id, course_filter=course_filter, course_hierarchy=course_hierarchy)

            # Re-fetch the updated course
            updated_course = await self.aget_course_by_id(course_id)
            if not updated_course:
                raise ValueError(f"Failed to retrieve updated course with id {course_id}")

            return updated_course
        except Exception as e:
            self.logger.error(f"Failed to update course: {e}")
            raise

    async def adelete_course_by_id(self, course_id: UUID) -> bool:
        """Delete a course (soft delete)."""
        try:
            await self.data_context.delete_entity_async(CourseHierarchyEntity, course_id)
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete course: {e}")
            return False
