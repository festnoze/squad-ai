"""Assets router: /api/projects/{project_id}/assets (upload, list, delete)
plus /api/assets/{asset_id}/file (binary serving with the stored mime type).

OWNED BY: backend-cms agent. Endpoints per docs/CONTRACTS.md section 1.4 and
docs/decisions-cms.md section 3. The router below is included from main.py
with prefix "/api". Uploaded files are also served by the StaticFiles mount
at /api/uploads defined in main.py; the per-asset /file endpoint is a direct
alternative that resolves by asset id.
"""

import re
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cms.utils import aensure_project, now_iso
from app.db import UPLOADS_DIR, aget_session
from app.models_cms import Asset

router = APIRouter()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _asset_out(asset: Asset) -> dict:
    return {
        "id": asset.id,
        "project_id": asset.project_id,
        "filename": asset.filename,
        "path": asset.path,
        "url": f"/api/uploads/{asset.path}",
        "mime": asset.mime,
        "size": asset.size,
        "created_at": asset.created_at,
    }


def _sanitize_filename(name: str) -> str:
    """Keep [A-Za-z0-9._-]; replace everything else with '-'."""
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "-", name)
    return sanitized or "upload"


@router.post("/projects/{project_id}/assets", status_code=201)
async def aupload_asset(
    project_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(aget_session),
):
    await aensure_project(session, project_id)
    mime = file.content_type or ""
    if not mime.startswith("image/"):
        raise HTTPException(status_code=415, detail="Only image uploads are supported")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    original = file.filename or "upload"
    stored_name = f"{uuid4().hex[:8]}_{_sanitize_filename(original)}"
    project_dir = UPLOADS_DIR / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / stored_name).write_bytes(content)

    asset = Asset(
        project_id=project_id,
        filename=original,
        path=f"{project_id}/{stored_name}",
        mime=mime,
        size=len(content),
        created_at=now_iso(),
    )
    session.add(asset)
    await session.commit()
    await session.refresh(asset)
    return _asset_out(asset)


@router.get("/projects/{project_id}/assets")
async def alist_assets(project_id: int, session: AsyncSession = Depends(aget_session)):
    await aensure_project(session, project_id)
    assets = (
        (
            await session.execute(
                select(Asset)
                .where(Asset.project_id == project_id)
                .order_by(Asset.created_at.desc(), Asset.id.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_asset_out(a) for a in assets]


@router.delete("/projects/{project_id}/assets/{asset_id}", status_code=204)
async def adelete_asset(
    project_id: int, asset_id: int, session: AsyncSession = Depends(aget_session)
):
    await aensure_project(session, project_id)
    asset = await session.get(Asset, asset_id)
    if asset is None or asset.project_id != project_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    file_path = UPLOADS_DIR / asset.path
    await session.delete(asset)
    await session.commit()
    try:
        file_path.unlink()
    except FileNotFoundError:
        pass
    return Response(status_code=204)


@router.get("/assets/{asset_id}/file")
async def aget_asset_file(asset_id: int, session: AsyncSession = Depends(aget_session)):
    asset = await session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    file_path = UPLOADS_DIR / asset.path
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(str(file_path), media_type=asset.mime)
