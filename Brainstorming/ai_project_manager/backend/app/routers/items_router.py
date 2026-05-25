"""HTTP router for project items (Epic 3).

Exposes the read endpoints the frontend needs to render and drive the
project tree (Epic / User Story / Task):

- ``GET /api/projects/{project_id}/items`` — list every non-deleted item
  of a project, optionally filtered by ``type`` query param.
- ``GET /api/items/{item_id}`` — fetch a single item by id.

V1 note: the old ``POST /api/items/{id}/execute`` endpoint was removed.
Task execution is now driven at the project level via
``POST /api/projects/{id}/runs`` (see `project_run_router`).

Architecture note: like `project_router`, the read endpoints are pure
reads and talk directly to `ItemRepository` without a service layer.
The `ItemResponse` schema and the `ChatResponseConverter` used for
serialization are imported from the chat facade module to avoid any
duplication — the wire shape of an item is the same whether it comes
from the scoping chat or from the items listing.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.facade.converters.chat_response_converter import ChatResponseConverter
from app.facade.response_models.chat_response import ItemResponse
from app.infrastructure.item_repository import ItemRepository
from app.infrastructure.project_repository import ProjectRepository
from app.models.item import ItemType

router = APIRouter(prefix="/api", tags=["items"])


async def _aensure_project_exists(
    project_id: UUID,
    db: AsyncSession,
) -> None:
    """Raise HTTP 404 if the given project id is unknown."""
    project_repo = ProjectRepository(db)
    project = await project_repo.aget_project_by_id(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )


@router.get(
    "/projects/{project_id}/items",
    response_model=list[ItemResponse],
)
async def aget_project_items(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    type_filter: ItemType | None = Query(default=None, alias="type"),
) -> list[ItemResponse]:
    """Return every non-deleted item of a project, optionally filtered by type.

    The ``?type=`` query param is typed as `ItemType`, so Pydantic handles
    the validation automatically and returns a uniform 422 response on
    invalid values — consistent with the rest of the API.

    Ordering (status asc, created_at asc) is handled by the repository so
    the tree view can group items by workflow state while preserving
    insertion order inside each group.
    """
    await _aensure_project_exists(project_id, db)

    repo = ItemRepository(db)
    items = await repo.aget_items_by_project(
        project_id,
        type_filter=type_filter,
    )
    return ChatResponseConverter.convert_items_to_responses(items)


@router.get(
    "/items/{item_id}",
    response_model=ItemResponse,
)
async def aget_item_by_id(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ItemResponse:
    """Return a single item by id, 404 if missing or soft-deleted."""
    repo = ItemRepository(db)
    item = await repo.aget_item_by_id(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} not found",
        )
    return ChatResponseConverter.convert_item_to_response(item)
