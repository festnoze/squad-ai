"""R6 (UX wave 3): deleting a story is no longer destructive.

With ``SOFT_DELETE_STORIES`` on, ``adelete_story`` moves the story to a bounded
``ProjectState.trash`` together with the ``depends_on`` links the deletion
strips from its siblings, and ``arestore_story`` puts the whole thing back (the
story as fresh TODO work, the dependency re-woven, the .feature file rewritten).
Everything the rest of the factory observes on a delete is unchanged - the story
still leaves ``state.stories`` and its feature file is still removed - so the
flag can be turned off for a byte-identical legacy hard delete.
"""

import httpx
import pytest

from autospec.agents.scripted import ScriptedRunner
from autospec.api import server
from autospec.config import settings
from autospec.models import (
    BuildStage,
    Epic,
    PipelinePhase,
    ProjectState,
    StoryStatus,
    UserStory,
)
from autospec.orchestrator import workspace
from autospec.orchestrator.pipeline import TRASH_MAX, Pipeline
from autospec.storage import workspace_dir

GHERKIN = "Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c"


def _state(project_id: str = "trash-proj") -> ProjectState:
    """A finished project with US-2 depending on US-1."""
    return ProjectState(
        id=project_id,
        name="app",
        goal="g",
        phase=PipelinePhase.DONE,
        epics=[Epic(id="EPIC-1", title="E")],
        stories=[
            UserStory(id="US-1", epic_id="EPIC-1", title="La story", gherkin=GHERKIN),
            UserStory(id="US-2", epic_id="EPIC-1", title="La suivante", depends_on=["US-1"]),
        ],
    )


def _pipeline(state: ProjectState) -> Pipeline:
    return Pipeline(state, ScriptedRunner())


def _feature_path(state: ProjectState, story: UserStory):
    return workspace_dir(state.id) / workspace.feature_rel_path(story)


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=server.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_delete_trashes_the_story_and_records_stripped_deps():
    state = _state()
    pipeline = _pipeline(state)
    workspace.write_feature_files(state, [state.story("US-1")])
    feature = _feature_path(state, state.story("US-1"))
    assert feature.exists()

    await pipeline.adelete_story("US-1")

    # Unchanged for every existing consumer: gone from the board, feature file
    # removed, sibling dependency scrubbed.
    assert [s.id for s in state.stories] == ["US-2"]
    assert state.story("US-2").depends_on == []
    assert not feature.exists()
    # New: the story and the damage it caused are recoverable.
    assert len(state.trash) == 1
    entry = state.trash[0]
    assert entry.story.id == "US-1"
    assert entry.story.title == "La story"
    assert entry.story.gherkin == GHERKIN
    assert entry.stripped_deps == {"US-2": ["US-1"]}
    assert entry.feature_rel_path == "features/us_1.feature"
    assert entry.deleted_at > 0


async def test_restore_puts_the_story_back_as_fresh_work():
    state = _state()
    pipeline = _pipeline(state)
    story = state.story("US-1")
    story.status = StoryStatus.FAILED
    story.attempts = 3
    story.infra_attempts = 2
    story.requeue_attempts = 1
    story.solo_attempted = True
    story.last_error = "boom"
    story.current_stage = BuildStage.IMPLEMENTING
    story.current_persona = "dev"

    await pipeline.adelete_story("US-1")
    restored = await pipeline.arestore_story("US-1")

    assert [s.id for s in state.stories] == ["US-2", "US-1"]
    assert restored.status == StoryStatus.TODO
    assert restored.attempts == 0
    assert restored.infra_attempts == 0
    assert restored.requeue_attempts == 0
    assert restored.solo_attempted is False
    assert restored.last_error == ""
    assert restored.current_stage == BuildStage.QUEUED
    assert restored.current_persona == ""
    # The dependency the deletion stripped is woven back on the sibling.
    assert state.story("US-2").depends_on == ["US-1"]
    # The .feature file is rewritten, and the trash entry is consumed.
    assert _feature_path(state, restored).read_text(encoding="utf-8").startswith("Feature: F")
    assert state.trash == []


async def test_restore_skips_a_sibling_deleted_in_the_meantime():
    """The re-weave must not resurrect a dependency on a story that is gone."""
    state = _state()
    pipeline = _pipeline(state)

    await pipeline.adelete_story("US-1")
    await pipeline.adelete_story("US-2")
    await pipeline.arestore_story("US-1")

    assert [s.id for s in state.stories] == ["US-1"]
    assert [t.story.id for t in state.trash] == ["US-2"]


