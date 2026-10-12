"""Docker artifact delivery; reviewed contracts never use the legacy bridge.

Talks to the local Docker daemon (``deploy.py`` stays the artifact writer). Every
subprocess call here is synchronous, mirroring ``runtime_acceptance`` — the
pipeline drives the heavy work through ``asyncio.to_thread``. OSError /
TimeoutExpired are trapped everywhere and, when they look like a daemon-down /
docker-absent condition, classified as *infra* (park, don't burn repair attempts).
Qualified contract images are immutable packages until owned NETNONE publication
exists; the shared-network rebuild/deploy path is legacy without a contract only.
"""

from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from ..config import settings
from ..models import ProjectState
from .runtime_acceptance import (  # noqa: F401 (re-exported convenience)
    _backend_web_candidate,
    _frontend_root,
    resolve_web_port,
)


@dataclass(frozen=True)
class DockerDeployResult:
    ok: bool
    detail: str
    skipped: bool = False
    infra: bool = False
    image: str = ""
    container: str = ""
    host_port: int = 0
    cancelled: bool = False
    packaged: bool = False
    created_package_alias: str = ""  # this exact call only; empty for reuse/recovery
    created_publication_container: str = ""  # exact CID from this publish call, not state differences


class DockerRuntimeError(RuntimeError):
    """A Docker query failed; an empty registry must never mean daemon failure."""


_operation = threading.local()
_port_lock = threading.RLock()
_port_reservations: dict[str, tuple[int, socket.socket | None]] = {}


def _cancelled() -> bool:
    event = getattr(_operation, "cancel_event", None)
    return event is not None and event.is_set()


def _pause(seconds: float) -> None:
    event = getattr(_operation, "cancel_event", None)
    if event is not None:
        event.wait(seconds)
    else:
        time.sleep(seconds)


def _kill_tree(proc: subprocess.Popen) -> None:
    """Close only the retained process handle and its preassigned owned Job."""
    from ..agents.runner import close_owned_process
    close_owned_process(proc)


def _run_process(args: list[str], *, timeout: float, cwd=None, on_line=None) -> tuple[int, str]:
    """Stream bounded output while an independent deadline supervises the CLI."""
    if _cancelled():
        return -2, "Docker operation cancelled"
    from ..agents.runner import spawn_owned_process
    try:
        proc = spawn_owned_process(args, cwd=str(cwd) if cwd is not None else None,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   cancel=getattr(_operation, "cancel_event", None))
    except OSError as exc:
        return -1, f"Docker CLI unavailable: {exc}"
    chunks: deque[str] = deque(maxlen=64)
    done = threading.Event()

    def read_output() -> None:
        try:
            assert proc.stdout is not None
            while chunk := proc.stdout.read1(4096):
                decoded = chunk.decode("utf-8", errors="replace")
                chunks.append(decoded)
                if on_line:
                    for line in decoded.splitlines():
                        try:
                            on_line(line)
                        except Exception:  # logging must not stop process supervision
                            pass
        finally:
            done.set()

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    deadline = time.monotonic() + max(timeout, 0.01)
    failure = ""
    parent_closed = False
    while proc.poll() is None or not done.is_set():
        if proc.poll() is not None and not parent_closed:
            _kill_tree(proc)  # descendants cannot hold stdout after leader exit
            parent_closed = True
        if _cancelled():
            failure = "Docker operation cancelled"
            break
        if time.monotonic() >= deadline:
            failure = f"Docker operation timeout after {timeout:g}s"
            break
        done.wait(min(0.05, max(0.001, deadline - time.monotonic())))
        if done.is_set() and proc.poll() is None:
            _pause(0.01)
    _kill_tree(proc)
    reader.join(timeout=1)
    if done.is_set() and proc.stdout is not None:
        proc.stdout.close()
    output = "".join(chunks)[-16000:]
    if failure:
        return (-2 if "cancelled" in failure else -1), output + "\n" + failure
    return proc.returncode, output


LABEL_PROJECT = "autospec.project"
LABEL_PORT = "autospec.port"
LABEL_ACTIVE = "autospec.delivery.active"

# Substrings that mark a "the daemon is not reachable / docker is not installed"
# condition — an infra problem, never a repairable wiring bug. The public tuple
# is shared with ``Pipeline._smoke_looks_like_infra`` (single source of truth);
# Missing application files are deliberately excluded: a failed Docker COPY is
# a repairable source problem, unlike a missing Docker executable or socket.
DOCKER_INFRA_MARKERS = (
    "error during connect",
    "cannot connect to the docker daemon",
    "pipe/docker_engine",
    "dockerdesktoplinuxengine",
    "is the docker daemon running",
    # Windows : Docker Desktop lancé dans la session d'un AUTRE utilisateur -
    # l'ACL du named pipe refuse notre process (vu en run supervisé 2026-07-20).
    "permission denied while trying to connect",
)
_DAEMON_DOWN_MARKERS = DOCKER_INFRA_MARKERS + ("dial unix /var/run/docker.sock",)

# Retry once for a peer's slow cold-start; unrelated peer pairs are not tested.
_PROBE_RETRY_DELAY_S = 2.0


