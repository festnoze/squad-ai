"""Deployment artifacts for the selected toolchain, preserving user edits.

An embedded checksum records generated content. Keeping the managed marker is
not sufficient to overwrite a file: user and repair-agent edits are preserved.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath

from ..config import settings

MANAGED_MARKER = "# autospec:managed"
_DIGEST_PREFIX = "# autospec:sha256="
_HEADER = f"# syntax=docker/dockerfile:1\n{MANAGED_MARKER}\n"
_KINDS = {"backend", "fullstack", "frontend", "cli", "library"}
_LANGUAGES = {"python", "go", "rust", "node"}

_SECRET_PATTERNS = """.env
.env.*
**/.env
**/.env.*
*.pem
*.key
*.p12
*.pfx
**/*.pem
**/*.key
**/*.p12
**/*.pfx
**/credentials.json
**/service-account*.json
.aws
**/.aws
.ssh
**/.ssh
.npmrc
**/.npmrc
.pypirc
**/.pypirc
"""
_LEGACY_DOCKERIGNORE = """.git
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
_DOCKERIGNORE = _LEGACY_DOCKERIGNORE + """**/.git
**/.venv
**/__pycache__
**/*.pyc
**/*.db
**/*.sqlite
**/*.sqlite3
.pytest_cache
**/.pytest_cache
.autospec
target
**/target
dist
**/dist
""" + _SECRET_PATTERNS

_LEGACY_CI = """name: CI
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

_NGINX_SPA_CONF = """server {
    listen 8080;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }
}
"""


def _signed(content: str) -> str:
    """Add a digest without moving Docker's first-line parser directive."""
    if MANAGED_MARKER not in content.splitlines()[:2]:
        content = f"{MANAGED_MARKER}\n{content}"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return content.replace(MANAGED_MARKER + "\n", f"{MANAGED_MARKER}\n{_DIGEST_PREFIX}{digest}\n", 1)


def _unmodified_generated(content: str) -> bool:
    lines = content.splitlines(keepends=True)
    if MANAGED_MARKER not in [line.strip() for line in lines[:2]]:
        return False
    signatures = [line for line in lines if line.startswith(_DIGEST_PREFIX)]
    if len(signatures) != 1:
        return False
    signature = signatures[0]
    unsigned = "".join(line for line in lines if line != signature)
    return hashlib.sha256(unsigned.encode("utf-8")).hexdigest() == signature.strip()[len(_DIGEST_PREFIX):]


def _options(port: int, kind: str, language: str, frontend_root: str) -> tuple[str, str]:
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Container port must be an integer between 1 and 65535")
    if kind not in _KINDS:
        raise ValueError(f"Unsupported deployment kind: {kind}")
    language = language.lower().strip()
    language = {"py": "python", "golang": "go", "javascript": "node", "typescript": "node", "nodejs": "node", "node.js": "node", "js": "node", "ts": "node"}.get(language, language)
    if language not in _LANGUAGES:
        raise ValueError(f"Unsupported deployment language: {language}; provide a custom Dockerfile")
    root = PurePosixPath(frontend_root)
    if not frontend_root or not re.fullmatch(r"[A-Za-z0-9_./-]+", frontend_root) or root.is_absolute() or ".." in root.parts:
        raise ValueError("frontend_root must be a relative workspace directory without '..'")
    return language, root.as_posix()


def _frontend_stage(root: str) -> str:
    return f"""FROM node:22-alpine AS fe
WORKDIR /fe
COPY {root}/ ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
RUN npm run build
"""


