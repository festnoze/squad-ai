"""HTTP router for `/api/projects/{project_id}/messages`.

Exposes the two endpoints driving the scoping chat (Epic 2):

- ``POST /api/projects/{project_id}/messages`` — send a new user message,
  invoke the `ScopingAgent`, return the assistant reply + any items it
  created or confirmed.
- ``GET  /api/projects/{project_id}/messages`` — return the full chat
  history of a project, oldest first.

Unlike `project_router`, these endpoints DO go through a service layer
(`ScopingAgent`) because the POST has to orchestrate the chat repository,
the item repository and an LLM call via common-tools.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.facade.converters.chat_response_converter import ChatResponseConverter
from app.facade.request_models.chat_request import SendMessageRequest
from app.facade.response_models.chat_response import (
    ChatMessageResponse,
    SendMessageResponse,
)
from app.infrastructure.chat_message_repository import ChatMessageRepository
from app.infrastructure.item_dependency_repository import (
    ItemDependencyRepository,
)
from app.infrastructure.item_repository import ItemRepository
from app.infrastructure.project_repository import ProjectRepository
from app.services.llm_factory import LlmNotConfiguredError
from app.services.scoping_agent import ScopingAgent

router = APIRouter(prefix="/api/projects", tags=["chat"])


async def _aensure_project_exists(
    project_id: UUID,
    db: AsyncSession,
) -> None:
    """Raise HTTP 404 if the given project id is unknown."""
    project_repo = ProjectRepository(db)
    project = await project_repo.aget_project_by_id(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )


def _build_scoping_agent(db: AsyncSession) -> ScopingAgent:
    """Factory used by the POST endpoint. Overridable in tests via DI."""
    return ScopingAgent(
        chat_repository=ChatMessageRepository(db),
        item_repository=ItemRepository(db),
        dependency_repository=ItemDependencyRepository(db),
    )


@router.post(
    "/{project_id}/messages",
    response_model=SendMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def asend_message(
    project_id: UUID,
    req: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
) -> SendMessageResponse:
    """Post a new user message and trigger the scoping agent."""
    await _aensure_project_exists(project_id, db)

    agent = _build_scoping_agent(db)

    try:
        result = await agent.aprocess_user_message(project_id, req.content)
    except LlmNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return ChatResponseConverter.convert_scoping_result_to_response(result)


@router.get(
    "/{project_id}/messages",
    response_model=list[ChatMessageResponse],
)
async def aget_project_messages(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ChatMessageResponse]:
    """Return the full chat history of a project, oldest first."""
    await _aensure_project_exists(project_id, db)

    chat_repo = ChatMessageRepository(db)
    messages = await chat_repo.aget_messages_by_project(project_id)
    return ChatResponseConverter.convert_chat_messages_to_responses(messages)
