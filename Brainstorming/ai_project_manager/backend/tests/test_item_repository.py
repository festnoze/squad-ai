"""Integration tests for `ItemRepository`."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.item_repository import ItemRepository
from app.infrastructure.project_repository import ProjectRepository
from app.models.item import Item, ItemStatus, ItemType
from app.models.project import Project


async def _create_project(session: AsyncSession) -> UUID:
    project_repo = ProjectRepository(session)
    project = await project_repo.acreate_project(
        Project(name="Test Project", description="fixture"),
    )
    assert project.id is not None
    return project.id


@pytest.mark.asyncio
async def test_create_and_retrieve_item(db_session: AsyncSession) -> None:
    project_id = await _create_project(db_session)
    repo = ItemRepository(db_session)

    created = await repo.acreate_item(
        Item(
            project_id=project_id,
            type=ItemType.TASK,
            title="Implement login button",
            description="A button on the landing page",
        ),
    )

    assert created.id is not None
    fetched = await repo.aget_item_by_id(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.title == "Implement login button"
    assert fetched.type == ItemType.TASK
    assert fetched.status == ItemStatus.TODO
    assert fetched.parent_id is None


@pytest.mark.asyncio
async def test_create_item_with_parent(db_session: AsyncSession) -> None:
    project_id = await _create_project(db_session)
    repo = ItemRepository(db_session)

    epic = await repo.acreate_item(
        Item(
            project_id=project_id,
            type=ItemType.EPIC,
            title="Auth Epic",
        ),
    )
    assert epic.id is not None

    story = await repo.acreate_item(
        Item(
            project_id=project_id,
            parent_id=epic.id,
            type=ItemType.USER_STORY,
            title="As a user I want to log in",
            acceptance_criteria=["Given a valid account, login succeeds"],
        ),
    )
    assert story.id is not None

    fetched = await repo.aget_item_by_id(story.id)
    assert fetched is not None
    assert fetched.parent_id == epic.id
    assert fetched.type == ItemType.USER_STORY
    assert fetched.acceptance_criteria == [
        "Given a valid account, login succeeds",
    ]


@pytest.mark.asyncio
async def test_get_items_by_project_filtered_by_type(
    db_session: AsyncSession,
) -> None:
    project_id = await _create_project(db_session)
    repo = ItemRepository(db_session)

    await repo.acreate_item(
        Item(project_id=project_id, type=ItemType.EPIC, title="E1"),
    )
    await repo.acreate_item(
        Item(project_id=project_id, type=ItemType.USER_STORY, title="US1"),
    )
    await repo.acreate_item(
        Item(project_id=project_id, type=ItemType.USER_STORY, title="US2"),
    )
    await repo.acreate_item(
        Item(project_id=project_id, type=ItemType.TASK, title="T1"),
    )
    await repo.acreate_item(
        Item(project_id=project_id, type=ItemType.TASK, title="T2"),
    )
    await repo.acreate_item(
        Item(project_id=project_id, type=ItemType.TASK, title="T3"),
    )

    all_items = await repo.aget_items_by_project(project_id)
    assert len(all_items) == 6

    epics = await repo.aget_items_by_project(project_id, type_filter=ItemType.EPIC)
    assert len(epics) == 1
    assert epics[0].title == "E1"

    stories = await repo.aget_items_by_project(
        project_id, type_filter=ItemType.USER_STORY,
    )
    assert len(stories) == 2
    assert {s.title for s in stories} == {"US1", "US2"}

    tasks = await repo.aget_items_by_project(project_id, type_filter=ItemType.TASK)
    assert len(tasks) == 3
    assert {t.title for t in tasks} == {"T1", "T2", "T3"}


@pytest.mark.asyncio
async def test_update_item_status(db_session: AsyncSession) -> None:
    project_id = await _create_project(db_session)
    repo = ItemRepository(db_session)

    created = await repo.acreate_item(
        Item(project_id=project_id, type=ItemType.TASK, title="Do the thing"),
    )
    assert created.id is not None
    assert created.status == ItemStatus.TODO

    updated = await repo.aupdate_item(created.id, status=ItemStatus.IN_PROGRESS)
    assert updated is not None
    assert updated.status == ItemStatus.IN_PROGRESS

    fetched = await repo.aget_item_by_id(created.id)
    assert fetched is not None
    assert fetched.status == ItemStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_soft_delete_item(db_session: AsyncSession) -> None:
    project_id = await _create_project(db_session)
    repo = ItemRepository(db_session)

    created = await repo.acreate_item(
        Item(project_id=project_id, type=ItemType.TASK, title="To delete"),
    )
    assert created.id is not None

    deleted = await repo.adelete_item(created.id)
    assert deleted is True

    fetched = await repo.aget_item_by_id(created.id)
    assert fetched is None
