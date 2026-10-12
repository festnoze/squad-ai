"""Explicit real-Docker smoke; isolated names/network, never touches user projects.

Run from backend: python scripts/docker_transaction_smoke.py
Requires Docker and a python:3.12-slim base image (downloads it if absent).
"""

from __future__ import annotations

import json
import tempfile
import urllib.request
import uuid
from pathlib import Path

from autospec.config import settings
from autospec.models import ProjectState
from autospec.orchestrator import docker_deploy as docker


DOCKERFILE = """FROM python:3.12-slim
WORKDIR /app
COPY server.py ./
RUN mkdir -p /app/data && chown 10001:10001 /app/data
USER 10001:10001
EXPOSE 8000
CMD ["python", "/app/server.py"]
"""
SERVER = """import json, os, sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        with sqlite3.connect(os.environ['DATABASE_URL'].removeprefix('sqlite:///')) as db:
            db.execute('CREATE TABLE IF NOT EXISTS marker (value TEXT)')
            if not db.execute('SELECT value FROM marker').fetchone():
                db.execute("INSERT INTO marker VALUES ('__VERSION__')")
            value = db.execute('SELECT value FROM marker').fetchone()[0]
        self.send_response(200)
        self.end_headers()
        if self.path == '/api/health':
            self.wfile.write(json.dumps({'status':'ok','service':'autospec-bootstrap','database':'ok'}).encode())
        else:
            self.wfile.write(value.encode() if self.path == '/data' else b"__VERSION__")
HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
"""


def main() -> None:
    project_id = "codex-runtime-smoke-" + uuid.uuid4().hex[:10]
    network = project_id + "-net"
    workspace = Path(tempfile.mkdtemp(prefix=project_id + "-"))
    state = ProjectState(id=project_id, name="isolated runtime smoke", goal="lifecycle validation",
                         technical_stack={"kind": "api", "backend": "python", "database": "sqlite"})
    original_root = settings.workspace_root
    original_port = settings.smoke_run_port
    settings.workspace_root = workspace / "states"
    settings.smoke_run_port = 8000
    owned_images: set[str] = set()
    (workspace / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8")
    try:
        def deploy(version: str, *, broken=False):
            (workspace / "server.py").write_text("raise RuntimeError('intentional smoke failure')\n" if broken else SERVER.replace("__VERSION__", version), encoding="utf-8")
            state.deploy_host_port = docker.allocate_host_port(state)
            result = docker.deploy_and_verify(state, workspace, network=network,
                host_port=state.deploy_host_port, build_timeout=180, deploy_timeout=15, kind="backend")
            if result.ok:
                info = docker._inspect_container(docker.container_name(state.id))
                if info and info.get("Image"):
                    owned_images.add(info["Image"])
            print(json.dumps({"step": version, "ok": result.ok, "infra": result.infra, "detail": result.detail}, ensure_ascii=True), flush=True)
            return result

        assert deploy("v1").ok
        url = f"http://127.0.0.1:{state.deploy_host_port}"
        with urllib.request.urlopen(url, timeout=5) as response:
            assert response.read() == b"v1"
        assert not deploy("broken", broken=True).ok
        with urllib.request.urlopen(url, timeout=5) as response:
            assert response.read() == b"v1", "candidate failure replaced the healthy service"
        assert deploy("v2").ok
        with urllib.request.urlopen(url, timeout=5) as response:
            assert response.read() == b"v2"
        with urllib.request.urlopen(url + "/data", timeout=5) as response:
            assert response.read() == b"v1", "replacement lost SQLite data"
        reconciled = docker.inspect_deployment(state.id)
        assert reconciled.ok and reconciled.host_port == state.deploy_host_port
        removed = docker.undeploy(state.id)
        assert removed.ok, removed.detail
        assert docker.inspect_deployment(state.id).skipped
        assert deploy("v3").ok
        with urllib.request.urlopen(url + "/data", timeout=5) as response:
            assert response.read() == b"v1", "undeploy erased SQLite data"
    finally:
        # Every targeted name was created in this function; no label-wide sweep.
        removed = docker.undeploy(state.id)
        network_rc, network_out = docker._docker(["network", "rm", network], timeout=15)
        for owned_image in owned_images:
            # No --force: a concurrent external reference protects its image.
            docker._docker(["rmi", owned_image], timeout=15)
        docker._docker(["volume", "rm", docker.data_volume_name(state.id)], timeout=15)
        settings.workspace_root = original_root
        settings.smoke_run_port = original_port
        assert removed.ok, removed.detail
        assert network_rc == 0 or "not found" in network_out.lower(), network_out
    print("Docker transaction smoke PASS: failed candidate preserves v1; v2 replaces it; SQLite survives replacement and undeploy/redeploy; cleanup verified.", flush=True)


if __name__ == "__main__":
    main()
