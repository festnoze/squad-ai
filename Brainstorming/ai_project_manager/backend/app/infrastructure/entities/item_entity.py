"""SQLAlchemy entity for the `items` table."""

from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.infrastructure.entities.base import GUID, StatefulBase


class ItemEntity(StatefulBase):
    """Persisted representation of an `Item` (Epic / User Story / Task).

    Inherits id, created_at, updated_at and deleted_at from `StatefulBase`.

    The `parent_id` column is a self-referencing FK, allowing the table to
    model the Epic -> User Story -> Task hierarchy without extra tables.
    Enum-like fields (`type`, `complexity`, `status`) are stored as short
    strings rather than SQL ENUMs: this keeps the SQLite schema simple and
    lets the domain layer own the enum validation via Pydantic.

    V1 additions:

    - ``deliverable_paths``: JSON list of generated file paths (relative to
      the backend ``generated/`` workspace) produced by the DevAgent.
    - ``deliverable_notes``: free-form markdown notes produced by the agents
      (dev notes, QA review, etc.). Concatenated over iterations.
    - ``blocked_reason``: set when the item's status is ``blocked`` (e.g.
      QA rejected twice, unmet dependency, etc.).
    """

    __tablename__ = "items"

    project_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("projects.id"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        GUID(),
        ForeignKey("items.id"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    complexity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="todo",
    )
    acceptance_criteria: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # V1: deliverables produced by the agents.
    deliverable_paths: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    deliverable_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
