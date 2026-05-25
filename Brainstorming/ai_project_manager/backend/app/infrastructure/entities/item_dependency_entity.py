"""SQLAlchemy entity for the `item_dependencies` join table.

Models "task A depends on task B" relationships produced during the
scoping phase. Keeping it as a separate join table (rather than a JSON
column on `items`) lets the orchestrator run efficient topological
queries and lets Alembic track the schema cleanly.

Each row is directional: ``(item_id, depends_on_item_id)`` means
``item_id`` cannot start until ``depends_on_item_id`` is in a terminal
status (``done`` or ``blocked``). The composite primary key prevents
duplicate pairs without needing a UNIQUE constraint.
"""

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.entities.base import GUID, Base


class ItemDependencyEntity(Base):
    """Directed edge in the item-dependency graph."""

    __tablename__ = "item_dependencies"

    id: Mapped[UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid4,
    )
    item_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("items.id"),
        nullable=False,
        index=True,
    )
    depends_on_item_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("items.id"),
        nullable=False,
        index=True,
    )
