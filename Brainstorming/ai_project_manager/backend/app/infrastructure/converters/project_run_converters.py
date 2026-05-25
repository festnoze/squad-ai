"""Bidirectional converters between `ProjectRunEntity` and `ProjectRun`."""

from app.infrastructure.entities.project_run_entity import ProjectRunEntity
from app.models.project_run import ProjectRun, ProjectRunStatus


class ProjectRunConverters:
    """Static helpers for the `project_runs` table."""

    @staticmethod
    def convert_project_run_entity_to_model(
        entity: ProjectRunEntity,
    ) -> ProjectRun:
        return ProjectRun(
            id=entity.id,
            project_id=entity.project_id,
            status=ProjectRunStatus(entity.status),
            started_at=entity.started_at,
            finished_at=entity.finished_at,
            error=entity.error,
            total_tasks=entity.total_tasks,
            done_tasks=entity.done_tasks,
            blocked_tasks=entity.blocked_tasks,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            deleted_at=entity.deleted_at,
        )

    @staticmethod
    def convert_project_run_model_to_entity(
        model: ProjectRun,
    ) -> ProjectRunEntity:
        entity = ProjectRunEntity(
            project_id=model.project_id,
            status=model.status.value,
            started_at=model.started_at,
            finished_at=model.finished_at,
            error=model.error,
            total_tasks=model.total_tasks,
            done_tasks=model.done_tasks,
            blocked_tasks=model.blocked_tasks,
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
