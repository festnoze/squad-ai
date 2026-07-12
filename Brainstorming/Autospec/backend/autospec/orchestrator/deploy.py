"""Deployment artifacts for the generated product (D1).

Writes a Dockerfile, a .dockerignore and a GitHub Actions CI workflow into the
generated uv project's workspace, idempotently, so the delivered product is
container- and CI-ready. Extends the I2 export/delivery.
"""

from __future__ import annotations

from pathlib import Path

from ..config import settings

#: Managed marker carried by every Autospec-generated Dockerfile. Autospec
#: safely regenerates a Dockerfile that still carries this marker, but never
#: clobbers one a user has taken over (marker removed). It sits on line 2:
#: the ``# syntax=`` parser directive is only honored by Docker when it is the
#: very FIRST line of the file.
MANAGED_MARKER = "# autospec:managed"

_SYNTAX_DIRECTIVE = "# syntax=docker/dockerfile:1"

#: Shared header of every managed Dockerfile: parser directive first (Docker
#: requirement), managed marker second.
_HEADER = f"{_SYNTAX_DIRECTIVE}\n{MANAGED_MARKER}\n"

_BACKEND_BODY = """FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
RUN uv sync --no-dev || uv sync || true
COPY . .
"""

_FE_BUILD_STAGE = """FROM node:20-alpine AS fe
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build
"""

_NGINX_SPA_CONF = """server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }
}
"""

_DOCKERIGNORE = """.git
.venv
node_modules
**/node_modules
__pycache__
*.pyc
*.db
*.sqlite
*.sqlite3
autospec-state.json
autospec-interactions.jsonl
build-monitor.jsonl
.autospec-cov.json
"""

_CI = """name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --extra dev || uv sync
      - run: uv run pytest
"""


def dockerfile_text(port: int, kind: str = "backend") -> str:
    """Build the managed Dockerfile text for ``kind`` exposing ``port``.

    ``kind`` is one of ``"backend"``, ``"fullstack"`` or ``"frontend"``:

    - ``backend``: a python:3.12-slim image running ``main.py`` (``EXPOSE {port}``).
    - ``fullstack``: multi-stage — the frontend is built with node then served
      by the python backend from ``./frontend/dist`` (one image, ``EXPOSE {port}``).
    - ``frontend``: a frontend-only SPA built with node then served by
      nginx (``EXPOSE 80``, SPA ``try_files`` fallback).
    """
    if kind == "frontend":
        return (
            _HEADER
            + _FE_BUILD_STAGE
            + "FROM nginx:alpine\n"
            "COPY --from=fe /fe/dist /usr/share/nginx/html\n"
            "COPY nginx.conf /etc/nginx/conf.d/default.conf\n"
            "EXPOSE 80\n"
        )
    if kind == "fullstack":
        return (
            _HEADER
            + _FE_BUILD_STAGE
            + _BACKEND_BODY
            + "COPY --from=fe /fe/dist ./frontend/dist\n"
            + f"EXPOSE {port}\n"
            'CMD ["uv", "run", "python", "main.py"]\n'
        )
    # backend (default)
    return (
        _HEADER
        + _BACKEND_BODY
        + f"EXPOSE {port}\n"
        'CMD ["uv", "run", "python", "main.py"]\n'
    )


def write_deploy_artifacts(
    ws: Path, *, port: int | None = None, kind: str = "backend"
) -> list[str]:
    """Write Dockerfile / .dockerignore / CI workflow into ``ws``.

    The Dockerfile is (re)written when absent OR when it still carries the
    managed marker as its first line AND its content differs from the freshly
    generated text (safe regeneration; a user-edited Dockerfile — marker
    removed — is never clobbered). The ``.dockerignore``, ``ci.yml`` and the
    frontend nginx conf keep never-overwrite semantics. ``port=None`` falls
    back to ``settings.smoke_run_port``. Returns the created/updated paths
    (posix-relative to ``ws``)."""
    if port is None:
        port = settings.smoke_run_port

    created: list[str] = []

    dockerfile = ws / "Dockerfile"
    wanted = dockerfile_text(port, kind)
    if _should_write_dockerfile(dockerfile, wanted):
        dockerfile.parent.mkdir(parents=True, exist_ok=True)
        dockerfile.write_text(wanted, encoding="utf-8")
        created.append(dockerfile.relative_to(ws).as_posix())

    # Never-overwrite artifacts.
    targets = [
        (ws / ".dockerignore", _DOCKERIGNORE),
        (ws / ".github" / "workflows" / "ci.yml", _CI),
    ]
    if kind == "frontend":
        targets.append((ws / "nginx.conf", _NGINX_SPA_CONF))
    for path, content in targets:
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(path.relative_to(ws).as_posix())

    return created


def _should_write_dockerfile(path: Path, wanted: str) -> bool:
    """Whether the managed Dockerfile should be (re)written.

    True when the file is absent, or when it is still Autospec-managed and its
    content has drifted from ``wanted``. The marker lives on line 2 (after the
    ``# syntax=`` parser directive); files generated before that reorder carry
    it on line 1 — both count as managed."""
    if not path.exists():
        return True
    try:
        current = path.read_text(encoding="utf-8")
    except OSError:
        return True
    head = [line.strip() for line in current.splitlines()[:2]]
    if MANAGED_MARKER not in head:
        return False  # user has taken over the Dockerfile
    return current != wanted
