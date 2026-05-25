"""Repository for the `project_runs` and `project_run_steps` tables.

A single repository covers both tables because they are tightly coupled
and always read/written together from the orchestration service. The
application layer never manipulates one without touching the other.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.infrastructure.base_repository import BaseRepository
from app.infrastructure.converters.project_run_converters import (
    ProjectRunConverters,
)
from app.infrastructure.converters.project_run_step_converters import (
    ProjectRunStepConverters,
)
from app.infrastructure.entities.project_run_entity import ProjectRunEntity
from app.infrastructure.entities.project_run_step_entity import (
    ProjectRunStepEntity,
)
from app.models.project_run import ProjectRun, ProjectRunStatus
from app.models.project_run_step import ProjectRunStep


class ProjectRunRepository(BaseRepository):
    """Domain-friendly facade around `project_runs` + `project_run_steps`."""

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    async def acreate_run(self, run: ProjectRun) -> ProjectRun:
        entity = ProjectRunConverters.convert_project_run_model_to_entity(run)
        entity = await self.aadd_entity(entity)
        return ProjectRunConverters.convert_project_run_entity_to_model(entity)

    async def aget_run_by_id(self, run_id: UUID) -> ProjectRun | None:
        entity = await self.aget_entity_by_id(ProjectRunEntity, run_id)
        if entity is None:
            return None
        return ProjectRunConverters.convert_project_run_entity_to_model(entity)

    async def aget_current_run_for_project(
        self,
        project_id: UUID,
    ) -> ProjectRun | None:
        """Return the most recent run for a project (running or otherwise).

        The frontend uses this to poll for live progress and to render
        the final status when the run is over.
        """
        query = (
            select(ProjectRunEntity)
            .where(ProjectRunEntity.project_id == project_id)
            .where(ProjectRunEntity.deleted_at.is_(None))
            .order_by(ProjectRunEntity.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        entity = result.scalars().first()
        if entity is None:
            return None
        return ProjectRunConverters.convert_project_run_entity_to_model(entity)

    async def aget_active_run_for_project(
        self,
        project_id: UUID,
    ) -> ProjectRun | None:
        """Return the in-flight run for a project, if any.

        Used by the service layer to refuse starting a second run while
        one is already running (409 Conflict).
        """
        query = (
            select(ProjectRunEntity)
            .where(ProjectRunEntity.project_id == project_id)
            .where(ProjectRunEntity.deleted_at.is_(None))
            .where(
                ProjectRunEntity.status.in_(
                    [ProjectRunStatus.PENDING.value, ProjectRunStatus.RUNNING.value]
                )
            )
            .limit(1)
        )
        result = await self.session.execute(query)
        entity = result.scalars().first()
        if entity is None:
            return None
        return ProjectRunConverters.convert_project_run_entity_to_model(entity)

    async def aupdate_run_fields(
        self,
        run_id: UUID,
        **fields: Any,
    ) -> ProjectRun | None:
        """Partial update of a run row (counters, status, finished_at, ...)."""
        normalised: dict[str, Any] = {}
        for key, value in fields.items():
            if hasattr(value, "value"):
                normalised[key] = value.value
            else:
                normalised[key] = value
        updated = await self.aupdate_entity(
            ProjectRunEntity,
            run_id,
            **normalised,
        )
        if updated is None:
            return None
        return ProjectRunConverters.convert_project_run_entity_to_model(updated)

    async def aget_orphan_running_runs(self) -> list[ProjectRun]:
        """Return every run left in ``running`` or ``pending`` state.

        Called by the startup hook to mark them as ``failed`` with reason
        ``server_restart`` — they cannot possibly still be running
        because the only process that could drive them (the previous
        FastAPI instance) is gone.
        """
        query = (
            select(ProjectRunEntity)
            .where(
                ProjectRunEntity.status.in_(
                    [ProjectRunStatus.PENDING.value, ProjectRunStatus.RUNNING.value]
                )
            )
            .where(ProjectRunEntity.deleted_at.is_(None))
        )
        result = await self.session.execute(query)
        entities = list(result.scalars().all())
        return [
            ProjectRunConverters.convert_project_run_entity_to_model(e)
            for e in entities
        ]

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    async def acreate_step(self, step: ProjectRunStep) -> ProjectRunStep:
        entity = (
            ProjectRunStepConverters.convert_project_run_step_model_to_entity(step)
        )
        entity = await self.aadd_entity(entity)
        return ProjectRunStepConverters.convert_project_run_step_entity_to_model(
            entity,
        )

    async def aupdate_step_fields(
        self,
        step_id: UUID,
        **fields: Any,
    ) -> ProjectRunStep | None:
        normalised: dict[str, Any] = {}
        for key, value in fields.items():
            if hasattr(value, "value"):
                normalised[key] = value.value
            else:
                normalised[key] = value
        updated = await self.aupdate_entity(
            ProjectRunStepEntity,
            step_id,
            **normalised,
        )
        if updated is None:
            return None
        return ProjectRunStepConverters.convert_project_run_step_entity_to_model(
            updated,
        )

    async def aget_steps_by_run(self, run_id: UUID) -> list[ProjectRunStep]:
        query = (
            select(ProjectRunStepEntity)
            .where(ProjectRunStepEntity.run_id == run_id)
            .where(ProjectRunStepEntity.deleted_at.is_(None))
            .order_by(ProjectRunStepEntity.created_at.asc())
        )
        result = await self.session.execute(query)
        entities = list(result.scalars().all())
        return [
            ProjectRunStepConverters.convert_project_run_step_entity_to_model(e)
            for e in entities
        ]
