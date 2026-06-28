"""Runtime acceptance gate for web/fullstack deliveries."""

import subprocess

from autospec.config import settings
from autospec.models import ProjectState, StoryStatus, Stream, StreamKind, UserStory
from autospec.orchestrator import runtime_acceptance
from autospec.storage import workspace_dir


def _done_frontend_state(pid="rt-fe") -> ProjectState:
    return ProjectState(
        id=pid,
        name="web",
        goal="g",
        streams=[
            Stream(id="backend", kind=StreamKind.BACKEND, primary=True),
            Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend"),
        ],
        stories=[
            UserStory(
                id="US-1",
                epic_id="E1",
                title="UI",
                status=StoryStatus.DONE,
                stream="frontend",
            )
        ],
    )


async def test_runtime_acceptance_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "runtime_acceptance_enabled", False)
    state = _done_frontend_state("rt-skip")
    result = await runtime_acceptance.arun_runtime_acceptance(state, workspace_dir(state.id))
    assert result.ok is True
    assert result.skipped is True


async def test_runtime_acceptance_invokes_node_script_for_frontend(monkeypatch):
    monkeypatch.setattr(settings, "runtime_acceptance_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(settings, "runtime_acceptance_timeout_s", 12.0)
    monkeypatch.setattr(settings, "node_cmd", "node")
    state = _done_frontend_state("rt-front")
    ws = workspace_dir(state.id)
    frontend = ws / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "package.json").write_text('{"scripts":{"preview":"vite preview"}}', encoding="utf-8")
    calls = []

    def _fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="[runtime] OK")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = await runtime_acceptance.arun_runtime_acceptance(state, ws)
    assert result.ok is True
    assert result.skipped is False
    cmd = calls[0][0]
    assert cmd[0] == "node"
    assert cmd[1].endswith("runtime_acceptance.js")
    assert cmd[2] == str(ws)
    assert cmd[4] == str(frontend)
    assert cmd[5] == "0"
