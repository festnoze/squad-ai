"""CLI acceptance at the isolated interface, plus an opt-in real Linux probe.

The former host Popen fixtures are retired. Unit fixtures test the gate's
decision and exact argv; only the real Docker test executes product source.
"""
import os
from pathlib import Path

import pytest

from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import ProjectState
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir

MUTE_MAIN = "raise SystemExit(0)\n"
HELPFUL_MAIN = "print('Usage: main.py --help')\n"
BROKEN_HELP_MAIN = "import sys\nif '--help' in sys.argv: sys.stderr.write('unrecognized argument --help'); raise SystemExit(2)\n"
STDERR_ONLY_MAIN = "import sys\nsys.stderr.write('Creating virtual environment...')\n"


def _state(project_id):
    return ProjectState(id=project_id, name="cli", goal="CLI", product_profile="cli")


def _scaffold(ws, source):
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text(source, encoding="utf-8")
    (ws / "pyproject.toml").write_text(
        '[project]\nname="cli-probe"\nversion="0.1.0"\nrequires-python=">=3.12"\ndependencies=[]\n')
    return ws


def _isolated_fixture(monkeypatch):
    calls = []
    class Validator:
        def __init__(self, *a, **kw): pass
        def run_captured(self, root, ecosystem, command, *, mode):
            assert ecosystem == "python" and mode == "runtime"
            assert command[0] == "/opt/venv/bin/python"
            calls.append(command[1:])
            source = (Path(root) / "main.py").read_text()
            if source == HELPFUL_MAIN:
                return 0, "Usage: main.py --help", "", None
            if source == BROKEN_HELP_MAIN and "--help" in command:
                return 2, "", "unrecognized argument --help", None
            if source == STDERR_ONLY_MAIN:
                return 0, "", "Creating virtual environment...", None
            assert source in {MUTE_MAIN, BROKEN_HELP_MAIN}
            return 0, "", "", None
    monkeypatch.setattr("autospec.orchestrator.isolated_validation.IsolatedValidator", Validator)
    return calls


@pytest.mark.parametrize("source,ok,detail", [
    (MUTE_MAIN, False, "muet"), (HELPFUL_MAIN, True, "--help"),
    (BROKEN_HELP_MAIN, False, "unrecognized argument"), (STDERR_ONLY_MAIN, False, "muet"),
])
def test_isolated_cli_help_decision_and_separate_stdout(monkeypatch, source, ok, detail):
    calls = _isolated_fixture(monkeypatch)
    monkeypatch.setattr(settings, "smoke_cli_help", True)
    state = _state("cli-help-decision")
    root = _scaffold(workspace_dir(state.id), source)
    observed = Pipeline(state, ScriptedRunner())._smoke_run_python(root)
    assert observed[0] is ok and detail in observed[1]
    assert calls == [["main.py"], ["main.py", "--help"]]


def test_flag_off_requires_only_normal_exit(monkeypatch):
    calls = _isolated_fixture(monkeypatch)
    monkeypatch.setattr(settings, "smoke_cli_help", False)
    state = _state("cli-help-off")
    root = _scaffold(workspace_dir(state.id), MUTE_MAIN)
    assert Pipeline(state, ScriptedRunner())._smoke_run_python(root) == (True, "CLI exécuté (code 0)")
    assert calls == [["main.py"]]


def test_web_product_never_uses_cli_or_host_port_probe(monkeypatch):
    calls = _isolated_fixture(monkeypatch)
    state = _state("web-not-cli")
    state.product_profile = "api"
    root = _scaffold(workspace_dir(state.id), MUTE_MAIN)
    ok, detail = Pipeline(state, ScriptedRunner())._smoke_run_python(root)
    assert not ok and "asynchronous isolated runtime" in detail
    assert calls == []


def test_helper_discards_legacy_host_argv_and_environment(monkeypatch, tmp_path):
    calls = _isolated_fixture(monkeypatch)
    _scaffold(tmp_path, HELPFUL_MAIN)
    ok, detail = Pipeline._smoke_cli_help_run(tmp_path,
        ["host-python", "--unsafe-launch"], {"ANTHROPIC_API_KEY": "not-forwarded"}, 5)
    assert ok and "--help" in detail
    assert calls == [["main.py", "--help"]]


@pytest.mark.skipif(os.getenv("AUTOSPEC_REAL_LINUX_VALIDATION") != "1", reason="explicit real Linux product probe")
def test_real_linux_cli_nominal_and_stderr_only_negative(monkeypatch):
    from autospec.orchestrator import acceptance
    from autospec.orchestrator.validation_environment import LinuxEnvironmentManager
    state = _state("real-isolated-cli")
    root = _scaffold(workspace_dir(state.id), HELPFUL_MAIN)
    manager = LinuxEnvironmentManager(acceptance.supervisor_root(state.id) / "environments", timeout=300)
    manager.ensure_lock(root, "python")
    monkeypatch.setattr(settings, "smoke_run_timeout_s", 300)
    monkeypatch.setattr(settings, "smoke_cli_help", True)
    pipeline = Pipeline(state, ScriptedRunner())
    assert pipeline._smoke_run_python(root)[0]
    (root / "main.py").write_text(STDERR_ONLY_MAIN)
    ok, detail = pipeline._smoke_run_python(root)
    assert not ok and "muet" in detail
    assert not (root / ".venv").exists()
