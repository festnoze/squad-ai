"""Pages router: /api/projects/{project_id}/pages, /preview and /export.

OWNED BY: backend-core agent. Endpoints per docs/CONTRACTS.md section 1.2
(plus the project export of section 1.1). The router is included from
main.py with prefix "/api". Pydantic schemas live in this module.

Set-home is done through PUT {"is_home": true} per CONTRACTS.md (it clears
the flag on the previous home page); there is no separate endpoint.
"""

import copy

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.projects import aget_project_or_404
from app.db import aget_session
from app.models_core import Page, empty_tree, slugify, utcnow_iso
from app.services.export import aexport_site_zip
from app.services.render import arender_page_html

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PageCreate(BaseModel):
    name: str = Field(min_length=1)
    slug: str | None = None
    is_home: bool | None = None


class PageUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    is_home: bool | None = None
    content: dict | None = None


class PageOut(BaseModel):
    id: int
    project_id: int
    name: str
    slug: str
    is_home: bool
    content: dict
    created_at: str
    updated_at: str


def page_to_out(page: Page) -> PageOut:
    return PageOut(
        id=page.id,
        project_id=page.project_id,
        name=page.name,
        slug=page.slug,
        is_home=page.is_home,
        content=page.content or empty_tree(),
        created_at=page.created_at,
        updated_at=page.updated_at,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def aget_page_or_404(session: AsyncSession, project_id: int, page_id: int) -> Page:
    page = await session.get(Page, page_id)
    if page is None or page.project_id != project_id:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


async def apage_slug_taken(
    session: AsyncSession, project_id: int, slug: str, exclude_id: int | None = None
) -> bool:
    query = select(Page.id).where(Page.project_id == project_id, Page.slug == slug)
    if exclude_id is not None:
        query = query.where(Page.id != exclude_id)
    result = await session.execute(query)
    return result.first() is not None


async def aunique_page_slug(session: AsyncSession, project_id: int, base_slug: str) -> str:
    slug = base_slug
    counter = 2
    while await apage_slug_taken(session, project_id, slug):
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


async def aclear_home_flag(session: AsyncSession, project_id: int, except_id: int | None = None):
    query = update(Page).where(Page.project_id == project_id, Page.is_home.is_(True))
    if except_id is not None:
        query = query.where(Page.id != except_id)
    await session.execute(query.values(is_home=False))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/pages", response_model=list[PageOut])
async def alist_pages(project_id: int, session: AsyncSession = Depends(aget_session)):
    await aget_project_or_404(session, project_id)
    result = await session.execute(
        select(Page).where(Page.project_id == project_id).order_by(Page.id)
    )
    return [page_to_out(p) for p in result.scalars().all()]


@router.post("/projects/{project_id}/pages", response_model=PageOut, status_code=201)
async def acreate_page(
    project_id: int, body: PageCreate, session: AsyncSession = Depends(aget_session)
):
    await aget_project_or_404(session, project_id)
    slug = slugify(body.slug) if body.slug else slugify(body.name)
    if await apage_slug_taken(session, project_id, slug):
        raise HTTPException(
            status_code=409, detail="A page with this slug already exists in this project"
        )
    result = await session.execute(
        select(Page.id).where(Page.project_id == project_id).limit(1)
    )
    is_first_page = result.first() is None
    is_home = body.is_home if body.is_home is not None else is_first_page
    if is_home:
        await aclear_home_flag(session, project_id)
    now = utcnow_iso()
    page = Page(
        project_id=project_id,
        name=body.name,
        slug=slug,
        is_home=is_home,
        content=empty_tree(),
        created_at=now,
        updated_at=now,
    )
    session.add(page)
    await session.commit()
    await session.refresh(page)
    return page_to_out(page)


@router.get("/projects/{project_id}/pages/{page_id}", response_model=PageOut)
async def aget_page(
    project_id: int, page_id: int, session: AsyncSession = Depends(aget_session)
):
    await aget_project_or_404(session, project_id)
    page = await aget_page_or_404(session, project_id, page_id)
    return page_to_out(page)


@router.put("/projects/{project_id}/pages/{page_id}", response_model=PageOut)
async def aupdate_page(
    project_id: int,
    page_id: int,
    body: PageUpdate,
    session: AsyncSession = Depends(aget_session),
):
    await aget_project_or_404(session, project_id)
    page = await aget_page_or_404(session, project_id, page_id)
    updates = body.model_dump(exclude_unset=True)
    if "slug" in updates and updates["slug"]:
        slug = slugify(updates["slug"])
        if await apage_slug_taken(session, project_id, slug, exclude_id=page.id):
            raise HTTPException(
                status_code=409, detail="A page with this slug already exists in this project"
            )
        page.slug = slug
    if "name" in updates and updates["name"]:
        page.name = updates["name"]
    if "is_home" in updates and updates["is_home"] is not None:
        if updates["is_home"]:
            await aclear_home_flag(session, project_id, except_id=page.id)
        page.is_home = updates["is_home"]
    if "content" in updates and updates["content"] is not None:
        page.content = updates["content"]
    page.updated_at = utcnow_iso()
    await session.commit()
    await session.refresh(page)
    return page_to_out(page)


@router.post(
    "/projects/{project_id}/pages/{page_id}/duplicate",
    response_model=PageOut,
    status_code=201,
)
async def aduplicate_page(
    project_id: int, page_id: int, session: AsyncSession = Depends(aget_session)
):
    await aget_project_or_404(session, project_id)
    source = await aget_page_or_404(session, project_id, page_id)
    slug = await aunique_page_slug(session, project_id, f"{source.slug}-copy")
    now = utcnow_iso()
    clone = Page(
        project_id=project_id,
        name=f"{source.name} copy",
        slug=slug,
        is_home=False,
        content=copy.deepcopy(source.content or empty_tree()),
        created_at=now,
        updated_at=now,
    )
    session.add(clone)
    await session.commit()
    await session.refresh(clone)
    return page_to_out(clone)


@router.delete("/projects/{project_id}/pages/{page_id}", status_code=204)
async def adelete_page(
    project_id: int, page_id: int, session: AsyncSession = Depends(aget_session)
):
    await aget_project_or_404(session, project_id)
    page = await aget_page_or_404(session, project_id, page_id)
    await session.delete(page)
    await session.commit()
    return Response(status_code=204)


@router.get("/projects/{project_id}/pages/{page_id}/preview", response_class=HTMLResponse)
async def apreview_page(
    project_id: int, page_id: int, session: AsyncSession = Depends(aget_session)
):
    project = await aget_project_or_404(session, project_id)
    page = await aget_page_or_404(session, project_id, page_id)
    html_doc = await arender_page_html(session, project, page)
    return HTMLResponse(content=html_doc)


@router.get("/projects/{project_id}/export")
async def aexport_project(project_id: int, session: AsyncSession = Depends(aget_session)):
    project = await aget_project_or_404(session, project_id)
    zip_bytes = await aexport_site_zip(session, project)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{project.slug}.zip"'},
    )
