"""Wave 7: the product evaluator (E6) must never hang on a long-running app.

Supervised run 2026-09-22 (project drv-p3-9ae648a7): the evaluator phase started
at 11:23:53 and NEVER returned. ``_aexercise_product`` used
``subprocess.run(..., stdout=PIPE, timeout=...)`` to launch ``uv run python
main.py``; at the timeout ``subprocess.run`` killed only the DIRECT child
(``uv.exe``) while the grandchild (``python`` running uvicorn on :8000) survived
with the inherited stdout pipe. The internal ``communicate()`` then blocked on
that pipe forever: the phase froze, the pilot hit its 2 h ceiling, and the
server was still listening an hour later.

These tests are deterministic and platform-neutral: they launch the CURRENT
interpreter on a tiny ``main.py`` that spawns a real GRANDCHILD inheriting
stdout, and they check both halves of the contract - the call returns fast, and
the grandchild is dead afterwards.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import ProjectState
from autospec.orchestrator import toolchain
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir

# main.py that spawns a grandchild (stdout INHERITED: it holds our pipe open)
# and then stays alive, like a server. This is the exact shape of the observed
# defect: uv -> python(uvicorn).
SPAWN_AND_HANG = (
    "import pathlib, subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    "pathlib.Path('grandchild.pid').write_text(str(child.pid), encoding='utf-8')\n"
    "print('server up', flush=True)\n"
    "time.sleep(60)\n"
)

# Same grandchild, but main.py EXITS immediately: the process we wait on is
# gone while the pipe stays open on the detached grandchild.
SPAWN_AND_EXIT = (
    "import pathlib, subprocess, sys\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    "pathlib.Path('grandchild.pid').write_text(str(child.pid), encoding='utf-8')\n"
    "print('bootstrap done', flush=True)\n"
)

HANG_ALONE = "import time\nprint('listening', flush=True)\ntime.sleep(60)\n"

EXIT_WITH_OUTPUT = (
    "print('hello from the delivered app')\n"
    "raise SystemExit(0)\n"
)

# ~1 MB on stdout, far above the evaluator's capture cap.
FLOOD_OUTPUT = (
    "import sys\n"
    "line = 'x' * 99 + '\\n'\n"
    "for _ in range(10000):\n"
    "    sys.stdout.write(line)\n"
    "sys.stdout.flush()\n"
)


# ------------------------------------------------------------------ helpers

def _alive(pid: int) -> bool:
    """Is ``pid`` still running? ``os.kill(pid, 0)`` is NOT portable: on Windows
    os.kill TERMINATES the target whatever the signal, so we ask tasklist."""
    if os.name == "nt":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {int(pid)}", "/NH", "/FO", "CSV"],
            capture_output=True, text=True, timeout=30,
        ).stdout or ""
        return f'"{int(pid)}"' in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # alive, owned by someone else
        return True
    return True


def _wait_dead(pid: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.2)
    return not _alive(pid)


def _force_kill(pid: int) -> None:
    """Never leave a test process behind, whatever the assertions did."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(int(pid))],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False, timeout=30,
            )
        else:
            os.kill(pid, 9)
    except (OSError, subprocess.SubprocessError):
        pass


def _grandchild_pid(ws: Path, timeout: float = 10.0) -> int:
    deadline = time.monotonic() + timeout
    pid_file = ws / "grandchild.pid"
    while time.monotonic() < deadline:
        try:
            return int(pid_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            time.sleep(0.1)
    raise AssertionError(f"main.py never wrote {pid_file}")


def _pipeline(monkeypatch, project_id: str, main_py: str, *,
              timeout: float = 2.0, profile: str = "cli") -> tuple[Pipeline, Path]:
    """A pipeline whose delivered product is ``main_py``, launched with THIS
    interpreter instead of ``uv run python`` (uv is not the contract here)."""
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(settings, "sandbox_enabled", False)
    monkeypatch.setattr(settings, "evaluator_run_timeout_s", timeout)
    monkeypatch.setattr(
        toolchain, "run_command",
        lambda language, args=None: [sys.executable, "main.py", *(args or [])],
    )
    state = ProjectState(id=project_id, name="app", goal="g")
    state.product_profile = profile
    ws = workspace_dir(state.id)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text(main_py, encoding="utf-8")
    return Pipeline(state, FakeRunner([])), ws


def _record_events(monkeypatch, pipeline: Pipeline) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        pipeline.monitor, "event",
        lambda kind, **fields: events.append((kind, fields)),
    )
    return events


# -------------------------------------------------------------- the defect

async def test_timeout_kills_the_whole_tree_and_returns(monkeypatch):
    """The regression test: a server-like main.py with a live grandchild must
    not freeze the phase, and must leave NOTHING running behind."""
    pipeline, ws = _pipeline(monkeypatch, "w7-tree-hang", SPAWN_AND_HANG)
    events = _record_events(monkeypatch, pipeline)

    started = time.monotonic()
    output = await pipeline._aexercise_product()
    elapsed = time.monotonic() - started

    assert elapsed < 20, f"the evaluator hung for {elapsed:.1f}s"
    assert "toujours actif après" in output
    assert "server up" in output  # startup output is kept, as before

    pid = _grandchild_pid(ws)
    try:
        assert _wait_dead(pid), f"grandchild {pid} survived the timeout"
    finally:
        _force_kill(pid)

    assert events and events[0][0] == "evaluator_run"
    assert events[0][1] == {"ok": True, "timed_out": True, "killed_tree": True}


