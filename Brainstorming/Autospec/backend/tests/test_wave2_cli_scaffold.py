"""Wave 2 - FACTORY_IMPROVEMENTS #4 (scaffold part): the generated ``main.py``
is a real CLI entry point instead of a mute ``register()`` loop.

Contract covered here:
  * ``main(argv=None)`` reads ``sys.argv[1:]`` by default and returns an int;
  * a hook whose signature accepts a positional parameter (or ``*args``) is
    called as ``register(argv)``, a hook without parameter as ``register()``;
  * ``--help`` / ``-h`` (or an empty argv when no hook consumes arguments)
    prints a NON EMPTY banner: application name + discovered feature modules;
  * the zero-feature message is unchanged (existing tests look it up);
  * a hook raising ``SystemExit`` propagates; a non-zero int return becomes the
    exit code.

The end-to-end checks generate a real workspace and run ``python main.py``
through a subprocess, so the template is proven to be valid Python once
``str.format`` has rendered it (doubled braces included).
"""

import os
import subprocess
import sys

from autospec.models import ProjectState
from autospec.orchestrator import workspace

ARGV_FEATURE = '''"""Fake feature consuming the relayed argv."""

import pathlib

TRACE = pathlib.Path(__file__).with_name("trace_alpha.txt")


def register(argv):
    TRACE.write_text("alpha:" + ",".join(argv), encoding="utf-8")
'''

BARE_FEATURE = '''"""Fake legacy feature: register() without any parameter."""

import pathlib

TRACE = pathlib.Path(__file__).with_name("trace_beta.txt")


def register():
    TRACE.write_text("beta", encoding="utf-8")
'''


def _scaffold(tmp_path, monkeypatch, project_id: str = "cli-scaffold"):
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    state = ProjectState(id=project_id, name="Cli Scaffold", goal="g")
    ws = workspace._scaffold_python(state, ui_tests_enabled=False)
    return ws, workspace.package_name(state)


def _run_main(ws, *args):
    # Same UTF-8 stdio the orchestrator forces on the generated app (BUG1),
    # otherwise the accented zero-feature message comes back as mojibake.
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, "main.py", *args],
        cwd=str(ws),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


# ------------------------------------------------------- template rendering

def test_main_template_renders_valid_python():
    """The template is a str.format: literal braces must stay doubled."""
    import ast

    rendered = workspace.MAIN_TEMPLATE.format(package="demo_pkg")
    ast.parse(rendered)
    assert 'APP_NAME = "demo_pkg"' in rendered
    assert "{package}" not in rendered and "{{" not in rendered


def test_scaffold_main_declares_the_cli_contract(tmp_path, monkeypatch):
    ws, pkg = _scaffold(tmp_path, monkeypatch)
    main_text = (ws / "main.py").read_text(encoding="utf-8")
    assert "def main(argv: list | None = None) -> int:" in main_text
    assert "sys.argv[1:]" in main_text
    assert f"from {pkg}.features import discover" in main_text
    assert 'HELP_FLAGS = ("-h", "--help")' in main_text
    assert "raise SystemExit(main())" in main_text
    # The zero-feature message stays byte-identical (older tests grep it).
    assert "Projet généré par Autospec" in main_text


# ------------------------------------------------------------- end to end

def test_help_lists_features_and_calls_both_hook_shapes(tmp_path, monkeypatch):
    """`python main.py --help`: non empty stdout, code 0, both hooks called."""
    ws, pkg = _scaffold(tmp_path, monkeypatch, "cli-help")
    features = ws / pkg / "features"
    (features / "alpha.py").write_text(ARGV_FEATURE, encoding="utf-8")
    (features / "beta.py").write_text(BARE_FEATURE, encoding="utf-8")

    proc = _run_main(ws, "--help")

    assert proc.returncode == 0, proc.stdout
    assert proc.stdout.strip(), "the --help output must not be empty"
    assert pkg in proc.stdout
    assert "alpha" in proc.stdout and "beta" in proc.stdout
    # Both hook shapes ran, and the argv-aware one received the relayed argv.
    assert (features / "trace_alpha.txt").read_text(encoding="utf-8") == "alpha:--help"
    assert (features / "trace_beta.txt").read_text(encoding="utf-8") == "beta"