async def test_restore_unknown_story_raises_key_error():
    state = _state()
    pipeline = _pipeline(state)

    with pytest.raises(KeyError):
        await pipeline.arestore_story("US-404")


async def test_restore_is_refused_while_the_pipeline_builds():
    state = _state()
    pipeline = _pipeline(state)
    await pipeline.adelete_story("US-1")
    state.phase = PipelinePhase.BUILD

    with pytest.raises(ValueError):
        await pipeline.arestore_story("US-1")

    assert len(state.trash) == 1  # nothing consumed by the refused restore


async def test_restore_is_refused_when_the_id_is_taken_again():
    state = _state()
    pipeline = _pipeline(state)
    await pipeline.adelete_story("US-1")
    state.stories.append(UserStory(id="US-1", epic_id="EPIC-1", title="Un homonyme"))

    with pytest.raises(ValueError):
        await pipeline.arestore_story("US-1")


async def test_trash_is_bounded_and_purges_the_oldest():
    state = _state("trash-bound")
    state.stories = [
        UserStory(id=f"US-{i}", epic_id="EPIC-1", title=f"S{i}") for i in range(1, 26)
    ]
    pipeline = _pipeline(state)

    for i in range(1, 26):
        await pipeline.adelete_story(f"US-{i}")

    assert len(state.trash) == TRASH_MAX == 20
    # The 5 oldest deletions (US-1..US-5) were purged; the newest is last.
    assert [t.story.id for t in state.trash] == [f"US-{i}" for i in range(6, 26)]


async def test_flag_off_keeps_the_historic_hard_delete(monkeypatch):
    monkeypatch.setattr(settings, "soft_delete_stories", False)
    state = _state("trash-off")
    pipeline = _pipeline(state)

    await pipeline.adelete_story("US-1")

    assert [s.id for s in state.stories] == ["US-2"]
    assert state.trash == []
    with pytest.raises(KeyError):
        await pipeline.arestore_story("US-1")


async def test_trash_endpoint_lists_the_deleted_stories():
    state = _state("trash-api")
    pipeline = _pipeline(state)
    server.pipelines.clear()
    server.pipelines[state.id] = pipeline

    async with _client() as client:
        assert (await client.get(f"/api/projects/{state.id}/trash")).json() == {"items": []}

        assert (
            await client.delete(f"/api/projects/{state.id}/stories/US-1")
        ).status_code == 200
        assert (
            await client.delete(f"/api/projects/{state.id}/stories/US-2")
        ).status_code == 200

        items = (await client.get(f"/api/projects/{state.id}/trash")).json()["items"]
        # Most recently deleted first.
        assert [i["id"] for i in items] == ["US-2", "US-1"]
        assert items[1]["title"] == "La story"
        assert items[1]["epic_id"] == "EPIC-1"
        assert items[0]["deleted_at"] >= items[1]["deleted_at"] > 0

        # The pushed state carries the trash, so the UI can read project.trash.
        pushed = (await client.get(f"/api/projects/{state.id}")).json()
        assert [t["story"]["id"] for t in pushed["trash"]] == ["US-1", "US-2"]

    server.pipelines.clear()


async def test_restore_endpoint_returns_the_state_and_maps_errors():
    state = _state("restore-api")
    pipeline = _pipeline(state)
    server.pipelines.clear()
    server.pipelines[state.id] = pipeline

    async with _client() as client:
        await client.delete(f"/api/projects/{state.id}/stories/US-1")

        resp = await client.post(f"/api/projects/{state.id}/stories/US-1/restore")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert sorted(s["id"] for s in body["state"]["stories"]) == ["US-1", "US-2"]
        assert body["state"]["trash"] == []

        # Unknown id -> 404, active pipeline -> 409.
        assert (
            await client.post(f"/api/projects/{state.id}/stories/US-404/restore")
        ).status_code == 404
        await client.delete(f"/api/projects/{state.id}/stories/US-1")
        state.phase = PipelinePhase.BUILD
        assert (
            await client.post(f"/api/projects/{state.id}/stories/US-1/restore")
        ).status_code == 409

    server.pipelines.clear()
