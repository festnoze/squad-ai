"""ClaudeCodeRunner against a fake CLI (hermetic), plus one opt-in real session."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from autospec.core.agent import (
    DEV_ALLOWED,
    QA_ALLOWED,
    ClaudeCodeRunner,
    _child_env,
    build_argv,
    parse_cli_output,
    resolve_claude_command,
)
from autospec.core.ports import AgentCall, AgentError, Capability
from autospec.core.settings import Settings

from tests_v2.fixtures.fake_claude import SUCCESS

FAKE = Path(__file__).parent / "fixtures" / "fake_claude.py"
SETTINGS = Settings(claude_cmd="claude", model="sonnet")
SYSTEM_FILE = Path("sys.md")
BASE_TAIL = ["--safe-mode", "--strict-mcp-config", "--permission-mode", "dontAsk",
             "--permission-prompts", "none", "--append-system-prompt-file", str(SYSTEM_FILE)]
TOOLS = "Read,Edit,Write,Glob,Grep,Bash"
NPM = "Bash(npm --prefix frontend:*)"


def _call(capability=Capability.DEV, **overrides) -> AgentCall:
    fields = {"role": capability.value, "prompt": "Implement US-1.\nThen run the suite: é → ok",
              "system_prompt": "You are the dev.\nSay \"done\" at the end.",
              "capability": capability, "cwd": None, "timeout_s": 30.0}
    fields.update(overrides)
    return AgentCall(**fields)


# --- build_argv ------------------------------------------------------------------------

def test_text_call_has_no_tool_at_all():
    argv = build_argv(SETTINGS, _call(Capability.TEXT), SYSTEM_FILE)
    assert argv == ["-p", "--output-format", "json", "--model", "sonnet", "--tools", "", *BASE_TAIL]
    assert "--restricted" not in argv and "--allowedTools" not in argv


def test_qa_call_may_only_run_pytest_and_frontend_npm():
    argv = build_argv(SETTINGS, _call(Capability.QA), SYSTEM_FILE)
    assert argv == ["-p", "--output-format", "json", "--model", "sonnet", "--restricted",
                    "--tools", TOOLS, "--allowedTools", "Read", "Edit", "Write", "Glob", "Grep",
                    "Bash(uv run pytest:*)", NPM, *BASE_TAIL]


def test_dev_call_may_also_manage_dependencies():
    argv = build_argv(SETTINGS, _call(Capability.DEV), SYSTEM_FILE)
    assert argv == ["-p", "--output-format", "json", "--model", "sonnet", "--restricted",
                    "--tools", TOOLS, "--allowedTools", "Read", "Edit", "Write", "Glob", "Grep",
                    "Bash(uv run pytest:*)", NPM, "Bash(uv add:*)",
                    "Bash(uv remove:*)", "Bash(uv sync:*)", "Bash(uv lock:*)", *BASE_TAIL]


def test_npm_is_only_allowed_against_the_frontend_directory():
    """CONTRACTS.md 8.1: npm runs from the repo root as `npm --prefix frontend <args>`;
    a bare `npm`, `npx` or `cd frontend` stays denied, for every profile."""
    for allowed in (QA_ALLOWED, DEV_ALLOWED):
        npm_rules = [rule for rule in allowed if "npm" in rule or "npx" in rule]
        assert npm_rules == [NPM]
        assert not [rule for rule in allowed if "cd " in rule or rule == "Bash"]


def test_call_model_budget_and_resume_flags():
    argv = build_argv(SETTINGS, _call(model="haiku", max_budget_usd=1.5, resume_session_id="sess-9"),
                      SYSTEM_FILE)
    assert argv[argv.index("--model") + 1] == "haiku"
    assert argv[-4:] == ["--max-budget-usd", "1.5", "--resume", "sess-9"]
    plain = build_argv(SETTINGS, _call(), SYSTEM_FILE)
    assert "--max-budget-usd" not in plain and "--resume" not in plain


@pytest.mark.parametrize("capability", list(Capability))
def test_prompts_never_reach_the_command_line(capability):
    call = _call(capability)
    argv = build_argv(SETTINGS, call, SYSTEM_FILE)
    assert not [arg for arg in argv if "\n" in arg or "\r" in arg or '"' in arg]
    assert call.prompt not in argv and call.system_prompt not in argv


def test_unsafe_argument_is_refused():
    with pytest.raises(ValueError):
        build_argv(SETTINGS, _call(model="sonnet\n--dangerously-skip-permissions"), SYSTEM_FILE)


# --- parse_cli_output ------------------------------------------------------------------

def _payload(**overrides) -> str:
    return json.dumps({**SUCCESS, **overrides})


def test_success_maps_usage_cache_tokens_and_denials():
    result = parse_cli_output(_payload())
    assert result.text == 'All green. {"summary": "done"}'
    assert result.session_id == "sess-123"
    assert result.cost_usd == pytest.approx(0.0123)
    assert result.input_tokens == 100 + 20 + 3
    assert result.output_tokens == 50
    assert (result.duration_ms, result.num_turns) == (4321, 7)
    assert result.denials == [{"tool_name": "Bash", "tool_use_id": "toolu_1",
                               "tool_input": {"command": "tasklist"}}]


def test_stray_line_before_the_json_is_tolerated():
    assert parse_cli_output("warning: update available\n" + _payload()).session_id == "sess-123"


def test_is_error_is_a_cli_error_with_partial_result():
    with pytest.raises(AgentError) as info:
        parse_cli_output(_payload(is_error=True, result="API Error: 529"))
    assert info.value.kind == "cli" and "529" in str(info.value)
    assert info.value.result.cost_usd == pytest.approx(0.0123)


def test_non_success_subtype_is_a_cli_error():
    with pytest.raises(AgentError) as info:
        parse_cli_output(_payload(subtype="error_during_execution", result=None))
    assert info.value.kind == "cli" and info.value.result.input_tokens == 123


def test_budget_subtype_is_a_budget_error():
    with pytest.raises(AgentError) as info:
        parse_cli_output(_payload(subtype="error_max_budget_usd", is_error=True, result=None,
                                  errors=["Reached maximum budget"]))
    assert info.value.kind == "budget" and "maximum budget" in str(info.value)
    assert info.value.result.output_tokens == 50


@pytest.mark.parametrize("stdout", ["", "not json", "[1, 2]", "{broken"])
def test_garbage_is_a_cli_error_without_result(stdout):
    with pytest.raises(AgentError) as info:
        parse_cli_output(stdout)
    assert info.value.kind == "cli" and info.value.result is None


# --- ClaudeCodeRunner against the fake CLI ------------------------------------------------

@pytest.fixture
def fake(tmp_path, monkeypatch):
    """Runner wired to the fake CLI; returns (runner, record reader)."""
    record = tmp_path / "record.json"
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record))
    runner = ClaudeCodeRunner(SETTINGS, command=[sys.executable, str(FAKE)])
    return runner, lambda: json.loads(record.read_text(encoding="utf-8"))


@pytest.fixture
def workspace(tmp_path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


async def test_success_feeds_prompt_on_stdin_and_system_prompt_by_file(fake, workspace, monkeypatch):
    runner, recorded = fake
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent-session")
    call = _call(Capability.DEV, cwd=workspace, resume_session_id="sess-1", max_budget_usd=2)
    result = await runner.arun(call)
    assert result.session_id == "sess-123" and result.input_tokens == 123
    seen = recorded()
    # procs.popen writes stdin in text mode: on Windows every LF reaches the CLI as CRLF.
    assert seen["stdin"].replace("\r\n", "\n") == call.prompt
    assert seen["system_prompt"] == call.system_prompt
    system_file = Path(seen["argv"][seen["argv"].index("--append-system-prompt-file") + 1])
    assert seen["argv"] == build_argv(SETTINGS, call, system_file)
    assert seen["argv"][-4:] == ["--max-budget-usd", "2", "--resume", "sess-1"]
    assert Path(seen["cwd"]).resolve() == workspace.resolve()
    assert seen["env"]["CLAUDECODE"] is None and seen["env"]["CLAUDE_CODE_SESSION_ID"] is None
    assert seen["env"]["FAKE_CLAUDE_SCENARIO"] is None  # default scenario, env still inherited


async def test_system_prompt_file_is_removed_after_the_call(fake, workspace):
    runner, recorded = fake
    await runner.arun(_call(Capability.QA, cwd=workspace))
    argv = recorded()["argv"]
    assert not Path(argv[argv.index("--append-system-prompt-file") + 1]).exists()


async def test_raw_stdout_is_logged_in_the_workspace(fake, workspace):
    runner, _ = fake
    await runner.arun(_call(Capability.QA, cwd=workspace))
    logs = list((workspace / ".autospec" / "logs").glob("qa-*.json"))
    assert len(logs) == 1
    assert json.loads(logs[0].read_text(encoding="utf-8"))["session_id"] == "sess-123"


async def test_text_call_without_cwd_writes_no_log(fake, tmp_path, monkeypatch):
    runner, recorded = fake
    monkeypatch.chdir(tmp_path)
    result = await runner.arun(_call(Capability.TEXT, role="pm"))
    assert result.text and recorded()["argv"][recorded()["argv"].index("--tools") + 1] == ""
    assert not (tmp_path / ".autospec").exists()


async def test_tool_calls_require_a_cwd(fake):
    runner, _ = fake
    with pytest.raises(ValueError):
        await runner.arun(_call(Capability.QA, cwd=None))


@pytest.mark.parametrize(("scenario", "kind", "has_result"), [
    ("is_error", "cli", True),
    ("budget", "budget", True),
    ("garbage", "cli", False),
    ("nonzero", "cli", False),
])
async def test_error_kinds(fake, workspace, monkeypatch, scenario, kind, has_result):
    runner, _ = fake
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", scenario)
    with pytest.raises(AgentError) as info:
        await runner.arun(_call(Capability.DEV, cwd=workspace))
    assert info.value.kind == kind
    assert (info.value.result is not None) is has_result
    if scenario == "nonzero":
        assert "exited 2" in str(info.value) and "invalid API key" in str(info.value)
    if scenario == "garbage":
        assert "something odd happened" in str(info.value)
    assert list((workspace / ".autospec" / "logs").glob("dev-*.json"))  # logged even on failure


async def test_timeout_kills_the_cli_quickly(fake, workspace, tmp_path, monkeypatch):
    runner, _ = fake
    ticks = tmp_path / "ticks.txt"
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "sleep")
    monkeypatch.setenv("FAKE_CLAUDE_TICKS", str(ticks))
    started = time.monotonic()
    with pytest.raises(AgentError) as info:
        await runner.arun(_call(Capability.DEV, cwd=workspace, timeout_s=2))
    assert info.value.kind == "timeout"
    assert time.monotonic() - started < 10
    size = ticks.stat().st_size
    assert size > 0
    time.sleep(0.6)
    assert ticks.stat().st_size == size  # nothing ticks any more: the process tree is dead


async def test_missing_cli_is_unavailable():
    runner = ClaudeCodeRunner(Settings(claude_cmd="no-such-claude-cli-4f2a"))
    with pytest.raises(AgentError) as info:
        await runner.arun(_call(Capability.TEXT))
    assert info.value.kind == "unavailable"


def test_child_env_drops_factory_venv_and_parent_session(monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", "C:/factory/.venv")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_SOCKET", "pipe")
    monkeypatch.setenv("AUTOSPEC_KEEP_ME", "yes")
    env = _child_env()
    assert not {"VIRTUAL_ENV", "CLAUDECODE", "CLAUDE_CODE_MESSAGING_SOCKET"} & set(env)
    assert env["AUTOSPEC_KEEP_ME"] == "yes" and "PATH" in {key.upper() for key in env}


# --- resolve_claude_command ------------------------------------------------------------------

NPM_SHIM = ('@ECHO off\r\nGOTO start\r\n:find_dp0\r\nSET dp0=%~dp0\r\nEXIT /b\r\n:start\r\n'
            'SETLOCAL\r\nCALL :find_dp0\r\n'
            '"%dp0%\\node_modules\\@anthropic-ai\\claude-code\\bin\\claude.exe"   %*\r\n')


def _npm_dir(tmp_path: Path, *, with_exe: bool) -> tuple[Path, Path]:
    npm = tmp_path / "npm"
    exe = npm / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    exe.parent.mkdir(parents=True)
    if with_exe:
        exe.write_bytes(b"MZ")
    shim = npm / "claude.cmd"
    shim.write_bytes(NPM_SHIM.encode("ascii"))
    return shim, exe


def test_npm_shim_resolves_to_the_native_exe(tmp_path):
    shim, exe = _npm_dir(tmp_path, with_exe=True)
    assert [Path(p) for p in resolve_claude_command(str(shim))] == [exe.resolve()]


@pytest.mark.skipif(sys.platform != "win32", reason="PATHEXT lookup of a .cmd is Windows only")
def test_bare_name_is_looked_up_on_path(tmp_path, monkeypatch):
    shim, exe = _npm_dir(tmp_path, with_exe=True)
    monkeypatch.setenv("PATH", str(shim.parent))
    assert [Path(p) for p in resolve_claude_command("claude")] == [exe.resolve()]


def test_shim_without_existing_target_falls_back_to_the_shim(tmp_path):
    shim, _ = _npm_dir(tmp_path, with_exe=False)
    assert [Path(p) for p in resolve_claude_command(str(shim))] == [shim.resolve()]


def test_unknown_shim_and_plain_exe_are_returned_as_is(tmp_path):
    other = tmp_path / "launcher.cmd"
    other.write_text("@echo off\r\npython fake.py %*\r\n", encoding="ascii")
    assert [Path(p) for p in resolve_claude_command(str(other))] == [other.resolve()]
    exe = tmp_path / "claude.exe"
    exe.write_bytes(b"MZ")
    assert [Path(p) for p in resolve_claude_command(str(exe))] == [exe.resolve()]


def test_nothing_found_is_unavailable(tmp_path):
    with pytest.raises(AgentError) as info:
        resolve_claude_command(str(tmp_path / "missing" / "claude.cmd"))
    assert info.value.kind == "unavailable"


# --- real CLI, opt-in ------------------------------------------------------------------------

PYPROJECT = """[project]
name = "realcheck"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
"""


@pytest.mark.skipif(os.environ.get("AUTOSPEC2_REAL_CLAUDE") != "1",
                    reason="real Claude Code session; set AUTOSPEC2_REAL_CLAUDE=1")
async def test_real_dev_session_writes_code_and_runs_pytest(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    call = AgentCall(
        role="dev", capability=Capability.DEV, cwd=tmp_path, model="haiku", max_budget_usd=1.0,
        timeout_s=600,
        # Without these rules haiku tried `pwd; ls -la; which uv`, got it denied and gave up
        # on Bash entirely (observed 2026-11-02).
        system_prompt=("You are a careful Python developer working in the current directory. "
                       "Bash only accepts commands starting with `uv run pytest`, `uv add`, "
                       "`uv remove`, `uv sync` or `uv lock`, one command at a time, never chained "
                       "with ; or &&. Use Read, Glob, Grep, Write and Edit for everything else."),
        prompt=("Create calc.py with a function add(a, b) returning a + b, and tests/test_calc.py "
                "with one pytest test for it. Then run `uv run pytest` and fix until it passes. "
                "End your answer with the single word DONE."),
    )
    result = await ClaudeCodeRunner(Settings()).arun(call)
    assert result.session_id and result.cost_usd > 0 and result.num_turns > 0
    assert (tmp_path / "calc.py").is_file() and (tmp_path / "tests" / "test_calc.py").is_file()
    # `uv run` creates the project venv: proves the agent ran the suite itself.
    assert (tmp_path / ".venv").is_dir(), f"the agent never ran uv: {result.text[:500]}"
    check = subprocess.run(["uv", "run", "pytest", "-q"], cwd=tmp_path, capture_output=True,
                           text=True, timeout=300, env=_child_env())
    assert check.returncode == 0, check.stdout + check.stderr
    assert list((tmp_path / ".autospec" / "logs").glob("dev-*.json"))
