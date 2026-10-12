"""Runtime acceptance gate for web/fullstack deliveries."""

import subprocess
import asyncio
import threading
import time
import sys
import json
import os
import socket
from pathlib import Path

import pytest

from autospec.config import settings
from autospec.models import BackendLanguage, ProjectState, StoryStatus, Stream, StreamKind, UserStory
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

    monkeypatch.setattr(runtime_acceptance, "_run_node", _fake_run)
    result = await runtime_acceptance.arun_runtime_acceptance(state, ws)
    assert result.ok is True
    assert result.skipped is False
    cmd = calls[0][0]
    assert cmd[0] == "node"
    assert cmd[1].endswith("runtime_acceptance.js")
    assert cmd[2] == str(ws)
    assert cmd[4] == str(frontend)
    assert cmd[5] == "0"


# ------------------------------------------------------------ resolve_web_port

def test_resolve_web_port_from_main_py(monkeypatch):
    """Le port doit venir de main.py quand il y est déclaré (source #1)."""
    monkeypatch.setattr(settings, "smoke_run_port", 8000)
    state = _done_frontend_state("rt-port-main")
    ws = workspace_dir(state.id)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("import uvicorn\nport = 9137\n", encoding="utf-8")
    assert runtime_acceptance.resolve_web_port(ws) == 9137


def test_resolve_web_port_falls_back_to_settings(monkeypatch):
    """Sans port dans main.py (ou sans main.py), on retombe sur settings (source #2)."""
    monkeypatch.setattr(settings, "smoke_run_port", 8123)
    state = _done_frontend_state("rt-port-fallback")
    ws = workspace_dir(state.id)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("import uvicorn  # no explicit port\n", encoding="utf-8")
    assert runtime_acceptance.resolve_web_port(ws) == 8123
    # Pas de main.py du tout : même repli.
    ws2 = workspace_dir("rt-port-nomain")
    ws2.mkdir(parents=True, exist_ok=True)
    assert runtime_acceptance.resolve_web_port(ws2) == 8123


# --------------------------------------------------- env passed to the JS gate

def _prep_frontend(state):
    ws = workspace_dir(state.id)
    frontend = ws / "frontend"
    frontend.mkdir(parents=True, exist_ok=True)
    (frontend / "package.json").write_text('{"scripts":{"preview":"vite preview"}}', encoding="utf-8")
    return ws, frontend


