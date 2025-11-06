import logging
from uuid import UUID
from infrastructure.course_hierarchy_repository import CourseHierarchyRepository
from models.course_hierarchy import CourseHierarchy
from pydantic import ValidationError
from helpers.course_helper_studi import CourseHelperStudi


class CourseService:
    def __init__(self, course_hierarchy_repository: CourseHierarchyRepository) -> None:
        self.logger = logging.getLogger(__name__)
        self.course_hierarchy_repository: CourseHierarchyRepository = course_hierarchy_repository

    async def acreate_course(self, course: CourseHierarchy) -> CourseHierarchy:
        """Create a new course."""
        try:
            return await self.course_hierarchy_repository.acreate_course(course)
        except ValidationError as e:
            raise ValueError(f"Invalid course data: {e}") from e
        except Exception as e:
            raise ValueError(f"Failed to create course: {e}") from e

    async def aget_course_by_id(self, course_id: UUID) -> CourseHierarchy | None:
        """Retrieve a course by its UUID.

        Args:
            course_id: Course's UUID

        Returns:
            Course model if found, None otherwise
        """
        return await self.course_hierarchy_repository.aget_course_by_id(course_id)

    async def aget_course_by_exact_filter(self, course_filter: dict) -> CourseHierarchy | None:
        """Retrieve a course by its filter JSON.

        Args:
            course_filter: Course filter JSON dictionary

        Returns:
            Course model if found, None otherwise
        """
        return await self.course_hierarchy_repository.aget_course_by_exact_filter(course_filter)

    async def acreate_or_update_course_hierarchy(self, course_hierarchy_dict: dict) -> CourseHierarchy:
        """Create or update a course hierarchy and its filter."""
        course: CourseHierarchy

        try:
            # Create course model and filter from dict
            course_filter = CourseHelperStudi.get_course_filter_for_studi(course_hierarchy_dict)
            course = CourseHierarchy(course_filter=course_filter, course_hierarchy=course_hierarchy_dict)
        except ValueError as e:
            raise ValueError(f"Invalid course hierarchy data: {e}") from e
        except Exception as e:
            raise ValueError(f"Fails to build course model: {e}") from e

        try:
            return await self.course_hierarchy_repository.acreate_or_update_course(course)
        except Exception as e:
            raise ValueError(f"Fails to persist course: {e}") from e

    async def adelete_course(self, course_id: UUID) -> bool:
        """Delete a course (soft delete).

        Args:
            course_id: Course's UUID

        Returns:
            True if deleted successfully, False otherwise

        Raises:
            ValueError: If deletion fails
        """
        try:
            return await self.course_hierarchy_repository.adelete_course_by_id(course_id)
        except Exception as e:
            raise ValueError(f"Failed to delete course: {e}") from e