def slug(project_id: str) -> str:
    """Sanitise a project id into a docker-safe token (``[a-z0-9-]`` only)."""
    s = re.sub(r"[^a-z0-9-]", "-", (project_id or "").lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "app"


def image_name(project_id: str) -> str:
    return f"autospec/{slug(project_id)}:latest"


def container_name(project_id: str) -> str:
    return f"autospec-{slug(project_id)}"


def data_volume_name(project_id: str) -> str:
    return f"{container_name(project_id)}-data"


def ensure_data_volume(project_id: str, name: str | None = None) -> str:
    """Create or reuse owned storage; never adopt another project's volume."""
    name = name or data_volume_name(project_id)
    rc, out = _docker(["volume", "inspect", name], timeout=15)
    if rc != 0:
        if "no such volume" not in out.lower():
            raise DockerRuntimeError(out)
        rc, out = _docker(["volume", "create", "--label", f"{LABEL_PROJECT}={project_id}", name], timeout=15)
        if rc != 0:
            raise DockerRuntimeError(out)
        rc, out = _docker(["volume", "inspect", name], timeout=15)
        if rc != 0:
            raise DockerRuntimeError(out)
    try:
        if (json.loads(out)[0].get("Labels") or {}).get(LABEL_PROJECT) != project_id:
            raise DockerRuntimeError(f"Le volume {name} appartient à un autre projet")
    except (ValueError, IndexError, TypeError, KeyError) as exc:
        raise DockerRuntimeError(f"volume inspect invalide : {out[:500]}") from exc
    return name


def _docker(args: list[str], *, timeout: float, cwd: str | Path | None = None) -> tuple[int, str]:
    """Run ``docker <args>`` synchronously; return ``(returncode, output)``.

    stdout+stderr are merged. A launch failure (docker absent) or a timeout is
    reported as ``(-1, str(exc))`` so callers can classify it via
    :func:`looks_like_daemon_down`."""
    return _run_process([settings.docker_cmd, *args], timeout=timeout, cwd=cwd)


def looks_like_daemon_down(output: str) -> bool:
    """Does ``output`` look like the Docker engine is unreachable / absent?"""
    low = (output or "").lower()
    return any(marker in low for marker in _DAEMON_DOWN_MARKERS) or "docker cli unavailable" in low


def looks_like_infra(output: str) -> bool:
    """Daemon, registry/network, and host resource errors are not app repairs."""
    low = (output or "").lower()
    return looks_like_daemon_down(output) or any(marker in low for marker in (
        "toomanyrequests", "pull rate limit", "failed to authorize", "unauthorized:",
        "failed to fetch oauth token", "proxyconnect", "tls handshake timeout",
        "no space left on device", "cannot assign requested address",
        "port is already allocated", "address already in use",
        "appartient à un autre projet",
    ))


def docker_available() -> tuple[bool, str]:
    """Is a Docker *daemon* reachable? Returns ``(ok, output)``."""
    rc, out = _docker(
        ["version", "--format", "{{.Server.Version}}"],
        timeout=15.0,
    )
    return rc == 0, out.strip()


def ensure_network(network: str) -> tuple[bool, str]:
    """Ensure the shared network exists (create if missing, tolerate races)."""
    rc, out = _docker(["network", "inspect", network], timeout=15.0)
    if rc == 0:
        return True, ""
    if looks_like_daemon_down(out):
        return False, out
    rc, out = _docker(["network", "create", network], timeout=30.0)
    if rc == 0:
        return True, ""
    # A concurrent creation (another pipeline) is not an error for us.
    if "already exists" in (out or "").lower():
        return True, ""
    return False, out


def build_image(
    ws: Path,
    image: str,
    *,
    timeout: float,
    on_line=None,
    cancel_event: threading.Event | None = None,
) -> tuple[bool, str]:
    """Build ``image`` from ``ws`` (the workspace holds the managed Dockerfile).

    Streams each build line to ``on_line`` (if given) and returns
    ``(succeeded, tail)`` where ``tail`` is the last ~4000 chars of output."""
    previous = getattr(_operation, "cancel_event", None)
    if cancel_event is not None:
        _operation.cancel_event = cancel_event
    try:
        from .isolated_validation import build_delivery_image
        try:
            ok, output = build_delivery_image(ws, image, docker=settings.docker_cmd, timeout=timeout)
        except (OSError, RuntimeError, ValueError) as exc:
            return False, str(exc)
        if on_line:
            for line in output.splitlines():
                on_line(line)
        return ok, output[-4000:]
    finally:
        _operation.cancel_event = previous


def replace_container(
    image: str,
    name: str,
    network: str,
    host_port: int,
    container_port: int,
    project_id: str,
    *, data_volume: str | None = None,
) -> tuple[bool, str]:
    """Start a fresh name; replacement/rollback is owned by deploy_and_verify."""
    rc, out = _docker(
        [
            "run",
            "-d",
            "--name",
            name,
            "--network",
            network,
            "-p",
            f"127.0.0.1:{host_port or ''}:{container_port}",
            "--label",
            f"{LABEL_PROJECT}={project_id}",
            "--label",
            f"{LABEL_PORT}={container_port}",
            "--label",
            f"{LABEL_ACTIVE}={int(name == container_name(project_id))}",
            "--restart",
            "on-failure:3",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--user", "65532:65532", "--read-only",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
            "--memory", "512m", "--cpus", "1", "--pids-limit", "256",
            *(["--mount", f"type=volume,source={data_volume},target=/app/data",
               "--env", "DATABASE_URL=sqlite:////app/data/app.db"] if data_volume else []),
            image,
        ],
        timeout=60.0,
    )
    return rc == 0, out.strip()


def _container_logs(name: str, *, tail: int = 80) -> str:
    _, out = _docker(["logs", "--tail", str(tail), name], timeout=15.0)
    return out.strip()


def wait_healthy(
    name: str, host_port: int, *, timeout: float,
    health_path: str = "/", expected: dict[str, str] | None = None,
    strict_http: bool = False,
) -> tuple[bool, str]:
    """Poll until the container is listening on ``127.0.0.1:host_port``.

    - ``docker inspect`` state ``exited``/``dead`` → fail fast with the logs.
    - Managed APIs must satisfy their JSON health contract inside the image.
    - Frontends must return HTTP 2xx; legacy products without a contract retain
      the historical connectivity-only check (any HTTP status).
    - Timeout → fail with the logs (repairable: localhost binding, boot crash,
      wrong internal port)."""
    import time

    deadline = time.monotonic() + max(timeout, 0.01)
    url = f"http://127.0.0.1:{host_port}{health_path}"
    last = ""
    while time.monotonic() < deadline:
        if _cancelled():
            return False, "Docker operation cancelled"
        rc, state = _docker(
            ["inspect", "-f", "{{.State.Status}}", name],
            timeout=min(15.0, max(0.01, deadline - time.monotonic())),
        )
        status = state.strip().lower()
        if rc != 0:
            last = state.strip()
            return False, last
        if status in ("exited", "dead"):
            logs = _container_logs(name)
            return False, f"container {status}\n{logs}"
        try:
            with urllib.request.urlopen(url, timeout=min(5, max(0.01, deadline - time.monotonic()))) as response:
                if expected is not None:
                    payload = json.loads(response.read(16384).decode("utf-8"))
                    if response.status == 200 and isinstance(payload, dict) and all(
                        payload.get(key) == value for key, value in expected.items()
                    ):
                        return True, ""
                    last = f"contrat santé {health_path} invalide (HTTP {response.status}, attendu {expected}, reçu {str(payload)[:500]})"
                elif not strict_http or 200 <= response.status < 300:
                    return True, ""
                else:
                    last = f"HTTP {response.status} sur {health_path}"
        except urllib.error.HTTPError as exc:
            if not strict_http and expected is None:
                return True, ""
            last = f"HTTP {exc.code} sur {health_path}"
        except (ValueError, UnicodeError) as exc:
            last = f"réponse santé JSON invalide sur {health_path}: {exc}"
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last = str(exc)
        _pause(min(1.0, max(0.01, deadline - time.monotonic())))

    logs = _container_logs(name)
    return False, f"health-wait timeout après {timeout:.0f}s ({last})\n{logs}"


_HOST_PORT_RE = re.compile(r"(?:\d{1,3}(?:\.\d{1,3}){3}|\[[^\]]*\]):(\d+)->")


def _parse_host_ports(ports_field: str) -> list[int]:
    """Extract the published HOST ports from a ``docker ps`` ``{{.Ports}}`` field.

    E.g. ``"0.0.0.0:18000->8000/tcp, [::]:18000->8000/tcp"`` → ``[18000]``."""
    return sorted({int(m) for m in _HOST_PORT_RE.findall(ports_field or "")})


def list_deployed(*, network: str | None = None) -> list[dict]:
    """Every currently-running Autospec container, from its labels.

    Label-based registry: containers of deleted/dead projects self-clean (they
    just drop out of ``docker ps``). ``port`` is the container-INTERNAL port
    (from the ``autospec.port`` label, used by the cross-container probes);
    ``host_ports`` are the actually-published HOST ports (from ``{{.Ports}}``,
    used by the port allocator)."""
    fmt = (
        "{{.Names}}\t{{.Label \"" + LABEL_PROJECT + "\"}}\t{{.Label \""
        + LABEL_PORT + "\"}}\t{{.Ports}}\t{{.Label \"" + LABEL_ACTIVE + "\"}}"
    )
    rc, out = _docker(
        ["ps", "--filter", f"label={LABEL_PROJECT}",
         *(["--filter", f"network={network}"] if network else []), "--format", fmt],
        timeout=15.0,
    )
    if rc != 0:
        raise DockerRuntimeError(out.strip() or "docker ps failed without diagnostic")
    deployed: list[dict] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) > 4 and parts[4] == "0":
            continue  # transactional candidate, not an independently delivered peer
        name = parts[0] if len(parts) > 0 else ""
        project = parts[1] if len(parts) > 1 else ""
        port_raw = parts[2] if len(parts) > 2 else ""
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            port = 0
        host_ports = _parse_host_ports(parts[3]) if len(parts) > 3 else []
        if name:
            deployed.append(
                {"name": name, "project": project, "port": port, "host_ports": host_ports}
            )
    return deployed


