import json

from autospec.agents import prompts
from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import (
    AcceptanceCriterion,
    FeatureHypothesis,
    PipelinePhase,
    ProjectState,
    StoryStatus,
    UserStory,
)
from autospec.orchestrator.pipeline import Pipeline

from .conftest import wait_until


async def test_scripted_runner_drives_full_pipeline(monkeypatch):
    # Demo mode: scripted agents + pytest short-circuit, no Claude CLI, no uv.
    monkeypatch.setattr(settings, "fake_agents", True)
    state = ProjectState(id="demo-1", name="demo", goal="démo")
    pipeline = Pipeline(state, ScriptedRunner())
    pipeline.start()

    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE, timeout=8)
    # Scripted PO plan yields 2 stories, both completed; criteria are structured.
    assert {s.id for s in pipeline.state.stories} == {"US-1", "US-2"}
    assert all(s.status == StoryStatus.DONE for s in pipeline.state.stories)
    us1 = pipeline.state.story("US-1")
    assert us1.acceptance_criteria[0].id == "AC-1"
    assert us1.test_plan and us1.test_plan[0].criteria == ["AC-1"]


def test_reply_routing_matches_every_prompt_builder():
    # Renders each real prompt (also a smoke test of the prompts' f-string
    # brace escaping) and checks it routes to the matching canned reply.
    state = ProjectState(id="p1", name="p", goal="une todo-list", brief="# Brief")
    story = UserStory(
        id="US-7",
        epic_id="EPIC-1",
        title="Créer une tâche",
        description="En tant qu'utilisateur, je veux créer une tâche.",
        acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="La tâche est créée.")],
        gherkin="Feature: Tâches",
    )
    hyp = FeatureHypothesis(id="FH-1", title="Filtrer les tâches")
    reply = ScriptedRunner._reply_for

    assert json.loads(reply(prompts.pm_interview(state)))["type"] == "brief"
    assert json.loads(reply(prompts.pm_brainstorm(state)))["type"] == "brief"
    assert json.loads(reply(prompts.pm_brief_for_feature(state, hyp)))["type"] == "brief"
    assert "epics" in json.loads(reply(prompts.po_plan(state, "pkg")))
    assert "design" in json.loads(reply(prompts.architect_design(state, "pkg")))
    assert "hypotheses" in json.loads(reply(prompts.analyst_explore(state)))

    qa = json.loads(reply(prompts.qa_test_plan(story, "pkg", architecture="## Archi")))
    # The QA plan must target the story actually named in the prompt.
    assert qa["tests"][0]["file_hint"] == "tests/unit/test_us_7_service.py"

    dev = json.loads(reply(prompts.dev_story(story, "pkg", "features/us_7.feature")))
    assert dev["status"] == "green"

    assert "score" in json.loads(
        reply(prompts.judge_quality("le plan", "{}", prompts.PLAN_CRITERIA))
    )
    assert "issues" in json.loads(
        reply(prompts.critic_review("le code", "{}", prompts.CODE_CRITERIA))
    )
    # Revision prompts keep routing to their maker agent.
    assert "epics" in json.loads(reply(prompts.po_revise(state, "pkg", "{}", "critique")))
    assert (
        json.loads(reply(prompts.dev_revise(story, "pkg", "features/us_7.feature", "critique")))[
            "status"
        ]
        == "green"
    )
