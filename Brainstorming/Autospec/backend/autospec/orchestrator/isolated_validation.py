"""Product tests and web runtimes run only behind the Linux Docker boundary.

Runtime ingress is an owned localhost TCP proxy into docker exec, not Docker
port publishing. The product keeps network=none: no host/LAN/registry egress.
"""
from __future__ import annotations

import json
import shutil
import socket
import socketserver
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..agents.file_broker import ExecutionContext, FileBroker
from ..agents.runner import _run_tracked, spawn_owned_process, close_owned_process
from .dependencies import atomic_json
from .sandbox import (run_isolated, require_sandbox, docker_run_cmd, _docker_call,
                      _container_identity, _cleanup_container, _unavailable)
from .test_integrity import SuiteEvidence, pytest_evidence, vitest_evidence, tap_evidence
from .validation_environment import LinuxEnvironmentManager, LinuxEnvironment, snapshot_product


@dataclass(frozen=True)
class IsolatedSuiteResult:
    evidence: SuiteEvidence
    output: str
    fingerprint: str
    image: str


def _node_command(command: list[str], *, report: bool = False, dist: bool = False) -> list[str]:
    # Native Linux tmpfs source avoids broken cross-filesystem symlinks in
    # Docker Desktop Windows binds. Deps stay image-owned /opt read-only, with
    # only Vite's cache redirected to /tmp. Export only selected report/dist.
    setup = 'mkdir -p /tmp/product /tmp/vite-cache; cp -r /app/. /tmp/product/; ln -s /opt/node_modules /tmp/product/node_modules; cd /tmp/product; '
    if not report and not dist:
        script = setup + 'exec "$@"'
    else:
        script = setup + '"$@"; status=$?; '
        if report:
            script += 'if [ -f suite-report.json ] && [ ! -L suite-report.json ]; then cp suite-report.json /app/suite-report.json; fi; '
        if dist:
            script += 'if [ "$status" = 0 ] && [ -d dist ] && [ ! -L dist ]; then cp -r dist /app/dist; fi; '
        script += 'exit "$status"'
    return ["/bin/sh", "-c", script, "autospec", *command]


