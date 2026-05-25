"""End-to-end tests for the `/api/projects/{id}/runs` router.

These tests override the `_build_service` FastAPI dependency with a
fake `ProjectRunService` so they:

- run deterministically (no LLM, no background task),
- validate the HTTP surface (status codes, payload shape),
- verify the 404/409 paths.

A separate test module (`test_project_run_service.py`) exercises the
real service behaviour in isolation.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.project_run_service import ProjectRunConflict
from app.infrastructure.project_run_repository import ProjectRunRepository
from app.models.project_run import ProjectRun, ProjectRunStatus
from app.models.project_run_step import (
    ProjectRunStep,
    ProjectRunStepRole,
    ProjectRunStepStatus,
)
from app.routers.project_run_router import _build_service


@dataclass
class _FakeRunService:
    """Minimal stand-in for `ProjectRunService` used by the router."""

    conflict: bool = False
    last_session: Any = None
    last_project_id: UUID | None = None

    async def astart_project_run(
        self,
        *,
        session: Any,
        project_id: UUID,
    ) -> ProjectRun:
        self.last_session = session
        self.last_project_id = project_id
        if self.conflict:
            raise ProjectRunConflict("boom")
        now = datetime.now(timezone.utc)
        return ProjectRun(
            id=uuid4(),
            project_id=project_id,
            status=ProjectRunStatus.RUNNING,
            started_at=now,
            total_tasks=0,
            created_at=now,
        )


async def _acreate_project(client: AsyncClient) -> UUID:
    resp = await client.post("/api/projects", json={"name": "RunRouter"})
    assert resp.status_code == 201
    return UUID(resp.json()["id"])


# ---------------------------------------------------------------------------
# POST /api/projects/{id}/runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_run_project_not_found(client: AsyncClient) -> None:
    response = await client.post(f"/api/projects/{uuid4()}/runs")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_start_run_success(client: AsyncClient) -> None:
    project_id = await _acreate_project(client)
    fake = _FakeRunService()
    client.app.dependency_overrides[_build_service] = lambda: fake  # type: ignore[attr-defined]

    try:
        response = await client.post(f"/api/projects/{project_id}/runs")
    finally:
        client.app.dependency_overrides.pop(_build_service, None)  # type: ignore[attr-defined]

    assert response.status_code == 202
    body = response.json()
    assert body["project_id"] == str(project_id)
    assert body["status"] == "running"
    assert fake.last_project_id == project_id


@pytest.mark.asyncio
async def test_start_run_conflict_409(client: AsyncClient) -> None:
    project_id = await _acreate_project(client)
    fake = _FakeRunService(conflict=True)
    client.app.dependency_overrides[_build_service] = lambda: fake  # type: ignore[attr-defined]

    try:
        response = await client.post(f"/api/projects/{project_id}/runs")
    finally:
        client.app.dependency_overrides.pop(_build_service, None)  # type: ignore[attr-defined]

    assert response.status_code == 409
    assert response.json()["detail"] == "boom"


# ---------------------------------------------------------------------------
# GET /api/projects/{id}/runs/current
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_run_project_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/api/projects/{uuid4()}/runs/current")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_current_run_no_run_yet(client: AsyncClient) -> None:
    project_id = await _acreate_project(client)
    response = await client.get(f"/api/projects/{project_id}/runs/current")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_current_run_returns_detail(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Seed one run + two steps, GET returns both nested."""
    project_id = await _acreate_project(client)

    run_repo = ProjectRunRepository(db_session)
    run = await run_repo.acreate_run(
        ProjectRun(
            project_id=project_id,
            status=ProjectRunStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            total_tasks=2,
        ),
    )
    assert run.id is not None
    await run_repo.acreate_step(
        ProjectRunStep(
            run_id=run.id,
            role=ProjectRunStepRole.ORCHESTRATOR,
            status=ProjectRunStepStatus.SUCCEEDED,
            iteration=0,
            summary="Run démarré.",
            started_at=datetime.now(timezone.utc),
        ),
    )
    await run_repo.acreate_step(
        ProjectRunStep(
            run_id=run.id,
            role=ProjectRunStepRole.DEV,
            status=ProjectRunStepStatus.RUNNING,
            iteration=1,
            summary="Dev itération 1",
            started_at=datetime.now(timezone.utc),
        ),
    )
    await db_session.commit()

    response = await client.get(f"/api/projects/{project_id}/runs/current")
    assert response.status_code == 200
    body = response.json()
    assert body["run"]["id"] == str(run.id)
    assert body["run"]["status"] == "running"
    assert body["run"]["total_tasks"] == 2
    assert len(body["steps"]) == 2
    assert body["steps"][0]["role"] == "orchestrator"
    assert body["steps"][1]["role"] == "dev"
