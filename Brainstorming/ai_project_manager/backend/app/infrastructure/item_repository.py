"""Repository for the `items` table."""

from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.infrastructure.base_repository import BaseRepository
from app.infrastructure.converters.item_converters import ItemConverters
from app.infrastructure.entities.item_entity import ItemEntity
from app.models.item import Item, ItemType


class ItemRepository(BaseRepository):
    """Domain-friendly facade around `ItemEntity`.

    All public methods exchange Pydantic `Item` models — SQLAlchemy entities
    never leak out of this class. Enum-typed fields (`type`, `status`) are
    serialised to their string value when hitting the DB because the column
    type is a simple `String(20)`.
    """

    async def acreate_item(self, item: Item) -> Item:
        """Persist a new item and return the stored model."""
        entity = ItemConverters.convert_item_model_to_entity(item)
        entity = await self.aadd_entity(entity)
        return ItemConverters.convert_item_entity_to_model(entity)

    async def aget_item_by_id(self, item_id: UUID) -> Item | None:
        """Fetch an item by id, excluding soft-deleted rows."""
        entity = await self.aget_entity_by_id(ItemEntity, item_id)
        if entity is None:
            return None
        return ItemConverters.convert_item_entity_to_model(entity)

    async def aget_items_by_project(
        self,
        project_id: UUID,
        type_filter: ItemType | None = None,
    ) -> list[Item]:
        """Return every item in a project, optionally filtered by type.

        Items are ordered by `status` then `created_at` ascending so the
        tree view can group them by workflow state while keeping insertion
        order inside each group.
        """
        query = (
            select(ItemEntity)
            .where(ItemEntity.project_id == project_id)
            .where(ItemEntity.deleted_at.is_(None))
            .order_by(ItemEntity.status.asc(), ItemEntity.created_at.asc())
        )
        if type_filter is not None:
            query = query.where(ItemEntity.type == type_filter.value)

        result = await self.session.execute(query)
        entities = list(result.scalars().all())
        return [
            ItemConverters.convert_item_entity_to_model(entity)
            for entity in entities
        ]

    async def aupdate_item(
        self,
        item_id: UUID,
        **fields: Any,
    ) -> Item | None:
        """Partial update by id. Only the provided fields are mutated.

        Enum values are normalised to their string representation so the
        caller can pass either a raw string or a proper enum member.
        """
        normalised: dict[str, Any] = {}
        for key, value in fields.items():
            if hasattr(value, "value"):
                normalised[key] = value.value
            else:
                normalised[key] = value

        updated_entity = await self.aupdate_entity(
            ItemEntity,
            item_id,
            **normalised,
        )
        if updated_entity is None:
            return None
        return ItemConverters.convert_item_entity_to_model(updated_entity)

    async def adelete_item(self, item_id: UUID) -> bool:
        """Soft-delete an item. Returns True if a row was affected."""
        return await self.adelete_entity(ItemEntity, item_id)
