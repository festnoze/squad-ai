"""Tests of the component proposal (E3) and setup executor (E4)."""

import json

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import ComponentStatus, PipelinePhase, ProjectState
from autospec.orchestrator import setup_exec
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir

from .conftest import wait_until

PM_BRIEF = json.dumps({"type": "brief", "message": "OK", "brief": "# Brief"})
PO_PLAN = json.dumps(
    {"epics": [{"id": "EPIC-1", "title": "E", "stories": [
        {"id": "US-1", "title": "S", "description": "d", "acceptance_criteria": ["c"],
         "gherkin": "Feature: F\n  Scenario: s\n    Given a\n    When b\n    Then c", "depends_on": []},
    ]}]}
)
QA_TRIVIAL = json.dumps({"message": "Trivial.", "tests": []})
DEV_GREEN = json.dumps({"status": "green", "summary": "ok", "files": []})
COMPONENTS = json.dumps(
    {
        "message": "Stack par défaut.",
        "components": [
            {"id": "backend", "kind": "backend", "name": "API", "technology": "Python + FastAPI", "optional": False},
            {"id": "frontend", "kind": "frontend", "name": "Web", "technology": "React + Vite", "optional": False},
            {"id": "db", "kind": "database", "name": "BDD", "technology": "PostgreSQL", "optional": True},
        ],
    },
    ensure_ascii=False,
)


def make_pipeline(replies: list[str]) -> Pipeline:
    state = ProjectState(id="proj-comp", name="todo", goal="Une todo-list")
    return Pipeline(state, FakeRunner(replies))


async def test_components_proposed_after_brief(monkeypatch, green_pytest):
    monkeypatch.setattr(settings, "components_enabled", True)
    pipeline = make_pipeline([PM_BRIEF, COMPONENTS, PO_PLAN, QA_TRIVIAL, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    components = {c.id: c for c in pipeline.state.components}
    assert set(components) == {"backend", "frontend", "db"}
    # Mandatory components are pre-approved; optional ones await the user.
    assert components["backend"].status == ComponentStatus.APPROVED
    assert components["frontend"].status == ComponentStatus.APPROVED
    assert components["db"].status == ComponentStatus.PROPOSED


async def test_components_phase_disabled_by_default(green_pytest):
    pipeline = make_pipeline([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    assert pipeline.state.components == []


async def test_set_components_replaces_list():
    pipeline = make_pipeline([])
    components = await pipeline.aset_components(
        [
            {"id": "backend", "kind": "backend", "name": "API", "technology": "FastAPI",
             "status": "approved"},
            {"kind": "cache", "name": "Cache", "technology": "Redis", "optional": True,
             "status": "rejected"},
        ]
    )
    assert [c.status for c in components] == [ComponentStatus.APPROVED, ComponentStatus.REJECTED]
    assert pipeline.state.components[1].id  # generated id when missing


async def test_setup_executor_creates_components_without_install():
    pipeline = make_pipeline([])
    await pipeline.aset_components(
        [
            {"id": "backend", "kind": "backend", "name": "API", "technology": "FastAPI", "status": "approved"},
            {"id": "frontend", "kind": "frontend", "name": "Web", "technology": "React", "status": "approved"},
            {"id": "db", "kind": "database", "name": "BDD", "technology": "PostgreSQL", "status": "approved"},
            {"id": "cache", "kind": "cache", "name": "Cache", "technology": "Redis", "status": "proposed"},
        ]
    )
    await pipeline.asetup_components()
    await wait_until(lambda: pipeline._setup_task is not None and pipeline._setup_task.done())
    ws = workspace_dir("proj-comp")
    assert (ws / "backend" / "pyproject.toml").exists()
    assert (ws / "backend" / "app" / "main.py").exists()
    assert (ws / "frontend" / "package.json").exists()
    compose = (ws / "docker-compose.yml").read_text(encoding="utf-8")
    assert "postgres" in compose
    assert "redis" not in compose  # not approved: not materialized
    statuses = {c.id: c.status for c in pipeline.state.components}
    assert statuses["backend"] == ComponentStatus.CREATED
    assert statuses["cache"] == ComponentStatus.PROPOSED


async def test_setup_requires_an_approved_component():
    import pytest

    pipeline = make_pipeline([])
    with pytest.raises(ValueError):
        await pipeline.asetup_components()


def test_setup_executor_is_idempotent(tmp_path):
    state = ProjectState(id="p", name="todo", goal="g")
    state.components = setup_exec.components_from_payload(
        [{"id": "backend", "kind": "backend", "status": "approved"}]
    )
    setup_exec.execute(state, tmp_path)
    marker = tmp_path / "backend" / "app" / "main.py"
    original = marker.read_text(encoding="utf-8")
    marker.write_text(original + "# edited\n", encoding="utf-8")
    setup_exec.execute(state, tmp_path)  # must not overwrite user/dev edits
    assert marker.read_text(encoding="utf-8").endswith("# edited\n")
