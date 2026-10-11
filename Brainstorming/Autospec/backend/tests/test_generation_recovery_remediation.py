from autospec import storage
from autospec.api import server
from autospec.models import PipelinePhase, ProjectState


def test_restart_marks_delivery_interrupted_without_provider_or_resume(tmp_path, monkeypatch):
    from autospec.config import settings
    monkeypatch.setattr(settings, "workspace_root", tmp_path)
    state = ProjectState(id="dead-worker", name="dead", goal="support", phase=PipelinePhase.BUILD,
                         delivery_ready=True, deploy_status="verifying", resume_at=1,
                         generation_checkpoint={"run_id": "run-1", "last_phase": "build", "at": 100},
                         agent_activity={"T1": {"phase": "provider"}})
    monkeypatch.setattr(server, "pipelines", {})
    assert server.recover_projects([state]) == ["dead-worker"]
    assert state.phase == PipelinePhase.STOPPED
    assert not state.delivery_ready and state.deploy_status == "failed"
    assert state.resume_at == 0 and state.agent_activity == {}
    assert "interrompue" in state.error
    assert state.generation_checkpoint["run_id"] == "run-1"
    assert state.generation_checkpoint["status"] == "interrupted"
    recovered = storage.load_state(state.id)
    assert recovered.generation_checkpoint == state.generation_checkpoint
    assert server.pipelines[state.id]._task is None


def test_old_state_without_checkpoint_remains_loadable():
    state = ProjectState.model_validate({"id": "old", "name": "old", "goal": "old"})
    assert state.generation_checkpoint == state.agent_activity == {}
