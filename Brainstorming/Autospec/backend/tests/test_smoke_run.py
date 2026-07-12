"""Smoke-run gate (SMOKE_RUN): after the suite is green, boot the
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
    # Isole du port :8000 de l'hôte : ce test couvre le CHEMIN de code (l'app
    # démarre → succès), pas la garde infra « port tenu par un tiers ».
    monkeypatch.setattr(Pipeline, "_port_is_free", staticmethod(lambda port: True))
    monkeypatch.setattr(Pipeline, "_smoke_run_python", lambda self, ws: (True, "listening :8000"))

    await pipeline._asmoke_phase()  # no raise
    assert not state.regressions


async def test_smoke_gate_fails_iteration_when_not_runnable(monkeypatch):
    monkeypatch.setattr(settings, "smoke_run", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    state = _state_with_done_story("smoke-ko")
    pipeline = Pipeline(state, ScriptedRunner())
    _scaffold(workspace_dir(state.id), web=True)
    # Isole du port :8000 de l'hôte : on veut atteindre le smoke run (app non
    # démarrable → échec/réparation), pas la garde infra « port tenu par un tiers ».
    monkeypatch.setattr(Pipeline, "_port_is_free", staticmethod(lambda port: True))
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


def test_expects_web_app_by_profile_and_streams():
    """La classification web doit venir de l'INTENTION (profil / stream
    frontend), pas seulement de l'artefact généré (piège messagerie2)."""
    from autospec.models import Stream, StreamKind

    p = Pipeline(_state_with_done_story("smoke-intent"), ScriptedRunner())
    p.state.product_profile = "fullstack"
    assert p._expects_web_app() is True
    p.state.product_profile = "api"
    assert p._expects_web_app() is True
    p.state.product_profile = "cli"
    assert p._expects_web_app() is False
    # auto : la présence d'un stream frontend implique un backend web.
    p.state.product_profile = "auto"
    assert p._expects_web_app() is False
    p.state.streams = [
        Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend"),
    ]
    assert p._expects_web_app() is True


def test_smoke_web_expected_by_intent_without_framework_fails(monkeypatch):
    """messagerie2 : app fullstack SANS framework web dans pyproject → l'ancien
    gate la classait CLI (exit 0 = succès). Avec l'intention web, main.py qui
    sort sans écouter doit ÉCHOUER, avec l'indice « framework absent »."""
    from autospec.models import Stream, StreamKind

    monkeypatch.setattr(settings, "smoke_run_timeout_s", 5.0)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _FakeProc(alive=False))
    monkeypatch.setattr(Pipeline, "_terminate_tree", staticmethod(lambda proc: None))
    state = _state_with_done_story("smoke-intent-web")
    state.streams = [
        Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend"),
    ]
    ws = _scaffold(workspace_dir(state.id), web=False)  # pas de framework déclaré
    pipeline = Pipeline(state, ScriptedRunner())

    ok, detail = pipeline._smoke_run_python(ws)
    assert ok is False
    assert "ne démarre pas le serveur" in detail
    assert "aucun framework web déclaré" in detail


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


# --------------------------------------------------- resolve_web_port (finding 2)

def test_pipeline_resolve_web_port_reads_main_py(monkeypatch):
    monkeypatch.setattr(settings, "smoke_run_port", 8000)
    state = _state_with_done_story("smoke-port-main")
    ws = _scaffold(workspace_dir(state.id), web=True, main_py="import uvicorn\nport = 9411\n")
    pipeline = Pipeline(state, ScriptedRunner())
    assert pipeline._resolve_web_port(ws) == 9411


def test_pipeline_resolve_web_port_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "smoke_run_port", 8222)
    state = _state_with_done_story("smoke-port-fb")
    ws = _scaffold(workspace_dir(state.id), web=True, main_py="import uvicorn  # no port\n")
    pipeline = Pipeline(state, ScriptedRunner())
    assert pipeline._resolve_web_port(ws) == 8222


# --------------------------------------- finding 1/4 : external port → infra park

async def test_smoke_external_port_occupied_is_infra_not_repair(monkeypatch):
    """Finding 1/4 : si le port reste tenu par un process EXTERNE après astop_app,
    c'est une condition d'infra — pas d'agent Dev, needs_attention direct."""
    from autospec.models import Stream, StreamKind

    monkeypatch.setattr(settings, "smoke_run", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(settings, "integration_fix_attempts", 2)
    state = _state_with_done_story("smoke-port-busy")
    state.streams = [Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend")]
    _scaffold(workspace_dir(state.id), web=True)

    async def _stop(self):
        return None

    monkeypatch.setattr(Pipeline, "astop_app", _stop)
    monkeypatch.setattr(Pipeline, "_port_is_free", staticmethod(lambda port: False))
    # Le smoke ne doit JAMAIS être atteint (on gare avant de booter).
    monkeypatch.setattr(
        Pipeline, "_smoke_run_python",
        lambda self, ws: (_ for _ in ()).throw(AssertionError("ne doit pas booter")),
    )
    runner = ScriptedRunner()
    pipeline = Pipeline(state, runner)

    assert await pipeline._asmoke_phase() is False
    assert pipeline._delivery_blocked is True
    assert any("process externe" in r for r in state.regressions)


async def test_smoke_launch_impossible_is_infra_not_repair(monkeypatch):
    """Finding 4 : « lancement impossible » (uv/python absent) ne dépense aucune
    tentative de réparation — needs_attention direct."""
    monkeypatch.setattr(settings, "smoke_run", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(settings, "integration_fix_attempts", 2)

    async def _snapshot(self, ws, label):
        raise AssertionError("aucune réparation ne doit démarrer")

    monkeypatch.setattr(Pipeline, "_agit_snapshot", _snapshot)
    state = _state_with_done_story("smoke-launch-ko")
    _scaffold(workspace_dir(state.id), web=True)
    monkeypatch.setattr(Pipeline, "_smoke_run_python", lambda self, ws: (False, "lancement impossible : uv absent"))
    pipeline = Pipeline(state, ScriptedRunner())

    assert await pipeline._asmoke_phase() is False
    assert pipeline._delivery_blocked is True
    assert any("infra" in r.lower() for r in state.regressions)


async def test_smoke_non_python_web_warns_not_silent(monkeypatch):
    """Finding 6 : un backend web non-python n'est pas skippé silencieusement —
    un WARNING est journalisé et le gate ne hard-bloque pas."""
    from autospec.models import BackendLanguage

    monkeypatch.setattr(settings, "smoke_run", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    state = _state_with_done_story("smoke-go")
    state.backend_language = BackendLanguage.GO
    state.product_profile = "api"  # intent web
    logs = []
    monkeypatch.setattr(Pipeline, "_log", lambda self, src, line: logs.append(line))
    pipeline = Pipeline(state, ScriptedRunner())

    assert await pipeline._asmoke_phase() is True  # pas de hard-block
    assert pipeline._delivery_blocked is False
    assert any("indisponible" in line and "go" in line.lower() for line in logs)
