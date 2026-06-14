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


async def wait_until_async(apredicate, timeout=20.0):
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


async def test_budget_endpoint_and_creation(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        # Budget set at creation.
        r = await client.post("/api/projects", json={"goal": "x", "budget_usd": 1.5})
        assert r.status_code == 200 and r.json()["state"]["budget_usd"] == 1.5
        rid = r.json()["id"]
        # Adjust the budget afterwards.
        b = await client.post(f"/api/projects/{rid}/budget", json={"budget_usd": 2.0, "budget_tokens": 5000})
        assert b.status_code == 200
        assert b.json()["budget_usd"] == 2.0 and b.json()["budget_tokens"] == 5000
        assert (await client.post("/api/projects/nope/budget", json={"budget_usd": 1})).status_code == 404


async def test_spec_mode_endpoint(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        rid = (await client.post("/api/projects", json={"goal": "x"})).json()["id"]
        r = await client.post(f"/api/projects/{rid}/spec-mode", json={"mode": "brainstorm"})
        assert r.status_code == 200 and r.json()["spec_mode"] == "brainstorm"
        bad = await client.post(f"/api/projects/{rid}/spec-mode", json={"mode": "bad"})
        assert bad.status_code == 422
        nf = await client.post("/api/projects/nope/spec-mode", json={"mode": "interview"})
        assert nf.status_code == 404


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


async def test_recover_accepts_explicit_states():
    # BUG2: the lifespan offloads list_states() and passes the result in, so
    # recover_projects must register from an explicit states list too.
    state = _persist_interrupted_project("proj-recover")
    server.pipelines.clear()

    ids = server.recover_projects([state])

    assert ids == ["proj-recover"]
    assert "proj-recover" in server.pipelines


async def test_arecover_projects_registers_in_background():
    # BUG2: the non-blocking background recovery still registers persisted projects.
    _persist_interrupted_project("proj-recover")
    server.pipelines.clear()

    await server._arecover_projects()

    assert "proj-recover" in server.pipelines


async def test_sync_does_not_block_the_event_loop(monkeypatch):
    # BUG2 (write path): _sync() fires on every state change during a build. The
    # blocking write (save_state_payload — file I/O + a Windows lock-retry sleep)
    # must run OFF the loop, else uvicorn's accept() is starved and the Vite proxy
    # reports `ETIMEDOUT 127.0.0.1:8100` on /api/*. Simulate a slow/contended write
    # and assert the loop stays responsive while it is in flight.
    import time as _time

    from autospec.models import ProjectState
    from autospec.orchestrator import pipeline as pipeline_mod

    loop = asyncio.get_running_loop()
    write_started = asyncio.Event()
    write_done = asyncio.Event()

    def _slow_write(project_id, payload):
        loop.call_soon_threadsafe(write_started.set)
        _time.sleep(0.5)  # a contended/locked disk write
        loop.call_soon_threadsafe(write_done.set)

    monkeypatch.setattr(pipeline_mod, "save_state_payload", _slow_write)

    pipeline = server.Pipeline(ProjectState(id="proj-sync", name="n", goal="g"), FakeRunner([]))

    t0 = loop.time()
    pipeline._sync()  # returns immediately — the write is offloaded
    assert loop.time() - t0 < 0.1

    # The loop advances here while the worker thread is still mid-write.
    await asyncio.wait_for(write_started.wait(), timeout=1.0)
    assert not write_done.is_set()
    await asyncio.wait_for(write_done.wait(), timeout=2.0)


def test_sync_writes_inline_without_a_running_loop(tmp_path, monkeypatch):
    # The offload only applies when a loop is running. Synchronous callers
    # (recover_projects, scripts, tests) must still see the state on disk at once.
    from autospec import storage
    from autospec.config import settings
    from autospec.models import ProjectState

    monkeypatch.setattr(settings, "workspace_root", tmp_path / "ws")
    pipeline = server.Pipeline(ProjectState(id="proj-inline", name="n", goal="g"), FakeRunner([]))

    pipeline._sync()  # no running loop -> inline write

    assert storage.load_state("proj-inline") is not None


async def test_recover_resets_architect_and_green():
    from autospec import storage
    from autospec.models import (
        Epic,
        PipelinePhase,
        ProjectState,
        StoryStatus,
        UserStory,
    )

    state = ProjectState(
        id="proj-arch",
        name="recover",
        goal="g",
        phase=PipelinePhase.ARCHITECT,
        epics=[Epic(id="EPIC-1", title="e")],
        stories=[
            UserStory(id="US-1", epic_id="EPIC-1", title="green", status=StoryStatus.GREEN),
            UserStory(
                id="US-2", epic_id="EPIC-1", title="wip", status=StoryStatus.IN_PROGRESS
            ),
        ],
    )
    storage.save_state(state)
    server.pipelines.clear()

    server.recover_projects()

    recovered = server.pipelines["proj-arch"].state
    assert recovered.phase == PipelinePhase.STOPPED
    assert recovered.story("US-1").status == StoryStatus.TODO
    assert recovered.story("US-2").status == StoryStatus.TODO


async def test_run_rejected_during_build(green_pytest):
    from autospec.models import PipelinePhase

    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        # Force the project into the BUILD phase: launching the app while dev
        # agents write into the same workspace is rejected.
        server.pipelines[project_id].state.phase = PipelinePhase.BUILD
        resp = await client.post(f"/api/projects/{project_id}/run")
        assert resp.status_code == 409


async def test_chat_records_message_on_done_project(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        resp = await client.post(
            f"/api/projects/{project_id}/chat", json={"message": "Un retour utilisateur"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        # Outside the interview the phase is unchanged (still done).
        assert body["phase"] == "done"

        # The message shows up in the project's chat history.
        state = (await client.get(f"/api/projects/{project_id}")).json()
        assert any(
            m["role"] == "user" and m["content"] == "Un retour utilisateur"
            for m in state["chat"]
        )
        # On a done project, the message is queued as feedback for the next cycle.
        assert "Un retour utilisateur" in state["feedback"]


async def test_chat_unknown_project_404(green_pytest):
    async with make_client([]) as client:
        resp = await client.post(
            "/api/projects/inconnu/chat", json={"message": "hello"}
        )
        assert resp.status_code == 404


async def test_pause_and_resume_toggle_flag(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)
        pipeline = server.pipelines[project_id]

        assert pipeline.state.paused is False

        resp = await client.post(f"/api/projects/{project_id}/pause")
        assert resp.status_code == 200
        assert pipeline.state.paused is True
        # The flag is reflected in the API view of the project.
        assert (await client.get(f"/api/projects/{project_id}")).json()["paused"] is True

        resp = await client.post(f"/api/projects/{project_id}/resume")
        assert resp.status_code == 200
        assert pipeline.state.paused is False
        assert (await client.get(f"/api/projects/{project_id}")).json()["paused"] is False


async def test_pause_resume_unknown_project_404(green_pytest):
    async with make_client([]) as client:
        assert (await client.post("/api/projects/inconnu/pause")).status_code == 404
        assert (await client.post("/api/projects/inconnu/resume")).status_code == 404


async def test_story_diff_available_on_done_project(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        # The workspace is committed per finished story, so a diff is recoverable.
        resp = await client.get(f"/api/projects/{project_id}/stories/US-1/diff")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert body["diff"]  # non-empty git show output

        # An unknown story is a 404.
        bad = await client.get(f"/api/projects/{project_id}/stories/US-404/diff")
        assert bad.status_code == 404


async def test_rebuild_story_on_done_project(green_pytest):
    # A rebuild re-runs QA test design + the dev agent, so it needs 2 more replies.
    async with make_client(
        [PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN, QA_TRIVIAL, DEV_GREEN]
    ) as client:
        project_id = await _acreate_done_project(client)

        resp = await client.post(
            f"/api/projects/{project_id}/stories/US-1/rebuild"
        )
        assert resp.status_code == 200

        # The rebuild runs in a background task; the project returns to done.
        async def adone():
            r = await client.get(f"/api/projects/{project_id}")
            return r.json()["phase"] == "done"

        await wait_until_async(adone, timeout=10.0)
        state = (await client.get(f"/api/projects/{project_id}")).json()
        assert state["stories"][0]["status"] == "done"

        # An unknown story is a 404.
        bad = await client.post(
            f"/api/projects/{project_id}/stories/US-404/rebuild"
        )
        assert bad.status_code == 404


async def test_rebuild_in_progress_story_409(green_pytest):
    from autospec.models import StoryStatus

    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        # A story currently being developed cannot be rebuilt.
        server.pipelines[project_id].state.story("US-1").status = StoryStatus.IN_PROGRESS
        resp = await client.post(
            f"/api/projects/{project_id}/stories/US-1/rebuild"
        )
        assert resp.status_code == 409


async def test_read_file_truncates_large_content(green_pytest):
    from autospec.storage import workspace_dir

    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        # Write a file larger than the 200_000-char cap into the workspace.
        big = "a" * 250_000
        (workspace_dir(project_id) / "big.txt").write_text(big, encoding="utf-8")

        resp = await client.get(
            f"/api/projects/{project_id}/files/raw", params={"path": "big.txt"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["truncated"] is True
        assert len(body["content"]) <= 200_000


def _persist_phase_project(phase, project_id: str):
    """Persist a project caught mid-run in the given (interrupted) phase."""
    from autospec import storage
    from autospec.models import Epic, ProjectState, StoryStatus, UserStory

    state = ProjectState(
        id=project_id,
        name="recover",
        goal="g",
        phase=phase,
        epics=[Epic(id="EPIC-1", title="e")],
        stories=[
            UserStory(
                id="US-1",
                epic_id="EPIC-1",
                title="s",
                status=StoryStatus.TODO,
            )
        ],
        running=True,
    )
    storage.save_state(state)
    return state


async def test_chat_empty_message_422(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        # A blank message would act as the internal stop sentinel during the
        # PM interview and waste an agent turn: rejected upfront.
        resp = await client.post(f"/api/projects/{project_id}/chat", json={"message": "   "})
        assert resp.status_code == 422


async def test_add_or_edit_story_blank_title_422(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        resp = await client.post(
            f"/api/projects/{project_id}/stories",
            json={"epic_id": "EPIC-1", "title": "   "},
        )
        assert resp.status_code == 422

        resp = await client.patch(
            f"/api/projects/{project_id}/stories/US-1", json={"title": ""}
        )
        assert resp.status_code == 422


async def test_archive_active_project_409(green_pytest):
    from autospec.models import PipelinePhase

    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        # Archiving while agents are working would hide a project that keeps
        # spending budget in the background.
        server.pipelines[project_id].state.phase = PipelinePhase.BUILD
        assert (await client.post(f"/api/projects/{project_id}/archive")).status_code == 409

        server.pipelines[project_id].state.phase = PipelinePhase.DONE
        assert (await client.post(f"/api/projects/{project_id}/archive")).status_code == 200


async def test_delete_locked_workspace_keeps_project_controllable(green_pytest, monkeypatch):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = await _acreate_done_project(client)

        locked = {"value": True}
        real_delete = server._force_delete_workspace

        def _maybe_locked(pid):
            if locked["value"]:
                raise OSError("workspace verrouillé")
            return real_delete(pid)

        monkeypatch.setattr(server, "_force_delete_workspace", _maybe_locked)
        resp = await client.delete(f"/api/projects/{project_id}")
        assert resp.status_code == 409
        # The pipeline is re-registered: the project is still listed and
        # controllable, and the delete can be retried once unlocked.
        assert project_id in server.pipelines
        assert (await client.get(f"/api/projects/{project_id}")).status_code == 200

        locked["value"] = False
        assert (await client.delete(f"/api/projects/{project_id}")).status_code == 200
        assert project_id not in server.pipelines


async def test_recover_stops_interrupted_spec_analyze_plan_phases():
    from autospec.models import PipelinePhase

    interrupted = {
        PipelinePhase.SPEC: "proj-spec",
        PipelinePhase.ANALYZE: "proj-analyze",
        PipelinePhase.PLAN: "proj-plan",
    }
    for phase, pid in interrupted.items():
        _persist_phase_project(phase, pid)

    server.pipelines.clear()
    server.recover_projects()

    for pid in interrupted.values():
        assert pid in server.pipelines
        recovered = server.pipelines[pid].state
        assert recovered.phase == PipelinePhase.STOPPED
        assert recovered.running is False
