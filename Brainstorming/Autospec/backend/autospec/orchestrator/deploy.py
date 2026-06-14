"""Deployment artifacts for the generated product (D1).

Writes a Dockerfile, a .dockerignore and a GitHub Actions CI workflow into the
generated uv project's workspace, idempotently, so the delivered product is
container- and CI-ready. Extends the I2 export/delivery.
"""

from __future__ import annotations

from pathlib import Path

_DOCKERFILE = """# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
RUN uv sync --no-dev || uv sync || true
COPY . .
CMD ["uv", "run", "python", "main.py"]
"""

_DOCKERIGNORE = """.git
.venv
__pycache__
*.pyc
autospec-state.json
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


def write_deploy_artifacts(ws: Path) -> list[str]:
    """Write Dockerfile / .dockerignore / CI workflow into ``ws`` if absent.

    Idempotent: never overwrites an existing file. Returns the created paths
    (posix-relative to ``ws``)."""
    targets = [
        (ws / "Dockerfile", _DOCKERFILE),
        (ws / ".dockerignore", _DOCKERIGNORE),
        (ws / ".github" / "workflows" / "ci.yml", _CI),
    ]
    created: list[str] = []
    for path, content in targets:
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(path.relative_to(ws).as_posix())
    return created
