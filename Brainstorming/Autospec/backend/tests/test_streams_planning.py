"""Lot 2 (ST-4 + ST-5): architect stream selection + multi-stream PO plan.

All new behaviour is gated behind ``settings.streams_enabled`` (pinned OFF by
the autouse conftest fixture). These tests flip it ON via monkeypatch to exercise
the stream-aware path, and assert the flag-OFF path is byte-identical to today.
"""

import json

import pytest

from autospec.agents import prompts
from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import (
    BackendLanguage,
    PipelinePhase,
    ProjectState,
    StreamKind,
    StoryStatus,
)
from autospec.orchestrator import streams as work_streams
from autospec.orchestrator.pipeline import Pipeline

from .conftest import wait_until
from .test_pipeline import PM_BRIEF, QA_PLAN, DEV_GREEN, make_pipeline
from autospec.agents.runner import FakeRunner


# ----------------------------------------------------------- ST-4 select_streams

def _streams_reply() -> str:
    return json.dumps(
        {
            "streams": [
                {"id": "backend", "kind": "backend", "language": "python", "file_root": ""},
                {"id": "frontend", "kind": "frontend", "language": "react", "file_root": "frontend"},
            ],
            "rationale": "API + UI web.",
        }
    )


async def test_select_streams_is_a_noop_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", False)
    pipeline, _ = make_pipeline([_streams_reply()])
    await pipeline._aselect_streams()
    assert pipeline.state.streams == []  # implicit backend, unchanged behaviour


