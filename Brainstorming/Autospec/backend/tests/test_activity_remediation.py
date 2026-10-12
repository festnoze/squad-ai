import asyncio

import pytest

from autospec.agents.runner import AgentResult, FakeRunner
from autospec.models import PipelinePhase, ProjectState
from autospec.orchestrator.pipeline import Pipeline, _BUILD_ITEM
from autospec import storage


async def test_mediated_tool_wait_is_not_counted_as_a_provider_call():
    from autospec.agents.runner import observe_provider
    tool_wait, release = asyncio.Event(), asyncio.Event()
    class Mediated:
        reports_provider_turns = True
        async def arun(self, *args, **kwargs):
            await observe_provider(True)
            assert pipeline._tracked._provider_calls == 1
            await observe_provider(False)
            tool_wait.set()
            await release.wait()
            await observe_provider(True)
            assert pipeline._tracked._provider_calls == 1
            await observe_provider(False)
            return AgentResult("ok", cost_usd=.1)
    pipeline = Pipeline(ProjectState(id="mediated-activity", name="test", goal="demo",
                                    phase=PipelinePhase.BUILD, budget_usd=1), Mediated())
    active = asyncio.create_task(pipeline._tracked.arun("p", "s"))
    await asyncio.wait_for(tool_wait.wait(), 2)
    row = next(iter(pipeline.state.agent_activity.values()))
    assert row["phase"] == "mediated_tools"
    assert row["logical_call_active"] is True
    assert row["active_provider_calls"] == 0
    assert pipeline._tracked._active_calls == 1  # budget remains reserved
    waiting = asyncio.create_task(pipeline._tracked.arun("p", "s"))
    await asyncio.sleep(0)
    assert any(a["phase"] == "waiting_budget" and a["active_provider_calls"] == 0
               for a in pipeline.state.agent_activity.values())
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    release.set()
    await active
    assert pipeline._tracked._provider_calls == 0
    assert pipeline.state.agent_activity == {}


def test_restart_between_mediated_turns_preserves_usage_uncertainty(monkeypatch, tmp_path):
    from autospec.config import settings
    from autospec.api import server
    monkeypatch.setattr(settings, "workspace_root", tmp_path)
    monkeypatch.setattr(server, "pipelines", {})
    storage.save_state(ProjectState(id="tool-interrupted", name="test", goal="demo",
        phase=PipelinePhase.BUILD, agent_activity={"T1": {
            "phase": "mediated_tools", "logical_call_active": True,
            "active_provider_calls": 0}}))
    server.recover_projects()
    state = storage.load_state("tool-interrupted")
    assert state.usage.unreported_calls == 1
    assert state.generation_checkpoint["cost_incomplete"] is True


async def test_checkpoint_failure_prevents_provider_spend(monkeypatch):
    from autospec.orchestrator import pipeline as module
    class Forbidden:
        async def arun(self, *args, **kwargs):
            pytest.fail("provider must not be called without a durable checkpoint")
    pipeline = Pipeline(ProjectState(id="checkpoint-error", name="test", goal="demo",
                                    phase=PipelinePhase.BUILD, budget_usd=1), Forbidden())
    def fail(*args, **kwargs):
        raise storage.PersistenceError("disk unavailable")
    monkeypatch.setattr(module, "save_state_checkpoint", fail)
    with pytest.raises(storage.PersistenceError):
        await pipeline._tracked.arun("p", "s")
    assert pipeline.state.usage.agent_calls == 0
    assert pipeline.state.agent_activity == {}


async def test_same_phase_calls_have_distinct_activity_rows():
    release, started = asyncio.Event(), asyncio.Event()
    class Pending:
        async def arun(self, *args, **kwargs):
            started.set()
            await release.wait()
            return AgentResult("ok", cost_usd=.1)
    pipeline = Pipeline(ProjectState(id="activity-phase", name="test", goal="demo",
                                    phase=PipelinePhase.PLAN, budget_usd=1), Pending())
    first = asyncio.create_task(pipeline._tracked.arun("p", "s"))
    await started.wait()
    second = asyncio.create_task(pipeline._tracked.arun("p", "s"))
    await asyncio.sleep(0)
    assert len(pipeline.state.agent_activity) == 2
    assert sorted(row["phase"] for row in pipeline.state.agent_activity.values()) == ["provider", "waiting_budget"]
    release.set()
    await asyncio.gather(first, second)
    assert pipeline.state.agent_activity == {}


