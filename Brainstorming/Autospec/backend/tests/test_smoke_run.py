"""Smoke-run gate (AUTOSPEC_SMOKE_RUN): after the suite is green, boot the
delivered app and require it to actually start — a non-runnable build fails the
iteration like a red test. These tests cover the gate contract and the
runnability check without launching `uv` (the subprocess/socket are faked)."""

import socket as socketmod
import subprocess

from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import ProjectState, StoryStatus, UserStory
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir


def _state_with_done_story(pid="smoke-proj"):
    st = ProjectState(id=pid, name="app", goal="g")
    st.stories = [UserStory(id="US-1", epic_id="E", title="t", status=StoryStatus.DONE)]
    return st


def _scaffold(ws, *, web: bool, main_py="print('hi')"):
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text(main_py, encoding="utf-8")
    dep = '"fastapi>=0.1"' if web else ""
    (ws / "pyproject.toml").write_text(
        f"[project]\nname='x'\ndependencies=[{dep}]\n", encoding="utf-8"
    )
    return ws


class _FakeSock:
    def __init__(self, listening): self._listening = listening
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def settimeout(self, _t): pass
    def connect_ex(self, _addr): return 0 if self._listening else 1


class _FakeProc:
    def __init__(self, alive=True): self._alive = alive; self.pid = 4321; self.returncode = 7; self.stdout = None
    def poll(self): return None if self._alive else self.returncode


# ----------------------------------------------------------------- gate contract

async def test_smoke_gate_noop_when_disabled(monkeypatch):
    # OFF by default: returns immediately, even with nothing to run.
    monkeypatch.setattr(settings, "smoke_run", False)
    pipeline = Pipeline(_state_with_done_story(), ScriptedRunner())
    await pipeline._asmoke_phase()  # must not raise


async def test_smoke_gate_passes_when_app_runs(monkeypatch):
    monkeypatch.setattr(settings, "smoke_run", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    state = _state_with_done_story("smoke-ok")
    pipeline = Pipeline(state, ScriptedRunner())
    _scaffold(workspace_dir(state.id), web=True)
    monkeypatch.setattr(Pipeline, "_smoke_run_python", lambda self, ws: (True, "listening :8000"))

    await pipeline._asmoke_phase()  # no raise
    assert not state.regressions


async def test_smoke_gate_fails_iteration_when_not_runnable(monkeypatch):
    monkeypatch.setattr(settings, "smoke_run", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    state = _state_with_done_story("smoke-ko")
    pipeline = Pipeline(state, ScriptedRunner())
    _scaffold(workspace_dir(state.id), web=True)
    monkeypatch.setattr(
        Pipeline, "_smoke_run_python", lambda self, ws: (False, "n'écoute pas")
    )

    assert await pipeline._asmoke_phase() is False
    assert pipeline._delivery_blocked is True
    assert any("Smoke run échoué" in issue for issue in state.delivery_issues)
    assert any("Smoke run échoué" in r for r in state.regressions)


# ----------------------------------------------------------- runnability check

def test_smoke_python_web_not_listening_fails(monkeypatch):
    monkeypatch.setattr(settings, "smoke_run_timeout_s", 1.0)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _FakeProc(alive=True))
    monkeypatch.setattr(socketmod, "socket", lambda *a, **k: _FakeSock(listening=False))
    monkeypatch.setattr(Pipeline, "_terminate_tree", staticmethod(lambda proc: None))
    state = _state_with_done_story("smoke-web-down")
    ws = _scaffold(workspace_dir(state.id), web=True)
    pipeline = Pipeline(state, ScriptedRunner())

    ok, detail = pipeline._smoke_run_python(ws)
    assert ok is False and "aucun serveur" in detail


def test_smoke_python_web_listening_passes(monkeypatch):
    monkeypatch.setattr(settings, "smoke_run_timeout_s", 5.0)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _FakeProc(alive=True))
    monkeypatch.setattr(socketmod, "socket", lambda *a, **k: _FakeSock(listening=True))
    monkeypatch.setattr(Pipeline, "_terminate_tree", staticmethod(lambda proc: None))
    state = _state_with_done_story("smoke-web-up")
    ws = _scaffold(workspace_dir(state.id), web=True, main_py="import uvicorn  # port=8000")
    pipeline = Pipeline(state, ScriptedRunner())

    ok, detail = pipeline._smoke_run_python(ws)
    assert ok is True and "8000" in detail


def test_smoke_python_web_process_exits_without_listening_fails(monkeypatch):
    # The P4 deviation: main.py runs and EXITS (printed instructions) — no server.
    monkeypatch.setattr(settings, "smoke_run_timeout_s", 5.0)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _FakeProc(alive=False))
    monkeypatch.setattr(Pipeline, "_terminate_tree", staticmethod(lambda proc: None))
    state = _state_with_done_story("smoke-web-exit")
    ws = _scaffold(workspace_dir(state.id), web=True)
    pipeline = Pipeline(state, ScriptedRunner())

    ok, detail = pipeline._smoke_run_python(ws)
    assert ok is False and "ne démarre pas le serveur" in detail


def test_smoke_python_cli_exit_zero_passes(monkeypatch):
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="done")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: completed)
    state = _state_with_done_story("smoke-cli-ok")
    ws = _scaffold(workspace_dir(state.id), web=False)
    pipeline = Pipeline(state, ScriptedRunner())

    ok, detail = pipeline._smoke_run_python(ws)
    assert ok is True and "code 0" in detail


def test_smoke_python_cli_nonzero_fails(monkeypatch):
    completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="boom")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: completed)
    state = _state_with_done_story("smoke-cli-ko")
    ws = _scaffold(workspace_dir(state.id), web=False)
    pipeline = Pipeline(state, ScriptedRunner())

    ok, detail = pipeline._smoke_run_python(ws)
    assert ok is False and "non nulle" in detail
