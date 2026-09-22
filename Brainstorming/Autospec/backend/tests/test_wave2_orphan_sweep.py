"""FACTORY_IMPROVEMENTS (completes fixes #10/#13): boot-time sweep of the
workspace orphans.

The port-scoped killer only reaps what holds the ONE port a gate is about to
use, so a backend that died - or a repair agent that bypassed its own cleanup -
leaves smoke runs, uvicorn reload supervisors and dev servers behind. They
resurface much later as an "infra" park on an unrelated project. At boot nothing
of ours is running yet, so anything whose command line points inside the
workspace root is an orphan by construction.

No real process is ever touched here: ``subprocess.run`` is replaced by a fake
process table, and the kill commands the sweep emits are captured instead of
executed. ``orphan_sweep_on_boot`` is pinned OFF in conftest for exactly that
reason - the pin is a SAFETY rule, not a hermeticity one.
"""

import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from autospec.config import settings
from autospec.orchestrator.pipeline import Pipeline

SELF = os.getpid()


def _install_table(monkeypatch, rows, *, posix=False):
    """Fake the process table the sweep probes, and capture the kills it emits.

    ``rows`` is a list of ``(pid, ppid, command_line)``. The Windows branch is
    answered by re-implementing what the generated PowerShell asks for, using
    the needle the PRODUCTION code embedded in its own script - so the test also
    pins that the needle really is the resolved workspace root.

    Returns the list of killed pids, in emission order.
    """
    monkeypatch.setattr(os, "name", "posix" if posix else "nt")
    killed: list[int] = []

    def runner(cmd, **_kwargs):
        argv = [str(c) for c in cmd]
        if argv[0] == "powershell":
            script = argv[-1]
            marker = "Contains('"
            start = script.index(marker) + len(marker)
            needle = script[start:script.index("')", start)]
            out = "\n".join(
                f"{pid}|{ppid}|{1 if needle in cmdline.lower() else 0}"
                for pid, ppid, cmdline in rows
            )
            return subprocess.CompletedProcess(args=argv, returncode=0, stdout=out)
        if argv[0] == "ps":
            out = "\n".join(f"{pid} {ppid} {cmdline}" for pid, ppid, cmdline in rows)
            return subprocess.CompletedProcess(args=argv, returncode=0, stdout=out)
        if argv[0] == "taskkill":
            killed.append(int(argv[argv.index("/PID") + 1]))
            return subprocess.CompletedProcess(args=argv, returncode=0, stdout="")
        if argv[0] == "kill":
            killed.append(int(argv[-1]))
            return subprocess.CompletedProcess(args=argv, returncode=0, stdout="")
        if argv[0] == "pkill":
            return subprocess.CompletedProcess(args=argv, returncode=0, stdout="")
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(subprocess, "run", runner)
    return killed


# ------------------------------------------------------------------- selection

