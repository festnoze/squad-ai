"""Tests for the projects API (/api/projects). OWNED BY: backend-core agent."""


async def test_list_projects_empty(client):
    resp = await client.get("/api/projects")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_project_minimal(client):
    resp = await client.post("/api/projects", json={"name": "My Site"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My Site"
    assert body["slug"] == "my-site"
    assert body["description"] == ""
    assert body["theme"] == {
        "primary_color": "#2563eb",
        "font": "system-ui",
        "base_spacing": 16,
    }
    assert body["created_at"].endswith("Z")
    assert body["updated_at"].endswith("Z")
    assert isinstance(body["id"], int)


async def test_create_project_full(client):
    payload = {
        "name": "Portfolio",
        "slug": "my-portfolio",
        "description": "A portfolio site",
        "theme": {"primary_color": "#ff0000", "font": "Georgia", "base_spacing": 24},
    }
    resp = await client.post("/api/projects", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "my-portfolio"
    assert body["description"] == "A portfolio site"
    assert body["theme"]["primary_color"] == "#ff0000"
    assert body["theme"]["base_spacing"] == 24


async def test_create_project_duplicate_slug_409(client):
    resp = await client.post("/api/projects", json={"name": "Site A", "slug": "same"})
    assert resp.status_code == 201
    resp = await client.post("/api/projects", json={"name": "Site B", "slug": "same"})
    assert resp.status_code == 409
    assert "slug" in resp.json()["detail"].lower()


async def test_create_project_missing_name_422(client):
    resp = await client.post("/api/projects", json={"slug": "no-name"})
    assert resp.status_code == 422


async def test_get_project(client):
    created = (await client.post("/api/projects", json={"name": "Read Me"})).json()
    resp = await client.get(f"/api/projects/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Read Me"


async def test_get_project_404(client):
    resp = await client.get("/api/projects/9999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Project not found"


async def test_list_projects_returns_created(client):
    await client.post("/api/projects", json={"name": "One"})
    await client.post("/api/projects", json={"name": "Two"})
    resp = await client.get("/api/projects")
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert names == ["One", "Two"]


async def test_update_project_partial(client):
    created = (await client.post("/api/projects", json={"name": "Old Name"})).json()
    resp = await client.put(
        f"/api/projects/{created['id']}",
        json={"name": "New Name", "description": "updated"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "New Name"
    assert body["description"] == "updated"
    # untouched fields preserved
    assert body["slug"] == "old-name"
    assert body["theme"]["primary_color"] == "#2563eb"


async def test_update_project_theme(client):
    created = (await client.post("/api/projects", json={"name": "Themed"})).json()
    resp = await client.put(
        f"/api/projects/{created['id']}",
        json={"theme": {"primary_color": "#00ff00", "font": "Arial", "base_spacing": 8}},
    )
    assert resp.status_code == 200
    assert resp.json()["theme"]["primary_color"] == "#00ff00"


async def test_update_project_slug_conflict_409(client):
    await client.post("/api/projects", json={"name": "Taken", "slug": "taken"})
    other = (await client.post("/api/projects", json={"name": "Other"})).json()
    resp = await client.put(f"/api/projects/{other['id']}", json={"slug": "taken"})
    assert resp.status_code == 409


async def test_update_project_slug_to_itself_ok(client):
    created = (await client.post("/api/projects", json={"name": "Self", "slug": "self"})).json()
    resp = await client.put(f"/api/projects/{created['id']}", json={"slug": "self"})
    assert resp.status_code == 200


async def test_update_project_404(client):
    resp = await client.put("/api/projects/9999", json={"name": "Nope"})
    assert resp.status_code == 404


async def test_delete_project(client):
    created = (await client.post("/api/projects", json={"name": "Doomed"})).json()
    resp = await client.delete(f"/api/projects/{created['id']}")
    assert resp.status_code == 204
    assert resp.content == b""
    resp = await client.get(f"/api/projects/{created['id']}")
    assert resp.status_code == 404


async def test_delete_project_404(client):
    resp = await client.delete("/api/projects/9999")
    assert resp.status_code == 404


async def test_delete_project_cascades_pages(client):
    project = (await client.post("/api/projects", json={"name": "With Pages"})).json()
    page = (
        await client.post(f"/api/projects/{project['id']}/pages", json={"name": "Home"})
    ).json()
    resp = await client.delete(f"/api/projects/{project['id']}")
    assert resp.status_code == 204
    resp = await client.get(f"/api/projects/{project['id']}/pages/{page['id']}")
    assert resp.status_code == 404
