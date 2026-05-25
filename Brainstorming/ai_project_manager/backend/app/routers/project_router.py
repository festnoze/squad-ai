"""HTTP router for `/api/projects`.

Implements the full CRUD surface exposed by Epic 1 of the PRD:

- ``GET    /api/projects``       — list every non-deleted project
- ``POST   /api/projects``       — create a new project
- ``PATCH  /api/projects/{id}``  — partial update
- ``DELETE /api/projects/{id}``  — soft-delete

Architecture note: Epic 1 is pure CRUD with no business orchestration, so the
router intentionally SKIPS the application/service layer and talks directly to
the `ProjectRepository`. Services will be introduced when an endpoint needs to
coordinate multiple repositories or call the LLM.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.facade.converters.project_request_converter import ProjectRequestConverter
from app.facade.converters.project_response_converter import ProjectResponseConverter
from app.facade.request_models.project_request import (
    CreateProjectRequest,
    UpdateProjectRequest,
)
from app.facade.response_models.project_response import ProjectResponse
from app.infrastructure.project_repository import ProjectRepository

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
async def aget_all_projects(
    db: AsyncSession = Depends(get_db),
) -> list[ProjectResponse]:
    """Return every non-deleted project, most recently updated first."""
    repo = ProjectRepository(db)
    projects = await repo.aget_all_projects()
    return ProjectResponseConverter.convert_projects_to_responses(projects)


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def acreate_project(
    req: CreateProjectRequest,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Create a new project from the request payload."""
    repo = ProjectRepository(db)
    project = ProjectRequestConverter.convert_create_request_to_project(req)
    created = await repo.acreate_project(project)
    return ProjectResponseConverter.convert_project_to_response(created)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def aupdate_project(
    project_id: UUID,
    req: UpdateProjectRequest,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Partially update a project. Unset fields are left untouched."""
    repo = ProjectRepository(db)
    fields = req.model_dump(exclude_unset=True)
    updated = await repo.aupdate_project_fields(project_id, **fields)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return ProjectResponseConverter.convert_project_to_response(updated)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def adelete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete a project and cascade on its items + chat messages.

    404 if the project does not exist (or is already soft-deleted).
    """
    repo = ProjectRepository(db)
    deleted = await repo.adelete_project_cascade(project_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
