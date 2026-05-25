"""SQLAlchemy entity for the `projects` table."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.entities.base import StatefulBase


class ProjectEntity(StatefulBase):
    """Persisted representation of a `Project`.

    Inherits id, created_at, updated_at and deleted_at from `StatefulBase`.
    """

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
