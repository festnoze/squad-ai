"""End-to-end tests for the items router (`/api/projects/{id}/items` and
`/api/items/{id}`).

Follows the same approach as `test_project_router.py`: the `client`
fixture wires a FastAPI app to an in-memory SQLite database and shares
the same session as `db_session`, so tests can seed data via the
repository and then assert the HTTP shape via the client.

Note on dependency override: `conftest.py` overrides `get_db` to yield
the exact same session the test uses for seeding, so we must
`commit()` seeded rows before the HTTP call (matching the pattern of
`test_get_messages_returns_chronological_order` in `test_chat_router`).

V1 note: the previous ``POST /api/items/{id}/execute`` endpoint has
been removed. Execution is now project-wide via
``POST /api/projects/{id}/runs`` and tested in `test_project_run_router.py`.
"""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.item_repository import ItemRepository
from app.models.item import Item, ItemStatus, ItemType


async def _acreate_project(client: AsyncClient, name: str = "Items P") -> UUID:
    """Helper — create a project via the public API and return its UUID."""
    response = await client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    return UUID(response.json()["id"])


async def _aseed_item(
    db_session: AsyncSession,
    project_id: UUID,
    *,
    item_type: ItemType,
    title: str,
    status: ItemStatus = ItemStatus.TODO,
) -> Item:
    """Insert one item via the repository and commit the transaction."""
    repo = ItemRepository(db_session)
    created = await repo.acreate_item(
        Item(
            project_id=project_id,
            type=item_type,
            title=title,
            status=status,
        ),
    )
    await db_session.commit()
    return created


# ---------------------------------------------------------------------------
# GET /api/projects/{project_id}/items
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_items_empty_project(client: AsyncClient) -> None:
    """A freshly created project has no items → GET returns []."""
    project_id = await _acreate_project(client)

    response = await client.get(f"/api/projects/{project_id}/items")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_items_project_not_found(client: AsyncClient) -> None:
    """GETting items for a random UUID yields 404."""
    response = await client.get(f"/api/projects/{uuid4()}/items")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_items_returns_all_without_filter(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Seed 1 epic + 2 US + 3 tasks, expect 6 items back without filter."""
    project_id = await _acreate_project(client)

    await _aseed_item(db_session, project_id, item_type=ItemType.EPIC, title="E1")
    await _aseed_item(
        db_session, project_id, item_type=ItemType.USER_STORY, title="US1",
    )
    await _aseed_item(
        db_session, project_id, item_type=ItemType.USER_STORY, title="US2",
    )
    await _aseed_item(db_session, project_id, item_type=ItemType.TASK, title="T1")
    await _aseed_item(db_session, project_id, item_type=ItemType.TASK, title="T2")
    await _aseed_item(db_session, project_id, item_type=ItemType.TASK, title="T3")

    response = await client.get(f"/api/projects/{project_id}/items")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 6

    titles = {item["title"] for item in body}
    assert titles == {"E1", "US1", "US2", "T1", "T2", "T3"}

    # Every payload carries the expected top-level keys.
    for item in body:
        assert "id" in item
        assert "project_id" in item
        assert "type" in item
        assert "status" in item
        assert "created_at" in item
        # V1 deliverable keys are always present, even if null.
        assert "deliverable_paths" in item
        assert "deliverable_notes" in item
        assert "blocked_reason" in item


@pytest.mark.asyncio
async def test_get_items_filtered_by_user_story(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """`?type=user_story` returns only the 2 user stories."""
    project_id = await _acreate_project(client)

    await _aseed_item(db_session, project_id, item_type=ItemType.EPIC, title="E1")
    await _aseed_item(
        db_session, project_id, item_type=ItemType.USER_STORY, title="US1",
    )
    await _aseed_item(
        db_session, project_id, item_type=ItemType.USER_STORY, title="US2",
    )
    await _aseed_item(db_session, project_id, item_type=ItemType.TASK, title="T1")
    await _aseed_item(db_session, project_id, item_type=ItemType.TASK, title="T2")
    await _aseed_item(db_session, project_id, item_type=ItemType.TASK, title="T3")

    response = await client.get(
        f"/api/projects/{project_id}/items",
        params={"type": "user_story"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {item["title"] for item in body} == {"US1", "US2"}
    assert all(item["type"] == "user_story" for item in body)


@pytest.mark.asyncio
async def test_get_items_filtered_by_task(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """`?type=task` returns only the 3 tasks."""
    project_id = await _acreate_project(client)

    await _aseed_item(db_session, project_id, item_type=ItemType.EPIC, title="E1")
    await _aseed_item(
        db_session, project_id, item_type=ItemType.USER_STORY, title="US1",
    )
    await _aseed_item(
        db_session, project_id, item_type=ItemType.USER_STORY, title="US2",
    )
    await _aseed_item(db_session, project_id, item_type=ItemType.TASK, title="T1")
    await _aseed_item(db_session, project_id, item_type=ItemType.TASK, title="T2")
    await _aseed_item(db_session, project_id, item_type=ItemType.TASK, title="T3")

    response = await client.get(
        f"/api/projects/{project_id}/items",
        params={"type": "task"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    assert {item["title"] for item in body} == {"T1", "T2", "T3"}
    assert all(item["type"] == "task" for item in body)


@pytest.mark.asyncio
async def test_get_items_invalid_type_filter(client: AsyncClient) -> None:
    """Unknown `?type=` value → 422 (Pydantic enum validation)."""
    project_id = await _acreate_project(client)

    response = await client.get(
        f"/api/projects/{project_id}/items",
        params={"type": "invalid_type"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/items/{item_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_item_by_id_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A seeded task can be fetched by id and serialized in full."""
    project_id = await _acreate_project(client)
    task = await _aseed_item(
        db_session,
        project_id,
        item_type=ItemType.TASK,
        title="Do the thing",
    )
    assert task.id is not None

    response = await client.get(f"/api/items/{task.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(task.id)
    assert body["project_id"] == str(project_id)
    assert body["title"] == "Do the thing"
    assert body["type"] == "task"
    assert body["status"] == "todo"
    assert body["deliverable_paths"] is None
    assert body["blocked_reason"] is None


@pytest.mark.asyncio
async def test_get_item_by_id_not_found(client: AsyncClient) -> None:
    """GETting a random UUID yields 404."""
    response = await client.get(f"/api/items/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_item_by_id_soft_deleted(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Soft-deleted items must be hidden from the GET-by-id endpoint."""
    project_id = await _acreate_project(client)
    task = await _aseed_item(
        db_session,
        project_id,
        item_type=ItemType.TASK,
        title="Gone soon",
    )
    assert task.id is not None

    repo = ItemRepository(db_session)
    deleted = await repo.adelete_item(task.id)
    await db_session.commit()
    assert deleted is True

    response = await client.get(f"/api/items/{task.id}")
    assert response.status_code == 404
