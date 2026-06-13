"""Setup executor: actually creates the approved components in the workspace.

For each APPROVED component it materializes folders and manifests (FastAPI
backend, React+Vite frontend, docker-compose services for databases/caches).
Real dependency installation (uv sync / npm install) only runs when
``settings.setup_install`` is on — the default is demo-safe (files only).
Idempotent: existing files are never overwritten.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from ..config import settings
from ..models import Component, ComponentStatus, ProjectState

BACKEND_PYPROJECT = """[project]
name = "{slug}-backend"
version = "0.1.0"
description = "Backend FastAPI de {name} (généré par Autospec)"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
]

[dependency-groups]
dev = ["pytest>=8.0", "httpx>=0.27"]
"""

BACKEND_MAIN = '''"""FastAPI entry point of the generated backend."""

from fastapi import FastAPI

app = FastAPI(title="{name}")


@app.get("/api/health")
async def ahealth() -> dict:
    return {{"status": "ok"}}
'''

FRONTEND_PACKAGE_JSON = """{{
  "name": "{slug}-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {{
    "dev": "vite",
    "build": "vite build"
  }},
  "dependencies": {{
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  }},
  "devDependencies": {{
    "@vitejs/plugin-react": "^4.2.0",
    "vite": "^5.0.0"
  }}
}}
"""

FRONTEND_INDEX_HTML = """<!doctype html>
<html lang="fr">
  <head>
    <meta charset="UTF-8" />
    <title>{name}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
"""

FRONTEND_MAIN_JSX = """import React from "react";
import {{ createRoot }} from "react-dom/client";

function App() {{
  return <h1>{name} — frontend généré par Autospec</h1>;
}}

createRoot(document.getElementById("root")).render(<App />);
"""

FRONTEND_VITE_CONFIG = """import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({ plugins: [react()] });
"""

COMPOSE_HEADER = "services:\n"

COMPOSE_SERVICES = {
    "database": """  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
""",
    "cache": """  cache:
    image: redis:7
    ports:
      - "6379:6379"
""",
}


def _slug(name: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "app"


def _ensure(path: Path, content: str) -> bool:
    """Write ``content`` to ``path`` unless it already exists. True if written."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _run_install(args: list[str], cwd: Path) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        return proc.returncode == 0, (proc.stdout or "")[-1000:]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def _setup_backend(ws: Path, state: ProjectState, log: list[str]) -> None:
    root = ws / "backend"
    slug = _slug(state.name)
    created = _ensure(root / "pyproject.toml", BACKEND_PYPROJECT.format(slug=slug, name=state.name))
    _ensure(root / "app" / "__init__.py", "")
    _ensure(root / "app" / "main.py", BACKEND_MAIN.format(name=state.name))
    _ensure(root / "tests" / "__init__.py", "")
    log.append(f"backend/ {'créé' if created else 'déjà présent'} (FastAPI)")
    if settings.setup_install:
        ok, out = _run_install([settings.uv_cmd, "sync"], root)
        log.append(f"backend : uv sync {'OK' if ok else 'ÉCHEC — ' + out}")


def _setup_frontend(ws: Path, state: ProjectState, log: list[str]) -> None:
    root = ws / "frontend"
    slug = _slug(state.name)
    created = _ensure(root / "package.json", FRONTEND_PACKAGE_JSON.format(slug=slug))
    _ensure(root / "index.html", FRONTEND_INDEX_HTML.format(name=state.name))
    _ensure(root / "src" / "main.jsx", FRONTEND_MAIN_JSX.format(name=state.name))
    _ensure(root / "vite.config.js", FRONTEND_VITE_CONFIG)
    log.append(f"frontend/ {'créé' if created else 'déjà présent'} (React + Vite)")
    if settings.setup_install:
        ok, out = _run_install([settings.npm_cmd, "install"], root)
        log.append(f"frontend : npm install {'OK' if ok else 'ÉCHEC — ' + out}")


def _setup_compose(ws: Path, kinds: list[str], log: list[str]) -> None:
    """Append the requested infrastructure services to docker-compose.yml."""
    path = ws / "docker-compose.yml"
    existing = path.read_text(encoding="utf-8") if path.exists() else COMPOSE_HEADER
    changed = False
    for kind in kinds:
        snippet = COMPOSE_SERVICES.get(kind)
        if snippet and snippet not in existing:
            existing += snippet
            changed = True
    if changed:
        path.write_text(existing, encoding="utf-8")
    log.append(
        "docker-compose.yml mis à jour" if changed else "docker-compose.yml déjà à jour"
    )


def execute(state: ProjectState, ws: Path) -> list[str]:
    """Create every APPROVED component (blocking; run via asyncio.to_thread).

    Returns human-readable log lines; components that were materialized move
    to ``CREATED``.
    """
    log: list[str] = []
    approved = [
        c for c in state.components
        if c.status in (ComponentStatus.APPROVED, ComponentStatus.CREATED)
    ]
    if not approved:
        log.append("Aucun composant approuvé : rien à créer.")
        return log
    infra = [c for c in approved if c.kind in COMPOSE_SERVICES]
    for component in approved:
        if component.kind == "backend":
            _setup_backend(ws, state, log)
        elif component.kind == "frontend":
            _setup_frontend(ws, state, log)
        elif component.kind in COMPOSE_SERVICES:
            pass  # grouped below in a single compose file
        else:
            _ensure(ws / component.id / ".gitkeep", "")
            log.append(f"{component.id}/ créé (composant {component.kind})")
        component.status = ComponentStatus.CREATED
    if infra:
        _setup_compose(ws, [c.kind for c in infra], log)
    if not settings.setup_install:
        log.append("Installation des dépendances ignorée (AUTOSPEC_SETUP_INSTALL=0).")
    return log


async def aexecute(state: ProjectState, ws: Path) -> list[str]:
    """Async wrapper: the installs are blocking subprocesses, so stay off the
    event loop (same pattern as the pipeline's pytest/git calls)."""
    return await asyncio.to_thread(execute, state, ws)


def components_from_payload(items: list[dict]) -> list[Component]:
    """Build the components list from the API payload (user edit/validation)."""
    components: list[Component] = []
    for i, item in enumerate(items, start=1):
        components.append(
            Component(
                id=str(item.get("id") or f"comp-{i}"),
                kind=str(item.get("kind") or "other"),
                name=str(item.get("name") or item.get("id") or f"Composant {i}"),
                technology=str(item.get("technology") or ""),
                rationale=str(item.get("rationale") or ""),
                optional=bool(item.get("optional", False)),
                status=ComponentStatus(item.get("status", "proposed")),
            )
        )
    return components