def test_only_processes_inside_the_workspace_are_swept(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    inside = os.path.realpath(root)
    rows = [
        (SELF, 1, "python -m autospec.api.server"),          # us, outside
        (1000, 1, f"uv run python {inside}/proj-a/main.py"),  # orphan smoke run
        (2000, 1, r"C:\Program Files\Editor\editor.exe"),     # an innocent third party
        (3000, 1, "node /home/dev/other-project/server.js"),  # another one
    ]
    killed = _install_table(monkeypatch, rows)

    assert Pipeline._sweep_workspace_orphans(root) == 1
    assert killed == [1000]


def test_the_sweep_climbs_to_the_topmost_workspace_ancestor(monkeypatch, tmp_path):
    """A uvicorn reload SUPERVISOR does not hold anything itself and respawns a
    worker right after the kill: only the top of the workspace chain is killed,
    and killing it takes the whole tree (/T)."""
    root = tmp_path / "workspace"
    root.mkdir()
    inside = os.path.realpath(root)
    rows = [
        (SELF, 1, "python -m autospec.api.server"),
        (500, 1, f"uv run python {inside}/proj-a/main.py"),        # supervisor
        (501, 500, f"python {inside}/proj-a/.venv/uvicorn worker"),  # its worker
        (502, 501, f"python {inside}/proj-a/child"),                 # a grandchild
    ]
    killed = _install_table(monkeypatch, rows)

    assert Pipeline._sweep_workspace_orphans(root) == 1
    assert killed == [500]


def test_the_current_process_and_its_ancestors_are_never_killed(monkeypatch, tmp_path):
    """Hard safety rule: even when OUR OWN command line mentions the workspace
    (a backend launched from inside it), neither we nor our ancestors may die.
    A CHILD of ours that lives in the workspace is still an orphan and goes."""
    root = tmp_path / "workspace"
    root.mkdir()
    inside = os.path.realpath(root)
    rows = [
        (7000, 1, f"powershell -c cd {inside}"),      # our grand-parent, in the ws
        (7001, 7000, f"bash {inside}/launch.sh"),     # our parent, in the ws
        (SELF, 7001, f"python -m autospec.api.server --root {inside}"),
        (7002, SELF, f"uv run python {inside}/proj-a/main.py"),  # our leaked child
        (8000, 1, f"python {inside}/proj-b/main.py"),            # a true orphan
    ]
    killed = _install_table(monkeypatch, rows)

    assert Pipeline._sweep_workspace_orphans(root) == 2
    assert sorted(killed) == [7002, 8000]
    assert SELF not in killed and 7000 not in killed and 7001 not in killed


def test_an_empty_workspace_kills_nothing(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    rows = [(SELF, 1, "python -m autospec.api.server"), (9000, 1, "chrome.exe")]
    killed = _install_table(monkeypatch, rows)

    assert Pipeline._sweep_workspace_orphans(root) == 0
    assert killed == []


def test_posix_sends_sigterm_to_the_subtree(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    inside = os.path.realpath(root)
    rows = [
        (SELF, 1, "python -m autospec.api.server"),
        (4242, 1, f"uv run python {inside}/proj-a/main.py"),
    ]
    signals: list[list[str]] = []
    killed = _install_table(monkeypatch, rows, posix=True)
    real_run = subprocess.run

    def spy(cmd, **kwargs):
        argv = [str(c) for c in cmd]
        if argv[0] in ("kill", "pkill"):
            signals.append(argv)
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)

    assert Pipeline._sweep_workspace_orphans(root) == 1
    assert killed == [4242]
    assert signals == [["pkill", "-15", "-P", "4242"], ["kill", "-15", "4242"]]


def test_a_failing_probe_never_raises(monkeypatch, tmp_path):
    """A boot cleanup that explodes must not take the backend down with it."""
    monkeypatch.setattr(os, "name", "nt")

    def boom(*_a, **_k):
        raise OSError("powershell introuvable")

    monkeypatch.setattr(subprocess, "run", boom)
    assert Pipeline._sweep_workspace_orphans(tmp_path / "workspace") == 0


def test_garbage_lines_are_ignored(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    inside = os.path.realpath(root)
    monkeypatch.setattr(os, "name", "nt")
    killed: list[int] = []

    def runner(cmd, **_kwargs):
        argv = [str(c) for c in cmd]
        if argv[0] == "powershell":
            return subprocess.CompletedProcess(
                args=argv, returncode=0,
                stdout=(
                    "\n"
                    "Get-CimInstance : Access is denied.\n"
                    "not|a|row\n"
                    f"{SELF}|1|0\n"
                    "6000|1|1\n"
                ),
            )
        killed.append(int(argv[argv.index("/PID") + 1]))
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="")

    monkeypatch.setattr(subprocess, "run", runner)
    assert inside  # the needle is built from the resolved root, garbage or not
    assert Pipeline._sweep_workspace_orphans(root) == 1
    assert killed == [6000]


# ------------------------------------------------------------------ the boot hook

@pytest.fixture
def boot(monkeypatch):
    """Drive ``server._arecover_projects`` with the sweep replaced by a spy."""
    from autospec.api import server

    seen: list[Path] = []
    monkeypatch.setattr(server, "list_states", lambda: [])
    monkeypatch.setattr(server, "recover_projects", lambda states: [])
    monkeypatch.setattr(
        Pipeline, "_sweep_workspace_orphans",
        staticmethod(lambda ws_root: seen.append(Path(ws_root)) or 0),
    )
    return server, seen


async def test_the_boot_sweeps_when_the_flag_is_on(boot, monkeypatch):
    server, seen = boot
    monkeypatch.setattr(settings, "orphan_sweep_on_boot", True)
    monkeypatch.setattr(settings, "fake_agents", False)

    await server._arecover_projects()

    assert seen == [Path(settings.workspace_root)]


async def test_the_boot_does_not_sweep_in_fake_agents_mode(boot, monkeypatch):
    """FAKE_AGENTS never spawns a real process, so there is nothing to reap and
    a demo run must not shell out to PowerShell at startup."""
    server, seen = boot
    monkeypatch.setattr(settings, "orphan_sweep_on_boot", True)
    monkeypatch.setattr(settings, "fake_agents", True)

    await server._arecover_projects()

    assert seen == []


async def test_the_boot_does_not_sweep_when_the_flag_is_off(boot, monkeypatch):
    server, seen = boot
    monkeypatch.setattr(settings, "orphan_sweep_on_boot", False)
    monkeypatch.setattr(settings, "fake_agents", False)

    await server._arecover_projects()

    assert seen == []


async def test_a_sweep_failure_does_not_break_the_recovery(monkeypatch):
    """Recovery must still register the projects when the sweep explodes."""
    from autospec.api import server

    recovered: list[str] = []
    monkeypatch.setattr(server, "list_states", lambda: [])
    monkeypatch.setattr(
        server, "recover_projects", lambda states: recovered.append("done") or []
    )

    def boom(_ws_root):
        raise RuntimeError("no powershell here")

    monkeypatch.setattr(Pipeline, "_sweep_workspace_orphans", staticmethod(boom))
    monkeypatch.setattr(settings, "orphan_sweep_on_boot", True)
    monkeypatch.setattr(settings, "fake_agents", False)

    await asyncio.wait_for(server._arecover_projects(), timeout=10)

    assert recovered == ["done"]
