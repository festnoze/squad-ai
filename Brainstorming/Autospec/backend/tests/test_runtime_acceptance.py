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








def test_javascript_runtime_lifecycle():
    script = Path(__file__).with_name("runtime_acceptance.test.cjs")
    result = subprocess.run([settings.node_cmd, "--test", str(script)], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr




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


@pytest.mark.asyncio
@pytest.mark.parametrize("ok,infra",[(True,False),(False,False),(False,True)])
async def test_runtime_gate_delegates_to_isolated_foundation(monkeypatch,ok,infra):
    from autospec.orchestrator import bootstrap
    monkeypatch.setattr(settings,"fake_agents",False)
    monkeypatch.setattr(settings,"runtime_acceptance_enabled",True)
    state=_done_frontend_state("isolated-rt")
    ws,_=_prep_frontend(state)
    calls=[]
    async def verify(project,root,**kwargs):
        calls.append((project,root,kwargs))
        return bootstrap.BootstrapResult(ok,"isolated evidence",infra=infra)
    monkeypatch.setattr(bootstrap,"verify_runtime",verify)
    monkeypatch.setattr(runtime_acceptance,"_run_node",lambda *_args,**_kwargs:pytest.fail("legacy host JS gate"))
    result=await runtime_acceptance.arun_runtime_acceptance(state,ws,timeout_s=3)
    assert result.ok==ok and result.infra==infra and not result.skipped
    assert calls[0][1]==ws and calls[0][2]["repair_dependencies"] is True
    assert calls[0][2]["timeout_s"]==3

@pytest.mark.asyncio
async def test_runtime_cancellation_waits_for_isolated_cleanup(monkeypatch):
    from autospec.orchestrator import bootstrap
    monkeypatch.setattr(settings,"fake_agents",False)
    monkeypatch.setattr(settings,"runtime_acceptance_enabled",True)
    state=_done_frontend_state("isolated-cancel");ws,_=_prep_frontend(state)
    started,cleaned=asyncio.Event(),asyncio.Event()
    async def verify(*args,**kwargs):
        started.set()
        try: await asyncio.sleep(60)
        finally:
            await asyncio.sleep(.02);cleaned.set()
    monkeypatch.setattr(bootstrap,"verify_runtime",verify)
    task=asyncio.create_task(runtime_acceptance.arun_runtime_acceptance(state,ws))
    await started.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert cleaned.is_set()

def test_done_journey_is_retained_as_contract_data():
    state=_done_frontend_state()
    state.stories[0].gherkin="Feature: login"
    assert runtime_acceptance._done_journey(state)=="Feature: login"
