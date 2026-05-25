"""Repository for the `item_dependencies` join table.

Exposes the minimal surface the application layer needs:

- add / bulk-add edges
- query the full dependency graph of a project (for the orchestrator)
- query the children of a given item (reverse edges, "what unblocks")

The graph is always loaded in full for a project because it's a small
blob for the scale we target (< few hundreds of tasks), so the
orchestrator can run its topological logic in pure Python.
"""

from uuid import UUID

from sqlalchemy import select

from app.infrastructure.base_repository import BaseRepository
from app.infrastructure.converters.item_dependency_converters import (
    ItemDependencyConverters,
)
from app.infrastructure.entities.item_dependency_entity import (
    ItemDependencyEntity,
)
from app.infrastructure.entities.item_entity import ItemEntity
from app.models.item_dependency import ItemDependency


class ItemDependencyRepository(BaseRepository):
    """Domain-friendly facade around the `item_dependencies` table."""

    async def acreate_dependency(
        self,
        dep: ItemDependency,
    ) -> ItemDependency:
        """Persist a single edge."""
        entity = (
            ItemDependencyConverters.convert_item_dependency_model_to_entity(dep)
        )
        entity = await self.aadd_entity(entity)
        return ItemDependencyConverters.convert_item_dependency_entity_to_model(
            entity,
        )

    async def acreate_many(
        self,
        deps: list[ItemDependency],
    ) -> list[ItemDependency]:
        """Persist multiple edges in one session flush."""
        stored: list[ItemDependency] = []
        for dep in deps:
            stored.append(await self.acreate_dependency(dep))
        return stored

    async def aget_dependencies_for_project(
        self,
        project_id: UUID,
    ) -> list[ItemDependency]:
        """Return every edge whose source item belongs to ``project_id``.

        Uses a join on `items` to scope by project without having to
        denormalise the project_id onto the dependency row.
        """
        query = (
            select(ItemDependencyEntity)
            .join(
                ItemEntity,
                ItemEntity.id == ItemDependencyEntity.item_id,
            )
            .where(ItemEntity.project_id == project_id)
            .where(ItemEntity.deleted_at.is_(None))
        )
        result = await self.session.execute(query)
        entities = list(result.scalars().all())
        return [
            ItemDependencyConverters.convert_item_dependency_entity_to_model(e)
            for e in entities
        ]
