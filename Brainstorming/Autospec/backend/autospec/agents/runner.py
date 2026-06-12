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

        out = (proc.stdout or "").strip()
        if proc.returncode != 0:
            err = (proc.stderr or "").strip()
            raise AgentError(f"claude CLI exited with {proc.returncode}: {err or out}")

        try:
            payload = json.loads(out)
            return AgentResult(
                text=payload.get("result", ""),
                session_id=payload.get("session_id"),
            )
        except json.JSONDecodeError:
            # --output-format json should always give JSON, but degrade gracefully
            return AgentResult(text=out)


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


def extract_json(text: str) -> dict:
    """Extract the first JSON object from an agent reply, tolerating fences/prose."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    if start == -1:
        raise AgentError(f"No JSON object in agent reply: {text[:200]!r}")
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise AgentError(f"Unbalanced JSON in agent reply: {text[:200]!r}")
