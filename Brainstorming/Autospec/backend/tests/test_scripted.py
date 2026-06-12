from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import ProjectState, PipelinePhase, StoryStatus
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
