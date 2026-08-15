"""Tests for the CMS module: collections CRUD, schema validation, entries CRUD
and entry data validation. OWNED BY: backend-cms agent.

The projects table is owned by the backend-core module; to keep this test file
independent, _acreate_project seeds a project row directly (creating a minimal
projects table when the core model is not present yet).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app.db import engine

FIELDS = [
    {"key": "title", "label": "Title", "type": "text", "required": True, "options": []},
    {"key": "body", "label": "Body", "type": "richtext", "required": False, "options": []},
    {"key": "views", "label": "Views", "type": "number", "required": False, "options": []},
    {"key": "published", "label": "Published", "type": "boolean", "required": False, "options": []},
    {"key": "published_on", "label": "Published on", "type": "date", "required": False, "options": []},
    {"key": "cover", "label": "Cover", "type": "image", "required": False, "options": []},
    {"key": "category", "label": "Category", "type": "select", "required": False, "options": ["news", "tech"]},
]


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


async def _acreate_collection(client, project_id: int, name="Blog Posts", fields=None, slug=None):
    body = {"name": name, "fields": FIELDS if fields is None else fields}
    if slug is not None:
        body["slug"] = slug
    resp = await client.post(f"/api/projects/{project_id}/collections", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _error_fields(resp) -> set:
    return {e["field"] for e in resp.json()["detail"]}


# ---------------------------------------------------------------- collections


async def test_create_collection_auto_slug_and_shape(client):
    pid = await _acreate_project()
    col = await _acreate_collection(client, pid)
    assert col["slug"] == "blog-posts"
    assert col["project_id"] == pid
    assert col["entry_count"] == 0
    assert [f["key"] for f in col["fields"]] == [f["key"] for f in FIELDS]
    assert col["created_at"].endswith("Z")


async def test_create_collection_duplicate_slug_409(client):
    pid = await _acreate_project()
    await _acreate_collection(client, pid)
    resp = await client.post(
        f"/api/projects/{pid}/collections", json={"name": "Blog Posts"}
    )
    assert resp.status_code == 409
    # same slug in ANOTHER project is fine
    pid2 = await _acreate_project()
    other = await _acreate_collection(client, pid2)
    assert other["slug"] == "blog-posts"


async def test_create_collection_bad_field_descriptors_422(client):
    pid = await _acreate_project()
    bad_descriptor_sets = [
        # unknown type
        [{"key": "a", "label": "A", "type": "video", "required": False, "options": []}],
        # bad key format (uppercase / leading digit)
        [{"key": "BadKey", "label": "A", "type": "text", "required": False, "options": []}],
        [{"key": "1bad", "label": "A", "type": "text", "required": False, "options": []}],
        # duplicate keys
        [
            {"key": "a", "label": "A", "type": "text", "required": False, "options": []},
            {"key": "a", "label": "A2", "type": "text", "required": False, "options": []},
        ],
        # select without options
        [{"key": "cat", "label": "Cat", "type": "select", "required": False, "options": []}],
    ]
    for fields in bad_descriptor_sets:
        resp = await client.post(
            f"/api/projects/{pid}/collections", json={"name": "X", "fields": fields}
        )
        assert resp.status_code == 422, fields


async def test_collection_get_update_delete(client):
    pid = await _acreate_project()
    col = await _acreate_collection(client, pid)
    cid = col["id"]

    resp = await client.get(f"/api/projects/{pid}/collections/{cid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Blog Posts"

    resp = await client.get(f"/api/projects/{pid}/collections/9999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Collection not found"

    new_fields = [
        {"key": "title", "label": "Title", "type": "text", "required": True, "options": []}
    ]
    resp = await client.put(
        f"/api/projects/{pid}/collections/{cid}",
        json={"name": "Posts", "fields": new_fields},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["name"] == "Posts"
    assert len(updated["fields"]) == 1
    assert updated["slug"] == "blog-posts"  # unchanged when omitted

    resp = await client.delete(f"/api/projects/{pid}/collections/{cid}")
    assert resp.status_code == 204
    resp = await client.get(f"/api/projects/{pid}/collections/{cid}")
    assert resp.status_code == 404


async def test_collection_update_slug_conflict_409(client):
    pid = await _acreate_project()
    await _acreate_collection(client, pid, name="Blog Posts")
    col2 = await _acreate_collection(client, pid, name="Team Members")
    resp = await client.put(
        f"/api/projects/{pid}/collections/{col2['id']}", json={"slug": "blog-posts"}
    )
    assert resp.status_code == 409


async def test_collections_list_entry_count(client):
    pid = await _acreate_project()
    col = await _acreate_collection(client, pid)
    for i in range(3):
        resp = await client.post(
            f"/api/projects/{pid}/collections/{col['id']}/entries",
            json={"data": {"title": f"Post {i}"}},
        )
        assert resp.status_code == 201
    resp = await client.get(f"/api/projects/{pid}/collections")
    assert resp.status_code == 200
    listing = resp.json()
    assert len(listing) == 1
    assert listing[0]["entry_count"] == 3


async def test_collections_project_not_found(client):
    resp = await client.get("/api/projects/999999/collections")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Project not found"


# -------------------------------------------------------------------- entries


async def test_create_entry_and_normalization(client):
    pid = await _acreate_project()
    col = await _acreate_collection(client, pid)
    resp = await client.post(
        f"/api/projects/{pid}/collections/{col['id']}/entries",
        json={"data": {"title": "Hello"}},
    )
    assert resp.status_code == 201
    entry = resp.json()
    # every schema key present, missing optional -> null
    assert entry["data"] == {
        "title": "Hello",
        "body": None,
        "views": None,
        "published": None,
        "published_on": None,
        "cover": None,
        "category": None,
    }
    assert entry["collection_id"] == col["id"]


async def test_entry_validation_per_type(client):
    pid = await _acreate_project()
    col = await _acreate_collection(client, pid)
    url = f"/api/projects/{pid}/collections/{col['id']}/entries"
    base = {"title": "Ok"}

    cases = [
        ({"title": 42}, "title"),                          # text must be str
        ({"title": "   "}, "title"),                       # required text non-empty
        ({**base, "body": 5}, "body"),                     # richtext must be str
        ({**base, "views": True}, "views"),                # bool rejected as number
        ({**base, "views": "12"}, "views"),                # string rejected as number
        ({**base, "published": "yes"}, "published"),       # boolean must be bool
        ({**base, "published_on": "01/08/2026"}, "published_on"),  # bad date
        ({**base, "category": "sports"}, "category"),      # select not in options
        ({**base, "cover": 424242}, "cover"),              # unknown asset id
        ({**base, "cover": ""}, "cover"),                  # empty url string
        ({**base, "nope": 1}, "nope"),                     # unknown key
        ({}, "title"),                                     # required missing
    ]
    for data, bad_field in cases:
        resp = await client.post(url, json={"data": data})
        assert resp.status_code == 422, (data, resp.text)
        assert bad_field in _error_fields(resp), (data, resp.text)

    # valid full entry passes
    ok = {
        "title": "Hello",
        "body": "<p>Hi</p>",
        "views": 12,
        "published": False,
        "published_on": "2026-08-01",
        "cover": "https://example.com/img.png",
        "category": "news",
    }
    resp = await client.post(url, json={"data": ok})
    assert resp.status_code == 201, resp.text


async def test_entry_image_asset_cross_project_rejected(client):
    pid_a = await _acreate_project()
    pid_b = await _acreate_project()
    col = await _acreate_collection(client, pid_a)

    # upload an asset in each project
    resp = await client.post(
        f"/api/projects/{pid_a}/assets",
        files={"file": ("a.png", b"\x89PNG-a", "image/png")},
    )
    assert resp.status_code == 201
    asset_a = resp.json()["id"]
    resp = await client.post(
        f"/api/projects/{pid_b}/assets",
        files={"file": ("b.png", b"\x89PNG-b", "image/png")},
    )
    assert resp.status_code == 201
    asset_b = resp.json()["id"]

    url = f"/api/projects/{pid_a}/collections/{col['id']}/entries"
    # same-project asset id accepted
    resp = await client.post(url, json={"data": {"title": "T", "cover": asset_a}})
    assert resp.status_code == 201, resp.text
    # other-project asset id rejected
    resp = await client.post(url, json={"data": {"title": "T", "cover": asset_b}})
    assert resp.status_code == 422
    assert "cover" in _error_fields(resp)


async def test_entries_list_pagination_and_order(client):
    pid = await _acreate_project()
    col = await _acreate_collection(client, pid)
    url = f"/api/projects/{pid}/collections/{col['id']}/entries"
    ids = []
    for i in range(5):
        resp = await client.post(url, json={"data": {"title": f"Post {i}"}})
        ids.append(resp.json()["id"])

    resp = await client.get(url)
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 5
    # newest first (created same second -> id DESC)
    assert [e["id"] for e in page["items"]] == list(reversed(ids))

    resp = await client.get(url, params={"limit": 2, "offset": 2})
    page = resp.json()
    assert page["total"] == 5
    assert [e["id"] for e in page["items"]] == [ids[2], ids[1]]


async def test_entry_get_update_delete(client):
    pid = await _acreate_project()
    col = await _acreate_collection(client, pid)
    base = f"/api/projects/{pid}/collections/{col['id']}/entries"
    resp = await client.post(base, json={"data": {"title": "Hello", "views": 1}})
    eid = resp.json()["id"]

    resp = await client.get(f"{base}/{eid}")
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "Hello"

    resp = await client.get(f"{base}/9999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Entry not found"

    # full replacement: views dropped from payload -> null afterwards
    resp = await client.put(f"{base}/{eid}", json={"data": {"title": "Hello 2"}})
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "Hello 2"
    assert resp.json()["data"]["views"] is None

    # replacement is validated too
    resp = await client.put(f"{base}/{eid}", json={"data": {"title": 5}})
    assert resp.status_code == 422

    resp = await client.delete(f"{base}/{eid}")
    assert resp.status_code == 204
    resp = await client.get(f"{base}/{eid}")
    assert resp.status_code == 404


async def test_removed_schema_field_disappears_from_responses(client):
    pid = await _acreate_project()
    fields = [
        {"key": "title", "label": "Title", "type": "text", "required": False, "options": []},
        {"key": "subtitle", "label": "Subtitle", "type": "text", "required": False, "options": []},
    ]
    col = await _acreate_collection(client, pid, name="News", fields=fields)
    base = f"/api/projects/{pid}/collections/{col['id']}/entries"
    resp = await client.post(base, json={"data": {"title": "A", "subtitle": "B"}})
    eid = resp.json()["id"]

    # drop the subtitle field from the schema
    resp = await client.put(
        f"/api/projects/{pid}/collections/{col['id']}", json={"fields": [fields[0]]}
    )
    assert resp.status_code == 200

    resp = await client.get(f"{base}/{eid}")
    assert resp.status_code == 200
    assert resp.json()["data"] == {"title": "A"}


async def test_delete_collection_cascades_entries(client):
    pid = await _acreate_project()
    col = await _acreate_collection(client, pid)
    base = f"/api/projects/{pid}/collections/{col['id']}/entries"
    for i in range(2):
        await client.post(base, json={"data": {"title": f"P{i}"}})

    resp = await client.delete(f"/api/projects/{pid}/collections/{col['id']}")
    assert resp.status_code == 204

    async with engine.connect() as conn:
        count = (
            await conn.execute(
                text("SELECT COUNT(*) FROM entries WHERE collection_id = :cid"),
                {"cid": col["id"]},
            )
        ).scalar_one()
    assert count == 0
