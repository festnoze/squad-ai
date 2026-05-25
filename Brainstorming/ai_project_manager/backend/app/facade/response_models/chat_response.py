"""Response models for `/api/projects/{project_id}/messages` endpoints.

Covers the three payload shapes used by the chat / scoping feature:

- `ChatMessageResponse`: a single stored message (user / assistant / system).
- `ItemResponse`: a single persisted `Item` (Epic / UserStory / Task) as
  returned alongside the assistant turn that produced it.
- `SendMessageResponse`: the envelope returned by the POST endpoint,
  bundling the freshly persisted assistant message with the items it
  created or updated in this turn.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ChatMessageResponse(BaseModel):
    """Serialized view of a `ChatMessage` returned by the HTTP layer."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={UUID: str, datetime: lambda v: v.isoformat()},
    )

    id: UUID
    project_id: UUID
    role: str  # "user" | "assistant" | "system"
    content: str
    meta_data: dict[str, Any] | None = None
    created_at: datetime


class ItemResponse(BaseModel):
    """Serialized view of an `Item` returned by the HTTP layer."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={UUID: str, datetime: lambda v: v.isoformat()},
    )

    id: UUID
    project_id: UUID
    parent_id: UUID | None = None
    type: str
    title: str
    description: str | None = None
    complexity: str | None = None
    status: str
    acceptance_criteria: list[str] | None = None
    order: int
    # V1 deliverable info (None until an agent produces something)
    deliverable_paths: list[str] | None = None
    deliverable_notes: str | None = None
    blocked_reason: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class SendMessageResponse(BaseModel):
    """Envelope returned by POST `/api/projects/{id}/messages`."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={UUID: str, datetime: lambda v: v.isoformat()},
    )

    message: ChatMessageResponse
    items_created: list[ItemResponse]
    items_updated: list[ItemResponse]
    action: str
