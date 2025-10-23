from facade.request_models.context_request import CourseContextStudiRequest
from typing import Any


class ContextHelperStudi:
    @staticmethod
    def get_content_filter_for_studi(context: CourseContextStudiRequest | dict | Any) -> dict:
        """Extract content filter from a CourseContextStudiRequest or dict.

        Args:
            context: Either a CourseContextStudiRequest object or a dict

        Returns:
            A dictionary containing the filter for content
        """
        if isinstance(context, dict):
            # If it's a dict, extract ressource_url if available
            ressource = context.get("ressource")
            if ressource and isinstance(ressource, dict):
                return {"ressource_url": ressource.get("ressource_url")}
            return {"ressource_url": None}
        elif isinstance(context, CourseContextStudiRequest):
            # If it's a CourseContextStudiRequest object
            return {"ressource_url": context.ressource.ressource_url if context.ressource else None}
        else:
            raise ValueError("Invalid context type")
