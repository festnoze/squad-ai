"""Claude Code launched headless as a native agent, confined by a tool allowlist.

One call = one CLI process. The prompt travels through stdin and the system prompt
through a temporary file, so the command line never carries a newline or a quote.
No retry happens here: the pipeline decides what to do with an ``AgentError``.
Cancelling ``arun`` (a stop, Ctrl-C) kills the CLI process tree at once.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from autospec.core.ports import AgentCall, AgentError, AgentResult, Capability
from autospec.core.procs import arun_capped
from autospec.core.settings import Settings

TOOLS = "Read,Edit,Write,Glob,Grep,Bash"
# npm always runs from the repo root on the fullstack frontend (CONTRACTS.md 8.1); the rule is
# granted to every profile because it is harmless where no frontend/ exists.
QA_ALLOWED = ("Read", "Edit", "Write", "Glob", "Grep", "Bash(uv run pytest:*)",
              "Bash(npm --prefix frontend:*)")
DEV_ALLOWED = (*QA_ALLOWED, "Bash(uv add:*)", "Bash(uv remove:*)", "Bash(uv sync:*)",
               "Bash(uv lock:*)")

# Never inherited by the agent: the factory's own venv (it would confuse `uv` in the
# product workspace) and the markers tying a process to a parent Claude Code session
# (the factory itself may be launched from one).
_DROPPED_ENV = frozenset({
    "VIRTUAL_ENV", "CLAUDECODE", "CLAUDE_PID", "CLAUDE_AGENT_SDK_VERSION",
    "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXECPATH", "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ATTENDED",
    "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
})
# npm shim line: "%dp0%\node_modules\@anthropic-ai\claude-code\bin\claude.exe"   %*
_SHIM_TARGET = re.compile(r'"%~?dp0%?[\\/]*([^"%]+?\.exe)"', re.IGNORECASE)
_FORBIDDEN_IN_ARGV = ("\n", "\r", '"')


def resolve_claude_command(cmd: str) -> list[str]:
    """Resolve ``cmd`` to the native executable, never to a cmd.exe shim.

    On Windows npm installs ``claude.cmd``, a batch file whose quoting rules would
    mangle arguments; its target ``claude.exe`` is read from the shim itself.
    """
    found = shutil.which(cmd) or (cmd if Path(cmd).is_file() else None)
    if not found:
        raise AgentError(f"Claude CLI not found: {cmd!r} (set AUTOSPEC2_CLAUDE_CMD)",
                         kind="unavailable")
    path = Path(found).resolve()
    if path.suffix.lower() in (".cmd", ".bat"):
        native = _shim_target(path)
        if native is not None:
            return [str(native)]
    return [str(path)]


def _shim_target(shim: Path) -> Path | None:
    try:
        text = shim.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for relative in reversed(_SHIM_TARGET.findall(text)):
        candidate = shim.parent.joinpath(*re.split(r"[\\/]+", relative))
        if candidate.is_file():
            return candidate
    return None


def _capability_flags(capability: Capability) -> list[str]:
    if capability is Capability.TEXT:
        return ["--tools", ""]
    allowed = DEV_ALLOWED if capability is Capability.DEV else QA_ALLOWED
    return ["--restricted", "--tools", TOOLS, "--allowedTools", *allowed]


def build_argv(settings: Settings, call: AgentCall, system_prompt_file: Path) -> list[str]:
    """CLI arguments for ``call``, without the executable (see ``resolve_claude_command``).

    The prompt itself is not part of it: it is written to stdin.
    """
    argv = ["-p", "--output-format", "json", "--model", call.model or settings.model,
            *_capability_flags(Capability(call.capability)),
            "--safe-mode", "--strict-mcp-config",
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--append-system-prompt-file", str(system_prompt_file)]
    if call.max_budget_usd:
        argv += ["--max-budget-usd", f"{call.max_budget_usd:g}"]
    if call.resume_session_id:
        argv += ["--resume", call.resume_session_id]
    unsafe = [arg for arg in argv if any(char in arg for char in _FORBIDDEN_IN_ARGV)]
    if unsafe:
        raise ValueError(f"newline or quote in a CLI argument: {unsafe!r}")
    return argv


def _load_json(stdout: str) -> dict | None:
    """The CLI prints one JSON object; tolerate stray lines printed before it."""
    text = stdout.strip()
    for chunk in (text, *(line.strip() for line in reversed(text.splitlines()))):
        if not chunk.startswith("{"):
            continue
        try:
            data = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _int(value: object) -> int:
    return int(value or 0)


def parse_cli_output(stdout: str) -> AgentResult:
    """Map ``--output-format json`` to an ``AgentResult``.

    Raises ``AgentError(kind="cli")`` (``"budget"`` for ``error_max_budget_usd``) when
    the session failed, with the partial result attached whenever the JSON was readable.
    """
    data = _load_json(stdout)
    if data is None:
        raise AgentError(f"claude printed no JSON result: {_tail(stdout, 500)!r}", kind="cli")
    usage = data.get("usage") or {}
    result = AgentResult(
        text=str(data.get("result") or ""),
        session_id=data.get("session_id"),
        cost_usd=float(data.get("total_cost_usd") or 0.0),
        input_tokens=_int(usage.get("input_tokens")) + _int(usage.get("cache_creation_input_tokens"))
        + _int(usage.get("cache_read_input_tokens")),
        output_tokens=_int(usage.get("output_tokens")),
        duration_ms=_int(data.get("duration_ms")),
        num_turns=_int(data.get("num_turns")),
        denials=list(data.get("permission_denials") or []),
    )
    subtype = data.get("subtype")
    if data.get("is_error") or subtype != "success":
        detail = data.get("result") or data.get("errors") or ""
        kind = "budget" if subtype == "error_max_budget_usd" else _infra_kind(str(detail)) or "cli"
        raise AgentError(f"claude session failed ({subtype}): {_tail(str(detail), 500)}",
                         kind=kind, result=result)
    return result


_NETWORK = re.compile(r"can't reach the api|ENOTFOUND|ECONNRESET|ECONNREFUSED|ETIMEDOUT|EAI_AGAIN|"
                      r"socket hang up|overloaded|\b529\b|\b503\b|connection error", re.IGNORECASE)
_LIMIT = re.compile(r"usage limit|limit reached|rate limit", re.IGNORECASE)


def _infra_kind(detail: str) -> str | None:
    """A provider-side failure, not the agent's work: "network" (transient) or "limit"."""
    if _LIMIT.search(detail):
        return "limit"
    if _NETWORK.search(detail):
        return "network"
    return None


