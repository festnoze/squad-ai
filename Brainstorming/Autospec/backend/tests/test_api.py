import asyncio
import json

import httpx
import pytest

from autospec.agents.runner import FakeRunner
from autospec.api import server

PM_QUESTION = json.dumps({"type": "question", "message": "CLI ou web ?"})
PM_BRIEF = json.dumps({"type": "brief", "message": "OK", "brief": "# Brief"})
PO_PLAN = json.dumps(
    {"epics": [{"id": "EPIC-1", "title": "E", "stories": [
        {"id": "US-1", "title": "S", "description": "d", "acceptance_criteria": ["c"],
         "gherkin": "Feature: F\n  Scenario: s\n    Given a\n    When b\n    Then c", "depends_on": []},
    ]}]}
)
QA_TRIVIAL = json.dumps({"message": "Story triviale, le Gherkin suffit.", "tests": []})
DEV_GREEN = json.dumps({"status": "green", "summary": "ok", "files": []})


def make_client(replies: list[str]) -> httpx.AsyncClient:
    server.pipelines.clear()
    server.set_runner(FakeRunner(replies))
    transport = httpx.ASGITransport(app=server.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def wait_until_async(apredicate, timeout=5.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while not await apredicate():
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError("condition not met in time")
        await asyncio.sleep(0.02)


async def test_create_and_complete_project(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        resp = await client.post("/api/projects", json={"goal": "Une todo-list", "name": "todo"})
        assert resp.status_code == 200
        project_id = resp.json()["id"]

        async def adone():
            r = await client.get(f"/api/projects/{project_id}")
            return r.json()["phase"] == "done"

        await wait_until_async(adone)
        state = (await client.get(f"/api/projects/{project_id}")).json()
        assert state["brief"] == "# Brief"
        assert [s["status"] for s in state["stories"]] == ["done"]
        assert (await client.get("/api/projects")).json()[0]["id"] == project_id


async def test_stop_during_interview(green_pytest):
    async with make_client([PM_QUESTION]) as client:
        resp = await client.post("/api/projects", json={"goal": "Une todo-list"})
        project_id = resp.json()["id"]

        async def aasked():
            r = await client.get(f"/api/projects/{project_id}")
            return any(m["role"] == "pm" for m in r.json()["chat"])

        await wait_until_async(aasked)
        await client.post(f"/api/projects/{project_id}/stop")

        async def astopped():
            r = await client.get(f"/api/projects/{project_id}")
            return r.json()["phase"] == "stopped"

        await wait_until_async(astopped)


async def test_delete_project(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = (
            await client.post("/api/projects", json={"goal": "Une todo-list"})
        ).json()["id"]

        async def adone():
            r = await client.get(f"/api/projects/{project_id}")
            return r.json()["phase"] == "done"

        await wait_until_async(adone)

        resp = await client.delete(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        assert project_id not in server.pipelines
        assert (await client.get(f"/api/projects/{project_id}")).status_code == 404
        assert (await client.get("/api/projects")).json() == []
        # Deleting again is a 404.
        assert (await client.delete(f"/api/projects/{project_id}")).status_code == 404


async def test_create_project_requires_goal(green_pytest):
    async with make_client([]) as client:
        resp = await client.post("/api/projects", json={"goal": "   "})
        assert resp.status_code == 422


async def test_unknown_project_404(green_pytest):
    async with make_client([]) as client:
        assert (await client.get("/api/projects/nope")).status_code == 404
        assert (await client.post("/api/projects/nope/run")).status_code == 404


async def test_archive_and_unarchive_project(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = (
            await client.post("/api/projects", json={"goal": "Une todo-list", "name": "todo"})
        ).json()["id"]

        async def adone():
            r = await client.get(f"/api/projects/{project_id}")
            return r.json()["phase"] == "done"

        await wait_until_async(adone)

        resp = await client.post(f"/api/projects/{project_id}/archive")
        assert resp.status_code == 200
        assert (await client.get(f"/api/projects/{project_id}")).json()["archived"] is True

        resp = await client.post(f"/api/projects/{project_id}/unarchive")
        assert resp.status_code == 200
        assert (await client.get(f"/api/projects/{project_id}")).json()["archived"] is False


async def test_archive_unknown_project_404(green_pytest):
    async with make_client([]) as client:
        assert (await client.post("/api/projects/inconnu/archive")).status_code == 404


async def _acreate_done_project(client) -> str:
    """Create a project and wait for it to reach the 'done' phase."""
    project_id = (
        await client.post("/api/projects", json={"goal": "Une todo-list", "name": "todo"})
    ).json()["id"]

    async def adone():
        r = await client.get(f"/api/projects/{project_id}")
        return r.json()["phase"] == "done"

    await wait_until_async(adone)
    return project_id


async def test_edit_story(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        resp = await client.patch(
            f"/api/projects/{project_id}/stories/US-1",
            json={
                "title": "Titre édité",
                "acceptance_criteria": [{"text": "premier"}, {"text": "second"}],
            },
        )
        assert resp.status_code == 200
        story = resp.json()["state"]["stories"][0]
        assert story["title"] == "Titre édité"
        assert [c["text"] for c in story["acceptance_criteria"]] == ["premier", "second"]
        assert [c["id"] for c in story["acceptance_criteria"]] == ["AC-1", "AC-2"]


async def test_add_story(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        resp = await client.post(
            f"/api/projects/{project_id}/stories",
            json={
                "epic_id": "EPIC-1",
                "title": "Nouvelle story",
                "acceptance_criteria": ["doit marcher"],
                "priority": 2,
            },
        )
        assert resp.status_code == 200
        stories = resp.json()["state"]["stories"]
        added = next(s for s in stories if s["title"] == "Nouvelle story")
        assert added["epic_id"] == "EPIC-1"
        assert added["priority"] == 2
        assert added["acceptance_criteria"][0]["text"] == "doit marcher"

        # Unknown epic -> 404.
        bad = await client.post(
            f"/api/projects/{project_id}/stories",
            json={"epic_id": "EPIC-404", "title": "x"},
        )
        assert bad.status_code == 404


async def test_delete_story(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        resp = await client.delete(f"/api/projects/{project_id}/stories/US-1")
        assert resp.status_code == 200
        state = (await client.get(f"/api/projects/{project_id}")).json()
        assert all(s["id"] != "US-1" for s in state["stories"])

        # Deleting an unknown story -> 404.
        assert (
            await client.delete(f"/api/projects/{project_id}/stories/US-404")
        ).status_code == 404


async def test_reorder_stories(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        resp = await client.post(
            f"/api/projects/{project_id}/stories/reorder",
            json={"priorities": [{"id": "US-1", "priority": 5}]},
        )
        assert resp.status_code == 200
        story = next(s for s in resp.json()["state"]["stories"] if s["id"] == "US-1")
        assert story["priority"] == 5


async def test_edit_unknown_story_and_project_404(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        assert (
            await client.patch(
                f"/api/projects/{project_id}/stories/US-404", json={"title": "x"}
            )
        ).status_code == 404
        assert (
            await client.patch("/api/projects/nope/stories/US-1", json={"title": "x"})
        ).status_code == 404


async def test_edit_in_progress_story_409(green_pytest):
    from autospec.models import StoryStatus

    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        # Force the story into the in-progress state and try to edit it.
        server.pipelines[project_id].state.story("US-1").status = StoryStatus.IN_PROGRESS
        resp = await client.patch(
            f"/api/projects/{project_id}/stories/US-1", json={"title": "x"}
        )
        assert resp.status_code == 409


async def test_stop_app_no_process_is_safe(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        # No app was launched: stopping is a safe no-op, not an error.
        resp = await client.post(f"/api/projects/{project_id}/stop-app")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


async def test_stop_app_unknown_project_404(green_pytest):
    async with make_client([]) as client:
        assert (await client.post("/api/projects/inconnu/stop-app")).status_code == 404


async def test_list_workspace_files(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        resp = await client.get(f"/api/projects/{project_id}/files")
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert "main.py" in files
        assert "pyproject.toml" in files
        assert all("autospec-state.json" not in f for f in files)


async def test_read_workspace_file(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        resp = await client.get(
            f"/api/projects/{project_id}/files/raw", params={"path": "main.py"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "def main" in body["content"]
        assert body["truncated"] is False


async def test_read_file_traversal_blocked(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        resp = await client.get(
            f"/api/projects/{project_id}/files/raw", params={"path": "../../secret"}
        )
        assert resp.status_code == 400


async def test_read_unknown_file_404(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        resp = await client.get(
            f"/api/projects/{project_id}/files/raw", params={"path": "nope.py"}
        )
        assert resp.status_code == 404


async def test_files_unknown_project_404(green_pytest):
    async with make_client([]) as client:
        assert (await client.get("/api/projects/inconnu/files")).status_code == 404


def _persist_interrupted_project(project_id: str = "proj-recover") -> "ProjectState":
    """Persist a project caught mid-build (story in progress, app running)."""
    from autospec import storage
    from autospec.models import (
        Epic,
        PipelinePhase,
        ProjectState,
        StoryStatus,
        UserStory,
    )

    state = ProjectState(
        id=project_id,
        name="recover",
        goal="g",
        phase=PipelinePhase.BUILD,
        epics=[Epic(id="EPIC-1", title="e")],
        stories=[
            UserStory(
                id="US-1",
                epic_id="EPIC-1",
                title="s",
                status=StoryStatus.IN_PROGRESS,
            )
        ],
        running=True,
        paused=True,
    )
    storage.save_state(state)
    return state


async def test_recover_registers_persisted_projects():
    from autospec.models import PipelinePhase, StoryStatus

    _persist_interrupted_project("proj-recover")
    server.pipelines.clear()

    ids = server.recover_projects()

    assert "proj-recover" in ids
    assert "proj-recover" in server.pipelines
    state = server.pipelines["proj-recover"].state
    assert state.phase == PipelinePhase.STOPPED
    assert state.story("US-1").status == StoryStatus.TODO
    assert state.running is False
    assert state.paused is False


async def test_recovered_project_is_controllable():
    _persist_interrupted_project("proj-recover")
    server.pipelines.clear()
    server.recover_projects()

    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Previously these actions would 404 because the pipeline was only on disk.
        assert (await client.get("/api/projects/proj-recover")).status_code == 200
        resp = await client.post(
            "/api/projects/proj-recover/stories/US-1/force-done"
        )
        assert resp.status_code == 200


async def test_recover_skips_already_live():
    state = _persist_interrupted_project("proj-recover")
    server.pipelines.clear()
    # Make the project already live in memory.
    server.pipelines["proj-recover"] = server.Pipeline(state, server._runner)

    ids = server.recover_projects()

    assert "proj-recover" not in ids
    assert len(server.pipelines) == 1