def probe(src: str, dst: str, dst_port: int) -> tuple[bool, str]:
    """From inside ``src``, can we HTTP-reach ``http://<dst>:<dst_port>/`` ?

    Python images ship no curl/wget; nginx:alpine ships busybox wget but no
    python. So we try ``python -c urllib`` first, then fall back to busybox
    ``wget``. An ``HTTPError`` inside the container counts as reachable — DNS +
    TCP + HTTP were all proved."""
    url = f"http://{dst}:{dst_port}/"
    py = (
        "import urllib.request,urllib.error,sys\n"
        f"try:\n urllib.request.urlopen('{url}',timeout=5)\n"
        "except urllib.error.HTTPError:\n pass\n"
        "except Exception as e:\n sys.stderr.write(str(e)); sys.exit(1)\n"
    )
    rc, out = _docker(["exec", src, "python", "-c", py], timeout=20.0)
    if rc == 0:
        return True, ""
    # python absent in the source container → busybox wget fallback (nginx image).
    combined = out.lower()
    if "executable file not found" in combined or "no such file" in combined or "not found" in combined:
        rc2, out2 = _docker(
            ["exec", src, "wget", "-S", "-O", "/dev/null", "-T", "5", url],
            timeout=20.0,
        )
        if rc2 == 0 or re.search(r"HTTP/\d(?:\.\d)?\s+[1-5]\d\d|server returned error: HTTP/\d(?:\.\d)?\s+[1-5]\d\d", out2, re.I):
            return True, ""
        if "not found" in out2.lower() or "no such file" in out2.lower():
            rc3, out3 = _docker(["exec", src, "curl", "--silent", "--show-error", "--output", "/dev/null", "--max-time", "5", url], timeout=10.0)
            return rc3 == 0, out3.strip()
        return False, (out2 or out).strip()
    return False, out.strip()


def check_cross_reachability(own_container: str, deployed: list[dict]) -> tuple[bool, str]:
    """Verify only the 2(N-1) directions involving this delivery."""
    ok = True
    lines: list[str] = []
    own = next((entry for entry in deployed if entry["name"] == own_container), None)
    if own is None:
        return False, f"container {own_container} absent du registre Docker"
    peers = [entry for entry in deployed if entry["name"] != own_container and entry.get("project") != own.get("project")]
    own_pairs = [(src, dst) for peer in peers for src, dst in ((own, peer), (peer, own)) if dst.get("port")]
    for src, dst in own_pairs:
        if _cancelled():
            return False, "Docker operation cancelled"
        dst_port = dst["port"]
        reachable, err = probe(src["name"], dst["name"], dst_port)
        if not reachable and not looks_like_infra(err):
            # One retry: a peer that just booted may need a moment.
            _pause(_PROBE_RETRY_DELAY_S)
            if _cancelled():
                return False, "Docker operation cancelled"
            reachable, err = probe(src["name"], dst["name"], dst_port)
        if reachable:
            lines.append(f"OK   {src['name']} -> {dst['name']}:{dst_port}")
        else:
            ok = False
            lines.append(f"FAIL {src['name']} -> {dst['name']}:{dst_port} ({err})")

    return ok, "\n".join(lines)


