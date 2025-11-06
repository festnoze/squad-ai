from models.base_model import IdStatefulBaseModel


class CourseHierarchy(IdStatefulBaseModel):
    """Course model representing a course structure.

    Inherits common fields (id, created_at, updated_at, deleted_at) from IdStatefulBaseModel.

    Attributes:
        course_filter: JSON object containing course filter information
        course_hierarchy: JSON object containing course hierarchy information
    """

    course_filter: dict = {}
    course_hierarchy: dict = {}
