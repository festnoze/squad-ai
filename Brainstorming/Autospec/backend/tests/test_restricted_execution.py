"""Security boundary regressions: no hostile command runs on the host."""
import json
import os
import shutil
import subprocess

import pytest

from autospec.agents import runner
from autospec.agents.file_broker import ExecutionContext, FileBroker, IsolationViolation, active_execution, active_dependency_handler
from autospec.agents.providers import _apply_tool, provider_capabilities


@pytest.mark.parametrize("path", ["../outside", "/outside", "C:\\outside", "C:outside",
    "\\\\server\\share", "x/../outside", "x/.env", ".env.production", ".claude/settings.json",
    ".git/config", ".git", ".codex/config", ".agents/skills/x", ".aws/credentials", ".ssh/id_rsa",
    ".credentials.json", "x/file:secret", "CON", "x/nul.py", "file.", "file ", "x//file",
    "autospec-state.json", "acceptance-contract.json", "independent-oracle/expected.json"])
def test_mediated_paths_refuse_host_credentials_metadata_and_ambiguous_names(tmp_path, path):
    outside = tmp_path.parent / "outside"
    outside.write_text("sentinel")
    with pytest.raises(runner.AgentError):
        _apply_tool(tmp_path, {"tool": "write_files", "files": [{"path": path, "content": "changed"}]})
    assert outside.read_text() == "sentinel"


def test_broker_batch_is_admitted_before_mutation_and_capabilities_are_truthful(tmp_path):
    with pytest.raises(runner.AgentError):
        _apply_tool(tmp_path, {"tool": "write_files", "files": [
            {"path": "ok.py", "content": "never written"}, {"path": "../outside", "content": "x"}]})
    assert not (tmp_path / "ok.py").exists()
    cap = provider_capabilities("claude code")
    assert cap.can_edit_files and not cap.can_run_shell and not cap.supports_native_skills
    assert cap.execution_model == "restricted_tools"


def test_broker_cannot_read_hardlinked_credentials(tmp_path):
    target = tmp_path.parent / "private-credential"
    target.write_text("not returned")
    os.link(target, tmp_path / "innocent.json")
    with pytest.raises(runner.AgentError, match="Linked files"):
        _apply_tool(tmp_path, {"tool": "read_files", "paths": ["innocent.json"]})
    with pytest.raises(runner.AgentError):
        _apply_tool(tmp_path, {"tool": "write_files", "files": [{"path": "innocent.json", "content": "x"}]})
    assert target.read_text() == "not returned"


def test_broker_rejects_junction_or_symlink(tmp_path):
    external = tmp_path.parent / "external-directory"
    external.mkdir()
    (external / "sentinel").write_text("intact")
    link = tmp_path / "link"
    if os.name == "nt":
        # Trusted test setup creates one junction, never evaluates model text.
        import ctypes
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(external)],
                                capture_output=True, timeout=5)
        assert result.returncode == 0
    else:
        link.symlink_to(external, target_is_directory=True)
    try:
        with pytest.raises(runner.AgentError):
            _apply_tool(tmp_path, {"tool": "write_files", "files": [{"path": "link/sentinel", "content": "changed"}]})
        with pytest.raises(runner.AgentError):
            _apply_tool(tmp_path, {"tool": "read_files", "paths": ["link/sentinel"]})
        assert (external / "sentinel").read_text() == "intact"
    finally:
        if os.name == "nt":
            link.rmdir()  # remove the junction itself, never recurse its target
        else:
            link.unlink()


def test_oracle_is_unavailable_and_context_cannot_move(tmp_path):
    oracle = tmp_path / "oracle"
    oracle.mkdir()
    (oracle / "expected.json").write_text("not exposed")
    context = ExecutionContext("run-a", tmp_path, protected_paths=("oracle",))
    token = active_execution.set(context)
    try:
        with pytest.raises(runner.AgentError):
            _apply_tool(tmp_path, {"tool": "read_files", "paths": ["oracle/expected.json"]})
        with pytest.raises(runner.AgentError):
            _apply_tool(tmp_path.parent, {"tool": "list_files"})
        assert "oracle" not in _apply_tool(tmp_path, {"tool": "list_files"})
    finally:
        active_execution.reset(token)
    assert not context.public()["host_shell"]


@pytest.mark.parametrize("tool", ["Bash", "PowerShell", "shell", "mcp", "execute", "delete_files"])
def test_hostile_requests_are_data_only_and_have_no_dispatch(tmp_path, tool):
    sentinel = tmp_path.parent / "sentinel.txt"
    sentinel.write_text("intact")
    with pytest.raises(runner.AgentError, match="Outil inconnu"):
        _apply_tool(tmp_path, {"tool": tool, "command": "taskkill //F //IM python.exe"})
    assert sentinel.read_text() == "intact"