def undeploy(project_id: str, *, publication_root: Path | None = None,
             packaging_root: Path | None = None, expected_package_alias: str | None = None,
             expected_package_image_id: str | None = None,
             expected_publication_container: str | None = None) -> DockerDeployResult:
    """Remove owned resources, reporting every actual failure to the caller."""
    if packaging_root is not None:
        if publication_root is not None:return DockerDeployResult(False,'Ambiguous package/publication cleanup authority',infra=True)
        from .owned_packages import PackageRegistry
        try:
            record=PackageRegistry(packaging_root).detach(project_id,expected_alias=expected_package_alias,
                expected_image_id=expected_package_image_id)
            return DockerDeployResult(True,'Exact owned package alias detached; shared immutable image untouched',
                image=record['spec']['image_id'],packaged=True)
        except (OSError,RuntimeError,ValueError) as exc:
            return DockerDeployResult(False,str(exc),infra=True,packaged=True)
    if publication_root is not None:
        from .owned_publication import PublicationRegistry
        try:
            record=PublicationRegistry(publication_root).stop(project_id,expected_container_id=expected_publication_container)
            release_host_port(project_id)
            return DockerDeployResult(True,'Owned NETNONE publication stopped; database retained',
                image=record['spec']['image_id'],host_port=record['host_port'])
        except (OSError,RuntimeError,ValueError) as exc:
            return DockerDeployResult(False,str(exc),infra=True)
    name = container_name(project_id)
    image = image_name(project_id)
    try:
        info = _inspect_container(name)
    except DockerRuntimeError as exc:
        return DockerDeployResult(False, str(exc), infra=True, container=name, image=image)
    if info and info.get("Config", {}).get("Labels", {}).get(LABEL_PROJECT) != project_id:
        return DockerDeployResult(False, "Refus de supprimer un conteneur appartenant à un autre projet", infra=True)
    rc, out = _docker(["rm", "-f", name], timeout=30.0)
    if rc != 0 and "no such container" not in out.lower():
        return DockerDeployResult(False, out, infra=looks_like_infra(out), container=name, image=image)
    rc, out = _docker(["rmi", image], timeout=60.0)
    if rc != 0 and "no such image" not in out.lower():
        return DockerDeployResult(False, out, infra=looks_like_infra(out), image=image)
    release_host_port(project_id)
    return DockerDeployResult(True, "Livraison Docker supprimée")


def host_port_is_free(port: int) -> bool:
    """Bind-test: also catches bound-but-not-listening sockets."""
    with socket.socket() as s:
        try:
            if os.name == "nt":
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def release_host_port(project_id: str, port: int | None = None) -> None:
    with _port_lock:
        reservation = _port_reservations.get(project_id)
        if reservation is not None and (port is None or reservation[0] == port):
            _port_reservations.pop(project_id)
            if reservation[1] is not None:
                reservation[1].close()


def _release_port_socket(project_id: str) -> None:
    """Keep the logical claim while Docker takes over the socket."""
    with _port_lock:
        reservation = _port_reservations.get(project_id)
        if reservation and reservation[1] is not None:
            reservation[1].close()
            _port_reservations[project_id] = (reservation[0], None)


def allocate_host_port(state: ProjectState) -> int:
    """Reserve a free socket, preferring a port still owned by this project.

    The socket protects against concurrent allocators/processes until Docker
    binds it. The in-process claim remains until deployment cleanup completes.
    Persisted ports are rechecked, never blindly reused.
    """
    from .. import storage
    with _port_lock:
        if state.id in _port_reservations:
            return _port_reservations[state.id][0]
        claimed = {value[0] for value in _port_reservations.values()}
        own_ports: set[int] = set()
        for entry in list_deployed():
            (own_ports if entry.get("project") == state.id else claimed).update(entry.get("host_ports") or [])
        for other in storage.list_states():
            if other.id != state.id and other.deploy_host_port:
                claimed.add(other.deploy_host_port)
        preferred = [state.deploy_host_port] if state.deploy_host_port else []
        for port in [*preferred, *range(int(settings.docker_host_port_base), 65536)]:
            if not 0 < port < 65536 or port in claimed:
                continue
            if port in own_ports:
                _port_reservations[state.id] = (port, None)
                return port
            if not host_port_is_free(port):
                continue
            sock = socket.socket()
            try:
                if os.name == "nt":
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                sock.bind(("127.0.0.1", port))
            except OSError:
                sock.close()
                continue
            _port_reservations[state.id] = (port, sock)
            return port
        raise DockerRuntimeError("Aucun port hôte disponible pour la livraison Docker")


def should_run(
    state: ProjectState,
    ws: Path,
    *,
    enabled: bool,
) -> tuple[bool, str, str]:
    """Resolve delivery from the selected technical stack, then legacy artifacts.

    Web projects are served; CLI and library projects receive a packaged image.
    Disabled, demo, unfinished, and unrecognised projects are skipped.
    """
    from ..models import StoryStatus

    if not enabled:
        return False, "livraison Docker désactivée", ""
    if settings.fake_agents:
        return False, "mode démo", ""
    if not any(s.effective_status() == StoryStatus.DONE for s in state.stories):
        return False, "aucune story livrée", ""

    stack = getattr(state, "technical_stack", None)
    stack_kind = stack.get("kind", "") if isinstance(stack, dict) else getattr(stack, "kind", "")
    if stack_kind in {"backend", "api", "fullstack", "frontend", "cli", "library"}:
        return True, "", "backend" if stack_kind == "api" else stack_kind
    profile = state.product_profile
    if profile in {"cli", "library-fast"}:
        return True, "", "cli" if profile == "cli" else "library"
    backend_web = _backend_web_candidate(ws)
    frontend = _frontend_root(state, ws)
    non_python = state.backend_language.value in {"go", "rust", "node", "typescript"}
    if backend_web or profile in {"api", "web-ssr", "fullstack"} or (non_python and ((ws / "go.mod").exists() or (ws / "Cargo.toml").exists())):
        kind = "fullstack" if frontend is not None else "backend"
        return True, "", kind

    if frontend is not None:
        return True, "", "frontend"

    if (ws / "main.py").exists() or (ws / "package.json").exists():
        return True, "", "cli"
    if (ws / "pyproject.toml").exists():
        return True, "", "library"
    return False, "aucun projet exécutable ou bibliothèque détecté", ""


