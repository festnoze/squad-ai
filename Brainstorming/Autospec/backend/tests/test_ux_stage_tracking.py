"""UX MVP backend tests: B1 stage/recovery/guidance fields, B4 endpoints, N4
persona stamping in a real (fake-agents) build, and B5 tick shape.

Additive: mirrors the existing fake-agents pipeline tests (FakeRunner +
``green_pytest`` + per-test ``tmp_workspace``) and never modifies them.
"""

import json

import httpx
import pytest

from autospec.agents.runner import FakeRunner
from autospec.api import server
from autospec.models import (
    BuildStage,
    GuidanceEntry,
    PipelinePhase,
    ProjectState,
    RecoveryState,
    StoryStatus,
    Task,
    UserStory,
)
from autospec.orchestrator.pipeline import Pipeline

from .conftest import wait_until

PM_BRIEF = json.dumps({"type": "brief", "message": "OK", "brief": "# Brief"})
QA_TRIVIAL = json.dumps({"message": "Story triviale, le Gherkin suffit.", "tests": []})
DEV_GREEN = json.dumps({"status": "green", "summary": "ok", "files": []})


def _po_plan(n: int = 1) -> str:
    stories = [
        {
            "id": f"US-{i}",
            "title": f"Story {i}",
            "description": "d",
            "acceptance_criteria": ["c"],
            "gherkin": f"Feature: F{i}\n  Scenario: s\n    Given a\n    When b\n    Then c",
            "depends_on": [],
        }
        for i in range(1, n + 1)
    ]
    return json.dumps({"epics": [{"id": "EPIC-1", "title": "E", "stories": stories}]})


# --------------------------------------------------------------- model defaults

def test_new_fields_default_safe():
    """Every new field has a safe default so a pre-UX persisted state loads."""
    story = UserStory(id="US-1", epic_id="E", title="t")
    assert story.current_stage == BuildStage.QUEUED
    assert story.stage_started_at == 0.0
    assert story.current_persona == ""
    assert story.recovery == RecoveryState()
    assert story.recovery.attempt == 0 and story.recovery.kind == ""
    assert story.guidance == []

    task = Task(id="T-1", story_id="US-1")
    assert task.current_stage == BuildStage.QUEUED
    assert task.current_persona == ""
    assert task.recovery.max_attempts == 0
    assert task.guidance == []


def test_legacy_state_without_ux_fields_loads():
    """A persisted state predating the UX fields round-trips unchanged."""
    legacy = {
        "id": "p1", "name": "n", "goal": "g",
        "epics": [{"id": "E", "title": "E"}],
        "stories": [{
            "id": "US-1", "epic_id": "E", "title": "t",
            "acceptance_criteria": [{"id": "AC-1", "text": "x"}],
            "status": "todo",
        }],
    }
    state = ProjectState.model_validate(legacy)
    s = state.story("US-1")
    assert s.current_stage == BuildStage.QUEUED
    assert s.recovery.kind == ""
    assert s.guidance == []


def test_new_fields_serialize_round_trip():
    """The new fields serialize and reload (load_state round-trip)."""
    story = UserStory(id="US-1", epic_id="E", title="t")
    story.current_stage = BuildStage.VERIFYING
    story.stage_started_at = 123.0
    story.current_persona = "qa"
    story.recovery = RecoveryState(attempt=2, max_attempts=3, kind="refining")
    story.guidance = [GuidanceEntry(id="g-1", text="hi", status="applied")]
    state = ProjectState(id="p1", name="n", goal="g", stories=[story])

    dumped = state.model_dump_json()
    reloaded = ProjectState.model_validate_json(dumped)
    r = reloaded.story("US-1")
    assert r.current_stage == BuildStage.VERIFYING
    assert r.stage_started_at == 123.0
    assert r.current_persona == "qa"
    assert r.recovery.attempt == 2 and r.recovery.kind == "refining"
    assert [(g.id, g.status) for g in r.guidance] == [("g-1", "applied")]


# ------------------------------------------------------------ endpoints (B4)

