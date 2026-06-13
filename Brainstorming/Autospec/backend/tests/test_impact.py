"""Tests of the feedback impact analysis (E2): a feedback sent while the
pipeline is dormant either updates an unimplemented story or plans new ones."""

import json

from autospec.agents.runner import FakeRunner
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
from autospec.storage import workspace_dir

from .conftest import wait_until


def make_done_pipeline(replies: list[str]) -> Pipeline:
    state = ProjectState(
        id="proj-impact",
        name="todo",
        goal="Une todo-list",
        phase=PipelinePhase.DONE,
        brief="# Brief",
        epics=[Epic(id="EPIC-1", title="Cœur")],
        stories=[
            UserStory(
                id="US-1",
                epic_id="EPIC-1",
                title="Story à venir",
                status=StoryStatus.TODO,
                acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="ancien critère")],
            ),
            UserStory(id="US-2", epic_id="EPIC-1", title="Déjà livrée", status=StoryStatus.DONE),
        ],
    )
    return Pipeline(state, FakeRunner(replies))


async def test_feedback_updates_unimplemented_story():
    reply = json.dumps(
        {
            "message": "On amende la story non implémentée.",
            "action": "update_story",
            "story_id": "US-1",
            "updates": {
                "title": "Story amendée",
                "gherkin": "Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
                "acceptance_criteria": ["nouveau critère"],
            },
        },
        ensure_ascii=False,
    )
    pipeline = make_done_pipeline([reply])
    await pipeline.asend_user_message("change la story 1")
    await wait_until(lambda: pipeline.state.story("US-1").title == "Story amendée")
    story = pipeline.state.story("US-1")
    assert story.acceptance_criteria[0].text == "nouveau critère"
    assert "Feature: F" in story.gherkin
    # The amended Gherkin was rewritten to the feature file.
    feature = workspace_dir("proj-impact") / "features" / "us_1.feature"
    assert "Feature: F" in feature.read_text(encoding="utf-8")
    assert any(
        m.role == ChatRole.ANALYST and "mise à jour" in m.content for m in pipeline.state.chat
    )


async def test_feedback_creates_new_epic_and_stories():
    reply = json.dumps(
        {
            "message": "Nouvelle tâche détectée.",
            "action": "new_stories",
            "epic": {"id": "EPIC-2", "title": "Retours", "description": ""},
            "stories": [
                {
                    "id": "US-10",
                    "title": "Nouvelle demande",
                    "description": "En tant qu'utilisateur…",
                    "acceptance_criteria": ["ça marche"],
                    "gherkin": "Feature: N\n  Scenario: s\n    Given a\n    When b\n    Then c",
                    "depends_on": [],
                    "priority": 1,
                }
            ],
        },
        ensure_ascii=False,
    )
    pipeline = make_done_pipeline([reply])
    await pipeline.asend_user_message("ajoute un export CSV")
    await wait_until(lambda: any(s.id == "US-10" for s in pipeline.state.stories))
    assert any(e.id == "EPIC-2" for e in pipeline.state.epics)
    story = pipeline.state.story("US-10")
    assert story.status == StoryStatus.TODO
    assert story.iteration == pipeline.state.iteration
    assert any(
        m.role == ChatRole.ANALYST and "Continuer le build" in m.content
        for m in pipeline.state.chat
    )


async def test_feedback_targeting_done_story_is_kept_as_feedback():
    reply = json.dumps(
        {
            "message": "On modifie US-2.",
            "action": "update_story",
            "story_id": "US-2",
            "updates": {"title": "Interdit"},
        },
        ensure_ascii=False,
    )
    pipeline = make_done_pipeline([reply])
    await pipeline.asend_user_message("change la story livrée")
    await wait_until(
        lambda: any(
            m.role == ChatRole.ANALYST and "déjà" in m.content for m in pipeline.state.chat
        )
    )
    assert pipeline.state.story("US-2").title == "Déjà livrée"
    assert pipeline.state.feedback == ["change la story livrée"]


async def test_feedback_during_active_phase_skips_impact_analysis():
    pipeline = make_done_pipeline([])  # no reply queued: an agent call would fail
    pipeline.state.phase = PipelinePhase.PLAN
    await pipeline.asend_user_message("un simple retour")
    assert pipeline._impact_task is None
    assert pipeline.state.feedback == ["un simple retour"]


async def test_failed_story_amended_by_feedback_is_requeued():
    reply = json.dumps(
        {
            "message": "Story échouée reformulée.",
            "action": "update_story",
            "story_id": "US-1",
            "updates": {"description": "reformulée"},
        },
        ensure_ascii=False,
    )
    pipeline = make_done_pipeline([reply])
    story = pipeline.state.story("US-1")
    story.status = StoryStatus.FAILED
    story.attempts = 2
    story.last_error = "boom"
    await pipeline.asend_user_message("reformule la story échouée")
    await wait_until(lambda: pipeline.state.story("US-1").status == StoryStatus.TODO)
    story = pipeline.state.story("US-1")
    assert story.attempts == 0 and story.last_error == ""