def test_explicit_resume_starts_new_run_identity():
    pipeline = Pipeline(ProjectState(id="resume-identity", name="test", goal="demo",
                                    phase=PipelinePhase.BUILD,
                                    generation_checkpoint={"run_id": "old", "status": "interrupted"}), FakeRunner([]))
    pipeline._sync()
    assert pipeline.state.generation_checkpoint["run_id"] != "old"
    assert pipeline.state.generation_checkpoint["previous_run_id"] == "old"
    identity = pipeline.state.generation_checkpoint["run_id"]
    pipeline._sync()
    assert pipeline.state.generation_checkpoint["run_id"] == identity


async def test_waiting_budget_visible_and_checkpoint_durable_before_provider():
    started, release = asyncio.Event(), asyncio.Event()
    class Pending:
        async def arun(self, *args, **kwargs):
            assert storage.load_state("activity-proof").generation_checkpoint["last_phase"] == "build"
            started.set()
            await release.wait()
            return AgentResult("ok", cost_usd=.1)
    pipeline = Pipeline(ProjectState(id="activity-proof", name="activity", goal="demo",
                                    phase=PipelinePhase.BUILD, budget_usd=1), Pending())
    async def call(item):
        token = _BUILD_ITEM.set(item)
        try:
            return await pipeline._tracked.arun("p", "s")
        finally:
            _BUILD_ITEM.reset(token)
    active = asyncio.create_task(call("T1"))
    await asyncio.wait_for(started.wait(), 2)
    waiting = asyncio.create_task(call("T2"))
    await asyncio.sleep(0)
    assert pipeline.state.agent_activity["T1"]["phase"] == "provider"
    assert pipeline.state.agent_activity["T2"]["phase"] == "waiting_budget"
    assert pipeline.state.agent_activity["T2"]["owner"] == ["T1"]
    assert pipeline.state.agent_activity["T2"]["active_provider_calls"] == 1
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert "T2" not in pipeline.state.agent_activity
    release.set()
    await active
    assert pipeline.state.agent_activity == {}
    assert pipeline.state.usage.agent_calls == 1


@pytest.mark.parametrize("stage", ["provider", "merge", "smoke"])
def test_abrupt_owned_worker_is_reconciled_on_restart(tmp_path, monkeypatch, stage):
    import subprocess
    import sys
    import time
    from autospec.config import settings
    from autospec.api import server
    root = tmp_path / stage
    root.mkdir()
    program = (
        "import time; from pathlib import Path; from autospec.config import settings; "
        "from autospec.models import ProjectState,PipelinePhase; from autospec.storage import save_state; "
        f"settings.workspace_root=Path({str(root)!r}); "
        f"save_state(ProjectState(id='worker',name='worker',goal='demo',phase=PipelinePhase.BUILD,"
        f"generation_checkpoint={{'run_id':'one','stage':{stage!r}}})); time.sleep(30)"
    )
    child = subprocess.Popen([sys.executable, "-c", program])
    try:
        deadline = time.monotonic() + 5
        while not (root / "worker/autospec-state.json").exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert (root / "worker/autospec-state.json").exists()
    finally:
        child.kill()  # exact owned handle, no descendants or name matching
        child.wait(timeout=5)
    monkeypatch.setattr(settings, "workspace_root", root)
    monkeypatch.setattr(server, "pipelines", {})
    server.recover_projects()
    state = storage.load_state("worker")
    assert state.phase == PipelinePhase.STOPPED
    assert state.generation_checkpoint["status"] == "interrupted"
    assert state.generation_checkpoint["stage"] == stage
    assert state.resume_at == 0 and not state.delivery_ready
