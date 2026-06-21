"""Agent execution backends.

ClaudeCliRunner drives the locally installed Claude Code CLI in headless mode
(`claude -p --output-format json`), which is how the BMAD personas get executed.
Tests use FakeRunner instead.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..config import settings


@dataclass
class AgentResult:
    text: str
    session_id: str | None = None
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0


class AgentError(RuntimeError):
    pass


class AgentRunner(Protocol):
    async def arun(
        self,
        prompt: str,
        system_prompt: str,
        cwd: Path | None = None,
        session_id: str | None = None,
        model: str | None = None,
    ) -> AgentResult: ...


class ClaudeCliRunner:
    """Runs one headless Claude Code turn. Pass session_id to continue a session."""

    async def arun(
        self,
        prompt: str,
        system_prompt: str,
        cwd: Path | None = None,
        session_id: str | None = None,
        model: str | None = None,
    ) -> AgentResult:
        args = [
            settings.claude_cmd,
            "-p",
            "--output-format", "json",
            "--permission-mode", settings.permission_mode,
            "--append-system-prompt", system_prompt,
        ]
        chosen_model = model or settings.claude_model
        if chosen_model:
            args += ["--model", chosen_model]
        if session_id:
            args += ["--resume", session_id]

        # Run the child process in a worker thread via the blocking subprocess
        # API: asyncio's subprocess support is unavailable on Windows'
        # SelectorEventLoop (the loop uvicorn runs), where
        # create_subprocess_exec raises NotImplementedError. Staying off the
        # event loop for child processes keeps this working on every platform.
        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                args,
                input=prompt,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(cwd) if cwd else None,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=settings.agent_timeout_s,
            )

        try:
            proc = await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired:
            raise AgentError(f"Agent timed out after {settings.agent_timeout_s}s")
        except OSError as exc:
            # e.g. claude CLI not installed / not on PATH
            raise AgentError(f"Could not run claude CLI ({settings.claude_cmd}): {exc}")

        out = (proc.stdout or "").strip()
        if proc.returncode != 0:
            err = (proc.stderr or "").strip()
            raise AgentError(f"claude CLI exited with {proc.returncode}: {err or out}")

        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            # --output-format json should always give JSON, but degrade gracefully
            return AgentResult(text=out)
        if not isinstance(payload, dict):
            return AgentResult(text=out)
        if payload.get("is_error"):
            # Some failures (e.g. error_during_execution) exit 0 but flag the payload.
            detail = payload.get("result") or payload.get("subtype") or out[:500]
            raise AgentError(f"claude CLI reported an error: {detail}")
        usage = payload.get("usage") or {}
        return AgentResult(
            text=str(payload.get("result") or ""),
            session_id=payload.get("session_id"),
            cost_usd=float(payload.get("total_cost_usd", 0) or 0),
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
            duration_ms=int(payload.get("duration_ms", 0) or 0),
        )


def _extract_codex_text(out: str) -> tuple[str, int, int]:
    """Parse ``codex exec --json`` output into (final_text, in_tokens, out_tokens).

    Codex emits JSONL (one event per line). We don't hard-code the exact event
    schema (it evolves across versions): we scan every line that parses as a JSON
    object and keep the LAST human-readable assistant message found under any of
    the common keys, plus any token-usage counters seen. If nothing parses as
    JSON (e.g. plain-text mode), the whole output is returned as the text."""
    last_text = ""
    in_tok = out_tok = 0
    saw_json = False

    def _dig_text(obj: dict) -> str:
        # Common shapes across codex versions: {"msg":{"type":"agent_message","message":...}},
        # {"item":{"type":"agent_message","text":...}}, {"type":"agent_message","text":...}.
        for container in (obj, obj.get("msg"), obj.get("item"), obj.get("message")):
            if not isinstance(container, dict):
                continue
            kind = str(container.get("type") or "")
            if kind and "agent_message" not in kind and "message" not in kind and "assistant" not in kind:
                continue
            for key in ("text", "message", "content", "last_agent_message"):
                val = container.get(key)
                if isinstance(val, str) and val.strip():
                    return val
        return ""

    for line in out.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        saw_json = True
        text = _dig_text(obj)
        if text:
            last_text = text
        usage = obj.get("usage") or obj.get("token_usage") or {}
        if isinstance(usage, dict):
            in_tok = int(usage.get("input_tokens", usage.get("prompt_tokens", in_tok)) or in_tok)
            out_tok = int(usage.get("output_tokens", usage.get("completion_tokens", out_tok)) or out_tok)

    if not saw_json:
        return out, 0, 0
    return (last_text or out), in_tok, out_tok


class CodexCliRunner:
    """Runs one headless OpenAI Codex turn via ``codex exec`` — the OpenAI
    counterpart of :class:`ClaudeCliRunner`. Codex has no ``--append-system-prompt``
    flag, so the system prompt is prepended to the user prompt; the combined
    prompt is fed on stdin. Output is parsed from ``codex exec --json`` JSONL.

    The exact codex flags are env-overridable (``AUTOSPEC_CODEX_CMD``) so the
    harness can adapt as the CLI evolves."""

    async def arun(
        self,
        prompt: str,
        system_prompt: str,
        cwd: Path | None = None,
        session_id: str | None = None,
        model: str | None = None,
    ) -> AgentResult:
        # Codex has no separate system-prompt channel: prepend it to the prompt.
        combined = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        args = [
            settings.codex_cmd,
            "exec",
            "--json",
            # Headless, non-interactive autonomy — the codex equivalent of
            # Claude's bypassPermissions (the orchestrator re-verifies anyway).
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
        ]
        chosen_model = model or settings.codex_model
        if chosen_model:
            args += ["--model", chosen_model]
        # Read the prompt from stdin ('-') rather than argv (Windows argv length
        # limits would truncate large BMAD prompts).
        args.append("-")

        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                args,
                input=combined,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(cwd) if cwd else None,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=settings.agent_timeout_s,
            )

        try:
            proc = await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired:
            raise AgentError(f"Agent timed out after {settings.agent_timeout_s}s")
        except OSError as exc:
            raise AgentError(f"Could not run codex CLI ({settings.codex_cmd}): {exc}")

        out = (proc.stdout or "").strip()
        if proc.returncode != 0:
            err = (proc.stderr or "").strip()
            raise AgentError(f"codex CLI exited with {proc.returncode}: {err or out}")

        text, in_tok, out_tok = _extract_codex_text(out)
        return AgentResult(text=text, input_tokens=in_tok, output_tokens=out_tok)


class FakeRunner:
    """Deterministic runner for tests: pops queued replies in order."""

    def __init__(self, replies: list[str] | None = None):
        self.replies = list(replies or [])
        self.calls: list[dict] = []

    def queue(self, *replies: str) -> None:
        self.replies.extend(replies)

    async def arun(
        self,
        prompt: str,
        system_prompt: str,
        cwd: Path | None = None,
        session_id: str | None = None,
        model: str | None = None,
    ) -> AgentResult:
        self.calls.append(
            {"prompt": prompt, "system_prompt": system_prompt, "cwd": cwd,
             "session_id": session_id, "model": model}
        )
        if not self.replies:
            raise AgentError("FakeRunner has no queued reply")
        return AgentResult(text=self.replies.pop(0), session_id="fake-session")


_FENCED_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _balanced_end(text: str, start: int) -> int:
    """Index of the '}' closing the object opened at `start`, or -1 (string-aware)."""
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _first_object(text: str) -> dict | None:
    """Return the first parseable top-level JSON object found in `text`, or None.

    Brace-balanced candidates that fail to parse (e.g. braces inside a code
    sample) are skipped instead of aborting the whole extraction.
    """
    pos = text.find("{")
    while pos != -1:
        end = _balanced_end(text, pos)
        if end != -1:
            try:
                obj = json.loads(text[pos : end + 1])
            except json.JSONDecodeError:
                obj = None
            if isinstance(obj, dict):
                return obj
        pos = text.find("{", pos + 1)
    return None


def extract_json(text: str) -> dict:
    """Extract the first JSON object from an agent reply, tolerating fences/prose.

    Fenced ```json blocks are tried first; if none yields a valid object the
    whole reply is scanned, so JSON preceded by brace-laden prose still parses.
    Raises AgentError (never JSONDecodeError) when no object can be extracted.
    """
    for match in _FENCED_RE.finditer(text):
        obj = _first_object(match.group(1))
        if obj is not None:
            return obj
    obj = _first_object(text)
    if obj is not None:
        return obj
    if "{" not in text:
        raise AgentError(f"No JSON object in agent reply: {text[:200]!r}")
    raise AgentError(f"No parseable JSON object in agent reply: {text[:200]!r}")