class IsolatedValidator:
    def __init__(self, cache_root: Path, *, docker: str = "docker", timeout: float = 300,
                 manager: LinuxEnvironmentManager | None = None):
        self.manager = manager or LinuxEnvironmentManager(cache_root, docker=docker, timeout=timeout)
        self.docker = docker
        self.timeout = timeout

    def run_suite(self, root: Path, ecosystem: str, mode: str, reportpath: Path,
                  *, test_args: tuple[str, ...] = ()) -> IsolatedSuiteResult:
        root, reportpath = Path(root).absolute(), Path(reportpath).absolute()
        if reportpath.resolve().is_relative_to(root.resolve()):
            raise _unavailable("Suite evidence must be stored outside producer writable root")
        environment = self.manager.prepare(root, ecosystem, mode)
        with tempfile.TemporaryDirectory(prefix="autospec-suite-") as temporary:
            stage = snapshot_product(root, Path(temporary) / "product")
            stale = FileBroker(ExecutionContext("suite-report-freshness", stage)).path("suite-report.json")
            if stale.exists():
                stale.unlink()  # a cached/product report is never a fresh proof
            if ecosystem == "python":
                command = ["/opt/venv/bin/python", "-m", "pytest", "--json-report", "--json-report-file=suite-report.json", *test_args]
                parser = pytest_evidence
            else:
                package = json.loads((stage / "package.json").read_text(encoding="utf-8"))
                has_vitest = "vitest" in {**package.get("dependencies", {}), **package.get("devDependencies", {})}
                if has_vitest:
                    command = ["node", "/opt/node_modules/vitest/vitest.mjs", "run", "--reporter=json", "--outputFile=suite-report.json", "--maxWorkers=2", "--minWorkers=1", *test_args]
                    parser = vitest_evidence
                else:
                    command = ["node", "--test", "--test-reporter=tap", *test_args]
                    parser = None
                command = _node_command(command, report=has_vitest)
            rc, out, err = run_isolated(command, stage, environment.image, docker=self.docker, timeout=self.timeout)
            output = out + err
            if parser is None:
                evidence = tap_evidence(output, rc)
                atomic_json(reportpath, {"format": "tap", "output": output, "exit_code": rc})
            else:
                report = FileBroker(ExecutionContext("suite-report-export", stage)).path("suite-report.json")
                if not report.is_file() or report.stat().st_size > 20_000_000:
                    evidence = SuiteEvidence({}, 0, rc, report_valid=False)
                    atomic_json(reportpath, {"invalid_report": True, "exit_code": rc})
                else:
                    data = json.loads(report.read_text(encoding="utf-8"))
                    atomic_json(reportpath, data)
                    evidence = parser(reportpath, rc)
            return IsolatedSuiteResult(evidence, output, environment.fingerprint, environment.image)

    def run_command(self, root: Path, ecosystem: str, command: list[str], *, mode: str = "test",
                    exports: tuple[str, ...] = ()) -> tuple[int, str, LinuxEnvironment]:
        """Run in a filtered snapshot; only explicit regular-file exports return.

        Used for deterministic frontend builds. No arbitrary recursive sync-back.
        A caller must enumerate artefacts or use build_frontend for dist only.
        """
        environment = self.manager.prepare(Path(root), ecosystem, mode)
        with tempfile.TemporaryDirectory(prefix="autospec-command-") as temporary:
            stage = snapshot_product(Path(root), Path(temporary) / "product")
            rc, out, err = run_isolated(_node_command(command) if ecosystem == "node" else command,
                                       stage, environment.image, docker=self.docker, timeout=self.timeout)
            if rc == 0:
                source = FileBroker(ExecutionContext("artifact-source", stage))
                target = FileBroker(ExecutionContext("artifact-target", Path(root)))
                batch = []
                for path in exports:
                    file = source.path(path)
                    if not file.is_file() or file.stat().st_size > 2_000_000:
                        raise _unavailable("Artifact export requires bounded regular files")
                    batch.append((target.path(path), file.read_bytes()))
                for file, data in batch:
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_bytes(data)
            return rc, out + err, environment

    def build_frontend(self, root: Path) -> tuple[int, str, Path, LinuxEnvironment]:
        """Vite builds inside Docker; returns a supervisor-owned temporary dist.

        Caller owns the returned directory. It contains dist only, never source,
        credentials, dependency links, or changes to generated project files.
        """
        environment = self.manager.prepare(Path(root), "node", "test")
        with tempfile.TemporaryDirectory(prefix="autospec-vite-") as temporary:
            stage = snapshot_product(Path(root), Path(temporary) / "product")
            # Never npm run: package scripts aren't allowed to change the recipe.
            command = _node_command(["node", "/opt/node_modules/vite/bin/vite.js", "build"], dist=True)
            rc, out, err = run_isolated(command, stage, environment.image, docker=self.docker, timeout=self.timeout)
            result = Path(tempfile.mkdtemp(prefix="autospec-dist-"))
            if rc == 0:
                snapshot_product(stage / "dist", result / "dist")
            return rc, out + err, result, environment


