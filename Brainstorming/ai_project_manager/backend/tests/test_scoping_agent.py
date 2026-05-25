"""Unit tests for `ScopingAgent` with the LLM call mocked out.

Since the real LLM lives behind ``common_tools.llm.llm_helper.Llm.ainvoke``
(reached through ``ScopingAgent._ainvoke_llm``), we patch the private
``_ainvoke_llm`` method on the class itself and return whatever parsed
``dict`` the test needs. This:

- keeps the tests independent of common-tools being installed in the venv,
- mirrors the post-parser shape the real code works with (``dict`` matching
  ``ScopingResponse``),
- and exercises every branch of ``aprocess_user_message`` identically to
  the previous tool-use version.
"""

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.chat_message_repository import ChatMessageRepository
from app.infrastructure.item_repository import ItemRepository
from app.infrastructure.project_repository import ProjectRepository
from app.models.chat_message import ChatMessageRole
from app.models.item import Item, ItemStatus, ItemType
from app.models.project import Project
from app.services.scoping_agent import ScopingAgent


async def _acreate_project(session: AsyncSession) -> UUID:
    project_repo = ProjectRepository(session)
    project = await project_repo.acreate_project(
        Project(name="Scoping Test Project"),
    )
    assert project.id is not None
    return project.id


def _patch_llm_with_parsed(parsed: dict[str, Any]):
    """Patch `ScopingAgent._ainvoke_llm` to return the given parsed dict."""
    return patch.object(
        ScopingAgent,
        "_ainvoke_llm",
        new=AsyncMock(return_value=parsed),
    )


def _patch_llm_raises(exc: Exception):
    """Patch `ScopingAgent._ainvoke_llm` to raise the given exception."""
    return patch.object(
        ScopingAgent,
        "_ainvoke_llm",
        new=AsyncMock(side_effect=exc),
    )


# ---------------------------------------------------------------------------
# test_process_user_message_with_propose_items_action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_user_message_with_propose_items_action(
    db_session: AsyncSession,
) -> None:
    project_id = await _acreate_project(db_session)
    chat_repo = ChatMessageRepository(db_session)
    item_repo = ItemRepository(db_session)
    agent = ScopingAgent(chat_repo, item_repo)

    parsed: dict[str, Any] = {
        "action": "propose_items",
        "message": "Voici ma proposition initiale :",
        "items": [
            {
                "temp_id": "epic-1",
                "type": "epic",
                "title": "Auth Epic",
                "description": "Authentication",
                "complexity": "complex",
                "parent_temp_id": None,
            },
            {
                "temp_id": "us-1",
                "type": "user_story",
                "title": "Login",
                "description": "As a user I want to log in",
                "complexity": "medium",
                "parent_temp_id": "epic-1",
                "acceptance_criteria": ["login works"],
            },
            {
                "temp_id": "us-2",
                "type": "user_story",
                "title": "Signup",
                "description": "As a user I want to sign up",
                "complexity": "medium",
                "parent_temp_id": "epic-1",
            },
        ],
    }

    with _patch_llm_with_parsed(parsed):
        result = await agent.aprocess_user_message(
            project_id,
            "I want auth in my app",
        )

    # User + assistant messages are persisted.
    messages = await chat_repo.aget_messages_by_project(project_id)
    assert len(messages) == 2
    assert messages[0].role == ChatMessageRole.USER
    assert messages[0].content == "I want auth in my app"
    assert messages[1].role == ChatMessageRole.ASSISTANT
    assert messages[1].meta_data is not None
    assert messages[1].meta_data["action"] == "propose_items"

    # Result bundles the action + created items.
    assert result.action == "propose_items"
    assert len(result.items_created) == 3
    assert all(it.status == ItemStatus.PROPOSED for it in result.items_created)

    # Parent references are resolved.
    stored_items = await item_repo.aget_items_by_project(project_id)
    assert len(stored_items) == 3

    epics = [i for i in stored_items if i.type == ItemType.EPIC]
    stories = [i for i in stored_items if i.type == ItemType.USER_STORY]
    assert len(epics) == 1
    assert len(stories) == 2
    epic_id = epics[0].id
    for story in stories:
        assert story.parent_id == epic_id


# ---------------------------------------------------------------------------
# test_process_user_message_with_ask_question_action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_user_message_with_ask_question_action(
    db_session: AsyncSession,
) -> None:
    project_id = await _acreate_project(db_session)
    chat_repo = ChatMessageRepository(db_session)
    item_repo = ItemRepository(db_session)
    agent = ScopingAgent(chat_repo, item_repo)

    parsed: dict[str, Any] = {
        "action": "ask_question",
        "message": "Peux-tu preciser ton besoin ?",
        "items": [],
    }

    with _patch_llm_with_parsed(parsed):
        result = await agent.aprocess_user_message(
            project_id,
            "I need something",
        )

    assert result.action == "ask_question"
    assert result.items_created == []
    assert result.items_updated == []

    # No items stored.
    items = await item_repo.aget_items_by_project(project_id)
    assert items == []

    # The assistant message was persisted.
    messages = await chat_repo.aget_messages_by_project(project_id)
    assert len(messages) == 2
    assert messages[1].role == ChatMessageRole.ASSISTANT
    assert "preciser" in messages[1].content


# ---------------------------------------------------------------------------
# test_process_user_message_with_confirm_action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_user_message_with_confirm_action(
    db_session: AsyncSession,
) -> None:
    project_id = await _acreate_project(db_session)
    chat_repo = ChatMessageRepository(db_session)
    item_repo = ItemRepository(db_session)
    agent = ScopingAgent(chat_repo, item_repo)

    # Seed two PROPOSED items (as if a previous turn had created them).
    for idx in range(2):
        await item_repo.acreate_item(
            Item(
                project_id=project_id,
                type=ItemType.TASK,
                title=f"Pending task {idx}",
                status=ItemStatus.PROPOSED,
            ),
        )

    parsed: dict[str, Any] = {
        "action": "confirm",
        "message": "C'est valide !",
        "items": [],
    }

    with _patch_llm_with_parsed(parsed):
        result = await agent.aprocess_user_message(project_id, "ok, valide")

    assert result.action == "confirm"
    assert result.items_created == []
    assert len(result.items_updated) == 2
    assert all(it.status == ItemStatus.TODO for it in result.items_updated)

    # Re-fetch from DB to be sure the change is persisted.
    stored = await item_repo.aget_items_by_project(project_id)
    assert len(stored) == 2
    assert all(it.status == ItemStatus.TODO for it in stored)


# ---------------------------------------------------------------------------
# test_process_user_message_api_error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_user_message_api_error(
    db_session: AsyncSession,
) -> None:
    project_id = await _acreate_project(db_session)
    chat_repo = ChatMessageRepository(db_session)
    item_repo = ItemRepository(db_session)
    agent = ScopingAgent(chat_repo, item_repo)

    with _patch_llm_raises(RuntimeError("network boom")):
        result = await agent.aprocess_user_message(
            project_id,
            "hello",
        )

    assert result.action == "error"
    assert result.items_created == []
    assert result.items_updated == []

    # User + error assistant message are stored.
    messages = await chat_repo.aget_messages_by_project(project_id)
    assert len(messages) == 2
    assert messages[0].role == ChatMessageRole.USER
    assert messages[1].role == ChatMessageRole.ASSISTANT
    assert "Erreur" in messages[1].content
    assert messages[1].meta_data is not None
    assert messages[1].meta_data["action"] == "error"

    # No items were created.
    items = await item_repo.aget_items_by_project(project_id)
    assert items == []
