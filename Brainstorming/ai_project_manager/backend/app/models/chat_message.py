"""ChatMessage domain model (Pydantic).

A `ChatMessage` is a single turn in the cadrage conversation between the PM
and the AI. Messages are always scoped to a `Project` — the conversation
history is how the assistant remembers the context of a given project.

The optional `meta_data` dict is a free-form JSON payload used by the
assistant to ship structured artefacts alongside the raw `content` — most
notably the list of `Item`s it proposes to add to the project tree before
the PM validates them.
"""

from enum import Enum
from typing import Any
from uuid import UUID

from app.models.base_model import IdStatefulBaseModel


class ChatMessageRole(str, Enum):
    """Author of a chat message."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(IdStatefulBaseModel):
    """A single message in a project's cadrage conversation.

    Attributes:
        project_id: Project the message belongs to.
        role: Who emitted the message (user / assistant / system).
        content: Raw text of the message.
        meta_data: Optional JSON payload (e.g. list of proposed items).
    """

    project_id: UUID
    role: ChatMessageRole
    content: str
    meta_data: dict[str, Any] | None = None
