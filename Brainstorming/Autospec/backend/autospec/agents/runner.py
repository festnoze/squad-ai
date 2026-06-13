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
    ) -> AgentResult: ...


class ClaudeCliRunner:
    """Runs one headless Claude Code turn. Pass session_id to continue a session."""

    async def arun(
        self,
        prompt: str,
        system_prompt: str,
        cwd: Path | None = None,
        session_id: str | None = None,
    ) -> AgentResult:
        args = [
            settings.claude_cmd,
            "-p",
            "--output-format", "json",
            "--permission-mode", settings.permission_mode,
            "--append-system-prompt", system_prompt,
        ]
        if settings.claude_model:
            args += ["--model", settings.claude_model]
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
    ) -> AgentResult:
        self.calls.append(
            {"prompt": prompt, "system_prompt": system_prompt, "cwd": cwd, "session_id": session_id}
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
