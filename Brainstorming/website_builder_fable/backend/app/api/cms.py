"""CMS router: /api/projects/{project_id}/collections and nested entries.

OWNED BY: backend-cms agent. Endpoints per docs/CONTRACTS.md section 1.3 and
docs/decisions-cms.md section 3. The router below is included from main.py
with prefix "/api"; routes are declared relative to that.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cms.utils import aensure_project, now_iso, slugify
from app.cms.validation import normalize_entry_data, validate_entry_data
from app.db import aget_session
from app.models_cms import Asset, Collection, Entry
from app.schemas_cms import CollectionCreate, CollectionUpdate, EntryCreate

router = APIRouter()


def _collection_out(collection: Collection, entry_count: int) -> dict:
    return {
        "id": collection.id,
        "project_id": collection.project_id,
        "name": collection.name,
        "slug": collection.slug,
        "fields": collection.fields,
        "entry_count": entry_count,
        "created_at": collection.created_at,
        "updated_at": collection.updated_at,
    }


def _entry_out(entry: Entry, fields: list[dict]) -> dict:
    return {
        "id": entry.id,
        "collection_id": entry.collection_id,
        "data": normalize_entry_data(fields, entry.data),
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


async def _acount_entries(session: AsyncSession, collection_id: int) -> int:
    result = await session.execute(
        select(func.count()).select_from(Entry).where(Entry.collection_id == collection_id)
    )
    return result.scalar_one()


async def _aget_collection_or_404(
    session: AsyncSession, project_id: int, collection_id: int
) -> Collection:
    await aensure_project(session, project_id)
    collection = await session.get(Collection, collection_id)
    if collection is None or collection.project_id != project_id:
        raise HTTPException(status_code=404, detail="Collection not found")
    return collection


async def _aget_entry_or_404(
    session: AsyncSession, project_id: int, collection_id: int, entry_id: int
) -> tuple[Collection, Entry]:
    collection = await _aget_collection_or_404(session, project_id, collection_id)
    entry = await session.get(Entry, entry_id)
    if entry is None or entry.collection_id != collection.id:
        raise HTTPException(status_code=404, detail="Entry not found")
    return collection, entry


async def _aslug_conflict(
    session: AsyncSession, project_id: int, slug: str, exclude_id: int | None = None
) -> bool:
    stmt = select(Collection.id).where(
        Collection.project_id == project_id, Collection.slug == slug
    )
    if exclude_id is not None:
        stmt = stmt.where(Collection.id != exclude_id)
    return (await session.execute(stmt)).first() is not None


async def _aproject_asset_ids(session: AsyncSession, project_id: int) -> set[int]:
    result = await session.execute(select(Asset.id).where(Asset.project_id == project_id))
    return set(result.scalars().all())


# ---------------------------------------------------------------- collections


@router.get("/projects/{project_id}/collections")
async def alist_collections(
    project_id: int, session: AsyncSession = Depends(aget_session)
):
    await aensure_project(session, project_id)
    collections = (
        (
            await session.execute(
                select(Collection)
                .where(Collection.project_id == project_id)
                .order_by(Collection.id)
            )
        )
        .scalars()
        .all()
    )
    counts_result = await session.execute(
        select(Entry.collection_id, func.count(Entry.id))
        .join(Collection, Entry.collection_id == Collection.id)
        .where(Collection.project_id == project_id)
        .group_by(Entry.collection_id)
    )
    counts = dict(counts_result.all())
    return [_collection_out(c, counts.get(c.id, 0)) for c in collections]


@router.post("/projects/{project_id}/collections", status_code=201)
async def acreate_collection(
    project_id: int,
    payload: CollectionCreate,
    session: AsyncSession = Depends(aget_session),
):
    await aensure_project(session, project_id)
    slug = slugify(payload.slug) if payload.slug else slugify(payload.name)
    if await _aslug_conflict(session, project_id, slug):
        raise HTTPException(
            status_code=409,
            detail="A collection with this slug already exists in this project",
        )
    now = now_iso()
    collection = Collection(
        project_id=project_id,
        name=payload.name,
        slug=slug,
        fields=[f.model_dump() for f in payload.fields],
        created_at=now,
        updated_at=now,
    )
    session.add(collection)
    await session.commit()
    await session.refresh(collection)
    return _collection_out(collection, 0)


@router.get("/projects/{project_id}/collections/{collection_id}")
async def aget_collection(
    project_id: int, collection_id: int, session: AsyncSession = Depends(aget_session)
):
    collection = await _aget_collection_or_404(session, project_id, collection_id)
    return _collection_out(collection, await _acount_entries(session, collection.id))


@router.put("/projects/{project_id}/collections/{collection_id}")
async def aupdate_collection(
    project_id: int,
    collection_id: int,
    payload: CollectionUpdate,
    session: AsyncSession = Depends(aget_session),
):
    collection = await _aget_collection_or_404(session, project_id, collection_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("slug"):
        new_slug = slugify(updates["slug"])
        if await _aslug_conflict(session, project_id, new_slug, exclude_id=collection.id):
            raise HTTPException(
                status_code=409,
                detail="A collection with this slug already exists in this project",
            )
        collection.slug = new_slug
    if updates.get("name"):
        collection.name = updates["name"]
    if "fields" in updates and payload.fields is not None:
        collection.fields = [f.model_dump() for f in payload.fields]
    collection.updated_at = now_iso()
    await session.commit()
    await session.refresh(collection)
    return _collection_out(collection, await _acount_entries(session, collection.id))


@router.delete("/projects/{project_id}/collections/{collection_id}", status_code=204)
async def adelete_collection(
    project_id: int, collection_id: int, session: AsyncSession = Depends(aget_session)
):
    collection = await _aget_collection_or_404(session, project_id, collection_id)
    await session.execute(delete(Entry).where(Entry.collection_id == collection.id))
    await session.delete(collection)
    await session.commit()
    return Response(status_code=204)


# -------------------------------------------------------------------- entries


@router.get("/projects/{project_id}/collections/{collection_id}/entries")
async def alist_entries(
    project_id: int,
    collection_id: int,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(aget_session),
):
    collection = await _aget_collection_or_404(session, project_id, collection_id)
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    total = await _acount_entries(session, collection.id)
    entries = (
        (
            await session.execute(
                select(Entry)
                .where(Entry.collection_id == collection.id)
                .order_by(Entry.created_at.desc(), Entry.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return {"total": total, "items": [_entry_out(e, collection.fields) for e in entries]}


@router.post(
    "/projects/{project_id}/collections/{collection_id}/entries", status_code=201
)
async def acreate_entry(
    project_id: int,
    collection_id: int,
    payload: EntryCreate,
    session: AsyncSession = Depends(aget_session),
):
    collection = await _aget_collection_or_404(session, project_id, collection_id)
    asset_ids = await _aproject_asset_ids(session, project_id)
    errors = validate_entry_data(collection.fields, payload.data, asset_ids)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    now = now_iso()
    entry = Entry(
        collection_id=collection.id, data=payload.data, created_at=now, updated_at=now
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return _entry_out(entry, collection.fields)


@router.get("/projects/{project_id}/collections/{collection_id}/entries/{entry_id}")
async def aget_entry(
    project_id: int,
    collection_id: int,
    entry_id: int,
    session: AsyncSession = Depends(aget_session),
):
    collection, entry = await _aget_entry_or_404(
        session, project_id, collection_id, entry_id
    )
    return _entry_out(entry, collection.fields)


@router.put("/projects/{project_id}/collections/{collection_id}/entries/{entry_id}")
async def aupdate_entry(
    project_id: int,
    collection_id: int,
    entry_id: int,
    payload: EntryCreate,
    session: AsyncSession = Depends(aget_session),
):
    collection, entry = await _aget_entry_or_404(
        session, project_id, collection_id, entry_id
    )
    asset_ids = await _aproject_asset_ids(session, project_id)
    errors = validate_entry_data(collection.fields, payload.data, asset_ids)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    entry.data = payload.data
    entry.updated_at = now_iso()
    await session.commit()
    await session.refresh(entry)
    return _entry_out(entry, collection.fields)


@router.delete(
    "/projects/{project_id}/collections/{collection_id}/entries/{entry_id}",
    status_code=204,
)
async def adelete_entry(
    project_id: int,
    collection_id: int,
    entry_id: int,
    session: AsyncSession = Depends(aget_session),
):
    _, entry = await _aget_entry_or_404(session, project_id, collection_id, entry_id)
    await session.delete(entry)
    await session.commit()
    return Response(status_code=204)
