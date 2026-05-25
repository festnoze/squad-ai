"""`ItemDependency` domain model (Pydantic).

Represents a directed edge in the item-dependency graph:
``item_id`` depends on ``depends_on_item_id`` and therefore cannot be
started until the latter has reached a terminal status.
"""

from uuid import UUID

from app.models.base_model import IdBaseModel


class ItemDependency(IdBaseModel):
    """A single dependency edge between two items."""

    item_id: UUID
    depends_on_item_id: UUID
