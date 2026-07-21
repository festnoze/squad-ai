"""Docker delivery: build, deploy & network-verify a project on a shared network.

Talks to the local Docker daemon (``deploy.py`` stays the artifact writer). Every
subprocess call here is synchronous, mirroring ``runtime_acceptance`` — the
pipeline drives the heavy work through ``asyncio.to_thread``. OSError /
TimeoutExpired are trapped everywhere and, when they look like a daemon-down /
docker-absent condition, classified as *infra* (park, don't burn repair attempts).
"""

from __future__ import annotations

import re
import socket
import subprocess
import urllib.error
import urllib.request
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


LABEL_PROJECT = "autospec.project"
LABEL_PORT = "autospec.port"

# Substrings that mark a "the daemon is not reachable / docker is not installed"
# condition — an infra problem, never a repairable wiring bug. The public tuple
# is shared with ``Pipeline._smoke_looks_like_infra`` (single source of truth);
# "no such file or directory" stays PRIVATE to this module: inside a smoke/pytest
# report it would misclassify an app-level FileNotFoundError as infra.
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
_DAEMON_DOWN_MARKERS = DOCKER_INFRA_MARKERS + (
    "no such file or directory",  # docker binary invoked but engine socket missing
)

# Cross-reachability tuning: one retry for pairs involving our own container
# (a slow cold-start must not burn a repair attempt), and a probe budget for
# foreign pairs so the matrix stays bounded on big fleets.
_PROBE_RETRY_DELAY_S = 2.0
_MAX_FOREIGN_PROBES = 20


