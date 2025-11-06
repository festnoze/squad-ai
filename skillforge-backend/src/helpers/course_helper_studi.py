class CourseHelperStudi:
    @staticmethod
    def get_course_filter_for_studi(course_hierarchy_dict: dict) -> dict:
        """Extract course filter from a CourseContextStudiRequest or dict.

        Args:
            course_hierarchy_dict: A dictionary containing the course hierarchy

        Returns:
            A dictionary containing the filter for course
        """
        if not isinstance(course_hierarchy_dict, dict):
            raise ValueError("Invalid course hierarchy type")

        parcours_code = course_hierarchy_dict.get("parcours_code")
        if not parcours_code:
            raise ValueError("Missing 'parcours_code' field in parcours hierarchy")

        parcours_name = course_hierarchy_dict.get("name", None)
        if not parcours_name:
            raise ValueError("Missing 'name' field in parcours hierarchy")

        parcours_id = course_hierarchy_dict.get("parcours_id", None)
        if not parcours_id:
            raise ValueError("Missing 'parcours_id' field in parcours hierarchy")

        course_filter = {"parcours_id": parcours_id, "parcours_code": parcours_code, "parcours_name": parcours_name}
        return course_filter
