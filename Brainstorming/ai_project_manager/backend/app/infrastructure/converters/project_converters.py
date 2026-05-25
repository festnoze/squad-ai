"""Bidirectional converters between `ProjectEntity` and `Project`."""

from app.infrastructure.entities.project_entity import ProjectEntity
from app.models.project import Project


class ProjectConverters:
    """Static helpers to keep the domain layer free of SQLAlchemy leaks."""

    @staticmethod
    def convert_project_entity_to_model(entity: ProjectEntity) -> Project:
        """Convert a SQLAlchemy entity into a Pydantic domain model."""
        return Project(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            deleted_at=entity.deleted_at,
        )

    @staticmethod
    def convert_project_model_to_entity(model: Project) -> ProjectEntity:
        """Convert a Pydantic domain model into a SQLAlchemy entity.

        Only populates fields that are not None so that the database's default
        values (e.g. `created_at`) can kick in for fresh inserts.
        """
        entity = ProjectEntity(
            name=model.name,
            description=model.description,
        )
        if model.id is not None:
            entity.id = model.id
        if model.created_at is not None:
            entity.created_at = model.created_at
        if model.updated_at is not None:
            entity.updated_at = model.updated_at
        if model.deleted_at is not None:
            entity.deleted_at = model.deleted_at
        return entity
