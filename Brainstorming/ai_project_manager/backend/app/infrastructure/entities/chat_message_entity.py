"""SQLAlchemy entity for the `chat_messages` table."""

from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.infrastructure.entities.base import GUID, StatefulBase


class ChatMessageEntity(StatefulBase):
    """Persisted representation of a `ChatMessage`.

    Inherits id, created_at, updated_at and deleted_at from `StatefulBase`.
    The `meta_data` column is a free-form JSON payload — we avoid the name
    ``metadata`` because it is reserved by SQLAlchemy's Declarative base.
    """

    __tablename__ = "chat_messages"

    project_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("projects.id"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