def build_delivery_image(root: Path, image: str, *, docker: str = "docker", timeout: float = 300) -> tuple[bool, str]:
    """Bake filtered source into a trusted recipe, never the product Dockerfile.

    Dependency installs/builds remain in separate confined phases. The final
    image layer only copies source/dist and sets the exact runtime entrypoint.
    """
    from .validation_environment import LinuxEnvironmentManager
    root = Path(root)
    if not image or image.startswith("-") or any(c.isspace() for c in image):
        raise _unavailable("Invalid delivery image name")
    manager = LinuxEnvironmentManager(Path(tempfile.gettempdir()).resolve() / "autospec-linux-environments", docker=docker, timeout=timeout)
    validator = IsolatedValidator(manager.cache_root, docker=docker, timeout=timeout, manager=manager)
    ecosystem = "python" if (root / "pyproject.toml").is_file() else "node" if (root / "package.json").is_file() else ""
    if not ecosystem:
        raise _unavailable("Delivery requires an isolated Python or Node lockfile")
    environment = manager.prepare(root, ecosystem, "runtime")
    frontend = root / "frontend" if (root / "frontend/package.json").is_file() else None
    dist = None
    try:
        if frontend:
            rc, output, dist, _ = validator.build_frontend(frontend)
            if rc:
                return False, output
        with tempfile.TemporaryDirectory(prefix="autospec-delivery-") as temporary:
            context = Path(temporary).resolve()
            stage = snapshot_product(root, context / "product")
            if dist:
                target = stage / "frontend/dist"
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(dist / "dist", target)
            # Reverify dependency tag identity immediately before use. Docker's
            # local image IDs cannot be used in FROM by BuildKit (treated as a
            # registry named sha256); immutable attestations pin the cache tag.
            base = "autospec/clean-env:" + environment.fingerprint
            if manager._image(base)["Id"] != environment.image:
                raise _unavailable("Dependency image tag changed identity")
            command = ["/opt/venv/bin/python", "main.py"] if ecosystem == "python" else ["node", "main.js"]
            recipe = f"FROM {base}\nWORKDIR /app\nCOPY --chown=65532:65532 product/ /app/\nENV HOME=/tmp PYTHONDONTWRITEBYTECODE=1\nUSER 65532:65532\nCMD {json.dumps(command)}\n"
            (context / "Dockerfile").write_text(recipe, encoding="utf-8")
            rc, out, err = _run_tracked([docker, "build", "--pull=false", "--network=none", "-t", image, "."], "", str(context), timeout)
            return rc == 0, out + err
    finally:
        if dist is not None:
            shutil.rmtree(dist)