def _stub_cli(monkeypatch, replies):
    commands = []
    def execute(args, text, cwd, timeout):
        assert "autospec-inference-" in cwd
        assert not os.listdir(cwd), "The native CLI never starts inside generated code"
        commands.append((args, text, runner._agent_environment.get()))
        result, cost = replies.pop(0)
        return 0, json.dumps({"result": result, "total_cost_usd": cost,
            "usage": {"input_tokens": 2, "output_tokens": 3}, "session_id": "native-never-resumed"}), ""
    monkeypatch.setattr(runner, "_run_tracked", execute)
    monkeypatch.setattr(runner, "_ensure_claude_isolation", lambda: None)
    return commands


async def test_cli_mediated_nominal_and_history_have_no_native_tools_or_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-must-not-inherit")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-must-not-inherit")
    monkeypatch.setenv("NODE_OPTIONS", "--require untrusted-code")
    commands = _stub_cli(monkeypatch, [
        (json.dumps({"tool": "write_files", "files": [{"path": "main.py", "content": "print('nominal')"}]}), .1),
        ('{"status":"green"}', .1), ('{"next":true}', .1)])
    cli = runner.ClaudeCliRunner()
    result = await cli.arun("build", "system", cwd=tmp_path)
    assert (tmp_path / "main.py").read_text() == "print('nominal')"
    assert result.cost_usd == pytest.approx(.2)
    assert result.input_tokens == 4 and result.output_tokens == 6
    await cli.arun("next question", "system", cwd=tmp_path, session_id=result.session_id)
    assert "build" in commands[-1][1] and "next question" in commands[-1][1]
    for args, text, environment in commands:
        assert args[args.index("--tools") + 1] == ""
        assert all(flag in args for flag in runner._CLAUDE_ISOLATION_FLAGS)
        assert "--resume" not in args and "--add-dir" not in args and "--bare" not in args
        assert not {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "NODE_OPTIONS"} & set(environment)
        assert "secret-must-not-inherit" not in text


async def test_budget_is_decremented_across_all_file_rounds(monkeypatch, tmp_path):
    commands = _stub_cli(monkeypatch, [(json.dumps({"tool": "list_files"}), .3), ('{"done":true}', .2)])
    token = runner.active_budget_usd.set(.8)
    try:
        result = await runner.ClaudeCliRunner().arun("p", "s", cwd=tmp_path)
    finally:
        runner.active_budget_usd.reset(token)
    assert result.cost_usd == pytest.approx(.5)
    caps = [float(args[args.index("--max-budget-usd") + 1]) for args, _, _ in commands]
    assert caps == pytest.approx([.8, .5])


async def test_dependency_request_uses_trusted_task_and_coordinator(monkeypatch, tmp_path):
    request = {"tool": "dependency_request", "task_id": "forged-other-task", "version": 1,
               "ecosystem": "python", "package": "argon2-cffi", "constraint": ">=23",
               "scope": "runtime", "manifest": "pyproject.toml", "lock": "uv.lock", "reason": "real hasher"}
    _stub_cli(monkeypatch, [(json.dumps(request), .1), ('{"status":"blocked_dependency"}', .1)])
    received = []
    def handle(root, request):
        received.append((root, request))
        return {"status": "pending", "package": request["package"]}
    execution = active_execution.set(ExecutionContext("run-a", tmp_path, task_id="AUTH-1"))
    handler = active_dependency_handler.set(handle)
    try:
        result = await runner.ClaudeCliRunner().arun("p", "s", cwd=tmp_path)
    finally:
        active_dependency_handler.reset(handler)
        active_execution.reset(execution)
    assert json.loads(result.text)["status"] == "blocked_dependency"
    assert received[0][0] == tmp_path and received[0][1]["task_id"] == "AUTH-1"
    assert "tool" not in received[0][1]
    assert not (tmp_path / "pyproject.toml").exists()  # model never installs anything


async def test_missing_dependency_coordinator_is_explicit_not_a_fallback(monkeypatch, tmp_path):
    _stub_cli(monkeypatch, [(json.dumps({"tool": "dependency_request", "package": "x"}), .1)])
    with pytest.raises(runner.AgentError) as caught:
        await runner.ClaudeCliRunner().arun("p", "s", cwd=tmp_path)
    assert caught.value.code == "DEPENDENCY_COORDINATOR_UNAVAILABLE"
    assert not list(tmp_path.iterdir())


