"""Tests of the factory retrospective (E7): a meta-learning agent mines an
iteration's build signals into durable lessons (injected into QA/Dev prompts)
and tuning recommendations."""

import json

import httpx
import pytest

from autospec.agents import prompts
from autospec.agents.runner import FakeRunner
from autospec.api import server
from autospec.config import settings
from autospec.models import (
    AcceptanceCriterion,
    ChatRole,
    Epic,
    PipelinePhase,
    ProjectState,
    StoryStatus,
    UserStory,
)
from autospec.orchestrator.pipeline import Pipeline

from .conftest import wait_until

RETRO = json.dumps(
    {
        "message": "Deux retries rouge→vert sur le client LLM.",
        "lessons": [
            "Mocker explicitement le client LLM dans les tests de service.",
            "Mocker explicitement le client LLM dans les tests de service.",  # dup
            "Découper les stories touchant le parsing JSON.",
        ],
        "recommendations": ["Passer refine_max_rounds à 3 vu les scores ~70."],
    },
    ensure_ascii=False,
)


def make_done_pipeline(replies: list[str]) -> Pipeline:
    state = ProjectState(
        id="proj-retro",
        name="todo",
        goal="Une todo-list",
        phase=PipelinePhase.DONE,
        brief="# Brief",
        epics=[Epic(id="EPIC-1", title="Cœur")],
        stories=[
            UserStory(
                id="US-1",
                epic_id="EPIC-1",
                title="Story livrée",
                status=StoryStatus.DONE,
                attempts=2,
                quality_score=72,
            ),
        ],
    )
    return Pipeline(state, FakeRunner(replies))


async def test_retro_produces_lessons_and_recommendations():
    pipeline = make_done_pipeline([RETRO])
    await pipeline._aretro_phase(force=True)
    # Lessons are deduplicated and persisted on the state for the next iteration.
    assert pipeline.state.lessons == [
        "Mocker explicitement le client LLM dans les tests de service.",
        "Découper les stories touchant le parsing JSON.",
    ]
    assert pipeline.state.retro_recommendations == [
        "Passer refine_max_rounds à 3 vu les scores ~70."
    ]
    assert any(
        m.role == ChatRole.ANALYST and "Rétrospective" in m.content for m in pipeline.state.chat
    )


async def test_retro_caps_lessons(monkeypatch):
    monkeypatch.setattr(settings, "retro_max_lessons", 2)
    reply = json.dumps(
        {"message": "m", "lessons": ["a", "b", "c", "d"], "recommendations": []},
        ensure_ascii=False,
    )
    pipeline = make_done_pipeline([reply])
    await pipeline._aretro_phase(force=True)
    assert pipeline.state.lessons == ["a", "b"]


async def test_lessons_injected_into_dev_and_qa_prompts():
    story = UserStory(
        id="US-1",
        epic_id="EPIC-1",
        title="S",
        description="d",
        acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="c")],
        gherkin="Feature: F",
    )
    lesson = "Mocker explicitement le client LLM."
    dev_prompt = prompts.dev_story(story, "app", "features/us_1.feature", lessons=lesson)
    qa_prompt = prompts.qa_test_plan(story, "app", lessons=lesson)
    revise_prompt = prompts.dev_revise(
        story, "app", "features/us_1.feature", "critique", lessons=lesson
    )
    assert lesson in dev_prompt
    assert lesson in qa_prompt
    assert lesson in revise_prompt
    # Without lessons the block is absent (no empty "Leçons" header).
    assert "Leçons des itérations précédentes" not in prompts.dev_story(
        story, "app", "features/us_1.feature"
    )


async def test_retro_disabled_by_default_in_lifecycle(green_pytest):
    pm_brief = json.dumps({"type": "brief", "message": "OK", "brief": "# Brief"})
    po_plan = json.dumps(
        {"epics": [{"id": "EPIC-1", "title": "E", "stories": [
            {"id": "US-1", "title": "S", "description": "d", "acceptance_criteria": ["c"],
             "gherkin": "Feature: F\n  Scenario: s\n    Given a\n    When b\n    Then c",
             "depends_on": []}]}]}
    )
    qa_trivial = json.dumps({"message": "Trivial.", "tests": []})
    dev_green = json.dumps({"status": "green", "summary": "ok", "files": []})
    state = ProjectState(id="proj-retro2", name="todo", goal="Une todo-list")
    pipeline = Pipeline(state, FakeRunner([pm_brief, po_plan, qa_trivial, dev_green]))
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    assert pipeline.state.lessons == []


async def test_retro_runs_in_lifecycle_when_enabled(monkeypatch, green_pytest):
    monkeypatch.setattr(settings, "retro_enabled", True)
    pm_brief = json.dumps({"type": "brief", "message": "OK", "brief": "# Brief"})
    po_plan = json.dumps(
        {"epics": [{"id": "EPIC-1", "title": "E", "stories": [
            {"id": "US-1", "title": "S", "description": "d", "acceptance_criteria": ["c"],
             "gherkin": "Feature: F\n  Scenario: s\n    Given a\n    When b\n    Then c",
             "depends_on": []}]}]}
    )
    qa_trivial = json.dumps({"message": "Trivial.", "tests": []})
    dev_green = json.dumps({"status": "green", "summary": "ok", "files": []})
    state = ProjectState(id="proj-retro3", name="todo", goal="Une todo-list")
    pipeline = Pipeline(state, FakeRunner([pm_brief, po_plan, qa_trivial, dev_green, RETRO]))
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    assert len(pipeline.state.lessons) == 2


async def test_retro_rejected_while_building():
    state = ProjectState(id="proj-retro4", name="todo", goal="g", phase=PipelinePhase.BUILD)
    pipeline = Pipeline(state, FakeRunner([]))
    with pytest.raises(ValueError):
        await pipeline.aretrospect()


async def test_retro_endpoint_and_unknown_404(green_pytest):
    server.pipelines.clear()
    server.set_runner(FakeRunner([RETRO]))
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/api/projects/nope/retro")).status_code == 404
        state = ProjectState(id="proj-retro5", name="todo", goal="g", phase=PipelinePhase.DONE)
        server.pipelines["proj-retro5"] = Pipeline(state, FakeRunner([RETRO]))
        assert (await client.post("/api/projects/proj-retro5/retro")).status_code == 200

        async def alessoned():
            return len(server.pipelines["proj-retro5"].state.lessons) == 2

        import asyncio

        for _ in range(2000):
            if await alessoned():
                break
            await asyncio.sleep(0.01)
        assert await alessoned()
