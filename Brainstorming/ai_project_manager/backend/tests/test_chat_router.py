"""HTTP-layer tests for the `/api/projects/{id}/messages` router.

The real `ScopingAgent` is kept in the loop — only the LLM call itself is
patched at `ScopingAgent._ainvoke_llm`, mirroring `test_scoping_agent.py`.
That way we exercise the router, the converters, the repositories and the
service together while avoiding any network I/O or dependency on
common-tools being installed.

A few tests also directly persist messages via `ChatMessageRepository` so we
can assert the GET endpoint returns them in chronological order.
"""

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.chat_message_repository import ChatMessageRepository
from app.models.chat_message import ChatMessage, ChatMessageRole
from app.services.scoping_agent import ScopingAgent


def _patch_llm_with_parsed(parsed: dict[str, Any]):
    """Patch `ScopingAgent._ainvoke_llm` to return the given parsed dict."""
    return patch.object(
        ScopingAgent,
        "_ainvoke_llm",
        new=AsyncMock(return_value=parsed),
    )


def _propose_items_parsed(
    message: str = "Voila ma proposition",
) -> dict[str, Any]:
    return {
        "action": "propose_items",
        "message": message,
        "items": [
            {
                "temp_id": "t-1",
                "type": "task",
                "title": "Do thing",
                "description": "one simple task",
                "complexity": "simple",
                "parent_temp_id": None,
            },
        ],
    }


# ---------------------------------------------------------------------------
# POST /messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message_creates_items(client: AsyncClient) -> None:
    # 1. Create a project via the existing CRUD.
    create = await client.post("/api/projects", json={"name": "Chat P"})
    assert create.status_code == 201
    project_id = create.json()["id"]

    # 2. POST a message with the LLM stubbed to propose one task.
    with _patch_llm_with_parsed(_propose_items_parsed()):
        response = await client.post(
            f"/api/projects/{project_id}/messages",
            json={"content": "I want a simple todo app"},
        )

    assert response.status_code == 201
    body = response.json()

    assert body["action"] == "propose_items"
    assert body["message"]["role"] == "assistant"
    assert body["message"]["project_id"] == project_id
    assert len(body["items_created"]) == 1
    assert body["items_created"][0]["type"] == "task"
    assert body["items_created"][0]["status"] == "proposed"
    assert body["items_updated"] == []


@pytest.mark.asyncio
async def test_send_message_project_not_found(client: AsyncClient) -> None:
    random_id = uuid4()
    response = await client.post(
        f"/api/projects/{random_id}/messages",
        json={"content": "anything"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_send_message_empty_content_rejected(
    client: AsyncClient,
) -> None:
    """Pydantic validation should kick in before we touch the router body."""
    create = await client.post("/api/projects", json={"name": "Chat P"})
    project_id = create.json()["id"]

    response = await client.post(
        f"/api/projects/{project_id}/messages",
        json={"content": ""},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_messages_empty(client: AsyncClient) -> None:
    create = await client.post("/api/projects", json={"name": "Chat P"})
    project_id = create.json()["id"]

    response = await client.get(f"/api/projects/{project_id}/messages")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_messages_returns_chronological_order(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    create = await client.post("/api/projects", json={"name": "Chat P"})
    project_id_str = create.json()["id"]
    from uuid import UUID

    project_id = UUID(project_id_str)

    # Seed three messages directly via the repository so we control ordering
    # without relying on the Claude mock.
    chat_repo = ChatMessageRepository(db_session)
    await chat_repo.acreate_message(
        ChatMessage(
            project_id=project_id,
            role=ChatMessageRole.USER,
            content="first",
        ),
    )
    await chat_repo.acreate_message(
        ChatMessage(
            project_id=project_id,
            role=ChatMessageRole.ASSISTANT,
            content="second",
        ),
    )
    await chat_repo.acreate_message(
        ChatMessage(
            project_id=project_id,
            role=ChatMessageRole.USER,
            content="third",
        ),
    )
    await db_session.commit()

    response = await client.get(f"/api/projects/{project_id_str}/messages")
    assert response.status_code == 200
    body = response.json()
    assert [m["content"] for m in body] == ["first", "second", "third"]
    assert [m["role"] for m in body] == ["user", "assistant", "user"]


@pytest.mark.asyncio
async def test_get_messages_project_not_found(client: AsyncClient) -> None:
    random_id = uuid4()
    response = await client.get(f"/api/projects/{random_id}/messages")
    assert response.status_code == 404
