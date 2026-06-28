"""Runtime acceptance gate for runnable web/fullstack deliveries."""

from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..config import BACKEND_DIR, PROJECT_DIR, settings
from ..models import ProjectState, StoryStatus
from . import workspace


@dataclass(frozen=True)
class RuntimeAcceptanceResult:
    ok: bool
    detail: str
    skipped: bool = False


def _frontend_root(state: ProjectState, ws: Path) -> Path | None:
    for stream in workspace.frontend_streams(state):
        root = workspace.stream_root(state, stream)
        if (root / "package.json").exists():
            return root
    fallback = ws / "frontend"
    return fallback if (fallback / "package.json").exists() else None


def _backend_web_candidate(ws: Path) -> bool:
    main = ws / "main.py"
    if not main.exists():
        return False
    text = main.read_text(encoding="utf-8", errors="replace").lower()[:80_000]
    pyproject = (ws / "pyproject.toml").read_text(encoding="utf-8", errors="replace").lower() if (ws / "pyproject.toml").exists() else ""
    haystack = text + "\n" + pyproject
    return any(token in haystack for token in ("fastapi", "uvicorn", "flask", "starlette"))


def should_run(state: ProjectState, ws: Path) -> tuple[bool, str]:
    if not settings.runtime_acceptance_enabled:
        return False, "runtime acceptance désactivé"
    if settings.fake_agents:
        return False, "mode démo"
    if not any(s.effective_status() == StoryStatus.DONE for s in state.stories):
        return False, "aucune story livrée"
    if _frontend_root(state, ws) is None and not _backend_web_candidate(ws):
        return False, "aucune cible web/frontend détectée"
    return True, ""


async def arun_runtime_acceptance(state: ProjectState, ws: Path) -> RuntimeAcceptanceResult:
    runnable, reason = should_run(state, ws)
    if not runnable:
        return RuntimeAcceptanceResult(ok=True, detail=reason, skipped=True)

    script = BACKEND_DIR / "scripts" / "runtime_acceptance.js"
    if not script.exists():
        return RuntimeAcceptanceResult(ok=False, detail=f"script introuvable : {script}")

    frontend = _frontend_root(state, ws)
    backend_web = _backend_web_candidate(ws)
    node_path = PROJECT_DIR / "frontend" / "node_modules"
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    if node_path.exists():
        existing = env.get("NODE_PATH", "")
        env["NODE_PATH"] = str(node_path) if not existing else str(node_path) + os.pathsep + existing

    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                settings.node_cmd,
                str(script),
                str(ws),
                str(int(settings.runtime_acceptance_timeout_s * 1000)),
                str(frontend or ""),
                "1" if backend_web else "0",
            ],
            cwd=str(ws),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=settings.runtime_acceptance_timeout_s + 15,
        )

    try:
        proc = await asyncio.to_thread(_run)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return RuntimeAcceptanceResult(ok=False, detail=str(exc))
    return RuntimeAcceptanceResult(ok=proc.returncode == 0, detail=(proc.stdout or "").strip())