def _tail(text: str, limit: int = 2000) -> str:
    return text[-limit:].strip()


def _child_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key.upper() not in _DROPPED_ENV}


def _write_log(cwd: Path, role: str, stdout: str) -> Path:
    logs = Path(cwd) / ".autospec" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = logs / f"{role}-{stamp}.json"
    path.write_bytes(stdout.encode("utf-8"))
    return path


class ClaudeCodeRunner:
    """``ports.AgentRunner`` backed by the Claude Code CLI.

    ``command`` replaces the resolved CLI executable (tests point it at a fake).
    """

    def __init__(self, settings: Settings, *, command: list[str] | None = None):
        self._settings = settings
        self._command = list(command) if command else None

    async def arun(self, call: AgentCall) -> AgentResult:
        capability = Capability(call.capability)
        if capability is not Capability.TEXT and call.cwd is None:
            raise ValueError(f"a {capability.value} call needs a cwd")
        if self._command is None:
            self._command = resolve_claude_command(self._settings.claude_cmd)
        with tempfile.TemporaryDirectory(prefix="autospec-agent-", ignore_cleanup_errors=True) as tmp:
            system_file = Path(tmp) / "system-prompt.md"
            system_file.write_bytes(call.system_prompt.encode("utf-8"))
            argv = [*self._command, *build_argv(self._settings, call, system_file)]
            try:
                proc = await arun_capped(argv, cwd=call.cwd, env=_child_env(), timeout_s=call.timeout_s,
                                         input_text=call.prompt)
            except OSError as exc:
                raise AgentError(f"cannot start {argv[0]}: {exc}", kind="unavailable") from exc
        if call.cwd is not None:
            _write_log(call.cwd, call.role, proc.stdout)
        if proc.timed_out:
            raise AgentError(f"{call.role} agent timed out after {call.timeout_s:g}s, process tree killed",
                             kind="timeout")
        try:
            return parse_cli_output(proc.stdout)
        except AgentError as exc:
            if exc.result is not None:
                raise
            raise AgentError(f"claude exited {proc.returncode} without a JSON result; "
                             f"stdout: {_tail(proc.stdout, 500)!r}; stderr: {_tail(proc.stderr)}",
                             kind="cli") from exc
