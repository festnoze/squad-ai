"""Generic async CRUD repository.

This is a deliberately simple version compared to the SkillForge reference.
We don't need a ContextVar-driven session manager for a local MVP: FastAPI
injects a fresh `AsyncSession` into each request via `Depends(get_db)` and
passes it to the repository's constructor. One request, one session, one
transaction — easy to reason about.

Soft-delete is supported automatically for any entity exposing a `deleted_at`
attribute (which is the case for everything inheriting from `StatefulBase`).
"""

from typing import Any, TypeVar, cast
from uuid import UUID

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.common import get_utc_now

T = TypeVar("T")


class BaseRepository:
    """Base class providing generic async CRUD operations.

    Concrete repositories receive an `AsyncSession` at construction time and
    delegate row-level operations to the helpers defined here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_deleted_at(entity_class: type) -> bool:
        return hasattr(entity_class, "deleted_at")

    @staticmethod
    def _has_updated_at(entity_class: type) -> bool:
        return hasattr(entity_class, "updated_at")

    def _apply_soft_delete_filter(
        self,
        query: Any,
        entity_class: type,
        include_deleted: bool,
    ) -> Any:
        if not include_deleted and self._has_deleted_at(entity_class):
            query = query.where(entity_class.deleted_at.is_(None))
        return query

    # ------------------------------------------------------------------
    # CRUD primitives
    # ------------------------------------------------------------------

    async def aadd_entity(self, entity: Any) -> Any:
        """Add a single entity, flush and refresh it so PKs/timestamps load."""
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def aget_entity_by_id(
        self,
        entity_class: type,
        entity_id: UUID,
        include_deleted: bool = False,
    ) -> Any | None:
        """Return a single entity by id, or None if not found/soft-deleted."""
        query = select(entity_class).where(entity_class.id == entity_id)
        query = self._apply_soft_delete_filter(query, entity_class, include_deleted)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def aget_all_entities(
        self,
        entity_class: type,
        filters: list[Any] | None = None,
        order_by: Any | None = None,
        include_deleted: bool = False,
    ) -> list[Any]:
        """Return every entity matching the optional filters."""
        query = select(entity_class)
        query = self._apply_soft_delete_filter(query, entity_class, include_deleted)
        if filters:
            for f in filters:
                query = query.where(f)
        if order_by is not None:
            query = query.order_by(order_by)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def aget_entity_count(
        self,
        entity_class: type,
        include_deleted: bool = False,
    ) -> int:
        """Count non-deleted entities of the given class."""
        query = select(func.count()).select_from(entity_class)
        query = self._apply_soft_delete_filter(query, entity_class, include_deleted)
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def aupdate_entity(
        self,
        entity_class: type,
        entity_id: UUID,
        **fields: Any,
    ) -> Any | None:
        """Partial update by id. Returns the refreshed entity or None."""
        entity = await self.aget_entity_by_id(entity_class, entity_id)
        if entity is None:
            return None

        for key, value in fields.items():
            if hasattr(entity, key):
                setattr(entity, key, value)

        if self._has_updated_at(entity_class) and "updated_at" not in fields:
            entity.updated_at = get_utc_now()

        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def adelete_entity(
        self,
        entity_class: type,
        entity_id: UUID,
        hard: bool = False,
    ) -> bool:
        """Delete an entity by id. Returns True if something was deleted.

        Defaults to soft-delete when the entity has a `deleted_at` column.
        """
        if not hard and self._has_deleted_at(entity_class):
            values: dict[str, Any] = {"deleted_at": get_utc_now()}
            if self._has_updated_at(entity_class):
                values["updated_at"] = get_utc_now()
            stmt = (
                update(entity_class)
                .where(entity_class.id == entity_id)
                .where(entity_class.deleted_at.is_(None))
                .values(**values)
            )
            result = cast(CursorResult[Any], await self.session.execute(stmt))
            return (result.rowcount or 0) > 0

        entity = await self.aget_entity_by_id(
            entity_class, entity_id, include_deleted=True
        )
        if entity is None:
            return False
        await self.session.delete(entity)
        await self.session.flush()
        return True
