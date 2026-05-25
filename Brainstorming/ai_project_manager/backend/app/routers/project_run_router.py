"""HTTP router for `/api/projects/{project_id}/runs`.

Exposes the V1 "Lancer l'implémentation" flow:

- ``POST /api/projects/{project_id}/runs`` — start a new run. Refuses
  if one is already running for the project (409).
- ``GET  /api/projects/{project_id}/runs/current`` — return the most
  recent run (with its steps) so the frontend can poll for progress.

The heavy lifting lives in `app.application.project_run_service`. This
router is a thin wiring layer that owns HTTP concerns (status codes,
404 on unknown project, 409 on run conflict).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.project_run_service import (
    ProjectRunConflict,
    ProjectRunService,
)
from app.database import get_db
from app.facade.converters.project_run_response_converter import (
    ProjectRunResponseConverter,
)
from app.facade.response_models.project_run_response import (
    ProjectRunDetailResponse,
    ProjectRunResponse,
)
from app.infrastructure.project_repository import ProjectRepository
from app.infrastructure.project_run_repository import ProjectRunRepository

router = APIRouter(prefix="/api/projects", tags=["project-runs"])


def _build_service() -> ProjectRunService:
    """Factory for the run service, overridable in tests via DI."""
    return ProjectRunService()


async def _aensure_project_exists(
    project_id: UUID,
    db: AsyncSession,
) -> None:
    """Raise HTTP 404 if the given project id is unknown."""
    project_repo = ProjectRepository(db)
    project = await project_repo.aget_project_by_id(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )


@router.post(
    "/{project_id}/runs",
    response_model=ProjectRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def astart_project_run(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    service: ProjectRunService = Depends(_build_service),
) -> ProjectRunResponse:
    """Kick off a new project run. 409 if one is already active."""
    await _aensure_project_exists(project_id, db)

    try:
        run = await service.astart_project_run(
            session=db,
            project_id=project_id,
        )
    except ProjectRunConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return ProjectRunResponseConverter.convert_project_run_to_response(run)


@router.get(
    "/{project_id}/runs/current",
    response_model=ProjectRunDetailResponse,
)
async def aget_current_run(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ProjectRunDetailResponse:
    """Return the most recent run for a project, with its steps.

    Returns 404 if the project has never had a run. The frontend
    uses that to decide whether to show the RunPanel or not.
    """
    await _aensure_project_exists(project_id, db)

    repo = ProjectRunRepository(db)
    run = await repo.aget_current_run_for_project(project_id)
    if run is None or run.id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No run found for project {project_id}",
        )
    steps = await repo.aget_steps_by_run(run.id)
    return ProjectRunResponseConverter.convert_detail(run=run, steps=steps)
