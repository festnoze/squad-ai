"""Tests of the delivery features (I2): tech-writer README + zip/git export."""

import io
import json
import zipfile

import httpx
import pytest

from autospec.agents.runner import FakeRunner
from autospec.api import server
from autospec.models import PipelinePhase, ProjectState
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
TECH_WRITER = json.dumps(
    {"message": "Doc prête.", "readme": "# Mon produit\n\nLancement : `uv run python main.py`\n"},
    ensure_ascii=False,
)


def make_client(replies: list[str]) -> httpx.AsyncClient:
    server.pipelines.clear()
    server.set_runner(FakeRunner(replies))
    transport = httpx.ASGITransport(app=server.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def wait_until_async(apredicate, timeout=20.0):
    import asyncio

    deadline = asyncio.get_event_loop().time() + timeout
    while not await apredicate():
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError("condition not met in time")
        await asyncio.sleep(0.02)


async def test_tech_writer_writes_readme():
    state = ProjectState(
        id="proj-doc", name="todo", goal="g", phase=PipelinePhase.DONE, brief="# Brief"
    )
    pipeline = Pipeline(state, FakeRunner([TECH_WRITER]))
    await pipeline.adocument()
    await wait_until(lambda: pipeline._doc_task is not None and pipeline._doc_task.done())
    readme = workspace_dir("proj-doc") / "README.md"
    assert "Mon produit" in readme.read_text(encoding="utf-8")
    assert any("📘" in m.content for m in state.chat)


async def test_tech_writer_rejected_while_building():
    state = ProjectState(id="proj-doc2", name="todo", goal="g", phase=PipelinePhase.BUILD)
    pipeline = Pipeline(state, FakeRunner([]))
    with pytest.raises(ValueError):
        await pipeline.adocument()


async def test_document_endpoint_and_export_zip(green_pytest):
    replies = [PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN, TECH_WRITER]
    async with make_client(replies) as client:
        project_id = (
            await client.post("/api/projects", json={"goal": "Une todo-list", "name": "todo"})
        ).json()["id"]

        async def adone():
            r = await client.get(f"/api/projects/{project_id}")
            return r.json()["phase"] == "done"

        await wait_until_async(adone)

        # Tech-writer triggered on demand.
        assert (await client.post(f"/api/projects/{project_id}/document")).status_code == 200

        async def adocumented():
            return (workspace_dir(project_id) / "README.md").exists()

        await wait_until_async(adocumented)

        # Zip export: contains the workspace code, never Autospec's state file.
        resp = await client.get(f"/api/projects/{project_id}/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        archive = zipfile.ZipFile(io.BytesIO(resp.content))
        names = archive.namelist()
        assert "pyproject.toml" in names
        assert "README.md" in names
        assert not any("autospec-state" in n for n in names)
        assert not any(n.startswith(".git/") for n in names)


async def test_git_export_commits_workspace(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = (
            await client.post("/api/projects", json={"goal": "Une todo-list"})
        ).json()["id"]

        async def adone():
            r = await client.get(f"/api/projects/{project_id}")
            return r.json()["phase"] == "done"

        await wait_until_async(adone)
        resp = await client.post(f"/api/projects/{project_id}/git-export")
        assert resp.status_code == 200
        assert len(resp.json()["commit"]) == 40  # full git sha


async def test_export_unknown_project_404():
    async with make_client([]) as client:
        assert (await client.get("/api/projects/nope/export")).status_code == 404
        assert (await client.post("/api/projects/nope/document")).status_code == 404