def _inspect_container(name: str) -> dict | None:
    rc, out = _docker(["inspect", name], timeout=15.0)
    if rc != 0:
        if "no such object" in out.lower() or "no such container" in out.lower():
            return None
        raise DockerRuntimeError(out or f"docker inspect {name} failed")
    try:
        return json.loads(out)[0]
    except (ValueError, IndexError, KeyError, TypeError) as exc:
        raise DockerRuntimeError(f"docker inspect {name}: invalid JSON: {out[:500]}") from exc


def _published_port(info: dict, container_port: int) -> int:
    ports = info.get("NetworkSettings", {}).get("Ports", {})
    for binding in ports.get(f"{container_port}/tcp") or []:
        if binding.get("HostIp") == "127.0.0.1":
            return int(binding["HostPort"])
    raise DockerRuntimeError("Aucune publication loopback retournée par Docker")


def inspect_deployment(project_id: str, *, publication_root: Path | None = None) -> DockerDeployResult:
    """Reconcile persisted deployment against Docker without changing resources."""
    if publication_root is not None:
        from .owned_publication import PublicationRegistry
        try:
            record=PublicationRegistry(publication_root).status(project_id)
            active=record.get('status')=='running' and record['running'] and record['ingress_attached']
            return DockerDeployResult(active,'Owned NETNONE ingress active' if active else
                'Owned publication stopped or ingress recovery required',
                image=record.get('spec',{}).get('image_id',''),container=record.get('container_id') or '',
                host_port=record.get('host_port',0),skipped=not record.get('registered') or record.get('status') in {'stopped','destroyed'})
        except (OSError,RuntimeError,ValueError) as exc:
            return DockerDeployResult(False,str(exc),infra=True)
    name = container_name(project_id)
    try:
        info = _inspect_container(name)
        if info is None:
            return DockerDeployResult(False, "Conteneur Docker absent", skipped=True)
        if info.get("Config", {}).get("Labels", {}).get(LABEL_PROJECT) != project_id:
            return DockerDeployResult(False, "Nom de conteneur occupé par une ressource étrangère", infra=True)
        running = info.get("State", {}).get("Running", False)
        port = int(info.get("Config", {}).get("Labels", {}).get(LABEL_PORT, 0))
        host = _published_port(info, port) if running else 0
        return DockerDeployResult(bool(running), "Conteneur actif" if running else "Conteneur arrêté",
                                  image=image_name(project_id), container=name, host_port=host)
    except (DockerRuntimeError, ValueError) as exc:
        return DockerDeployResult(False, str(exc), infra=True)


def inspect_packaged_image(project_id: str, *, packaging_root: Path | None = None,
                           qualified_image_id: str | None = None,
                           expected_snapshot: str | None = None,
                           expected_runtime_command=None,
                           expected_contract_hash: str | None = None) -> DockerDeployResult:
    """A packaged CLI/library owns an image, not a long-running container."""
    if packaging_root is not None or qualified_image_id is not None:
        from .owned_packages import PackageRegistry,PackageSpec,attest_package_image
        try:
            spec=None
            if qualified_image_id is not None:
                spec=PackageSpec(qualified_image_id,expected_snapshot,expected_contract_hash,expected_runtime_command)
            if packaging_root is not None:
                record=PackageRegistry(packaging_root).inspect(project_id,expected=spec)
                return DockerDeployResult(bool(record['packaged']),'Exact qualified package alias present' if record['packaged'] else 'Owned package absent/detached',
                    image=record.get('spec',{}).get('image_id',''),packaged=True,
                    skipped=not record.get('registered') or record.get('status')=='detached')
            attest_package_image(spec)
            return DockerDeployResult(True,'Qualified immutable image freshly re-attested; no alias removal authority',image=spec.image_id,packaged=True)
        except (OSError,RuntimeError,ValueError,TypeError) as exc:
            return DockerDeployResult(False,str(exc),infra=True,packaged=True)
    image = image_name(project_id)
    rc, out = _docker(["image", "inspect", image], timeout=15.0)
    if rc != 0:
        absent = "no such image" in out.lower() or "no such object" in out.lower()
        return DockerDeployResult(False, out.strip(), skipped=absent,
                                  infra=not absent, packaged=True)
    return DockerDeployResult(True, "Image Docker disponible", image=image, packaged=True)


def recover_publication(project_id: str, publication_root: Path, *, timeout: float = 30,
                        intended_active_only: bool = False, cancel_event=None) -> DockerDeployResult:
    """Explicit factory-start recovery; status inspection never adopts state."""
    from .owned_publication import PublicationRegistry
    try:
        registry=PublicationRegistry(publication_root)
        if intended_active_only:
            status=registry.status(project_id)
            if not status.get('registered') or status.get('status') in {'stopped','destroyed'}:
                return DockerDeployResult(False,'Intentional stopped/absent publication was not restarted',skipped=True)
            if status.get('status') not in {'running','creating'}:
                return DockerDeployResult(False,'Publication journal is not intended active; explicit disposition required',infra=True)
        record=registry.recover(project_id,timeout=timeout,cancel_event=cancel_event)
        return DockerDeployResult(True,'Owned NETNONE ingress recovered without rebuild or source overlay',
            image=record['spec']['image_id'],container=record['container_id'],host_port=record['host_port'])
    except (OSError,RuntimeError,ValueError) as exc:
        return DockerDeployResult(False,str(exc),infra=True)


def destroy_publication_data(project_id: str, publication_root: Path) -> DockerDeployResult:
    """Irreversible explicit cleanup, not an implicit part of undeploy/stop."""
    from .owned_publication import PublicationRegistry
    try:
        record=PublicationRegistry(publication_root).destroy_data(project_id)
        return DockerDeployResult(True,'Exact owned publication database destroyed',image=record['spec']['image_id'])
    except (OSError,RuntimeError,ValueError) as exc:
        return DockerDeployResult(False,str(exc),infra=True)