async def test_unknown_session_and_codex_fail_before_spawning(monkeypatch):
    def no_launch(*args, **kwargs):
        pytest.fail("An unavailable backend cannot launch a CLI")
    monkeypatch.setattr(runner, "_run_tracked", no_launch)
    with pytest.raises(runner.AgentError, match="ISOLATION_UNAVAILABLE"):
        await runner.ClaudeCliRunner().arun("p", "s", session_id="legacy-id")
    with pytest.raises(runner.AgentError, match="ISOLATION_UNAVAILABLE"):
        await runner.CodexCliRunner().arun("p", "s")


def test_missing_cli_capability_fails_closed(monkeypatch):
    runner._probe_claude_isolation.cache_clear()
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **kw:
                        subprocess.CompletedProcess(a[0], 0, "--tools --safe-mode", ""))
    with pytest.raises(runner.AgentError, match="ISOLATION_UNAVAILABLE"):
        runner._probe_claude_isolation(("fake-no-model",), (0,))


@pytest.mark.skipif(os.name != "nt" or not shutil.which("node.exe"), reason="Windows native FakeCLI")
async def test_real_fake_cli_process_exercises_nominal_mediated_files(monkeypatch, tmp_path):
    npm = tmp_path / "npm"
    package = npm / "node_modules" / "@anthropic-ai" / "claude-code"
    package.mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({"name": "@anthropic-ai/claude-code", "bin": {"claude": "cli.js"}}))
    shim = npm / "claude.cmd"
    shim.write_text("@exit /b 99")  # must never be evaluated as a host shell
    fake = """
const args = process.argv.slice(2);
if(args.includes('--help')) { console.log(%s); process.exit(0); }
if(args[args.indexOf('--tools')+1] !== '' || !args.includes('--safe-mode') || !args.includes('--restricted')) process.exit(70);
let text=''; process.stdin.on('data',x=>text+=x); process.stdin.on('end',()=> {
 const result = text.includes('TOOL RESULT:') ? JSON.stringify({status:'green'}) :
 JSON.stringify({tool:'write_files',files:[{path:'main.py',content:'print(42)\\n'}]});
 console.log(JSON.stringify({result,total_cost_usd:0,usage:{input_tokens:1,output_tokens:1}}));
});
""" % json.dumps(" ".join(runner._CLAUDE_ISOLATION_FLAGS))
    (package / "cli.js").write_text(fake)
    workspace = tmp_path / "product"
    workspace.mkdir()
    monkeypatch.setattr(runner.settings, "claude_cmd", str(shim))
    result = await runner.ClaudeCliRunner().arun("nominal local no-model", "s", cwd=workspace)
    assert json.loads(result.text)["status"] == "green"
    assert (workspace / "main.py").read_text() == "print(42)\n"


@pytest.mark.skipif(os.getenv("AUTOSPEC_REAL_CLAUDE_PROBE") != "1", reason="Explicit offline native CLI probe")
def test_native_cli_init_only_skips_product_hooks_and_mcp(tmp_path):
    marker = tmp_path / "hook-must-not-run"
    config = tmp_path / ".claude"
    config.mkdir()
    # Benign sentinel hook only; no shutdown/destructive command is supplied.
    hook_file = tmp_path / "benign-hook.cjs"
    hook_file.write_text(f"require('fs').writeFileSync({json.dumps(str(marker))},'unexpected')")
    # Positive fixture control: this trusted script really can write the marker.
    control = subprocess.run([shutil.which("node.exe") or "node", str(hook_file)], timeout=5)
    assert control.returncode == 0 and marker.exists()
    marker.unlink()
    hook = f'node "{hook_file.as_posix()}"'
    (config / "settings.json").write_text(json.dumps({"hooks": {"SessionStart": [
        {"hooks": [{"type": "command", "command": hook}]}]}}))
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"sentinel": {
        "command": "node", "args": [str(hook_file)]}}}))
    runner._ensure_claude_isolation()
    args = [runner.settings.claude_cmd, "--init-only", "-p", "--restricted", "--safe-mode",
            "--tools", "", "--strict-mcp-config", "--disallowedTools", "*",
            "--disable-slash-commands", "--no-chrome", "--no-session-persistence",
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--settings", '{"disableAllHooks":true}']
    token = runner._agent_environment.set(runner._subscription_environment())
    try:
        rc, out, err = runner._run_tracked(args, "", str(tmp_path), 15)
    finally:
        runner._agent_environment.reset(token)
    assert rc == 0, (out, err)
    assert not marker.exists()
