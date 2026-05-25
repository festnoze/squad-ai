"""Integration tests for `ChatMessageRepository`."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.chat_message_repository import ChatMessageRepository
from app.infrastructure.project_repository import ProjectRepository
from app.models.chat_message import ChatMessage, ChatMessageRole
from app.models.project import Project


async def _create_project(session: AsyncSession) -> UUID:
    project_repo = ProjectRepository(session)
    project = await project_repo.acreate_project(
        Project(name="Chat Test Project"),
    )
    assert project.id is not None
    return project.id


@pytest.mark.asyncio
async def test_create_and_list_messages_by_project(
    db_session: AsyncSession,
) -> None:
    project_id = await _create_project(db_session)
    repo = ChatMessageRepository(db_session)

    first = await repo.acreate_message(
        ChatMessage(
            project_id=project_id,
            role=ChatMessageRole.USER,
            content="Hello assistant",
        ),
    )
    second = await repo.acreate_message(
        ChatMessage(
            project_id=project_id,
            role=ChatMessageRole.ASSISTANT,
            content="Hi, how can I help?",
        ),
    )
    third = await repo.acreate_message(
        ChatMessage(
            project_id=project_id,
            role=ChatMessageRole.USER,
            content="I want to scope a project",
        ),
    )

    messages = await repo.aget_messages_by_project(project_id)
    assert len(messages) == 3
    assert [m.id for m in messages] == [first.id, second.id, third.id]
    assert [m.role for m in messages] == [
        ChatMessageRole.USER,
        ChatMessageRole.ASSISTANT,
        ChatMessageRole.USER,
    ]
    assert messages[0].content == "Hello assistant"
    assert messages[1].content == "Hi, how can I help?"
    assert messages[2].content == "I want to scope a project"


@pytest.mark.asyncio
async def test_meta_data_round_trip(db_session: AsyncSession) -> None:
    project_id = await _create_project(db_session)
    repo = ChatMessageRepository(db_session)

    payload = {
        "proposed_items": [
            {"type": "epic", "title": "Auth"},
            {"type": "user_story", "title": "Login"},
        ],
        "tokens_used": 42,
    }

    created = await repo.acreate_message(
        ChatMessage(
            project_id=project_id,
            role=ChatMessageRole.ASSISTANT,
            content="Here are the items I propose",
            meta_data=payload,
        ),
    )
    assert created.id is not None

    fetched = await repo.aget_message_by_id(created.id)
    assert fetched is not None
    assert fetched.meta_data == payload
    assert fetched.meta_data is not None
    assert fetched.meta_data["tokens_used"] == 42
    assert len(fetched.meta_data["proposed_items"]) == 2
