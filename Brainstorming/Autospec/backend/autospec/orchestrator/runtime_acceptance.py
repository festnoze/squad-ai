"""Runtime acceptance gate for runnable web/fullstack deliveries."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..config import BACKEND_DIR, PROJECT_DIR, settings
from ..models import ProjectState, StoryStatus
from . import toolchain, workspace

logger = logging.getLogger(__name__)


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

    # Finding 6 : un backend web non-python ne peut pas être vérifié à l'exécution
    # par ce gate (le script JS pilote un serveur python/node). On journalise un
    # AVERTISSEMENT plutôt que de bloquer silencieusement.
    lang = toolchain.normalize(state.backend_language.value)
    if lang != "python" and _frontend_root(state, ws) is None:
        logger.warning(
            "Runtime acceptance : backend %s non-python détecté sans frontend — "
            "vérification à l'exécution indisponible pour ce langage.",
            lang,
        )
        return RuntimeAcceptanceResult(
            ok=True,
            detail=f"backend {lang} non-python : vérification runtime indisponible",
            skipped=True,
        )

    script = BACKEND_DIR / "scripts" / "runtime_acceptance.js"
    if not script.exists():
        return RuntimeAcceptanceResult(ok=False, detail=f"script introuvable : {script}")

    frontend = _frontend_root(state, ws)
    backend_web = _backend_web_candidate(ws)
    node_path = PROJECT_DIR / "frontend" / "node_modules"
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    timeout = settings.runtime_acceptance_timeout_s if timeout_s is None else timeout_s
    if node_path.exists():
        existing = env.get("NODE_PATH", "")
        env["NODE_PATH"] = str(node_path) if not existing else str(node_path) + os.pathsep + existing
    # Contrat JS #2/#3 : le port résolu (même source que le smoke) et le parcours
    # Gherkin des stories DONE sont passés par variable d'environnement.
    env["RUNTIME_BACKEND_PORT"] = str(resolve_web_port(ws))
    env["RUNTIME_JOURNEY"] = _done_journey(state)

    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                settings.node_cmd,
                str(script),
                str(ws),
                str(int(timeout * 1000)),
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
            timeout=timeout + 15,
        )

    try:
        proc = await asyncio.to_thread(_run)
    except (OSError, subprocess.TimeoutExpired) as exc:
        # Un lancement impossible (node/playwright absent) est une panne d'infra,
        # pas un bug de câblage réparable.
        return RuntimeAcceptanceResult(ok=False, detail=str(exc), infra=True)
    # Convention de code de sortie du gate JS (contrat #4) : 0 = OK, 1 = échec
    # d'intégration RÉPARABLE, 2 = panne d'INFRA/environnement (playwright/node
    # absent, ou port occupé par un process externe) — NON réparable.
    infra = proc.returncode == 2
    return RuntimeAcceptanceResult(
        ok=proc.returncode == 0,
        detail=(proc.stdout or "").strip(),
        infra=infra,
    )