def _backend_stages(language: str, kind: str) -> str:
    if language == "python":
        return """FROM python:3.12-slim AS runtime
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY . .
RUN if [ -f uv.lock ]; then uv sync --frozen --no-dev; else uv sync --no-dev; fi
RUN useradd --uid 10001 --create-home app && mkdir -p /app/data && chown app:app /app/data
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER app
"""
    if language == "node":
        return """FROM node:22-alpine AS backend-build
WORKDIR /app
COPY . .
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
RUN npm run build --if-present && npm prune --omit=dev
FROM node:22-alpine AS runtime
WORKDIR /app
COPY --from=backend-build /app /app
RUN mkdir -p /app/data && chown node:node /app/data
ENV NODE_ENV=production
USER node
"""
    if language == "go":
        build = "go build ./..." if kind == "library" else 'go build -trimpath -ldflags="-s -w" -o /out/app .'
        stage = f"""FROM golang:1-bookworm AS backend-build
WORKDIR /app
COPY . .
RUN go mod download && {build}
"""
        if kind == "library":
            return stage + "RUN useradd --uid 10001 --create-home app\nUSER app\n"
        return stage + """FROM debian:bookworm-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
COPY --from=backend-build /out/app /usr/local/bin/autospec-app
RUN useradd --uid 10001 --create-home app && mkdir -p /app/data && chown app:app /app/data
USER app
"""
    stage = """FROM rust:1-slim-bookworm AS backend-build
WORKDIR /app
COPY . .
RUN if [ -f Cargo.lock ]; then cargo build --release --locked; else cargo build --release; fi
"""
    if kind == "library":
        return stage + "RUN useradd --uid 10001 --create-home app\nUSER app\n"
    # A generated service has one bin target. Fail clearly for multi-bin crates
    # instead of silently choosing an arbitrary program to deploy.
    return stage + """RUN mkdir /out && set -- $(find target/release -maxdepth 1 -type f -executable ! -name '*.so') && test "$#" -eq 1 && cp "$1" /out/app
FROM debian:bookworm-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl libssl3 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
COPY --from=backend-build /out/app /usr/local/bin/autospec-app
RUN useradd --uid 10001 --create-home app && mkdir -p /app/data && chown app:app /app/data
USER app
"""


def dockerfile_text(
    port: int, kind: str = "backend", language: str = "python", frontend_root: str = "frontend"
) -> str:
    """Render a production image; non-web images deliberately have no EXPOSE.

    Fullstack backends serve ``AUTOSPEC_STATIC_DIR``. Runtime startup never
    installs dependencies. CLI images execute their normal entry point and
    library images package sources/build products for downstream consumption.
    """
    language, root = _options(port, kind, language, frontend_root)
    body = _HEADER
    if kind in {"frontend", "fullstack"}:
        body += _frontend_stage(root)
    if kind == "frontend":
        return _signed(body + """FROM nginxinc/nginx-unprivileged:stable-alpine AS runtime
COPY --from=fe /fe/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
USER 101
EXPOSE 8080
""")
    body += _backend_stages(language, kind)
    if kind == "fullstack":
        body += f"COPY --from=fe /fe/dist /app/{root}/dist\nENV AUTOSPEC_STATIC_DIR=/app/{root}/dist\n"
    if kind in {"backend", "fullstack"}:
        body += f"ENV HOST=0.0.0.0 PORT={port}\nEXPOSE {port}\n"
    command = {
        "python": '["/app/.venv/bin/python", "main.py"]',
        "node": '["npm", "start"]',
        "go": '["/usr/local/bin/autospec-app"]',
        "rust": '["/usr/local/bin/autospec-app"]',
    }[language]
    if kind == "library":
        command = '["/bin/sh"]'
    if kind == "cli":
        if language == "node":
            command = '["npm", "start", "--"]'
        return _signed(body + f'ENTRYPOINT {command}\nCMD ["--help"]\n')
    return _signed(body + f"CMD {command}\n")


