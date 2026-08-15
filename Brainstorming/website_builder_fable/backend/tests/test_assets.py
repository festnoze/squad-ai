"""Tests for the assets module: multipart upload, listing, deletion and the
per-asset binary file endpoint. OWNED BY: backend-cms agent.

The projects table is owned by the backend-core module; to keep this test file
independent, _acreate_project seeds a project row directly (creating a minimal
projects table when the core model is not present yet).
"""

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app.db import UPLOADS_DIR, engine

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-image-payload"


async def _acreate_project() -> int:
    """Insert a project row directly, adapting to whatever projects table exists."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    values = {
        "name": "Test Project",
        "slug": "proj-" + uuid.uuid4().hex[:8],
        "description": "",
        "theme": '{"primary_color": "#2563eb", "font": "system-ui", "base_spacing": 16}',
        "created_at": now,
        "updated_at": now,
    }
    async with engine.begin() as conn:
        exists = (
            await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'")
            )
        ).first()
        if exists is None:
            await conn.execute(
                text(
                    "CREATE TABLE projects ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "name TEXT NOT NULL DEFAULT '', "
                    "slug TEXT NOT NULL DEFAULT '', "
                    "description TEXT NOT NULL DEFAULT '', "
                    "theme TEXT NOT NULL DEFAULT '{}', "
                    "created_at TEXT NOT NULL DEFAULT '', "
                    "updated_at TEXT NOT NULL DEFAULT '')"
                )
            )
        columns = (await conn.execute(text("PRAGMA table_info(projects)"))).fetchall()
        insert_cols: list[str] = []
        params: dict = {}
        for col in columns:
            cname, notnull, pk = col[1], col[3], col[5]
            if pk:
                continue
            if cname in values:
                insert_cols.append(cname)
                params[cname] = values[cname]
            elif notnull:
                insert_cols.append(cname)
                params[cname] = ""
        stmt = (
            "INSERT INTO projects (" + ", ".join(insert_cols) + ") VALUES ("
            + ", ".join(":" + c for c in insert_cols) + ")"
        )
        result = await conn.execute(text(stmt), params)
        return result.lastrowid


async def _aupload(client, project_id: int, filename="photo.png", content=PNG_BYTES, mime="image/png"):
    return await client.post(
        f"/api/projects/{project_id}/assets",
        files={"file": (filename, content, mime)},
    )


async def test_upload_asset_happy_path(client):
    pid = await _acreate_project()
    resp = await _aupload(client, pid)
    assert resp.status_code == 201, resp.text
    asset = resp.json()
    assert asset["project_id"] == pid
    assert asset["filename"] == "photo.png"
    assert asset["mime"] == "image/png"
    assert asset["size"] == len(PNG_BYTES)
    assert asset["path"].startswith(f"{pid}/")
    assert asset["path"].endswith("_photo.png")
    assert asset["url"] == f"/api/uploads/{asset['path']}"
    assert asset["created_at"].endswith("Z")
    # file exists on disk with the exact content
    disk_file = Path(UPLOADS_DIR) / asset["path"]
    assert disk_file.is_file()
    assert disk_file.read_bytes() == PNG_BYTES


async def test_upload_filename_sanitized(client):
    pid = await _acreate_project()
    resp = await _aupload(client, pid, filename="we ird na@me!.png")
    assert resp.status_code == 201
    asset = resp.json()
    # original name preserved in metadata, stored name sanitized
    assert asset["filename"] == "we ird na@me!.png"
    stored_name = asset["path"].split("/", 1)[1]
    assert re.fullmatch(r"[A-Za-z0-9._-]+", stored_name)
    assert stored_name.endswith("_we-ird-na-me-.png")


async def test_upload_non_image_415(client):
    pid = await _acreate_project()
    resp = await _aupload(client, pid, filename="doc.pdf", mime="application/pdf")
    assert resp.status_code == 415
    assert resp.json()["detail"] == "Only image uploads are supported"


async def test_upload_too_large_413(client):
    pid = await _acreate_project()
    big = b"0" * (10 * 1024 * 1024 + 1)
    resp = await _aupload(client, pid, content=big)
    assert resp.status_code == 413


async def test_upload_project_not_found(client):
    resp = await _aupload(client, 999999)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Project not found"


async def test_list_assets_order_and_scope(client):
    pid = await _acreate_project()
    other_pid = await _acreate_project()
    first = (await _aupload(client, pid, filename="first.png")).json()
    second = (await _aupload(client, pid, filename="second.png")).json()
    await _aupload(client, other_pid, filename="elsewhere.png")

    resp = await client.get(f"/api/projects/{pid}/assets")
    assert resp.status_code == 200
    listing = resp.json()
    # only this project's assets, newest first (id DESC within the same second)
    assert [a["id"] for a in listing] == [second["id"], first["id"]]


async def test_delete_asset_removes_row_and_file(client):
    pid = await _acreate_project()
    asset = (await _aupload(client, pid)).json()
    disk_file = Path(UPLOADS_DIR) / asset["path"]
    assert disk_file.is_file()

    resp = await client.delete(f"/api/projects/{pid}/assets/{asset['id']}")
    assert resp.status_code == 204
    assert not disk_file.exists()

    listing = (await client.get(f"/api/projects/{pid}/assets")).json()
    assert listing == []

    resp = await client.delete(f"/api/projects/{pid}/assets/{asset['id']}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Asset not found"


async def test_delete_asset_wrong_project_404(client):
    pid = await _acreate_project()
    other_pid = await _acreate_project()
    asset = (await _aupload(client, pid)).json()
    resp = await client.delete(f"/api/projects/{other_pid}/assets/{asset['id']}")
    assert resp.status_code == 404


async def test_get_asset_file_serves_binary_with_mime(client):
    pid = await _acreate_project()
    asset = (await _aupload(client, pid)).json()

    resp = await client.get(f"/api/assets/{asset['id']}/file")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == PNG_BYTES

    resp = await client.get("/api/assets/999999/file")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Asset not found"


async def test_get_asset_file_missing_on_disk_404(client):
    pid = await _acreate_project()
    asset = (await _aupload(client, pid)).json()
    (Path(UPLOADS_DIR) / asset["path"]).unlink()
    resp = await client.get(f"/api/assets/{asset['id']}/file")
    assert resp.status_code == 404
