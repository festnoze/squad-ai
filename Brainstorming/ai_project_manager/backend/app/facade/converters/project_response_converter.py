"""Converters that turn domain `Project` models into HTTP responses."""

from app.facade.response_models.project_response import ProjectResponse
from app.models.project import Project


class ProjectResponseConverter:
    """Static helpers bridging the domain layer and the HTTP facade."""

    @staticmethod
    def convert_project_to_response(project: Project) -> ProjectResponse:
        """Convert a single `Project` into its `ProjectResponse` view.

        The `id` and `created_at` fields are required on the response model so
        we assert they are present — they always are for persisted projects,
        but the type checker needs the reassurance.
        """
        if project.id is None or project.created_at is None:
            raise ValueError(
                "Cannot serialize a project missing id/created_at — "
                "this should never happen for a persisted project."
            )
        return ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    @staticmethod
    def convert_projects_to_responses(
        projects: list[Project],
    ) -> list[ProjectResponse]:
        """Convert a list of `Project` models into their response views."""
        return [
            ProjectResponseConverter.convert_project_to_response(project)
            for project in projects
        ]
