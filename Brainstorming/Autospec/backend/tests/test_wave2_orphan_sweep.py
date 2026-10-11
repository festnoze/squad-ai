"""REM-02: legacy path matching never establishes process ownership."""
import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from autospec.config import settings
from autospec.orchestrator.pipeline import Pipeline


def test_legacy_sweep_never_enumerates_or_kills_processes(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("unknown process enumeration/kill is forbidden")
    monkeypatch.setattr(subprocess, "run", forbidden)
    assert Pipeline._sweep_workspace_orphans(tmp_path) == 0
    assert Pipeline._kill_workspace_port_holders(8000, tmp_path) == 0


def test_legacy_sweeps_preserve_native_sentinel(tmp_path):
    # The argv deliberately mentions the workspace: the retired heuristic
    # would consider this process owned. No ownership handle is registered.
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", str(tmp_path)])
    try:
        assert Pipeline._sweep_workspace_orphans(tmp_path) == 0
        assert Pipeline._kill_workspace_port_holders(8000, tmp_path) == 0
        assert child.poll() is None
    finally:
        child.kill()
        child.wait(timeout=5)


@pytest.mark.parametrize("enabled", [False, True])
async def test_restart_only_reconciles_state(enabled, monkeypatch):
    from autospec.api import server
    seen = []
    monkeypatch.setattr(settings, "orphan_sweep_on_boot", enabled)
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(server, "list_states", lambda: [])
    monkeypatch.setattr(server, "pipelines", {})
    monkeypatch.setattr(server, "recover_projects", lambda states: seen.append(states))
    def forbidden(*args, **kwargs):
        pytest.fail("restart must not kill by path")
    monkeypatch.setattr(Pipeline, "_sweep_workspace_orphans", staticmethod(forbidden))
    await asyncio.wait_for(server._arecover_projects(), timeout=2)
    assert seen == [[]]
