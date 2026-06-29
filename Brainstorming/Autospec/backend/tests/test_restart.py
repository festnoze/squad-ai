"""Restart-from-scratch: wipe everything generated EXCEPT the initial brief,
then relaunch PO planning + the global build."""

import pytest

from autospec.agents.scripted import ScriptedRunner
from autospec.models import (
    AcceptanceCriterion,
    Epic,
    PipelinePhase,
    ProjectState,
    StoryStatus,
    Usage,
    UserStory,
)
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir


def _seeded_state(project_id="restart-proj"):
    st = ProjectState(id=project_id, name="App", goal="g")
    st.brief = "BRIEF: build a todo list."
    st.phase = PipelinePhase.DONE
    st.epics = [Epic(id="EPIC-1", title="E")]
    st.stories = [
        UserStory(
            id="US-1", epic_id="EPIC-1", title="t",
            acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="x")],
            status=StoryStatus.DONE,
        )
    ]
    st.lessons = ["old lesson"]
    st.usage = Usage(cost_usd=1.23, agent_calls=5)
    st.iteration = 3
    return st


async def test_restart_keeps_brief_clears_everything_and_wipes_workspace(monkeypatch):
    state = _seeded_state()
    pipeline = Pipeline(state, ScriptedRunner())
    # Materialize a workspace with generated code + a stale state file.
    ws = workspace_dir(state.id)
    (ws / "src").mkdir(parents=True, exist_ok=True)
    (ws / "src" / "old.py").write_text("print('old')", encoding="utf-8")
    (ws / "autospec-state.json").write_text("{}", encoding="utf-8")

    # Don't run the whole lifecycle here — assert the reset synchronously.
    launched = {"started": False}
    monkeypatch.setattr(pipeline, "start", lambda: launched.__setitem__("started", True))

    await pipeline.arestart_from_scratch()

    assert state.brief == "BRIEF: build a todo list."   # kept
    assert state.name == "App" and state.goal == "g"     # identity kept
    assert state.epics == [] and state.stories == []     # cleared
    assert state.lessons == []
    assert state.usage.cost_usd == 0 and state.usage.agent_calls == 0
    assert state.iteration == 1
    assert not (ws / "src" / "old.py").exists()          # generated code wiped
    assert launched["started"] is True                   # pipeline relaunched


async def test_restart_rejected_without_brief():
    state = _seeded_state()
    state.brief = ""
    pipeline = Pipeline(state, ScriptedRunner())
    with pytest.raises(ValueError):
        await pipeline.arestart_from_scratch()


async def test_restart_rejected_when_active():
    state = _seeded_state()
    state.phase = PipelinePhase.BUILD  # active
    pipeline = Pipeline(state, ScriptedRunner())
    with pytest.raises(ValueError):
        await pipeline.arestart_from_scratch()
