"""Owned interactive preview of an untrusted product, exclusively in Linux."""
from __future__ import annotations

import shutil
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..agents.runner import AgentError
from ..models import ProjectState
from . import acceptance
from .isolated_validation import IsolatedValidator, RuntimeSession
from .validation_environment import snapshot_product


@dataclass
class ProductPreview:
    session: RuntimeSession
    temporary: tempfile.TemporaryDirectory

    @property
    def origin(self):
        return self.session.origin

    def is_running(self):
        return self.session.is_running()

    def close(self):
        try:
            self.session.close()
        finally:
            self.temporary.cleanup()


def open_preview(state: ProjectState, root: Path, *, docker: str, timeout: float,
                 arguments: tuple[str, ...] = (), readiness_path: str = "/") -> ProductPreview:
    # Factory-selected same-origin HTTP target, not a producer URL. A 403/404
    # merely proves a listener exists, not that this preview target is ready.
    if (not isinstance(readiness_path, str) or len(readiness_path) > 2000 or
        not re.fullmatch(r"/[A-Za-z0-9_./~-]*", readiness_path) or
        readiness_path.startswith("//") or any(part in {".", ".."} for part in readiness_path.split("/"))):
        raise AgentError("Invalid factory preview readiness path", code="ISOLATION_UNAVAILABLE")
    kind = state.technical_stack.get("kind", "api")
    frontend_only = kind == "frontend"
    if kind not in {"api", "fullstack", "frontend"}:
        raise AgentError("ISOLATION_UNAVAILABLE: interactive preview only supports web products",
                         code="ISOLATION_UNAVAILABLE")
    ecosystem = "node" if frontend_only or state.backend_language.value == "node" else "python"
    if not frontend_only and state.backend_language.value not in {"python", "node"}:
        raise AgentError("ISOLATION_UNAVAILABLE: no attested interactive profile for this language",
                         code="ISOLATION_UNAVAILABLE")
    if frontend_only and (root / "frontend/package.json").is_file():
        root = root / "frontend"
    validator = IsolatedValidator(acceptance.supervisor_root(state.id) / "environments",
                                  docker=docker, timeout=timeout)
    environment = validator.manager.prepare(root, ecosystem, "test" if frontend_only else "runtime")
    temporary = tempfile.TemporaryDirectory(prefix="autospec-preview-")
    session = None
    dist = None
    try:
        stage = snapshot_product(root, Path(temporary.name) / "product")
        frontend = root if frontend_only else root / "frontend"
        if (frontend / "package.json").is_file():
            code, output, dist, _ = validator.build_frontend(frontend)
            if code:
                raise AgentError(f"Isolated frontend build failed: {output[-2000:]}")
            target = stage / "dist" if frontend_only else stage / "frontend/dist"
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if not target.resolve().is_relative_to(stage):
                    raise AgentError("Unsafe preview build path")
                shutil.rmtree(target)
            shutil.copytree(dist / "dist", target)
        command = (["node", "/opt/node_modules/vite/bin/vite.js", "preview", "--host", "127.0.0.1", "--port", "8000"]
                   if frontend_only else ["/opt/venv/bin/python", "main.py", *arguments]
                   if ecosystem == "python" else ["node", "main.js", *arguments])
        session = RuntimeSession(stage, environment.image, command, port=8000, ecosystem=ecosystem,
            docker=docker, application_origin=True, local_cookie_mode=True,
            env={"PORT": "8000", "HOST": "127.0.0.1", **({"DATABASE_URL": "sqlite:////tmp/preview.sqlite"} if ecosystem == "python" else {})})
        session.__enter__()
        deadline = time.monotonic() + min(timeout, 60)
        ready = False
        with httpx.Client(trust_env=False, follow_redirects=False) as client:
            while time.monotonic() < deadline:
                if not session.is_running():
                    raise AgentError("Preview container exited before HTTP readiness")
                try:
                    response = client.get(session.origin + readiness_path, timeout=min(5, max(.1, deadline-time.monotonic())))
                    ready = 200 <= response.status_code < 300
                except httpx.HTTPError:
                    pass
                if ready:
                    break
                time.sleep(.1)
        if not ready:
            raise AgentError("Preview HTTP readiness timeout; not marked running")
        return ProductPreview(session, temporary)
    except BaseException:
        if session is not None:
            session.close()
        temporary.cleanup()
        raise
    finally:
        if dist is not None:
            shutil.rmtree(dist)
