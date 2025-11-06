from infrastructure.entities.course_hierarchy_entity import CourseHierarchyEntity
from models.course_hierarchy import CourseHierarchy


class CourseConverters:
    @staticmethod
    def convert_course_entity_to_model(course_hierarchy_entity: CourseHierarchyEntity) -> CourseHierarchy:
        """Convert a CourseHierarchyEntity to a Course model.

        Args:
            course_hierarchy_entity: The database entity to convert

        Returns:
            Course model instance
        """
        return CourseHierarchy(
            id=course_hierarchy_entity.id,
            course_filter=course_hierarchy_entity.course_filter,
            course_hierarchy=course_hierarchy_entity.course_hierarchy,
            created_at=course_hierarchy_entity.created_at,
            updated_at=course_hierarchy_entity.updated_at,
            deleted_at=course_hierarchy_entity.deleted_at,
        )

    @staticmethod
    def convert_course_model_to_entity(course_hierarchy: CourseHierarchy) -> CourseHierarchyEntity:
        """Convert a Course model to a CourseHierarchyEntity.

        Args:
            course_hierarchy: The Course model to convert

        Returns:
            CourseHierarchyEntity instance
        """
        return CourseHierarchyEntity(
            id=course_hierarchy.id,
            course_filter=course_hierarchy.course_filter,
            course_hierarchy=course_hierarchy.course_hierarchy,
            created_at=course_hierarchy.created_at,
            updated_at=course_hierarchy.updated_at,
            deleted_at=course_hierarchy.deleted_at,
        )
