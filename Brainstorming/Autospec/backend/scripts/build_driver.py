"""Headless build driver — exercises the Autospec pipeline via the backend
orchestrator directly (no UI), with the **Claude CLI** provider, and reports a
machine-readable summary. Used to build 3 projects of increasing complexity and
diagnose the common failure causes.

Usage (from backend/, venv active):
    python -m scripts.build_driver 1     # simple, backend-only
    python -m scripts.build_driver 2     # medium, backend-only
    python -m scripts.build_driver 3     # back + front + db (streams)

Each run:
  * forces provider=claude (overriding any .env codex default),
  * turns on the build monitor (JSONL timeline) + a per-run logs dir,
  * runs spec(seeded brief)->plan->build->done with an overall wall-clock cap,
  * then runs the generated workspace's REAL test suite (uv run pytest),
  * prints a JSON summary to stdout and writes it next to the timeline.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

LOGS_ROOT = Path(__file__).resolve().parent.parent / "build-logs"


# --- seeded briefs (skip the PM interview) --------------------------------
BRIEFS: dict[int, dict] = {
    1: {
        "name": "Slugify lib",
        "goal": "Une petite bibliothèque Python de slugification de chaînes.",
        "brief": (
            "# Brief — bibliothèque slugify\n\n"
            "Une **bibliothèque Python** minimale, sans dépendance, exposant une "
            "fonction `slugify(text: str) -> str` qui transforme une chaîne en "
            "slug d'URL : minuscules, espaces et ponctuation remplacés par des "
            "tirets, accents retirés, tirets multiples compressés, pas de tiret "
            "en début/fin.\n\n"
            "## Périmètre (une seule petite story)\n"
            "- `slugify('Hello, World!')` == `'hello-world'`\n"
            "- `slugify('  Étude   de  CAS ')` == `'etude-de-cas'`\n"
            "- L'entrée vide renvoie une chaîne vide.\n\n"
            "Garder le périmètre minimal : une fonction, testée."
        ),
        "settings": {  # simplest harness: no streams/worktrees
            "streams_enabled": False,
            "components_enabled": False,
            "setup_install": False,
        },
    },
    2: {
        "name": "Todo CLI",
        "goal": "Une petite application CLI de gestion de tâches en mémoire.",
        "brief": (
            "# Brief — Todo CLI (en mémoire)\n\n"
            "Un **service Python** de gestion de tâches, sans dépendance externe, "
            "exposant une petite API de fonctions/classe `TodoList` :\n\n"
            "## Périmètre (2-3 stories)\n"
            "- `add(title)` ajoute une tâche et renvoie son id incrémental.\n"
            "- `list()` renvoie les tâches dans l'ordre d'ajout.\n"
            "- `complete(id)` marque une tâche comme faite ; lever une erreur "
            "claire si l'id est inconnu.\n\n"
            "Tout est en mémoire (pas de persistance). Garder le périmètre serré."
        ),
        "settings": {  # backend-only but exercises the parallel worktree+merge path
            "streams_enabled": True,
            "components_enabled": False,
            "setup_install": False,
        },
    },
    3: {
        "name": "Counter webapp",
        "goal": "Une mini web-app compteur : API FastAPI + UI React + persistance.",
        "brief": (
            "# Brief — Web-app Compteur\n\n"
            "Une **petite application web** complète :\n"
            "- **Backend** FastAPI exposant `GET /count` et `POST /increment` ; "
            "la valeur est **persistée** (SQLite/fichier) pour survivre au "
            "redémarrage.\n"
            "- **Frontend** React : affiche la valeur courante et un bouton "
            "« +1 » qui appelle l'API.\n\n"
            "## Périmètre minimal\n"
            "- Incrémenter via l'API met à jour la persistance.\n"
            "- L'écran affiche la valeur renvoyée par l'API.\n\n"
            "Garder le périmètre minimal : un seul compteur."
        ),
        "settings": {
            "components_enabled": True,
            "streams_enabled": True,
            "setup_install": True,
        },
    },
    4: {
        "name": "Counter web SSR",
        "goal": "Une web-app compteur complète et simple : page HTML servie par FastAPI, persistée en SQLite.",
        "brief": (
            "# Brief — Compteur web (rendu serveur)\n\n"
            "Une **application web complète mais minimale**, en **Python/FastAPI**, "
            "**sans frontend séparé** : le serveur rend directement une page HTML.\n\n"
            "## Comportement\n"
            "- `GET /` renvoie une page HTML (200) affichant le compteur courant "
            "sous la forme EXACTE `Compteur : N` (N = l'entier persistant, 0 au "
            "départ), et un bouton **« Incrémenter »** dans un `<form>` qui fait "
            "POST vers `/increment`.\n"
            "- `POST /increment` incrémente le compteur, le **persiste en SQLite** "
            "(fichier `counter.db` à la racine), puis redirige (303) vers `/`.\n"
            "- La valeur **survit au redémarrage** (persistance fichier).\n\n"
            "## Contraintes d'exécution (IMPORTANT)\n"
            "- L'app DOIT démarrer avec `uv run python main.py` et **servir sur "
            "http://127.0.0.1:8099** (uvicorn lancé depuis `main.py` via "
            "`if __name__ == '__main__': uvicorn.run(...)`, host 127.0.0.1 port 8099).\n"
            "- Déclare `fastapi` et `uvicorn` dans les dépendances du `pyproject.toml`.\n\n"
            "## Critères d'acceptance\n"
            "1. La page d'accueil affiche `Compteur : 0` au premier lancement.\n"
            "2. Cliquer « Incrémenter » affiche `Compteur : 1`.\n"
            "3. Après rechargement de la page, la valeur reste `Compteur : 1`.\n\n"
            "Garder le périmètre minimal : un seul compteur, une seule page."
        ),
        "settings": {  # full but simple: single server-rendered Python app
            "streams_enabled": False,
            "components_enabled": False,
            "setup_install": False,
        },
    },
}


def _configure(proj: int, run_dir: Path) -> None:
    os.environ["AUTOSPEC_BUILD_MONITOR"] = "1"
    os.environ["AUTOSPEC_BUILD_MONITOR_DIR"] = str(run_dir)
    from autospec.config import settings

    # Force the Claude CLI provider regardless of any .env default (e.g. codex).
    settings.agent_provider = "claude"
    settings.fake_agents = False
    # Keep the heavy optional phases off unless this project needs them.
    settings.approval_gates_enabled = False
    settings.brainstorm_assist_enabled = False
    settings.ui_tests_enabled = False
    settings.coverage_enabled = False
    settings.mutation_enabled = False
    # Pin the complexity-ladder flags to a known base, then apply per-project
    # overrides — so behaviour is deterministic regardless of any .env defaults.
    settings.streams_enabled = False
    settings.components_enabled = False
    settings.setup_install = False
    for key, value in BRIEFS[proj]["settings"].items():
        setattr(settings, key, value)


async def _run(proj: int) -> dict:
    spec = BRIEFS[proj]
    run_dir = LOGS_ROOT / f"p{proj}"
    run_dir.mkdir(parents=True, exist_ok=True)
    _configure(proj, run_dir)

    from autospec.agents.providers import make_runner
    from autospec.config import settings
    from autospec.models import ChatMessage, ChatRole, ProjectState, new_id
    from autospec.orchestrator.pipeline import Pipeline
    from autospec.storage import workspace_dir

    runner = make_runner("claude")
    state = ProjectState(
        id=new_id(f"drv-p{proj}"),
        name=spec["name"],
        goal=spec["goal"],
        auto_spec=False,
        brief=spec["brief"],
    )
    state.chat.append(ChatMessage(role=ChatRole.USER, content=spec["goal"]))
    pipeline = Pipeline(state, runner)

    cap_s = float(os.environ.get("AUTOSPEC_DRIVER_CAP_S", "2400"))
    t0 = time.time()
    timed_out = False
    try:
        await asyncio.wait_for(pipeline._alifecycle(), timeout=cap_s)
    except asyncio.TimeoutError:
        timed_out = True
        await pipeline.adispose()
    wall_s = round(time.time() - t0, 1)

    ws = workspace_dir(state.id)
    summary = {
        "project": proj,
        "id": state.id,
        "name": state.name,
        "provider": settings.agent_provider,
        "phase": state.phase.value,
        "error": state.error,
        "timed_out": timed_out,
        "wall_s": wall_s,
        "backend_language": state.backend_language.value,
        "streams": [s.id for s in state.streams],
        "components": [c.name for c in state.components],
        "stories": [
            {"id": s.id, "title": s.title, "status": s.status.value,
             "attempts": s.attempts, "stream": getattr(s, "stream", "")}
            for s in state.stories
        ],
        "usage": {
            "agent_calls": state.usage.agent_calls,
            "cost_usd": round(state.usage.cost_usd, 4),
            "input_tokens": state.usage.input_tokens,
            "output_tokens": state.usage.output_tokens,
        },
        "workspace": str(ws),
        "monitor_log": str(ws / "build-monitor.jsonl"),
    }

    # Real verification of the produced backend suite (uv run pytest).
    summary["pytest"] = _run_backend_tests(ws)
    return summary


def _run_backend_tests(ws: Path) -> dict:
    """Run the generated backend suite for real and capture the outcome."""
    if not (ws / "pyproject.toml").exists():
        return {"ran": False, "reason": "no pyproject.toml at workspace root"}
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    try:
        proc = subprocess.run(
            ["uv", "run", "pytest", "-q"],
            cwd=str(ws), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", env=env, timeout=600,
        )
        return {
            "ran": True, "returncode": proc.returncode,
            "green": proc.returncode in (0, 5),  # 5 = no tests collected
            "tail": (proc.stdout or "")[-1500:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ran": False, "reason": str(exc)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=int, choices=[1, 2, 3, 4])
    args = ap.parse_args()
    summary = asyncio.run(_run(args.project))
    out = LOGS_ROOT / f"p{args.project}" / "summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=== SUMMARY ===")
    # ascii-safe for legacy Windows consoles (cp1252) — the file keeps full UTF-8.
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    print(f"\n[summary written to {out}]")


if __name__ == "__main__":
    main()