def test_short_help_flag_is_supported(tmp_path, monkeypatch):
    ws, pkg = _scaffold(tmp_path, monkeypatch, "cli-h")
    (ws / pkg / "features" / "alpha.py").write_text(ARGV_FEATURE, encoding="utf-8")

    proc = _run_main(ws, "-h")

    assert proc.returncode == 0, proc.stdout
    assert pkg in proc.stdout and "alpha" in proc.stdout


def test_bare_run_without_consumer_still_prints_the_banner(tmp_path, monkeypatch):
    """Empty argv + no hook consuming args: the smoke run sees real output."""
    ws, pkg = _scaffold(tmp_path, monkeypatch, "cli-bare")
    (ws / pkg / "features" / "beta.py").write_text(BARE_FEATURE, encoding="utf-8")

    proc = _run_main(ws)

    assert proc.returncode == 0, proc.stdout
    assert pkg in proc.stdout and "beta" in proc.stdout
    assert (ws / pkg / "features" / "trace_beta.txt").exists()


def test_argv_is_relayed_to_the_consuming_hook(tmp_path, monkeypatch):
    ws, pkg = _scaffold(tmp_path, monkeypatch, "cli-argv")
    features = ws / pkg / "features"
    (features / "alpha.py").write_text(ARGV_FEATURE, encoding="utf-8")

    proc = _run_main(ws, "add", "--count", "3")

    assert proc.returncode == 0, proc.stdout
    assert (features / "trace_alpha.txt").read_text(encoding="utf-8") == "alpha:add,--count,3"


def test_zero_feature_keeps_the_legacy_message(tmp_path, monkeypatch):
    ws, _pkg = _scaffold(tmp_path, monkeypatch, "cli-empty")

    proc = _run_main(ws)

    assert proc.returncode == 0, proc.stdout
    assert "Projet généré par Autospec" in proc.stdout


def test_hook_systemexit_propagates_as_exit_code(tmp_path, monkeypatch):
    """argparse inside a feature: SystemExit is NOT swallowed."""
    ws, pkg = _scaffold(tmp_path, monkeypatch, "cli-exit")
    (ws / pkg / "features" / "boom.py").write_text(
        "def register(argv):\n    raise SystemExit(3)\n", encoding="utf-8"
    )

    proc = _run_main(ws, "whatever")

    assert proc.returncode == 3, proc.stdout


def test_non_zero_int_return_becomes_the_exit_code(tmp_path, monkeypatch):
    ws, pkg = _scaffold(tmp_path, monkeypatch, "cli-status")
    (ws / pkg / "features" / "fail.py").write_text(
        "def register(argv):\n    return 2\n", encoding="utf-8"
    )

    proc = _run_main(ws, "run")

    assert proc.returncode == 2, proc.stdout


def test_truthy_non_int_return_stays_a_success(tmp_path, monkeypatch):
    """A hook returning a str or True must not turn into a failing exit code."""
    ws, pkg = _scaffold(tmp_path, monkeypatch, "cli-truthy")
    features = ws / pkg / "features"
    (features / "s.py").write_text("def register():\n    return 'hello'\n", encoding="utf-8")
    (features / "b.py").write_text("def register():\n    return True\n", encoding="utf-8")

    proc = _run_main(ws)

    assert proc.returncode == 0, proc.stdout


# ---------------------------------------------------- in-process signature

def test_accepts_argv_recognises_the_hook_shapes(tmp_path, monkeypatch):
    """_accepts_argv is exercised directly on every shape a dev may write."""
    ws, pkg = _scaffold(tmp_path, monkeypatch, "cli-sig")
    namespace: dict = {}
    source = (ws / "main.py").read_text(encoding="utf-8")
    # Execute only the helper block (no import of the generated package).
    head = source.split("from " + pkg + ".features import discover")[0]
    tail = source.split("def _accepts_argv", 1)[1].split("def _feature_names", 1)[0]
    exec(head + "def _accepts_argv" + tail, namespace)  # noqa: S102 - template probe
    accepts = namespace["_accepts_argv"]

    assert accepts(lambda argv: None) is True
    assert accepts(lambda *args: None) is True
    assert accepts(lambda argv=None: None) is True
    assert accepts(lambda: None) is False
    assert accepts(lambda *, flag=1: None) is False
    assert accepts(object()) is False  # opaque callable: called without argv