def slug(project_id: str) -> str:
    """Sanitise a project id into a docker-safe token (``[a-z0-9-]`` only)."""
    s = re.sub(r"[^a-z0-9-]", "-", (project_id or "").lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "app"


def image_name(project_id: str) -> str:
    return f"autospec/{slug(project_id)}:latest"


def container_name(project_id: str) -> str:
    return f"autospec-{slug(project_id)}"


def _docker(args: list[str], *, timeout: float, cwd: str | Path | None = None) -> tuple[int, str]:
    """Run ``docker <args>`` synchronously; return ``(returncode, output)``.

    stdout+stderr are merged. A launch failure (docker absent) or a timeout is
    reported as ``(-1, str(exc))`` so callers can classify it via
    :func:`looks_like_daemon_down`."""
    try:
        proc = subprocess.run(
            [settings.docker_cmd, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd) if cwd is not None else None,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, str(exc)
    return proc.returncode, (proc.stdout or "")


def looks_like_daemon_down(output: str) -> bool:
    """Does ``output`` look like the Docker engine is unreachable / absent?"""
    low = (output or "").lower()
    return any(marker in low for marker in _DAEMON_DOWN_MARKERS)


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
) -> tuple[bool, str]:
    """Build ``image`` from ``ws`` (the workspace holds the managed Dockerfile).

    Streams each build line to ``on_line`` (if given) and returns
    ``(succeeded, tail)`` where ``tail`` is the last ~4000 chars of output."""
    lines: list[str] = []
    try:
        proc = subprocess.Popen(
            [settings.docker_cmd, "build", "-t", image, "."],
            cwd=str(ws),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return False, str(exc)

    assert proc.stdout is not None
    try:
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            lines.append(line)
            if on_line is not None:
                try:
                    on_line(line)
                except Exception:  # noqa: BLE001 — a logging hook must never break the build
                    pass
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            lines.append(f"[build timeout after {timeout:.0f}s]")
            return False, "\n".join(lines)[-4000:]
    finally:
        try:
            proc.stdout.close()
        except Exception:  # noqa: BLE001
            pass

    tail = "\n".join(lines)[-4000:]
    return proc.returncode == 0, tail


def replace_container(
    image: str,
    name: str,
    network: str,
    host_port: int,
    container_port: int,
    project_id: str,
) -> tuple[bool, str]:
    """Remove any old container of this name, then run the fresh image detached."""
    # rm -f old — ignore rc (it may simply not exist yet).
    _docker(["rm", "-f", name], timeout=30.0)
    rc, out = _docker(
        [
            "run",
            "-d",
            "--name",
            name,
            "--network",
            network,
            "-p",
            f"{host_port}:{container_port}",
            "--label",
            f"{LABEL_PROJECT}={project_id}",
            "--label",
            f"{LABEL_PORT}={container_port}",
            "--restart",
            "unless-stopped",
            image,
        ],
        timeout=60.0,
    )
    return rc == 0, out.strip()


def _container_logs(name: str, *, tail: int = 80) -> str:
    _, out = _docker(["logs", "--tail", str(tail), name], timeout=15.0)
    return out.strip()


def wait_healthy(name: str, host_port: int, *, timeout: float) -> tuple[bool, str]:
    """Poll until the container is listening on ``127.0.0.1:host_port``.

    - ``docker inspect`` state ``exited``/``dead`` → fail fast with the logs.
    - Any HTTP status (incl. 404/500) on ``GET /`` proves the port is open =
      healthy.
    - Timeout → fail with the logs (repairable: localhost binding, boot crash,
      wrong internal port)."""
    import time

    deadline = time.monotonic() + max(timeout, 1.0)
    url = f"http://127.0.0.1:{host_port}/"
    last = ""
    while time.monotonic() < deadline:
        rc, state = _docker(
            ["inspect", "-f", "{{.State.Status}}", name],
            timeout=15.0,
        )
        status = state.strip().lower()
        if rc != 0:
            last = state.strip()
            if looks_like_daemon_down(state):
                return False, last
        if status in ("exited", "dead"):
            logs = _container_logs(name)
            return False, f"container {status}\n{logs}"
        try:
            with urllib.request.urlopen(url, timeout=5):
                return True, ""
        except urllib.error.HTTPError:
            # Reached the server; any HTTP status means it is listening.
            return True, ""
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last = str(exc)
        time.sleep(1.0)

    logs = _container_logs(name)
    return False, f"health-wait timeout après {timeout:.0f}s ({last})\n{logs}"


_HOST_PORT_RE = re.compile(r"(?:\d{1,3}(?:\.\d{1,3}){3}|\[[^\]]*\]):(\d+)->")


def _parse_host_ports(ports_field: str) -> list[int]:
    """Extract the published HOST ports from a ``docker ps`` ``{{.Ports}}`` field.

    E.g. ``"0.0.0.0:18000->8000/tcp, [::]:18000->8000/tcp"`` → ``[18000]``."""
    return sorted({int(m) for m in _HOST_PORT_RE.findall(ports_field or "")})


def list_deployed() -> list[dict]:
    """Every currently-running Autospec container, from its labels.

    Label-based registry: containers of deleted/dead projects self-clean (they
    just drop out of ``docker ps``). ``port`` is the container-INTERNAL port
    (from the ``autospec.port`` label, used by the cross-container probes);
    ``host_ports`` are the actually-published HOST ports (from ``{{.Ports}}``,
    used by the port allocator)."""
    fmt = (
        "{{.Names}}\t{{.Label \"" + LABEL_PROJECT + "\"}}\t{{.Label \""
        + LABEL_PORT + "\"}}\t{{.Ports}}"
    )
    rc, out = _docker(
        ["ps", "--filter", f"label={LABEL_PROJECT}", "--format", fmt],
        timeout=15.0,
    )
    if rc != 0:
        return []
    deployed: list[dict] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
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
            ["exec", src, "wget", "-q", "-O-", "-T", "5", url],
            timeout=20.0,
        )
        if rc2 == 0:
            return True, ""
        return False, (out2 or out).strip()
    return False, out.strip()


def check_cross_reachability(own_container: str, deployed: list[dict]) -> tuple[bool, str]:
    """Probe reachability between the deployed containers.

    A failing pair *involving* ``own_container`` fails this project's gate
    (attributable, repairable) — those pairs are probed FIRST and get ONE retry
    after ``_PROBE_RETRY_DELAY_S`` so a slow cold-start never burns a repair
    attempt. A failing pair between two *foreign* containers is a warning only
    (never our bug to fix); foreign pairs have no retry and stop after
    ``_MAX_FOREIGN_PROBES`` probes so the matrix stays bounded on big fleets.
    Returns ``(ok_for_own, detail)``."""
    import time

    ok = True
    lines: list[str] = []
    warnings: list[str] = []

    own_pairs: list[tuple[dict, dict]] = []
    foreign_pairs: list[tuple[dict, dict]] = []
    for src in deployed:
        for dst in deployed:
            if src["name"] == dst["name"] or not (dst.get("port") or 0):
                continue
            if own_container in (src["name"], dst["name"]):
                own_pairs.append((src, dst))
            else:
                foreign_pairs.append((src, dst))

    for src, dst in own_pairs:
        dst_port = dst["port"]
        reachable, err = probe(src["name"], dst["name"], dst_port)
        if not reachable:
            # One retry: a peer that just booted may need a moment.
            time.sleep(_PROBE_RETRY_DELAY_S)
            reachable, err = probe(src["name"], dst["name"], dst_port)
        if reachable:
            lines.append(f"OK   {src['name']} -> {dst['name']}:{dst_port}")
        else:
            ok = False
            lines.append(f"FAIL {src['name']} -> {dst['name']}:{dst_port} ({err})")

    probed = 0
    for src, dst in foreign_pairs:
        if probed >= _MAX_FOREIGN_PROBES:
            warnings.append(
                f"(budget de sondes atteint : {len(foreign_pairs) - probed} "
                f"paire(s) tierce(s) non sondée(s))"
            )
            break
        probed += 1
        dst_port = dst["port"]
        reachable, err = probe(src["name"], dst["name"], dst_port)
        if reachable:
            lines.append(f"OK   {src['name']} -> {dst['name']}:{dst_port}")
        else:
            warnings.append(f"FAIL {src['name']} -> {dst['name']}:{dst_port} ({err})")

    if warnings:
        lines.append("--- avertissements (paires tierces) ---")
        lines.extend(warnings)
    return ok, "\n".join(lines)


def undeploy(project_id: str) -> None:
    """Best-effort teardown: force-remove the container, then remove the image."""
    name = container_name(project_id)
    image = image_name(project_id)
    _docker(["rm", "-f", name], timeout=30.0)
    _docker(["rmi", "-f", image], timeout=60.0)


def host_port_is_free(port: int) -> bool:
    """Is nothing already listening on ``127.0.0.1:<port>`` ? (connect-test).

    Single shared implementation — ``Pipeline._port_is_free`` delegates here."""
    with socket.socket() as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", port)) != 0


def allocate_host_port(state: ProjectState) -> int:
    """Return a stable host port for ``state``.

    Reuse ``state.deploy_host_port`` if already assigned. Otherwise scan upward
    from ``settings.docker_host_port_base`` skipping the HOST ports actually
    published by running autospec containers (authoritative even when a project
    state file is gone), the ports claimed by other persisted project states,
    and any host-busy port."""
    if state.deploy_host_port:
        return state.deploy_host_port

    claimed: set[int] = set()
    for entry in list_deployed():
        claimed.update(entry.get("host_ports") or [])
    from .. import storage

    for other in storage.list_states():
        if other.id == state.id:
            continue
        if other.deploy_host_port:
            claimed.add(other.deploy_host_port)

    port = int(settings.docker_host_port_base)
    while port < 65536:
        if port not in claimed and host_port_is_free(port):
            return port
        port += 1
    # Extremely unlikely fallback.
    return int(settings.docker_host_port_base)


def should_run(
    state: ProjectState,
    ws: Path,
    *,
    enabled: bool,
) -> tuple[bool, str, str]:
    """Should Docker delivery run for this project, and as which ``kind`` ?

    Returns ``(run, reason, kind)`` where ``kind`` ∈ ``{"backend", "fullstack",
    "frontend", ""}``:

    - a python web backend without a frontend → ``"backend"``;
    - a python web backend *with* a frontend root → ``"fullstack"`` (one image);
    - a frontend-only SPA (no python web backend) → ``"frontend"`` (nginx image,
      container port 80);

    Skip (``run=False``) when: the gate is off | demo mode (``fake_agents``) |
    no DONE story | a web backend written in a non-python language | neither a
    web backend nor a frontend was detected."""
    from ..models import StoryStatus

    if not enabled:
        return False, "livraison Docker désactivée", ""
    if settings.fake_agents:
        return False, "mode démo", ""
    if not any(s.effective_status() == StoryStatus.DONE for s in state.stories):
        return False, "aucune story livrée", ""

    backend_web = _backend_web_candidate(ws)
    frontend = _frontend_root(state, ws)

    if backend_web:
        from . import toolchain

        lang = toolchain.normalize(state.backend_language.value)
        if lang != "python":
            return (
                False,
                f"backend web {lang} non-python : livraison Docker non applicable",
                "",
            )
        kind = "fullstack" if frontend is not None else "backend"
        return True, "", kind

    if frontend is not None:
        return True, "", "frontend"

    return False, "produit non-web : livraison Docker non applicable", ""


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
) -> DockerDeployResult:
    """Single entry point: build → deploy → health → cross-reachability.

    Also reused as the repair ``averify`` (a full rebuild + redeploy + reverify).
    ``kind`` is the deploy kind already resolved by the caller (re-derived via
    :func:`should_run` only when empty). ``on_stage`` (if given) receives
    ``"building"`` / ``"deploying"`` / ``"verifying"`` as each stage starts so
    the UI can track progress — including during repair re-verifies.
    Classification contract:

    - ``docker_available`` / ``ensure_network`` failures → ``infra`` (park);
    - build / replace_container / wait_healthy / own-pair reachability failures →
      repairable (``ok=False`` without ``infra``).

    ``detail`` concatenates the build tail, the docker logs and the network
    sections."""
    if not kind:
        _, _, kind = should_run(state, ws, enabled=True)
    container_port = 80 if kind == "frontend" else resolve_web_port(ws)

    image = image_name(state.id)
    name = container_name(state.id)

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
            infra=infra,
            image=image,
            container=name,
            host_port=host_port,
        )

    # --- infra pre-checks -------------------------------------------------
    ok, out = docker_available()
    if not ok:
        return _fail(f"docker indisponible — {out}", infra=True)
    ok, out = ensure_network(network)
    if not ok:
        return _fail(f"réseau {network} indisponible — {out}", infra=True)

    # --- build (repairable) ----------------------------------------------
    _stage("building")
    built, build_tail = build_image(ws, image, timeout=build_timeout, on_line=on_line)
    if not built:
        return _fail("=== docker build (tail) ===\n" + build_tail)

    # --- deploy (repairable) ---------------------------------------------
    _stage("deploying")
    started, run_out = replace_container(
        image, name, network, host_port, container_port, state.id
    )
    if not started:
        return _fail(
            "=== docker build (tail) ===\n"
            + build_tail
            + "\n\n=== docker run ===\n"
            + run_out
        )

    # --- health (repairable) ---------------------------------------------
    _stage("verifying")
    healthy, health_out = wait_healthy(name, host_port, timeout=deploy_timeout)
    if not healthy:
        return _fail(
            "=== docker build (tail) ===\n"
            + build_tail[-1500:]
            + "\n\n=== docker logs ===\n"
            + health_out
        )

    # --- cross-container reachability (repairable for own pairs) ----------
    deployed = list_deployed()
    net_ok, net_detail = check_cross_reachability(name, deployed)
    if not net_ok:
        return _fail(
            "=== docker logs ===\n"
            + _container_logs(name)
            + "\n\n=== réseau ===\n"
            + net_detail
        )

    detail = f"déployé {name} sur http://localhost:{host_port} (réseau {network})"
    if net_detail:
        detail += "\n\n=== réseau ===\n" + net_detail
    return DockerDeployResult(
        ok=True,
        detail=detail,
        image=image,
        container=name,
        host_port=host_port,
    )
