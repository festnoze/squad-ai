"""End-to-end tests for the `/api/projects` router.

These tests exercise the full HTTP layer using the shared `client` fixture
defined in `conftest.py`, which wires a FastAPI app to an in-memory SQLite
database. They intentionally do NOT mock the repository — the point is to
prove the router, converters, repository and database play well together.
"""

import asyncio
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.chat_message_repository import ChatMessageRepository
from app.infrastructure.item_repository import ItemRepository
from app.models.chat_message import ChatMessage, ChatMessageRole
from app.models.item import Item, ItemStatus, ItemType


async def test_list_projects_empty(client: AsyncClient) -> None:
    """GET on a fresh DB returns an empty list, not a 404."""
    response = await client.get("/api/projects")

    assert response.status_code == 200
    assert response.json() == []


async def test_create_project_success(client: AsyncClient) -> None:
    """POST with a valid body returns 201 + the serialized project."""
    response = await client.post(
        "/api/projects",
        json={"name": "My Project", "description": "hello"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "My Project"
    assert body["description"] == "hello"
    assert "id" in body
    assert "created_at" in body


async def test_create_project_empty_name_rejected(client: AsyncClient) -> None:
    """Pydantic's `min_length=1` should reject an empty `name`."""
    response = await client.post(
        "/api/projects",
        json={"name": "", "description": None},
    )

    assert response.status_code == 422


async def test_list_projects_after_create(client: AsyncClient) -> None:
    """Two creates → GET returns both, ordered by `updated_at` desc."""
    first = await client.post("/api/projects", json={"name": "First"})
    assert first.status_code == 201

    # Sleep a hair so `updated_at` differs between the two rows.
    await asyncio.sleep(0.01)

    second = await client.post("/api/projects", json={"name": "Second"})
    assert second.status_code == 201

    response = await client.get("/api/projects")
    assert response.status_code == 200
    body = response.json()

    assert len(body) == 2
    assert body[0]["name"] == "Second"
    assert body[1]["name"] == "First"


async def test_delete_project_success(client: AsyncClient) -> None:
    """Create, delete, then ensure the project is gone from the list."""
    created = await client.post("/api/projects", json={"name": "Doomed"})
    project_id = created.json()["id"]

    delete_response = await client.delete(f"/api/projects/{project_id}")
    assert delete_response.status_code == 204

    list_response = await client.get("/api/projects")
    assert list_response.status_code == 200
    assert all(p["id"] != project_id for p in list_response.json())


async def test_delete_project_not_found(client: AsyncClient) -> None:
    """Deleting a random UUID should return 404."""
    response = await client.delete(f"/api/projects/{uuid4()}")
    assert response.status_code == 404


async def test_delete_project_cascades_to_items_and_messages(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """DELETE /projects/{id} must soft-delete every child item and chat
    message, not just the project row itself.
    """
    # Create a project via the public API.
    created = await client.post("/api/projects", json={"name": "Cascade"})
    project_id_str = created.json()["id"]
    project_id = UUID(project_id_str)

    # Seed one item and one chat message directly via the repositories
    # so we don't depend on a real LLM call.
    item_repo = ItemRepository(db_session)
    chat_repo = ChatMessageRepository(db_session)
    await item_repo.acreate_item(
        Item(
            project_id=project_id,
            type=ItemType.TASK,
            title="Orphan candidate",
            status=ItemStatus.TODO,
        ),
    )
    await chat_repo.acreate_message(
        ChatMessage(
            project_id=project_id,
            role=ChatMessageRole.USER,
            content="hello",
        ),
    )
    await db_session.commit()

    # Sanity check: children are visible before the delete.
    pre_items = await client.get(f"/api/projects/{project_id_str}/items")
    assert pre_items.status_code == 200
    assert len(pre_items.json()) == 1
    pre_messages = await client.get(
        f"/api/projects/{project_id_str}/messages",
    )
    assert pre_messages.status_code == 200
    assert len(pre_messages.json()) == 1

    # Cascade delete.
    delete_response = await client.delete(f"/api/projects/{project_id_str}")
    assert delete_response.status_code == 204

    # Project is gone from the list.
    list_response = await client.get("/api/projects")
    assert all(p["id"] != project_id_str for p in list_response.json())

    # The child endpoints now 404 (because _aensure_project_exists
    # refuses soft-deleted projects), which indirectly proves the
    # cascade landed: the repositories would expose live items / messages
    # if they had not been soft-deleted too.
    post_items = await client.get(f"/api/projects/{project_id_str}/items")
    assert post_items.status_code == 404
    post_messages = await client.get(
        f"/api/projects/{project_id_str}/messages",
    )
    assert post_messages.status_code == 404

    # Belt-and-braces check: hit the repositories directly with a fresh
    # filter and confirm zero live rows remain for this project.
    live_items = await item_repo.aget_items_by_project(project_id)
    assert live_items == []
    live_messages = await chat_repo.aget_messages_by_project(project_id)
    assert live_messages == []


async def test_patch_project_rename(client: AsyncClient) -> None:
    """PATCH updates only the provided fields and returns the new state."""
    created = await client.post(
        "/api/projects",
        json={"name": "Old Name", "description": "keep me"},
    )
    project_id = created.json()["id"]

    patch_response = await client.patch(
        f"/api/projects/{project_id}",
        json={"name": "New Name"},
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["name"] == "New Name"
    # Description was NOT sent, so it must stay untouched.
    assert patched["description"] == "keep me"

    # A follow-up GET should reflect the same state.
    list_response = await client.get("/api/projects")
    assert list_response.status_code == 200
    project_from_list = next(
        p for p in list_response.json() if p["id"] == project_id
    )
    assert project_from_list["name"] == "New Name"
    assert project_from_list["description"] == "keep me"


async def test_patch_project_not_found(client: AsyncClient) -> None:
    """PATCHing an unknown UUID should return 404."""
    response = await client.patch(
        f"/api/projects/{uuid4()}",
        json={"name": "does not matter"},
    )
    assert response.status_code == 404