async def test_runtime_gate_passes_backend_port_and_journey_env(monkeypatch):
    """Contrat JS #2/#3 : RUNTIME_BACKEND_PORT (port résolu) et RUNTIME_JOURNEY
    (Gherkin des stories DONE) sont exportés au process node."""
    monkeypatch.setattr(settings, "runtime_acceptance_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(settings, "node_cmd", "node")
    monkeypatch.setattr(settings, "smoke_run_port", 8000)
    state = _done_frontend_state("rt-env")
    state.stories[0].gherkin = "Feature: login\n  Scenario: happy\n    Given a user"
    ws, _frontend = _prep_frontend(state)
    (ws / "main.py").write_text("import uvicorn\nport = 9200\n", encoding="utf-8")

    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return subprocess.CompletedProcess(cmd, 0, stdout="[runtime] OK")

    monkeypatch.setattr(runtime_acceptance, "_run_node", _fake_run)
    result = await runtime_acceptance.arun_runtime_acceptance(state, ws)
    assert result.ok is True
    assert captured["env"]["RUNTIME_BACKEND_PORT"] == "9200"
    assert "Feature: login" in captured["env"]["RUNTIME_JOURNEY"]


async def test_runtime_gate_journey_empty_when_no_done_gherkin(monkeypatch):
    monkeypatch.setattr(settings, "runtime_acceptance_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(settings, "node_cmd", "node")
    state = _done_frontend_state("rt-env-empty")  # story has no gherkin
    ws, _frontend = _prep_frontend(state)

    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return subprocess.CompletedProcess(cmd, 0, stdout="OK")

    monkeypatch.setattr(runtime_acceptance, "_run_node", _fake_run)
    await runtime_acceptance.arun_runtime_acceptance(state, ws)
    assert captured["env"]["RUNTIME_JOURNEY"] == ""


# ------------------------------------------------------------ exit-code = infra

async def test_runtime_gate_exit_2_is_infra(monkeypatch):
    """Contrat JS #4 : exit 2 = panne d'infra/environnement (NON réparable)."""
    monkeypatch.setattr(settings, "runtime_acceptance_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(settings, "node_cmd", "node")
    state = _done_frontend_state("rt-infra")
    ws, _frontend = _prep_frontend(state)

    monkeypatch.setattr(
        runtime_acceptance, "_run_node",
        lambda cmd, **k: subprocess.CompletedProcess(cmd, 2, stdout="playwright not installed"),
    )
    result = await runtime_acceptance.arun_runtime_acceptance(state, ws)
    assert result.ok is False
    assert result.infra is True


async def test_runtime_gate_exit_1_is_repairable(monkeypatch):
    """Exit 1 = échec d'intégration RÉPARABLE : infra reste False."""
    monkeypatch.setattr(settings, "runtime_acceptance_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(settings, "node_cmd", "node")
    state = _done_frontend_state("rt-repairable")
    ws, _frontend = _prep_frontend(state)

    monkeypatch.setattr(
        runtime_acceptance, "_run_node",
        lambda cmd, **k: subprocess.CompletedProcess(cmd, 1, stdout="blank page on /"),
    )
    result = await runtime_acceptance.arun_runtime_acceptance(state, ws)
    assert result.ok is False
    assert result.infra is False


async def test_runtime_launch_failure_is_infra(monkeypatch):
    """Un OSError au lancement (node absent) est une panne d'infra."""
    monkeypatch.setattr(settings, "runtime_acceptance_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(settings, "node_cmd", "node")
    state = _done_frontend_state("rt-launch-ko")
    ws, _frontend = _prep_frontend(state)

    def _boom(cmd, **k):
        raise OSError("node introuvable")

    monkeypatch.setattr(runtime_acceptance, "_run_node", _boom)
    result = await runtime_acceptance.arun_runtime_acceptance(state, ws)
    assert result.ok is False
    assert result.infra is True


# ------------------------------------------- finding 6 : non-python web backend

async def test_runtime_non_python_backend_warns_and_skips(monkeypatch):
    """Un backend web non-python sans frontend ne peut être vérifié : on skip en
    AVERTISSANT (pas de hard-block, finding 6)."""
    monkeypatch.setattr(settings, "runtime_acceptance_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    state = ProjectState(id="rt-go", name="svc", goal="g", backend_language=BackendLanguage.GO)
    state.stories = [UserStory(id="US-1", epic_id="E", title="t", status=StoryStatus.DONE)]
    ws = workspace_dir(state.id)
    ws.mkdir(parents=True, exist_ok=True)
    # main.py python-ish pour passer should_run's backend_web_candidate.
    (ws / "main.py").write_text("import fastapi\n", encoding="utf-8")

    result = await runtime_acceptance.arun_runtime_acceptance(state, ws)
    assert result.skipped is True
    assert result.ok is True
    assert "non-python" in result.detail


def test_javascript_runtime_lifecycle():
    script = Path(__file__).with_name("runtime_acceptance.test.cjs")
    result = subprocess.run([settings.node_cmd, "--test", str(script)], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


async def test_frontend_stack_never_starts_a_leftover_backend(monkeypatch):
    monkeypatch.setattr(settings, "runtime_acceptance_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    state = _done_frontend_state("pure-frontend")
    state.technical_stack = {"kind": "frontend", "frontend": "react", "backend": "none"}
    ws, _ = _prep_frontend(state)
    (ws / "main.py").write_text("import fastapi\n", encoding="utf-8")
    captured = []
    def run(cmd, **kwargs):
        captured.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="OK")
    monkeypatch.setattr(runtime_acceptance, "_run_node", run)
    assert (await runtime_acceptance.arun_runtime_acceptance(state, ws)).ok
    assert captured[0][-1] == "0"


async def test_runtime_cancellation_waits_for_worker_tree_cleanup(monkeypatch):
    monkeypatch.setattr(settings, "runtime_acceptance_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    state = _done_frontend_state("cancel-runtime")
    ws, _ = _prep_frontend(state)
    started = threading.Event()
    cleaned = threading.Event()
    def run(cmd, *, cancel_event, **kwargs):
        started.set()
        assert cancel_event.wait(2)
        time.sleep(0.02)
        cleaned.set()
        raise subprocess.TimeoutExpired(cmd, 2)
    monkeypatch.setattr(runtime_acceptance, "_run_node", run)
    task = asyncio.create_task(runtime_acceptance.arun_runtime_acceptance(state, ws))
    assert await asyncio.to_thread(started.wait, 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()


def test_runtime_timeout_reaps_the_actual_child_process(monkeypatch):
    original = subprocess.Popen
    processes = []
    def launch(*args, **kwargs):
        proc = original(*args, **kwargs)
        processes.append(proc)
        return proc
    monkeypatch.setattr(subprocess, "Popen", launch)
    with pytest.raises(subprocess.TimeoutExpired):
        runtime_acceptance._run_node(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cancel_event=threading.Event(), timeout=0.15,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
    assert processes and processes[0].poll() is not None


@pytest.mark.parametrize("manifest_name", [".autospec-bootstrap.json", ".autospec/bootstrap.json"])
def test_native_backend_is_detected_from_current_or_legacy_manifest(tmp_path, manifest_name):
    manifest = tmp_path / manifest_name
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"stack": {"kind": "api", "backend": "go"}}), encoding="utf-8")
    assert runtime_acceptance._backend_web_candidate(tmp_path)


def test_frontend_manifest_takes_precedence_over_legacy_backend_artifacts(tmp_path):
    (tmp_path / ".autospec-bootstrap.json").write_text(json.dumps({"stack": {"kind": "frontend"}}), encoding="utf-8")
    (tmp_path / "main.py").write_text("import fastapi\n", encoding="utf-8")
    assert not runtime_acceptance._backend_web_candidate(tmp_path)


def test_api_runtime_starts_and_cleans_a_real_owned_server_without_browser(tmp_path):
    server = tmp_path / "server.py"
    server.write_text(
        "import os\nfrom http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "class Handler(BaseHTTPRequestHandler):\n"
        " def do_GET(self):\n"
        "  self.send_response(200); self.end_headers(); self.wfile.write(b'{}')\n"
        "HTTPServer(('127.0.0.1', int(os.environ['RUNTIME_BACKEND_PORT'])), Handler).serve_forever()\n",
        encoding="utf-8",
    )
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    env = {key: value for key, value in os.environ.items() if key.upper() in {
        "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "PATHEXT",
    }}
    env.update(RUNTIME_BACKEND_PORT=str(port), RUNTIME_BACKEND_LANGUAGE="native",
               RUNTIME_BACKEND_COMMAND=json.dumps([sys.executable, "-u", str(server)]))
    script = Path(__file__).parents[1] / "scripts" / "runtime_acceptance.js"
    result = runtime_acceptance._run_node(
        [settings.node_cmd, str(script), str(tmp_path), "5000", "", "1"],
        cancel_event=threading.Event(), timeout=15, cwd=tmp_path, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, result.stdout
    assert "OK API" in result.stdout
    assert "DEP0190" not in result.stdout
    with socket.socket() as check:
        check.settimeout(0.5)
        assert check.connect_ex(("127.0.0.1", port)) != 0, "runtime leaked its server"


def test_runtime_resolves_and_executes_real_npm_without_command_shell():
    gate = Path(__file__).parents[1] / "scripts" / "runtime_acceptance.js"
    script = (
        "const gate=require(process.argv[1]);"
        "const command=gate.resolveCommand(process.argv[2],['--version']);"
        "const r=require('node:child_process').spawnSync(command.cmd,command.args,{shell:false,encoding:'utf8'});"
        "process.stdout.write(r.stdout||'');process.stderr.write(r.stderr||'');"
        "process.exitCode=r.status===null?1:r.status;"
    )
    result = subprocess.run([settings.node_cmd, "-e", script, str(gate), settings.npm_cmd],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip()
    assert "DEP0190" not in result.stderr
