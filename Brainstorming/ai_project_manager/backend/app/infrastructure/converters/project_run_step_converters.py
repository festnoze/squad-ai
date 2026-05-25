"""Bidirectional converters between `ProjectRunStepEntity` and
`ProjectRunStep`."""

from app.infrastructure.entities.project_run_step_entity import (
    ProjectRunStepEntity,
)
from app.models.project_run_step import (
    ProjectRunStep,
    ProjectRunStepRole,
    ProjectRunStepStatus,
)


class ProjectRunStepConverters:
    """Static helpers for the `project_run_steps` table."""

    @staticmethod
    def convert_project_run_step_entity_to_model(
        entity: ProjectRunStepEntity,
    ) -> ProjectRunStep:
        return ProjectRunStep(
            id=entity.id,
            run_id=entity.run_id,
            item_id=entity.item_id,
            role=ProjectRunStepRole(entity.role),
            status=ProjectRunStepStatus(entity.status),
            iteration=entity.iteration,
            summary=entity.summary,
            detail=entity.detail,
            started_at=entity.started_at,
            finished_at=entity.finished_at,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            deleted_at=entity.deleted_at,
        )

    @staticmethod
    def convert_project_run_step_model_to_entity(
        model: ProjectRunStep,
    ) -> ProjectRunStepEntity:
        entity = ProjectRunStepEntity(
            run_id=model.run_id,
            item_id=model.item_id,
            role=model.role.value,
            status=model.status.value,
            iteration=model.iteration,
            summary=model.summary,
            detail=model.detail,
            started_at=model.started_at,
            finished_at=model.finished_at,
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
