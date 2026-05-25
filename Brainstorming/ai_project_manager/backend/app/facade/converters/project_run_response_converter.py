"""Converters between the `ProjectRun` domain layer and HTTP response
models."""

from app.facade.response_models.project_run_response import (
    ProjectRunDetailResponse,
    ProjectRunResponse,
    ProjectRunStepResponse,
)
from app.models.project_run import ProjectRun
from app.models.project_run_step import ProjectRunStep


class ProjectRunResponseConverter:
    """Static helpers for the `project_runs` facade."""

    @staticmethod
    def convert_project_run_to_response(run: ProjectRun) -> ProjectRunResponse:
        if run.id is None or run.created_at is None:
            raise ValueError(
                "Cannot serialize a run missing id/created_at — "
                "this should never happen for a persisted run.",
            )
        return ProjectRunResponse(
            id=run.id,
            project_id=run.project_id,
            status=run.status.value,
            started_at=run.started_at,
            finished_at=run.finished_at,
            error=run.error,
            total_tasks=run.total_tasks,
            done_tasks=run.done_tasks,
            blocked_tasks=run.blocked_tasks,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    @staticmethod
    def convert_project_run_step_to_response(
        step: ProjectRunStep,
    ) -> ProjectRunStepResponse:
        if step.id is None or step.created_at is None:
            raise ValueError(
                "Cannot serialize a step missing id/created_at — "
                "this should never happen for a persisted step.",
            )
        return ProjectRunStepResponse(
            id=step.id,
            run_id=step.run_id,
            item_id=step.item_id,
            role=step.role.value,
            status=step.status.value,
            iteration=step.iteration,
            summary=step.summary,
            detail=step.detail,
            started_at=step.started_at,
            finished_at=step.finished_at,
            created_at=step.created_at,
        )

    @staticmethod
    def convert_detail(
        run: ProjectRun,
        steps: list[ProjectRunStep],
    ) -> ProjectRunDetailResponse:
        return ProjectRunDetailResponse(
            run=ProjectRunResponseConverter.convert_project_run_to_response(run),
            steps=[
                ProjectRunResponseConverter.convert_project_run_step_to_response(s)
                for s in steps
            ],
        )
