"""Repository for the `projects` table."""

from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, update

from app.infrastructure.base_repository import BaseRepository
from app.infrastructure.common import get_utc_now
from app.infrastructure.converters.project_converters import ProjectConverters
from app.infrastructure.entities.chat_message_entity import ChatMessageEntity
from app.infrastructure.entities.item_entity import ItemEntity
from app.infrastructure.entities.project_entity import ProjectEntity
from app.models.project import Project


class ProjectRepository(BaseRepository):
    """Domain-friendly facade around `ProjectEntity`.

    All public methods exchange Pydantic `Project` models — SQLAlchemy entities
    never leak out of this class.
    """

    async def acreate_project(self, project: Project) -> Project:
        """Persist a new project and return the stored model."""
        entity = ProjectConverters.convert_project_model_to_entity(project)
        entity = await self.aadd_entity(entity)
        return ProjectConverters.convert_project_entity_to_model(entity)

    async def aget_project_by_id(self, project_id: UUID) -> Project | None:
        """Fetch a project by id, excluding soft-deleted rows."""
        entity = await self._aget_project_entity_by_id(project_id)
        if entity is None:
            return None
        return ProjectConverters.convert_project_entity_to_model(entity)

    async def aget_all_projects(self) -> list[Project]:
        """Return every non-deleted project, most recently updated first."""
        entities = await self.aget_all_entities(
            ProjectEntity,
            order_by=ProjectEntity.updated_at.desc(),
        )
        return [
            ProjectConverters.convert_project_entity_to_model(entity)
            for entity in entities
        ]

    async def aupdate_project(self, project: Project) -> Project | None:
        """Partial update using the provided model's mutable fields."""
        if project.id is None:
            raise ValueError("Cannot update a project without an id")

        updated_entity = await self.aupdate_entity(
            ProjectEntity,
            project.id,
            name=project.name,
            description=project.description,
        )
        if updated_entity is None:
            return None
        return ProjectConverters.convert_project_entity_to_model(updated_entity)

    async def aupdate_project_fields(
        self,
        project_id: UUID,
        **fields: Any,
    ) -> Project | None:
        """Partial update by id. Only the provided fields are mutated.

        Intended for the PATCH endpoint: the router passes
        `model_dump(exclude_unset=True)` so omitted keys keep their current
        values — unlike `aupdate_project`, which unconditionally rewrites
        `name` and `description` from a full `Project` model.
        """
        if not fields:
            return await self.aget_project_by_id(project_id)

        updated_entity = await self.aupdate_entity(
            ProjectEntity,
            project_id,
            **fields,
        )
        if updated_entity is None:
            return None
        return ProjectConverters.convert_project_entity_to_model(updated_entity)

    async def adelete_project(self, project_id: UUID) -> bool:
        """Soft-delete a project. Returns True if a row was affected."""
        return await self.adelete_entity(ProjectEntity, project_id)

    async def adelete_project_cascade(self, project_id: UUID) -> bool:
        """Soft-delete a project AND every child item / chat message.

        Walks the two child tables (`items`, `chat_messages`) with bulk
        UPDATE statements so we don't have to load each row individually.
        Only rows that are still live (``deleted_at IS NULL``) are
        touched — running the cascade twice is a no-op on children that
        were already deleted.

        Returns True if the project itself was soft-deleted, False if it
        was already gone.
        """
        now = get_utc_now()

        # Cascade the children first so a transient failure between
        # steps never leaves a "deleted" project pointing at live items.
        for child_entity in (ItemEntity, ChatMessageEntity):
            stmt = (
                update(child_entity)
                .where(child_entity.project_id == project_id)
                .where(child_entity.deleted_at.is_(None))
                .values(deleted_at=now, updated_at=now)
            )
            # Cast for pyright: Result[Any] is actually a CursorResult
            # for UPDATE statements at runtime.
            cast(CursorResult[Any], await self.session.execute(stmt))

        return await self.adelete_entity(ProjectEntity, project_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _aget_project_entity_by_id(
        self,
        project_id: UUID,
    ) -> ProjectEntity | None:
        """Internal helper returning the raw SQLAlchemy entity."""
        return await self.aget_entity_by_id(ProjectEntity, project_id)
