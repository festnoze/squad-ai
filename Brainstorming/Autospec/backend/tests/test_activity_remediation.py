import asyncio

import pytest

from autospec.agents.runner import AgentResult
from autospec.models import PipelinePhase, ProjectState
from autospec.orchestrator.pipeline import Pipeline, _BUILD_ITEM
from autospec import storage


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