def _ci_text(kind: str, language: str, root: str) -> str:
    body = """name: CI
on: [push, pull_request]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
"""
    if kind != "frontend":
        body += {
            "python": """      - uses: astral-sh/setup-uv@v5
      - run: |
          if [ -f uv.lock ]; then uv sync --frozen --all-extras; else uv sync --all-extras; fi
      - run: uv run --no-sync pytest
""",
            "go": """      - uses: actions/setup-go@v5
        with:
          go-version-file: go.mod
      - run: go test ./...
      - run: go build ./...
""",
            "rust": """      - uses: dtolnay/rust-toolchain@stable
      - run: |
          if [ -f Cargo.lock ]; then cargo test --locked; else cargo test; fi
      - run: |
          if [ -f Cargo.lock ]; then cargo build --release --locked; else cargo build --release; fi
""",
            "node": """      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - run: |
          if [ -f package-lock.json ]; then npm ci; else npm install; fi
      - run: npm test
      - run: npm run build --if-present
""",
        }[language]
    if kind in {"frontend", "fullstack"}:
        body += f"""      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - run: |
          if [ -f package-lock.json ]; then npm ci; else npm install; fi
        working-directory: {root}
      - run: npm test
        working-directory: {root}
      - run: npm run build
        working-directory: {root}
"""
    return _signed(body)


def _legacy_dockerfile(content: str) -> bool:
    """Recognize complete historical templates, never marker-only ownership."""
    header = f"# syntax=docker/dockerfile:1\n{MANAGED_MARKER}\n"
    legacy_header = f"{MANAGED_MARKER}\n# syntax=docker/dockerfile:1\n"
    normalized = content.replace(legacy_header, header, 1)
    backend = """FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
RUN uv sync --no-dev || uv sync || true
COPY . .
"""
    frontend = """FROM node:20-alpine AS fe
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build
"""
    match = re.search(r"^EXPOSE ([0-9]+)$", normalized, re.MULTILINE)
    if not match:
        return False
    port = match[1]
    tail = f'EXPOSE {port}\nCMD ["uv", "run", "python", "main.py"]\n'
    known = {
        header + backend + tail,
        header + frontend + backend + "COPY --from=fe /fe/dist ./frontend/dist\n" + tail,
        header + frontend + "FROM nginx:alpine\nCOPY --from=fe /fe/dist /usr/share/nginx/html\nCOPY nginx.conf /etc/nginx/conf.d/default.conf\nEXPOSE 80\n",
    }
    return normalized in known


def _should_write_dockerfile(path: Path, wanted: str) -> bool:
    if not path.exists():
        return True
    current = path.read_text(encoding="utf-8")
    return current != wanted and (_unmodified_generated(current) or _legacy_dockerfile(current))


def write_deploy_artifacts(
    ws: Path, *, port: int | None = None, kind: str = "backend", language: str = "python", frontend_root: str = "frontend"
) -> list[str]:
    """Generate artifacts, updating only verifiably unedited generated files."""
    if port is None:
        port = settings.smoke_run_port
    language, root = _options(port, kind, language, frontend_root)
    targets = [(ws / "Dockerfile", dockerfile_text(port, kind, language, root))]
    targets += [(ws / ".dockerignore", _signed(_DOCKERIGNORE)), (ws / ".github/workflows/ci.yml", _ci_text(kind, language, root))]
    if kind == "frontend":
        targets.append((ws / "nginx.conf", _signed(_NGINX_SPA_CONF)))
    created: list[str] = []
    for path, wanted in targets:
        if path.exists():
            current = path.read_text(encoding="utf-8")
            legacy = (path.name == "Dockerfile" and _legacy_dockerfile(current)) or (path.name == ".dockerignore" and current == _LEGACY_DOCKERIGNORE) or (path.name == "ci.yml" and current == _LEGACY_CI) or (path.name == "nginx.conf" and current == _NGINX_SPA_CONF.replace("listen 8080", "listen 80"))
            # Docker does not honor .gitignore. Keep a custom ignore's rules,
            # but exclude secrets at the very end, after possible negations.
            if path.name == ".dockerignore" and not (legacy or _unmodified_generated(current)):
                guard = "# Autospec: never include credentials in the build context\n" + _SECRET_PATTERNS
                if not current.endswith(guard):
                    path.write_text(current.rstrip() + "\n\n" + guard, encoding="utf-8")
                    created.append(path.relative_to(ws).as_posix())
                continue
            if current == wanted or not (_unmodified_generated(current) or legacy):
                continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(wanted, encoding="utf-8")
        created.append(path.relative_to(ws).as_posix())
    return created