async def test_detached_grandchild_holding_the_pipe_does_not_block(monkeypatch):
    """main.py EXITS but its grandchild keeps the stdout pipe open: the old
    ``communicate()`` blocked there too. We must return on the exit code."""
    pipeline, ws = _pipeline(monkeypatch, "w7-tree-exit", SPAWN_AND_EXIT, timeout=30.0)

    started = time.monotonic()
    output = await pipeline._aexercise_product()
    elapsed = time.monotonic() - started

    pid = _grandchild_pid(ws)
    _force_kill(pid)

    assert elapsed < 20, f"the evaluator hung for {elapsed:.1f}s"
    assert "(processus terminé, code 0)" in output
    assert "tube ouvert" in output  # the truncation is reported, not silent


async def test_web_product_also_sweeps_the_port_holders(monkeypatch):
    """Like the smoke gate, a WEB product gets a double tap: a uvicorn reload
    supervisor can respawn a worker that still holds the port."""
    pipeline, _ws = _pipeline(monkeypatch, "w7-tree-web", HANG_ALONE, profile="api")
    swept: list[tuple[int, Path]] = []
    monkeypatch.setattr(
        Pipeline, "_kill_workspace_port_holders",
        staticmethod(lambda port, ws: swept.append((port, ws)) or 0),
    )

    output = await pipeline._aexercise_product()

    assert "toujours actif après" in output
    assert len(swept) == 1 and swept[0][0] > 0


async def test_cli_product_does_not_sweep_ports(monkeypatch):
    """A CLI product never listens: no port sweep, no PowerShell/lsof call."""
    pipeline, _ws = _pipeline(monkeypatch, "w7-tree-cli", HANG_ALONE, profile="cli")
    swept: list[tuple[int, Path]] = []
    monkeypatch.setattr(
        Pipeline, "_kill_workspace_port_holders",
        staticmethod(lambda port, ws: swept.append((port, ws)) or 0),
    )

    await pipeline._aexercise_product()

    assert swept == []


# ------------------------------------------------------------ nominal paths

async def test_process_that_exits_is_reported_with_its_code_and_output(monkeypatch):
    pipeline, _ws = _pipeline(monkeypatch, "w7-tree-ok", EXIT_WITH_OUTPUT, timeout=30.0)
    events = _record_events(monkeypatch, pipeline)

    output = await pipeline._aexercise_product()

    assert output.startswith("(processus terminé, code 0)")
    assert "hello from the delivered app" in output
    assert events[0] == ("evaluator_run", {"ok": True, "timed_out": False, "killed_tree": False})


async def test_flood_of_output_is_capped_without_blocking(monkeypatch):
    """A chatty app must neither blow up the evaluator prompt nor deadlock on a
    full pipe: the reader drains everything, the buffer stays bounded."""
    pipeline, _ws = _pipeline(monkeypatch, "w7-tree-flood", FLOOD_OUTPUT, timeout=60.0)

    started = time.monotonic()
    output = await pipeline._aexercise_product()
    elapsed = time.monotonic() - started

    assert elapsed < 30, f"the capture took {elapsed:.1f}s"
    assert output.startswith("(processus terminé, code 0)")
    # 1 MB written, at most the cap (plus the short header) kept.
    assert 100_000 < len(output) <= 200_000 + 200


async def test_unlaunchable_command_is_reported(monkeypatch):
    pipeline, _ws = _pipeline(monkeypatch, "w7-tree-oserror", EXIT_WITH_OUTPUT)
    monkeypatch.setattr(
        toolchain, "run_command",
        lambda language, args=None: ["autospec-does-not-exist-w7", "main.py"],
    )
    events = _record_events(monkeypatch, pipeline)

    output = await pipeline._aexercise_product()

    assert output.startswith("(lancement impossible")
    assert events[0][1]["ok"] is False


async def test_demo_mode_never_spawns_a_process(monkeypatch):
    pipeline, _ws = _pipeline(monkeypatch, "w7-tree-demo", SPAWN_AND_HANG)
    monkeypatch.setattr(settings, "fake_agents", True)

    def _boom(*_a, **_k):  # pragma: no cover - must never run
        raise AssertionError("demo mode must not launch the product")

    monkeypatch.setattr(subprocess, "Popen", _boom)

    assert "démo" in await pipeline._aexercise_product()


@pytest.mark.skipif(os.name != "nt", reason="taskkill /T is the Windows tree kill")
def test_kill_tree_is_the_windows_tree_killer(monkeypatch):
    """Guard the mechanism itself: the timeout path must shell out to a TREE
    kill, never to a plain terminate()."""
    calls: list[list[str]] = []
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kwargs: calls.append([str(c) for c in cmd]) or
        subprocess.CompletedProcess(args=cmd, returncode=0),
    )

    class _Live:
        pid = 4321

        def poll(self):
            return None

    assert Pipeline._kill_tree(_Live()) is True
    assert calls and calls[0][:4] == ["taskkill", "/F", "/T", "/PID"]
