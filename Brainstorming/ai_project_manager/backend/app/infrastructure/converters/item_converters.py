"""Bidirectional converters between `ItemEntity` and `Item`."""

from app.infrastructure.entities.item_entity import ItemEntity
from app.models.item import Item, ItemComplexity, ItemStatus, ItemType


class ItemConverters:
    """Static helpers to keep the domain layer free of SQLAlchemy leaks."""

    @staticmethod
    def convert_item_entity_to_model(entity: ItemEntity) -> Item:
        """Convert a SQLAlchemy entity into a Pydantic domain model."""
        return Item(
            id=entity.id,
            project_id=entity.project_id,
            parent_id=entity.parent_id,
            type=ItemType(entity.type),
            title=entity.title,
            description=entity.description,
            complexity=(
                ItemComplexity(entity.complexity)
                if entity.complexity is not None
                else None
            ),
            status=ItemStatus(entity.status),
            acceptance_criteria=entity.acceptance_criteria,
            order=entity.order,
            deliverable_paths=entity.deliverable_paths,
            deliverable_notes=entity.deliverable_notes,
            blocked_reason=entity.blocked_reason,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            deleted_at=entity.deleted_at,
        )

    @staticmethod
    def convert_item_model_to_entity(model: Item) -> ItemEntity:
        """Convert a Pydantic domain model into a SQLAlchemy entity.

        Only populates fields that are not None so that the database's
        default values (e.g. `created_at`) can kick in for fresh inserts.
        """
        entity = ItemEntity(
            project_id=model.project_id,
            parent_id=model.parent_id,
            type=model.type.value,
            title=model.title,
            description=model.description,
            complexity=(
                model.complexity.value if model.complexity is not None else None
            ),
            status=model.status.value,
            acceptance_criteria=model.acceptance_criteria,
            order=model.order,
            deliverable_paths=model.deliverable_paths,
            deliverable_notes=model.deliverable_notes,
            blocked_reason=model.blocked_reason,
        )
        if model.id is not None:
            entity.id = model.id
        if model.created_at is not None:
            entity.created_at = model.created_at
        if model.updated_at is not None:
            entity.updated_at = model.updated_at
        if model.deleted_at is not None:
            entity.deleted_at = model.deleted_at
        return entity
