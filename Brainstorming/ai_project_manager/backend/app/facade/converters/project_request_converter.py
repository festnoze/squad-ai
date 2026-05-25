"""Converters that turn incoming HTTP request payloads into domain models."""

from app.facade.request_models.project_request import CreateProjectRequest
from app.models.project import Project


class ProjectRequestConverter:
    """Static helpers bridging the HTTP facade and the domain layer."""

    @staticmethod
    def convert_create_request_to_project(req: CreateProjectRequest) -> Project:
        """Build a fresh `Project` domain model from a create request.

        No `id`/`created_at` are set: they are populated by the database on
        insert and then loaded back onto the domain model via the repository.
        """
        return Project(
            name=req.name,
            description=req.description,
        )