def _qualified_image_facts(identifier: str, snapshot: str, runtime_command) -> dict:
    """Fresh inspection of an already admitted immutable artifact, never rebuild."""
    if (not isinstance(identifier,str) or not re.fullmatch(r'sha256:[a-f0-9]{64}',identifier) or
        not isinstance(snapshot,str) or not re.fullmatch(r'[a-f0-9]{64}',snapshot) or
        not isinstance(runtime_command,(list,tuple)) or not 1<=len(runtime_command)<=200 or
        any(not isinstance(arg,str) or len(arg)>4096 or '\x00' in arg for arg in runtime_command) or
        not runtime_command[0] or runtime_command[0].startswith('-')):
        raise DockerRuntimeError('QUALIFIED_IMAGE_FACTS_REQUIRED: immutable ID, snapshot and exact reviewed argv')
    rc,out=_docker(['image','inspect',identifier],timeout=15)
    if rc:
        raise DockerRuntimeError('QUALIFIED_IMAGE_INSPECTION_UNAVAILABLE: '+out)
    try:
        values=json.loads(out)
        if not isinstance(values,list) or len(values)!=1:raise ValueError('one exact image required')
        info=values[0];config=info['Config']
        if (info['Id']!=identifier or info.get('Os')!='linux' or
            config.get('Labels',{}).get('autospec.snapshot')!=snapshot or config.get('WorkingDir')!='/app' or
            config.get('Cmd')!=list(runtime_command) or config.get('Entrypoint') not in (None,[])):
            raise ValueError('actual immutable image/source/default command differs')
        return info
    except (ValueError,KeyError,TypeError) as exc:
        raise DockerRuntimeError('QUALIFIED_IMAGE_FACTS_DIFFER: actual image, source, CMD or entrypoint') from exc


def _package_qualified_image(state,ws,*,identifier,snapshot,runtime_command,kind,on_stage=None,cancel_event=None):
    """Keep qualified artifacts, refuse publication without host isolation.

    Docker --internal still permits gateway/host services. A dedicated bridge
    is therefore NOT an admitted host boundary. No network/foreign container is
    probed or changed; a future owned NETNONE publication port is required.
    """
    from ..validation.final_gate import source_snapshot
    alias=image_name(state.id).removesuffix(':latest')+':qualified-'+uuid.uuid4().hex
    previous=getattr(_operation,'cancel_event',None);_operation.cancel_event=cancel_event
    tag_requested=keep_tag=False
    try:
        if _cancelled():raise DockerRuntimeError('Docker operation cancelled')
        root=Path(ws).absolute()
        if root.resolve()!=root or not root.is_dir():
            raise DockerRuntimeError('QUALIFIED_SOURCE_REFUSED: canonical existing source required')
        # Do not query a daemon or mutate tags without complete source facts.
        if not isinstance(snapshot,str) or not re.fullmatch(r'[a-f0-9]{64}',snapshot) or source_snapshot(root).digest!=snapshot:
            raise DockerRuntimeError('QUALIFIED_SOURCE_REFUSED: exact source snapshot differs')
        _qualified_image_facts(identifier,snapshot,runtime_command)
        if _cancelled():raise DockerRuntimeError('Docker operation cancelled')
        rc,out=_docker(['image','inspect',alias],timeout=15)
        if not rc or not any(marker in out.lower() for marker in ('no such image','no such object')):
            raise DockerRuntimeError('QUALIFIED_IMAGE_ALIAS_OCCUPIED_OR_UNAVAILABLE')
        if on_stage is not None:
            try:on_stage('packaging')
            except Exception:pass
        tag_requested=True
        rc,out=_docker(['tag',identifier,alias],timeout=15)
        if rc:raise DockerRuntimeError('QUALIFIED_IMAGE_TAG_UNAVAILABLE: '+out)
        # Inspect the alias freshly, then the immutable ID. A tag alone cannot
        # confer qualification or substitute another project's artifact.
        rc,out=_docker(['image','inspect',alias],timeout=15)
        try:
            if rc or json.loads(out)[0]['Id']!=identifier:raise ValueError('alias identity differs')
        except (ValueError,KeyError,IndexError,TypeError) as exc:
            raise DockerRuntimeError('QUALIFIED_IMAGE_TAG_IDENTITY_DIFFER') from exc
        _qualified_image_facts(identifier,snapshot,runtime_command)
        if source_snapshot(root).digest!=snapshot:
            raise DockerRuntimeError('QUALIFIED_SOURCE_REFUSED: source changed while packaging')
        if _cancelled():raise DockerRuntimeError('Docker operation cancelled')
        keep_tag=True
        if kind in {'cli','library'}:
            return DockerDeployResult(True,'Qualified immutable artifact packaged without rebuild; alias '+alias,
                image=identifier,packaged=True)
        return DockerDeployResult(False,'PUBLICATION_ISOLATION_UNAVAILABLE: qualified image packaged, NOT deployed; '
            'an owned NETNONE ingress is required (internal bridge permits host gateway access); alias '+alias,
            image=identifier,packaged=True,infra=True)
    except (DockerRuntimeError,OSError,RuntimeError,ValueError) as exc:
        return DockerDeployResult(False,str(exc),image=identifier or '',cancelled=_cancelled(),
            infra='UNAVAILABLE' in str(exc),packaged=False)
    finally:
        _operation.cancel_event=None  # owned cleanup is allowed after cancellation
        try:
            if tag_requested and not keep_tag:
                # Only our preflight-absent UUID alias with the exact expected ID.
                # A replacement/unknown daemon state is not deletion authority.
                try:
                    rc,out=_docker(['image','inspect',alias],timeout=15)
                    if not rc and json.loads(out)[0]['Id']==identifier:
                        _docker(['image','rm',alias],timeout=15)
                except (OSError,RuntimeError,ValueError,KeyError,IndexError,TypeError):
                    pass  # no identity/daemon capability: never remove a foreign tag
        finally:
            _operation.cancel_event=previous