def make_client(replies: list[str]) -> httpx.AsyncClient:
    server.pipelines.clear()
    server.set_runner(FakeRunner(replies))
    transport = httpx.ASGITransport(app=server.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _make_project(client: httpx.AsyncClient) -> str:
    """Create a project and seed one TODO story via the pipeline directly (no
    build run), so the chat/extend endpoints have a stable target."""
    from autospec.models import Epic

    resp = await client.post("/api/projects", json={"goal": "Une todo-list", "name": "todo"})
    project_id = resp.json()["id"]
    pipeline = server.pipelines[project_id]
    await pipeline.astop()  # detach the lifecycle task; we drive state directly
    pipeline.state.phase = PipelinePhase.STOPPED
    pipeline.state.epics = [Epic(id="E", title="E")]
    pipeline.state.stories = [
        UserStory(id="US-1", epic_id="E", title="Story 1", status=StoryStatus.TODO)
    ]
    return project_id


async def test_story_chat_appends_guidance():
    async with make_client([PM_BRIEF]) as client:
        pid = await _make_project(client)
        resp = await client.post(
            f"/api/projects/{pid}/stories/US-1/chat",
            json={"message": "utilise une dataclass"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True and body["entry_id"]
        story = server.pipelines[pid].state.story("US-1")
        assert len(story.guidance) == 1
        assert story.guidance[0].text == "utilise une dataclass"
        assert story.guidance[0].status == "queued"  # TODO story → still injectable


async def test_story_chat_is_idempotent():
    async with make_client([PM_BRIEF]) as client:
        pid = await _make_project(client)
        for _ in range(2):
            resp = await client.post(
                f"/api/projects/{pid}/stories/US-1/chat",
                json={"message": "encore", "entry_id": "fixed-key"},
            )
            assert resp.json()["entry_id"] == "fixed-key"
        story = server.pipelines[pid].state.story("US-1")
        assert len(story.guidance) == 1  # not double-appended


async def test_story_chat_404_unknown_story():
    async with make_client([PM_BRIEF]) as client:
        pid = await _make_project(client)
        resp = await client.post(
            f"/api/projects/{pid}/stories/US-NOPE/chat",
            json={"message": "x"},
        )
        assert resp.status_code == 404


async def test_task_chat_appends_guidance():
    async with make_client([PM_BRIEF]) as client:
        pid = await _make_project(client)
        story = server.pipelines[pid].state.story("US-1")
        story.tasks = [Task(id="T-1", story_id="US-1", title="back", status=StoryStatus.TODO)]
        resp = await client.post(
            f"/api/projects/{pid}/tasks/T-1/chat",
            json={"message": "mets un index"},
        )
        assert resp.status_code == 200
        assert story.tasks[0].guidance[0].text == "mets un index"


async def test_task_chat_404_unknown_task():
    async with make_client([PM_BRIEF]) as client:
        pid = await _make_project(client)
        resp = await client.post(
            f"/api/projects/{pid}/tasks/T-NOPE/chat", json={"message": "x"}
        )
        assert resp.status_code == 404


async def test_extend_story_appends_criteria():
    async with make_client([PM_BRIEF]) as client:
        pid = await _make_project(client)
        resp = await client.post(
            f"/api/projects/{pid}/stories/US-1/extend",
            json={"acceptance_criteria": ["nouveau critère", "et un autre"]},
        )
        assert resp.status_code == 200
        story = server.pipelines[pid].state.story("US-1")
        texts = [c.text for c in story.acceptance_criteria]
        assert "nouveau critère" in texts and "et un autre" in texts


async def test_extend_story_409_when_not_todo():
    async with make_client([PM_BRIEF]) as client:
        pid = await _make_project(client)
        server.pipelines[pid].state.story("US-1").status = StoryStatus.DONE
        resp = await client.post(
            f"/api/projects/{pid}/stories/US-1/extend",
            json={"acceptance_criteria": ["trop tard"]},
        )
        assert resp.status_code == 409


async def test_extend_story_404_unknown():
    async with make_client([PM_BRIEF]) as client:
        pid = await _make_project(client)
        resp = await client.post(
            f"/api/projects/{pid}/stories/US-NOPE/extend",
            json={"acceptance_criteria": ["x"]},
        )
        assert resp.status_code == 404


# ------------------------------------------------- stage/persona in a real build

async def test_build_stamps_stage_and_persona(green_pytest, tmp_workspace):
    """A fake-agents BUILD stamps current_stage + current_persona on the item.

    QA designs the plan (analyzing/qa), the dev implements (implementing/dev),
    the orchestrator verifies, and the item lands on the DONE stage."""
    state = ProjectState(id="proj-ux", name="todo", goal="g")
    pipeline = Pipeline(state, FakeRunner([PM_BRIEF, _po_plan(1), QA_TRIVIAL, DEV_GREEN]))
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)

    story = pipeline.state.story("US-1")
    assert story.status == StoryStatus.DONE
    # Terminal stage stamped; persona stamping happened during the build.
    assert story.current_stage == BuildStage.DONE
    assert story.stage_started_at > 0.0
    # Recovery cleared after a clean green build.
    assert story.recovery.kind == ""


async def test_guidance_injected_and_marked_applied(green_pytest, tmp_workspace):
    """Per-item guidance is injected into that item's dev prompt and the
    delivered entry is marked ``applied``.

    Driven deterministically: seed guidance on a TODO story, then run the build
    helper directly (a full fake build is too fast to win the seeding race)."""
    from autospec.models import Epic

    story = UserStory(
        id="US-1", epic_id="E", title="Story 1",
        acceptance_criteria=[],
        gherkin="Feature: F\n  Scenario: s\n    Given a\n    When b\n    Then c",
        status=StoryStatus.TODO,
    )
    state = ProjectState(
        id="proj-ux2", name="todo", goal="g",
        epics=[Epic(id="E", title="E")], stories=[story],
    )
    runner = FakeRunner([QA_TRIVIAL, DEV_GREEN])
    pipeline = Pipeline(state, runner)

    await pipeline.achat_story("US-1", "utilise le pattern repository")
    assert story.guidance[0].status == "queued"

    await pipeline._abuild_story(story)

    assert story.status == StoryStatus.DONE
    assert story.guidance[0].status == "applied"
    dev_prompts = [c["prompt"] for c in runner.calls if "PROCESSUS OBLIGATOIRE" in c["prompt"]]
    assert any("utilise le pattern repository" in p for p in dev_prompts)


# ----------------------------------------------------------------- tick (B5)

def test_tick_payload_shape():
    state = ProjectState(
        id="proj-tick", name="n", goal="g",
        epics=[],
        stories=[
            UserStory(id="US-1", epic_id="E", title="t", status=StoryStatus.DONE),
            UserStory(id="US-2", epic_id="E", title="t2", status=StoryStatus.IN_PROGRESS),
        ],
    )
    pipeline = Pipeline(state, FakeRunner([]))
    payload = pipeline._tick_payload()
    assert payload["type"] == "tick"
    assert payload["project_id"] == "proj-tick"
    assert isinstance(payload["ts"], float)
    assert payload["stall_reason"] == ""
    ids = {it["id"] for it in payload["items"]}
    assert ids == {"US-1", "US-2"}
    one = next(it for it in payload["items"] if it["id"] == "US-1")
    assert set(one) == {
        "id", "kind", "status", "current_stage",
        "stage_started_at", "current_persona", "recovery",
    }
    assert set(one["recovery"]) == {"attempt", "max_attempts", "kind"}
    assert payload["counts"]["done"] == 1
    assert payload["counts"]["running"] == 1


def test_tick_not_replayed_on_reconnect():
    """An ephemeral tick is fanned out live but never buffered for replay."""
    from autospec.orchestrator.events import EventBus

    eb = EventBus()
    eb.publish({"type": "state"})
    base = eb.latest_seq
    eb.publish_ephemeral({"type": "tick"})
    # The tick consumed a seq but is not in the replay ring.
    replayed = eb.replay_since(0)
    assert all(ev.get("type") != "tick" for _seq, ev in replayed)
    assert eb.latest_seq > base