async def test_select_streams_populates_streams_with_primary_backend(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    pipeline, _ = make_pipeline([_streams_reply()])
    pipeline.state.backend_language = BackendLanguage.GO
    await pipeline._aselect_streams()

    streams = pipeline.state.streams
    ids = [s.id for s in streams]
    assert "backend" in ids and "frontend" in ids
    # Exactly one primary, and it is the backend carrying the project language.
    primaries = [s for s in streams if s.primary]
    assert len(primaries) == 1
    assert primaries[0].id == "backend" and primaries[0].kind == StreamKind.BACKEND
    assert primaries[0].language == "go"  # forced to the backend language
    assert pipeline.state.primary_stream_id == "backend"
    assert any("Streams retenus" in m.content for m in pipeline.state.chat)


async def test_select_streams_forces_backend_even_if_agent_omits_it(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    reply = json.dumps(
        {"streams": [{"id": "frontend", "kind": "frontend", "language": "react"}], "rationale": "UI"}
    )
    pipeline, _ = make_pipeline([reply])
    await pipeline._aselect_streams()
    ids = [s.id for s in pipeline.state.streams]
    assert ids[0] == "backend"  # always prepended, primary
    assert pipeline.state.streams[0].primary


async def test_select_streams_dedups_ids_and_demotes_agent_backend(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    reply = json.dumps(
        {
            "streams": [
                {"id": "backend", "kind": "backend", "language": "java"},  # agent backend dropped
                {"id": "frontend", "kind": "frontend", "language": "react"},
                {"id": "frontend", "kind": "frontend", "language": "vue"},  # dup id
            ],
            "rationale": "x",
        }
    )
    pipeline, _ = make_pipeline([reply])
    await pipeline._aselect_streams()
    ids = [s.id for s in pipeline.state.streams]
    assert ids == ["backend", "frontend"]  # our backend + a single frontend
    # The lone primary backend carries the project language, not the agent's "java".
    assert pipeline.state.streams[0].language == "python"


def test_select_streams_prompt_only_present_when_relevant():
    st = ProjectState(id="p", name="p", goal="g")
    p = prompts.select_streams(st)
    assert "STREAMS parallélisables" in p
    assert "backend" in p and "frontend" in p


# ----------------------------------------------------- ST-4 scripted recognition

async def test_scripted_runner_recognizes_select_streams():
    st = ProjectState(id="p", name="p", goal="g")
    runner = ScriptedRunner()
    res = await runner.arun(prompts.select_streams(st), system_prompt="")
    data = json.loads(res.text)
    kinds = {s["kind"] for s in data["streams"]}
    assert "backend" in kinds and "frontend" in kinds


# ------------------------------------------------------------ ST-5 po_plan parse

def _make_plan_pipeline(po_reply: str):
    """A pipeline whose _aplan_phase will consume one PO reply (refine disabled)."""
    state = ProjectState(id="proj-test", name="todo", goal="Une todo-list")
    return Pipeline(state, FakeRunner([po_reply]))


def _stream_plan_reply() -> str:
    return json.dumps(
        {
            "epics": [
                {
                    "id": "EPIC-1",
                    "title": "Cœur",
                    "description": "",
                    "stories": [
                        {
                            "id": "US-1",
                            "title": "Addition (API + UI)",
                            "description": "...",
                            "acceptance_criteria": ["somme ok"],
                            "gherkin": "Feature: A",
                            "depends_on": [],
                            "stream": "",
                            "tasks": [
                                {
                                    "id": "T-1",
                                    "stream": "backend",
                                    "title": "API addition",
                                    "description": "endpoint",
                                    "acceptance_criteria": ["GET /add"],
                                    "gherkin": "Feature: API",
                                    "depends_on": [],
                                },
                                {
                                    "id": "T-2",
                                    "stream": "frontend",
                                    "title": "Écran addition",
                                    "description": "form",
                                    "acceptance_criteria": ["affiche somme"],
                                    "gherkin": "Feature: UI",
                                    "depends_on": ["T-1"],
                                },
                            ],
                        },
                        {
                            "id": "US-2",
                            "title": "Soustraction",
                            "description": "...",
                            "acceptance_criteria": ["diff ok"],
                            "gherkin": "Feature: S",
                            "depends_on": ["US-1"],
                            "stream": "backend",
                            "tasks": [],
                        },
                    ],
                }
            ]
        }
    )


async def test_plan_parsing_unchanged_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", False)
    pipeline = _make_plan_pipeline(_stream_plan_reply())
    await pipeline._aplan_phase()
    # Even though the reply carries tasks/stream, the flag-off parse ignores them.
    for s in pipeline.state.stories:
        assert s.stream == ""
        assert s.tasks == []


async def test_plan_builds_streams_tasks_and_cross_task_deps(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    pipeline = _make_plan_pipeline(_stream_plan_reply())
    await pipeline._aplan_phase()

    us1 = pipeline.state.story("US-1")
    assert us1.stream == ""  # multi-stream container, derives status from tasks
    assert [t.id for t in us1.tasks] == ["T-1", "T-2"]
    back = pipeline.state.task("T-1")
    front = pipeline.state.task("T-2")
    assert back.stream == "backend" and front.stream == "frontend"
    # Cross-stream dependency: front task depends on the back task.
    assert front.depends_on == ["T-1"]

    us2 = pipeline.state.story("US-2")
    assert us2.stream == "backend" and us2.tasks == []  # mono-stream US

    # The produced work graph is valid (no dangling deps / cycle).
    assert work_streams.validate(pipeline.state) == []
    # Readiness: only the back task is ready (front waits on it; US-2 on US-1).
    ready = [w.id for w in work_streams.ready_items(pipeline.state)]
    assert ready == ["T-1"]


async def test_plan_task_ids_are_remapped_uniquely_across_iterations(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    pipeline = _make_plan_pipeline(_stream_plan_reply())
    await pipeline._aplan_phase()
    assert {t.id for t in pipeline.state.all_tasks()} == {"T-1", "T-2"}

    # A second plan reusing the SAME raw ids must be deduplicated, and the
    # cross-task dep must follow the rename.
    pipeline.state.iteration = 2
    pipeline.runner = FakeRunner([_stream_plan_reply()])
    await pipeline._aplan_phase()

    all_ids = [t.id for t in pipeline.state.all_tasks()]
    assert len(all_ids) == len(set(all_ids))  # globally unique
    # The new iteration's tasks were renamed off T-1/T-2.
    new_tasks = [t for t in pipeline.state.all_tasks() if t.id not in ("T-1", "T-2")]
    assert len(new_tasks) == 2
    front_new = next(t for t in new_tasks if t.stream == "frontend")
    back_new = next(t for t in new_tasks if t.stream == "backend")
    assert front_new.depends_on == [back_new.id]  # dep remapped consistently


async def test_scripted_po_reply_intact_off_decomposed_on():
    runner = ScriptedRunner()
    st = ProjectState(id="p", name="p", goal="g")

    # Flag OFF: the prompt has no multi-stream marker -> the original PO reply.
    settings.streams_enabled = False
    try:
        off = json.loads((await runner.arun(prompts.po_plan(st, "pkg"), system_prompt="")).text)
    finally:
        settings.streams_enabled = False
    stories_off = off["epics"][0]["stories"]
    assert all(not s.get("tasks") for s in stories_off)

    # Flag ON: the prompt gains the marker -> a decomposed reply (back + front).
    settings.streams_enabled = True
    try:
        st.streams = []  # effective_streams synthesizes a backend
        on = json.loads((await runner.arun(prompts.po_plan(st, "pkg"), system_prompt="")).text)
    finally:
        settings.streams_enabled = False
    tasks = on["epics"][0]["stories"][0]["tasks"]
    streams = {t["stream"] for t in tasks}
    assert "backend" in streams and "frontend" in streams
    front = next(t for t in tasks if t["stream"] == "frontend")
    assert front["depends_on"]  # depends on the backend task