class RuntimeSession:
    """An exact owned net-none container plus trusted localhost ingress proxy."""
    def __init__(self, stage: Path, image: str, command: list[str], *, port: int = 8000,
                 ecosystem: str = "python", docker: str = "docker", env: dict[str, str] | None = None,
                 connection_timeout: float = 15):
        if not 1 <= port <= 65535 or ecosystem not in {"python", "node"}:
            raise _unavailable("Invalid runtime port/ecosystem")
        self.stage, self.image, self.command = Path(stage), image, command
        self.port, self.ecosystem, self.docker = port, ecosystem, docker
        self.env = dict(env or {})
        allowed = {"PORT", "DATABASE_URL", "AUTOSPEC_STATIC_DIR", "AUTOSPEC_BOOTSTRAP_TOKEN", "HOST", "PYTHONPATH"}
        if set(self.env) - allowed or any("\x00" in value for value in self.env.values()):
            raise _unavailable("Runtime environment is factory-owned and allowlisted")
        if "DATABASE_URL" in self.env and not self.env["DATABASE_URL"].startswith("sqlite:////tmp/"):
            raise _unavailable("Runtime validation DB must be disposable SQLite under /tmp")
        self.timeout = connection_timeout
        self.owner, self.name = uuid.uuid4().hex, "autospec-sandbox-" + uuid.uuid4().hex
        self.identifier = None
        self.server = None
        self.thread = None
        self.lock = threading.Lock()
        self.clients: set[subprocess.Popen] = set()
        self.sockets: set[socket.socket] = set()
        self.capacity = threading.BoundedSemaphore(64)

    def __enter__(self):
        require_sandbox(self.stage, self.image, docker=self.docker)
        command = _node_command(self.command) if self.ecosystem == "node" else self.command
        argv = docker_run_cmd(command, str(self.stage), self.image, self.docker, run_id=self.owner, container_name=self.name)
        argv.remove("--rm")  # retain exit/log evidence until owned explicit cleanup
        argv.insert(2, "-d")
        at = argv.index("--entrypoint")
        argv[at:at] = [piece for key, value in self.env.items() for piece in ("--env", f"{key}={value}")]
        try:
            rc, out, err = _run_tracked(argv, "", str(self.stage), 15)
            if rc:
                raise _unavailable(f"Runtime container failed: {out} {err}")
            self.identifier = _container_identity(self.docker, self.name, self.owner)
            if self.identifier is None:
                raise _unavailable("Runtime container identity absent")
            session = self
            class Handler(socketserver.BaseRequestHandler):
                def handle(self):
                    session._forward(self.request)
            class Server(socketserver.ThreadingTCPServer):
                daemon_threads = True
                allow_reuse_address = False
            self.server = Server(("127.0.0.1", 0), Handler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            self.host_port = self.server.server_address[1]
            self.origin = f"http://127.0.0.1:{self.host_port}"
            return self
        except BaseException:
            self.close()
            raise

    def _forward(self, connection: socket.socket) -> None:
        if not self.capacity.acquire(blocking=False):
            return
        process = None
        connection.settimeout(self.timeout)
        with self.lock:
            self.sockets.add(connection)
        try:
            # No host code from the product: argv and forwarding program are
            # factory constants, aimed at an immutable attested container ID.
            if self.ecosystem == "python":
                code = ("import socket,sys,threading; s=socket.create_connection(('127.0.0.1'," + str(self.port) + "),2); "
                        "exec(\"def upload():\\n try:\\n  while True:\\n   b=sys.stdin.buffer.read1(65536)\\n   if not b: break\\n   s.sendall(b)\\n except OSError: pass\\n finally:\\n  try: s.shutdown(socket.SHUT_WR)\\n  except OSError: pass\\n\"); "
                        "threading.Thread(target=upload,daemon=True).start(); "
                        "exec(\"while True:\\n b=s.recv(65536)\\n if not b: break\\n sys.stdout.buffer.write(b); sys.stdout.buffer.flush()\\n\")")
                bridge = ["/opt/venv/bin/python", "-u", "-c", code]
            else:
                bridge = ["node", "-e", f"const s=require('net').connect({self.port},'127.0.0.1');s.on('connect',()=>{{process.stdin.pipe(s);s.pipe(process.stdout);}});s.on('error',()=>process.exit(1));s.on('close',()=>process.exit());"]
            process = spawn_owned_process([self.docker, "exec", "-i", self.identifier, *bridge],
                                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            with self.lock:
                self.clients.add(process)
            timer = threading.Timer(self.timeout, close_owned_process, args=(process,))
            timer.start()
            def upload():
                try:
                    while data := connection.recv(65536):
                        process.stdin.write(data)
                        process.stdin.flush()
                except (OSError, ValueError):
                    pass
                finally:
                    try:
                        process.stdin.close()
                    except (OSError, ValueError):
                        pass
            uploader = threading.Thread(target=upload, daemon=True)
            uploader.start()
            try:
                while data := process.stdout.read1(65536):
                    connection.sendall(data)
            finally:
                timer.cancel()
                connection.shutdown(socket.SHUT_RDWR)
                uploader.join(timeout=1)
        except (OSError, ValueError):
            pass
        finally:
            if process is not None:
                close_owned_process(process)
                with self.lock:
                    self.clients.discard(process)
                for stream in (process.stdin, process.stdout):
                    if stream is not None and not stream.closed:
                        stream.close()
            with self.lock:
                self.sockets.discard(connection)
            self.capacity.release()

    def logs(self) -> str:
        if self.identifier is None:
            return ""
        result = _docker_call([self.docker, "logs", "--tail", "100", self.identifier], capture_output=True, text=True, timeout=3, check=False)
        return (result.stdout + result.stderr)[-12000:]

    def close(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        with self.lock:
            clients, sockets = list(self.clients), list(self.sockets)
        for connection in sockets:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for process in clients:
            close_owned_process(process)
        _cleanup_container(self.docker, self.name, self.owner)

    def __exit__(self, *_):
        self.close()
