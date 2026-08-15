"""Tests for the pages API, preview and export. OWNED BY: backend-core agent."""

import io
import zipfile

EMPTY_ROOT = {"id": "root", "type": "page", "props": {}, "style": {}, "children": []}


async def acreate_project(client, name="Site"):
    resp = await client.post("/api/projects", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def sample_tree():
    return {
        "id": "root",
        "type": "page",
        "props": {},
        "style": {},
        "children": [
            {
                "id": "sec1",
                "type": "section",
                "props": {},
                "style": {"paddingTop": 48, "backgroundColor": "#f9fafb"},
                "children": [
                    {
                        "id": "h1",
                        "type": "heading",
                        "props": {"text": "Hello World", "level": 1},
                        "style": {"fontSize": 40, "color": "#111111"},
                        "children": [],
                    }
                ],
            }
        ],
    }


async def test_create_page_initializes_content_and_home(client):
    project = await acreate_project(client)
    resp = await client.post(f"/api/projects/{project['id']}/pages", json={"name": "Home"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Home"
    assert body["slug"] == "home"
    assert body["content"] == EMPTY_ROOT
    # first page of a project becomes home when is_home omitted
    assert body["is_home"] is True
    assert body["project_id"] == project["id"]


async def test_second_page_not_home_by_default(client):
    project = await acreate_project(client)
    await client.post(f"/api/projects/{project['id']}/pages", json={"name": "Home"})
    resp = await client.post(f"/api/projects/{project['id']}/pages", json={"name": "About"})
    assert resp.status_code == 201
    assert resp.json()["is_home"] is False


async def test_create_page_duplicate_slug_409(client):
    project = await acreate_project(client)
    await client.post(f"/api/projects/{project['id']}/pages", json={"name": "Home"})
    resp = await client.post(f"/api/projects/{project['id']}/pages", json={"name": "Home"})
    assert resp.status_code == 409


async def test_same_slug_allowed_across_projects(client):
    p1 = await acreate_project(client, "One")
    p2 = await acreate_project(client, "Two")
    r1 = await client.post(f"/api/projects/{p1['id']}/pages", json={"name": "Home"})
    r2 = await client.post(f"/api/projects/{p2['id']}/pages", json={"name": "Home"})
    assert r1.status_code == 201
    assert r2.status_code == 201


async def test_create_page_project_404(client):
    resp = await client.post("/api/projects/9999/pages", json={"name": "Home"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Project not found"


async def test_list_pages(client):
    project = await acreate_project(client)
    await client.post(f"/api/projects/{project['id']}/pages", json={"name": "Home"})
    await client.post(f"/api/projects/{project['id']}/pages", json={"name": "About"})
    resp = await client.get(f"/api/projects/{project['id']}/pages")
    assert resp.status_code == 200
    assert [p["slug"] for p in resp.json()] == ["home", "about"]


async def test_get_page_and_404s(client):
    project = await acreate_project(client)
    page = (
        await client.post(f"/api/projects/{project['id']}/pages", json={"name": "Home"})
    ).json()
    resp = await client.get(f"/api/projects/{project['id']}/pages/{page['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == page["id"]
    resp = await client.get(f"/api/projects/{project['id']}/pages/9999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Page not found"
    resp = await client.get(f"/api/projects/9999/pages/{page['id']}")
    assert resp.status_code == 404


async def test_page_not_reachable_from_other_project(client):
    p1 = await acreate_project(client, "One")
    p2 = await acreate_project(client, "Two")
    page = (await client.post(f"/api/projects/{p1['id']}/pages", json={"name": "Home"})).json()
    resp = await client.get(f"/api/projects/{p2['id']}/pages/{page['id']}")
    assert resp.status_code == 404


async def test_put_content_saves_block_tree(client):
    project = await acreate_project(client)
    page = (
        await client.post(f"/api/projects/{project['id']}/pages", json={"name": "Home"})
    ).json()
    tree = sample_tree()
    resp = await client.put(
        f"/api/projects/{project['id']}/pages/{page['id']}", json={"content": tree}
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == tree
    # persisted
    resp = await client.get(f"/api/projects/{project['id']}/pages/{page['id']}")
    assert resp.json()["content"] == tree


async def test_put_rename_and_slug_conflict(client):
    project = await acreate_project(client)
    await client.post(f"/api/projects/{project['id']}/pages", json={"name": "Home"})
    page = (
        await client.post(f"/api/projects/{project['id']}/pages", json={"name": "About"})
    ).json()
    resp = await client.put(
        f"/api/projects/{project['id']}/pages/{page['id']}", json={"name": "About Us"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "About Us"
    resp = await client.put(
        f"/api/projects/{project['id']}/pages/{page['id']}", json={"slug": "home"}
    )
    assert resp.status_code == 409


async def test_put_page_404(client):
    project = await acreate_project(client)
    resp = await client.put(
        f"/api/projects/{project['id']}/pages/9999", json={"name": "Nope"}
    )
    assert resp.status_code == 404


async def test_set_home_clears_previous_home(client):
    project = await acreate_project(client)
    home = (
        await client.post(f"/api/projects/{project['id']}/pages", json={"name": "Home"})
    ).json()
    about = (
        await client.post(f"/api/projects/{project['id']}/pages", json={"name": "About"})
    ).json()
    resp = await client.put(
        f"/api/projects/{project['id']}/pages/{about['id']}", json={"is_home": True}
    )
    assert resp.status_code == 200
    assert resp.json()["is_home"] is True
    resp = await client.get(f"/api/projects/{project['id']}/pages/{home['id']}")
    assert resp.json()["is_home"] is False


async def test_duplicate_page(client):
    project = await acreate_project(client)
    page = (
        await client.post(f"/api/projects/{project['id']}/pages", json={"name": "Home"})
    ).json()
    tree = sample_tree()
    await client.put(f"/api/projects/{project['id']}/pages/{page['id']}", json={"content": tree})
    resp = await client.post(f"/api/projects/{project['id']}/pages/{page['id']}/duplicate")
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Home copy"
    assert body["slug"] != page["slug"]
    assert body["is_home"] is False
    assert body["content"] == tree
    # duplicating again still yields a unique slug
    resp = await client.post(f"/api/projects/{project['id']}/pages/{page['id']}/duplicate")
    assert resp.status_code == 201
    assert resp.json()["slug"] != body["slug"]


async def test_duplicate_page_404(client):
    project = await acreate_project(client)
    resp = await client.post(f"/api/projects/{project['id']}/pages/9999/duplicate")
    assert resp.status_code == 404


async def test_delete_page(client):
    project = await acreate_project(client)
    page = (
        await client.post(f"/api/projects/{project['id']}/pages", json={"name": "Home"})
    ).json()
    resp = await client.delete(f"/api/projects/{project['id']}/pages/{page['id']}")
    assert resp.status_code == 204
    resp = await client.get(f"/api/projects/{project['id']}/pages/{page['id']}")
    assert resp.status_code == 404


async def test_delete_page_404(client):
    project = await acreate_project(client)
    resp = await client.delete(f"/api/projects/{project['id']}/pages/9999")
    assert resp.status_code == 404


async def test_preview_returns_rendered_html(client):
    project = await acreate_project(client)
    page = (
        await client.post(f"/api/projects/{project['id']}/pages", json={"name": "Home"})
    ).json()
    await client.put(
        f"/api/projects/{project['id']}/pages/{page['id']}", json={"content": sample_tree()}
    )
    resp = await client.get(f"/api/projects/{project['id']}/pages/{page['id']}/preview")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    html_doc = resp.text
    assert html_doc.startswith("<!doctype html>")
    assert "Hello World" in html_doc
    assert "<h1" in html_doc
    assert "--primary-color: #2563eb" in html_doc


async def test_preview_404s(client):
    project = await acreate_project(client)
    resp = await client.get(f"/api/projects/{project['id']}/pages/9999/preview")
    assert resp.status_code == 404
    resp = await client.get("/api/projects/9999/pages/1/preview")
    assert resp.status_code == 404


async def test_export_zip(client):
    project = await acreate_project(client)
    home = (
        await client.post(f"/api/projects/{project['id']}/pages", json={"name": "Home"})
    ).json()
    await client.post(f"/api/projects/{project['id']}/pages", json={"name": "About"})
    await client.put(
        f"/api/projects/{project['id']}/pages/{home['id']}", json={"content": sample_tree()}
    )
    resp = await client.get(f"/api/projects/{project['id']}/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        names = archive.namelist()
        assert "index.html" in names
        assert "about.html" in names
        index_html = archive.read("index.html").decode("utf-8")
        assert "Hello World" in index_html


async def test_export_404(client):
    resp = await client.get("/api/projects/9999/export")
    assert resp.status_code == 404
