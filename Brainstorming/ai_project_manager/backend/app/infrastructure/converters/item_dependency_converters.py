"""Bidirectional converters between `ItemDependencyEntity` and
`ItemDependency`."""

from app.infrastructure.entities.item_dependency_entity import (
    ItemDependencyEntity,
)
from app.models.item_dependency import ItemDependency


class ItemDependencyConverters:
    """Static helpers for the item-dependency join table."""

    @staticmethod
    def convert_item_dependency_entity_to_model(
        entity: ItemDependencyEntity,
    ) -> ItemDependency:
        return ItemDependency(
            id=entity.id,
            item_id=entity.item_id,
            depends_on_item_id=entity.depends_on_item_id,
        )

    @staticmethod
    def convert_item_dependency_model_to_entity(
        model: ItemDependency,
    ) -> ItemDependencyEntity:
        entity = ItemDependencyEntity(
            item_id=model.item_id,
            depends_on_item_id=model.depends_on_item_id,
        )
        if model.id is not None:
            entity.id = model.id
        return entity
