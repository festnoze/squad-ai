"""Runtime acceptance gate for runnable web/fullstack deliveries."""

from __future__ import annotations

import asyncio
import logging
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ..config import BACKEND_DIR, PROJECT_DIR, settings
from ..models import ProjectState, StoryStatus
from . import toolchain, workspace

logger = logging.getLogger(__name__)


def _run_node(command: list[str], *, cancel_event: threading.Event, timeout: float,
              **kwargs) -> subprocess.CompletedProcess[str]:
    """Bound the Node gate and all servers it owns, including cancellation."""
    from ..agents.runner import spawn_owned_process, close_owned_process
    proc = spawn_owned_process(command, cancel=cancel_event, **kwargs)
    deadline = time.monotonic() + timeout
    finished = False
    try:
        while True:
            if cancel_event.is_set():
                raise subprocess.TimeoutExpired(command, timeout, output="runtime acceptance cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                output, _ = proc.communicate(timeout=min(0.1, remaining))
                finished = True
                return subprocess.CompletedProcess(command, proc.returncode, stdout=output)
            except subprocess.TimeoutExpired:
                continue
    finally:
        close_owned_process(proc)
        if proc.stdout is not None:
            proc.stdout.close()


@dataclass(frozen=True)
class RuntimeAcceptanceResult:
    ok: bool
    detail: str
    skipped: bool = False
    infra: bool = False


def resolve_web_port(ws: Path) -> int:
    """Single source of truth for the web port a delivered app listens on.

    Parse ``ws/main.py`` for ``port = <4-5 digits>`` (the value the generated
    app actually binds), else fall back to ``settings.smoke_run_port``. Both the
    smoke gate and the runtime gate MUST resolve the port this way so they never
    validate a different port than the one the app opens (finding 2)."""
    main = ws / "main.py"
    if main.exists():
        text = main.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"port\s*=\s*(\d{4,5})", text)
        if m:
            return int(m.group(1))
    return settings.smoke_run_port


def _done_journey(state: ProjectState, *, limit: int = 6000) -> str:
    """Concatenated Gherkin of the DONE stories of the current delivery.

    The JS gate uses it to click through a happy-path journey (finding 5). We
    truncate to ~``limit`` chars and return ``""`` when nothing is DONE."""
    chunks: list[str] = []
    for story in state.stories:
        if story.effective_status() != StoryStatus.DONE:
            continue
        gherkin = (story.gherkin or "").strip()
        if gherkin:
            chunks.append(gherkin)
    return "\n\n".join(chunks)[:limit]


def _frontend_root(state: ProjectState, ws: Path) -> Path | None:
    for stream in workspace.frontend_streams(state):
        root = workspace.stream_root(state, stream)
        if (root / "package.json").exists():
            return root
    fallback = ws / "frontend"
    return fallback if (fallback / "package.json").exists() else None


def _backend_web_candidate(ws: Path) -> bool:
    for manifest in (ws / ".autospec-bootstrap.json", ws / ".autospec" / "bootstrap.json"):
        if not manifest.is_file():
            continue
        try:
            stack = json.loads(manifest.read_text(encoding="utf-8")).get("stack", {})
            if stack.get("kind") in ("api", "fullstack"):
                return True
            if stack.get("kind") in ("frontend", "cli", "library"):
                return False
        except (OSError, ValueError):
            pass
    main = ws / "main.py"
    if not main.exists():
        return False
    text = main.read_text(encoding="utf-8", errors="replace").lower()[:80_000]
    pyproject = (ws / "pyproject.toml").read_text(encoding="utf-8", errors="replace").lower() if (ws / "pyproject.toml").exists() else ""
    haystack = text + "\n" + pyproject
    return any(token in haystack for token in ("fastapi", "uvicorn", "flask", "starlette"))


def should_run(state: ProjectState, ws: Path, *, enabled: bool | None = None) -> tuple[bool, str]:
    if not (settings.runtime_acceptance_enabled if enabled is None else enabled):
        return False, "runtime acceptance désactivé"
    if settings.fake_agents:
        return False, "mode démo"
    if not any(s.effective_status() == StoryStatus.DONE for s in state.stories):
        return False, "aucune story livrée"
    if _frontend_root(state, ws) is None and not _backend_web_candidate(ws):
        return False, "aucune cible web/frontend détectée"
    return True, ""


async def arun_runtime_acceptance(
    state: ProjectState,
    ws: Path,
    *,
    enabled: bool | None = None,
    timeout_s: float | None = None,
) -> RuntimeAcceptanceResult:
    runnable, reason = should_run(state, ws, enabled=enabled)
    if not runnable:
        return RuntimeAcceptanceResult(ok=True, detail=reason, skipped=True)

    # Every product build/server/migration/seed stays behind the Linux boundary.
    # The old JS gate could launch Python/npm on the host; it is no longer used.
    from .bootstrap import verify_runtime
    result = await verify_runtime(
        state, ws,
        timeout_s=settings.runtime_acceptance_timeout_s if timeout_s is None else timeout_s,
        repair_dependencies=True,
    )
    return RuntimeAcceptanceResult(result.ok, result.detail, result.skipped, result.infra)