def deploy_and_verify(
    state: ProjectState,
    ws: Path,
    *,
    network: str,
    host_port: int,
    build_timeout: float,
    deploy_timeout: float,
    kind: str = "",
    on_line=None,
    on_stage=None,
    cancel_event: threading.Event | None = None,
    qualified_image_id: str | None = None,
    expected_snapshot: str | None = None,
    expected_runtime_command: list[str] | tuple[str, ...] | None = None,
    publication_root: Path | None = None,
    publication_contract_hash: str | None = None,
    publication_internal_port: int | None = None,
    publication_local_cookie_mode: bool | None = None,
    publication_database_path: str | None = None,
    publication_health_path: str | None = None,
    publication_migration_command: list[str] | tuple[str,...] | None = None,
    packaging_root: Path | None = None,
) -> DockerDeployResult:
    """Build and verify a candidate before replacing the last working delivery.

    Docker cannot change an existing container's host-port mapping. A candidate
    is checked on an ephemeral loopback port first; the fixed-port cutover then
    retains a stopped backup until health AND network checks pass. Any failure
    restores it. Cancellation cooperatively stops CLI processes and performs the
    same rollback, so callers must await thread completion before teardown.
    """
    if qualified_image_id is not None or getattr(state,'acceptance_contract_hash',''):
        # Contract publication never enters the legacy rebuild/shared-network
        # route, even when a caller forgot the independently qualified facts.
        if kind in {'cli','library'}:
            from .owned_packages import PackageRegistry,PackageSpec
            try:
                if packaging_root is None:raise DockerRuntimeError('PACKAGING_REGISTRY_REQUIRED: no legacy/latest-name fallback')
                spec=PackageSpec(qualified_image_id,expected_snapshot,getattr(state,'acceptance_contract_hash',''),expected_runtime_command)
                record=PackageRegistry(packaging_root).package(state.id,ws,spec,cancel_event=cancel_event)
                return DockerDeployResult(True,'Qualified immutable CLI/library package journaled; alias '+record['alias'],
                    image=spec.image_id,packaged=True,created_package_alias=record['alias'] if record['created_this_call'] else '')
            except (OSError,RuntimeError,ValueError,TypeError) as exc:
                return DockerDeployResult(False,str(exc),image=qualified_image_id or '',infra=True,packaged=True,
                    cancelled=cancel_event is not None and cancel_event.is_set())
        if publication_root is not None:
            from .owned_publication import PublicationRegistry,PublicationSpec
            try:
                if publication_contract_hash!=getattr(state,'acceptance_contract_hash',''):
                    raise DockerRuntimeError('PUBLICATION_CONTRACT_IDENTITY_DIFFER')
                spec=PublicationSpec(qualified_image_id,expected_snapshot,publication_contract_hash,
                    expected_runtime_command,publication_internal_port,publication_local_cookie_mode,
                    publication_database_path,publication_health_path,publication_migration_command)
                # Release only this supervisor's retained allocator socket.
                # Registry binds the selected loopback port before daemon work;
                # an externally occupied port is refused, never swept/killed.
                _release_port_socket(state.id)
                record=PublicationRegistry(publication_root).publish(state.id,ws,spec,
                    host_port=host_port,timeout=deploy_timeout,cancel_event=cancel_event)
                return DockerDeployResult(True,'Qualified immutable image published through owned NETNONE ingress',
                    image=qualified_image_id,container=record['container_id'],host_port=record['host_port'],
                    created_publication_container=record['container_id'] if record['created_this_call'] else '')
            except (OSError,RuntimeError,ValueError,TypeError) as exc:
                return DockerDeployResult(False,str(exc),image=qualified_image_id or '',infra=True,
                    cancelled=cancel_event is not None and cancel_event.is_set())
        return _package_qualified_image(state,ws,identifier=qualified_image_id,
            snapshot=expected_snapshot,runtime_command=expected_runtime_command,kind=kind,
            on_stage=on_stage,cancel_event=cancel_event)
    if not kind:
        _, _, kind = should_run(state, ws, enabled=True)
    container_port = 8080 if kind == "frontend" else resolve_web_port(ws)
    image = image_name(state.id)
    name = container_name(state.id)
    token = uuid.uuid4().hex[:12]
    candidate_image = image.removesuffix(":latest") + f":candidate-{token}"
    candidate = name + f"-candidate-{token}"
    backup = name + f"-backup-{token}"
    package = kind in {"cli", "library"}
    stack = state.technical_stack or {}
    persistent_volume = ""
    candidate_volume = ""
    candidate_volume_owned = False
    health_options: dict = {}
    if stack.get("kind") in {"api", "fullstack"}:
        health_options = {
            "health_path": "/api/health", "strict_http": True,
            "expected": {"status": "ok", "service": "autospec-bootstrap",
                         "database": "ok" if stack.get("database", "none") != "none" else "none"},
        }
    elif kind == "frontend":
        health_options = {"strict_http": True}
    previous_event = getattr(_operation, "cancel_event", None)
    _operation.cancel_event = cancel_event
    candidate_started = False
    final_started = False
    backup_created = False
    old_was_running = False
    old_stopped = False
    committed = False
    cleanup_errors: list[str] = []
    build_tail = ""
    result: DockerDeployResult | None = None

    def _stage(stage: str) -> None:
        if on_stage is not None:
            try:
                on_stage(stage)
            except Exception:  # noqa: BLE001 — a UI hook must never break the deploy
                pass

    def _fail(detail: str, *, infra: bool = False) -> DockerDeployResult:
        return DockerDeployResult(
            ok=False,
            detail=detail,
            infra=infra or looks_like_infra(detail),
            image=image,
            container=name,
            host_port=host_port,
            cancelled=_cancelled(),
        )

    def command(args: list[str], timeout: float = 30.0) -> str:
        if _cancelled():
            raise DockerRuntimeError("Docker operation cancelled")
        rc, out = _docker(args, timeout=timeout)
        if rc != 0:
            raise DockerRuntimeError(out or f"docker {args[0]} failed")
        return out

    def cleanup(args: list[str]) -> bool:
        rc, out = _docker(args, timeout=30.0)
        if rc and not any(x in out.lower() for x in ("no such container", "no such image", "no such volume")):
            cleanup_errors.append(f"docker {' '.join(args)}: {out}")
            return False
        return True

    try:
        if _cancelled():
            raise DockerRuntimeError("Docker operation cancelled")
        ok, out = docker_available()
        if not ok:
            result = _fail(f"docker indisponible — {out}", infra=True)
        if result is None and not package:
            ok, out = ensure_network(network)
            if not ok:
                result = _fail(f"réseau {network} indisponible — {out}", infra=True)
        if result is None:
            _stage("building")
            built, build_tail = build_image(ws, candidate_image, timeout=build_timeout, on_line=on_line)
            if not built:
                result = _fail("=== docker build (tail) ===\n" + build_tail)
        if result is None and package:
            _stage("verifying")
            # --rm alone cannot clean a daemon-side container when the attached
            # CLI is killed. A known name allows the finally block to remove it.
            if kind == "cli":
                candidate_started = True
                command(["run", "--rm", "--name", candidate, "--network", "none",
                         "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                         "--memory", "512m", "--cpus", "1", "--pids-limit", "256",
                         candidate_image, "--help"], deploy_timeout)
            command(["tag", candidate_image, image])
            committed = True
            result = DockerDeployResult(True, f"Image {image} construite et {'commande --help vérifiée' if kind == 'cli' else 'paquet compilé/installé'} ({kind})",
                                        image=image, packaged=True)
        if result is None:
            if _cancelled():
                raise DockerRuntimeError("Docker operation cancelled")
            if stack.get("database") == "sqlite":
                persistent_volume = ensure_data_volume(state.id)
                candidate_volume = data_volume_name(state.id) + f"-candidate-{token}"
                ensure_data_volume(state.id, candidate_volume)
                candidate_volume_owned = True
            old = _inspect_container(name)
            if old and old.get("Config", {}).get("Labels", {}).get(LABEL_PROJECT) != state.id:
                raise DockerRuntimeError("Nom de conteneur occupé par une ressource étrangère")
            old_was_running = bool(old and old.get("State", {}).get("Running"))
            _stage("deploying")
            candidate_started = True  # run can create a container before reporting an error
            started, out = replace_container(candidate_image, candidate, network, 0, container_port, state.id,
                                              data_volume=candidate_volume or None)
            if not started:
                raise DockerRuntimeError(out)
            candidate_info = _inspect_container(candidate)
            if candidate_info is None:
                raise DockerRuntimeError("Conteneur candidat absent après docker run")
            try:
                temp_port = _published_port(candidate_info, container_port)
            except DockerRuntimeError as exc:
                # A fast boot crash can remove the binding before our first
                # inspect. Keep its real traceback for the repair agent.
                raise DockerRuntimeError(f"{exc}\n{_container_logs(candidate)}") from exc
            _stage("verifying")
            healthy, out = wait_healthy(candidate, temp_port, timeout=deploy_timeout, **health_options)
            if not healthy:
                raise DockerRuntimeError(out)
            if _cancelled():
                raise DockerRuntimeError("Docker operation cancelled")
            if old:
                if old_was_running:
                    old_stopped = True
                    command(["stop", "--time", "5", name], 15.0)
                backup_created = True
                command(["rename", name, backup])
            _release_port_socket(state.id)
            final_started = True
            started, out = replace_container(candidate_image, name, network, host_port, container_port, state.id,
                                              data_volume=persistent_volume or None)
            if not started:
                raise DockerRuntimeError(out)
            healthy, out = wait_healthy(name, host_port, timeout=deploy_timeout, **health_options)
            if not healthy:
                raise DockerRuntimeError(out)
            net_ok, net_detail = check_cross_reachability(name, list_deployed(network=network))
            if not net_ok:
                raise DockerRuntimeError(net_detail)
            command(["tag", candidate_image, image])
            if _cancelled():
                raise DockerRuntimeError("Docker operation cancelled")
            committed = True
            result = DockerDeployResult(True,
                f"déployé {name} sur http://127.0.0.1:{host_port} (réseau {network})\n{net_detail}".strip(),
                image=image, container=name, host_port=host_port)
    except DockerRuntimeError as exc:
        result = _fail(f"{exc}\n\n=== docker build (tail) ===\n{build_tail[-1500:]}")
    finally:
        # Rollback/cleanup must be allowed to run after a cancellation request.
        _operation.cancel_event = None
        try:
            if not committed:
                removed = not final_started or cleanup(["rm", "-f", name])
                # A cancelled rename CLI may have completed on the daemon.
                # Inspect the actual result before choosing how to restore.
                actual_backup = False
                if backup_created:
                    try:
                        actual_backup = _inspect_container(backup) is not None
                    except DockerRuntimeError as exc:
                        cleanup_errors.append(str(exc))
                restored = not actual_backup or (removed and cleanup(["rename", backup, name]))
                if restored and old_was_running and (backup_created or old_stopped):
                    cleanup(["start", name])
            elif backup_created:
                cleanup(["rm", "-f", backup])
            if candidate_started:
                cleanup(["rm", "-f", candidate])
            if candidate_volume:
                if not candidate_volume_owned:
                    # Creation may have reached the daemon before cancellation.
                    # Never delete a volume whose ownership validation failed.
                    rc, volume_info = _docker(["volume", "inspect", candidate_volume], timeout=15)
                    if rc == 0:
                        try:
                            candidate_volume_owned = (json.loads(volume_info)[0].get("Labels") or {}).get(LABEL_PROJECT) == state.id
                        except (ValueError, IndexError, TypeError, KeyError):
                            pass
                if candidate_volume_owned:
                    cleanup(["volume", "rm", candidate_volume])
            cleanup(["rmi", candidate_image])
        finally:
            release_host_port(state.id)
            _operation.cancel_event = previous_event
    assert result is not None
    if cleanup_errors:
        from dataclasses import replace
        result = replace(result, ok=False, infra=True,
                         detail=result.detail + "\n=== nettoyage / rollback incomplet ===\n" + "\n".join(cleanup_errors))
    return result
