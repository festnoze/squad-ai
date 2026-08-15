"""Projects router: /api/projects CRUD.

OWNED BY: backend-core agent. Endpoints per docs/CONTRACTS.md section 1.1.
The router below is included from main.py with prefix "/api"; routes are
declared relative to that. Pydantic schemas live in this module.
"""

import shutil

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import UPLOADS_DIR, aget_session
from app.models_core import DEFAULT_THEME, Project, slugify, utcnow_iso

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class Theme(BaseModel):
    primary_color: str = DEFAULT_THEME["primary_color"]
    font: str = DEFAULT_THEME["font"]
    base_spacing: int = DEFAULT_THEME["base_spacing"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)
    slug: str | None = None
    description: str = ""
    theme: Theme = Field(default_factory=Theme)


class ProjectUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    theme: Theme | None = None


class ProjectOut(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    theme: Theme
    created_at: str
    updated_at: str


def project_to_out(project: Project) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description or "",
        theme=Theme(**{**DEFAULT_THEME, **(project.theme or {})}),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


# ---------------------------------------------------------------------------
# Helpers (shared with the pages router)
# ---------------------------------------------------------------------------


async def aget_project_or_404(session: AsyncSession, project_id: int) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def aslug_taken(session: AsyncSession, slug: str, exclude_id: int | None = None) -> bool:
    query = select(Project.id).where(Project.slug == slug)
    if exclude_id is not None:
        query = query.where(Project.id != exclude_id)
    result = await session.execute(query)
    return result.first() is not None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/projects", response_model=list[ProjectOut])
async def alist_projects(session: AsyncSession = Depends(aget_session)):
    result = await session.execute(select(Project).order_by(Project.id))
    return [project_to_out(p) for p in result.scalars().all()]


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def acreate_project(body: ProjectCreate, session: AsyncSession = Depends(aget_session)):
    slug = slugify(body.slug) if body.slug else slugify(body.name)
    if await aslug_taken(session, slug):
        raise HTTPException(status_code=409, detail="A project with this slug already exists")
    now = utcnow_iso()
    project = Project(
        name=body.name,
        slug=slug,
        description=body.description,
        theme=body.theme.model_dump(),
        created_at=now,
        updated_at=now,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project_to_out(project)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def aget_project(project_id: int, session: AsyncSession = Depends(aget_session)):
    project = await aget_project_or_404(session, project_id)
    return project_to_out(project)


@router.put("/projects/{project_id}", response_model=ProjectOut)
async def aupdate_project(
    project_id: int, body: ProjectUpdate, session: AsyncSession = Depends(aget_session)
):
    project = await aget_project_or_404(session, project_id)
    updates = body.model_dump(exclude_unset=True)
    if "slug" in updates and updates["slug"]:
        slug = slugify(updates["slug"])
        if await aslug_taken(session, slug, exclude_id=project.id):
            raise HTTPException(
                status_code=409, detail="A project with this slug already exists"
            )
        project.slug = slug
    if "name" in updates and updates["name"]:
        project.name = updates["name"]
    if "description" in updates and updates["description"] is not None:
        project.description = updates["description"]
    if "theme" in updates and updates["theme"] is not None:
        project.theme = Theme(**updates["theme"]).model_dump()
    project.updated_at = utcnow_iso()
    await session.commit()
    await session.refresh(project)
    return project_to_out(project)


@router.delete("/projects/{project_id}", status_code=204)
async def adelete_project(project_id: int, session: AsyncSession = Depends(aget_session)):
    project = await aget_project_or_404(session, project_id)
    # Pages cascade via FK ON DELETE. CMS tables have no DB-level FK to
    # projects (module decoupling), so purge their rows here; entries then
    # cascade from collections. models_cms is imported lazily.
    try:
        from sqlalchemy import delete as sa_delete

        from app import models_cms

        for model_name in ("Collection", "Asset"):
            model = getattr(models_cms, model_name, None)
            if model is not None:
                await session.execute(sa_delete(model).where(model.project_id == project_id))
    except ImportError:
        pass
    await session.delete(project)
    await session.commit()
    # Uploaded files live under one folder per project.
    shutil.rmtree(UPLOADS_DIR / str(project_id), ignore_errors=True)
    return Response(status_code=204)
