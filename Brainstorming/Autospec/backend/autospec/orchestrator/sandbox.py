"""Fail-closed generated-code boundary, separate from CLI inference.

No host fallback, credential environment, Docker socket, privilege or external
networking is granted. Windows paths are literal argv with forward slashes.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from pathlib import Path

from ..agents.file_broker import ExecutionContext, FileBroker, IsolationViolation
from ..agents.runner import AgentError, _await_tracked, _run_tracked, _resolve_agent_command


def _unavailable(message: str) -> AgentError:
    return AgentError(f"ISOLATION_UNAVAILABLE: {message}", code="ISOLATION_UNAVAILABLE")


def _docker_call(args: list[str], **kwargs):
    # Apply the same native-command policy to preflight/cleanup as execution;
    # Windows must not reinterpret an arbitrary batch shim as a host shell.
    return subprocess.run(_resolve_agent_command(args), **kwargs)


def docker_run_cmd(inner_cmd: list[str], ws: str, image: str, docker: str = "docker",
                   network: str = "none", *, run_id: str | None = None,
                   container_name: str | None = None) -> list[str]:
    """Pure builder. Use run_isolated for preflight and daemon-side cleanup."""
    if network != "none":
        raise _unavailable("Generated-code execution requires network=none")
    if not inner_cmd or any(not isinstance(p, str) or "\x00" in p for p in inner_cmd):
        raise _unavailable("Invalid container command")
    if not image or image.startswith("-") or any(c.isspace() for c in image):
        raise _unavailable("Invalid sandbox image")
    if any(c in ws for c in (",", "\n", "\r", "\x00")):
        raise _unavailable("Ambiguous project mount path")
    owner = run_id or uuid.uuid4().hex
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", owner):
        raise _unavailable("Invalid run ownership label")
    name = container_name or f"autospec-sandbox-{uuid.uuid4().hex}"
    if not re.fullmatch(r"autospec-sandbox-[a-z0-9-]+", name):
        raise _unavailable("Invalid owned container name")
    return [docker, "run", "--rm", "--name", name,
            "--label", f"autospec.run_id={owner}", "--label", "autospec.kind=sandbox",
            "--pull", "never", "--network", "none", "--ipc", "private",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges=true",
            "--user", "65532:65532", "--read-only", "--pids-limit", "128",
            "--memory", "1g", "--cpus", "2", "--ulimit", "nofile=1024:1024",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
            "--env", "HOME=/tmp", "--env", "PYTHONDONTWRITEBYTECODE=1",
            "-v", f"{ws.replace(chr(92), '/')}:/app:rw", "-w", "/app",
            "--entrypoint", inner_cmd[0], image, *inner_cmd[1:]]


def require_sandbox(ws: str | Path, image: str, *, docker: str = "docker") -> Path:
    """Attest a Linux engine/local image and reject unsafe host-mounted links."""
    try:
        context = ExecutionContext("sandbox-preflight", Path(ws))
        broker = FileBroker(context)
        # Use a filtered clean product copy, never blindly mount a checkout.
        for path in context.project_root.rglob("*"):
            broker.path(path.relative_to(context.project_root).as_posix())
            if not path.is_file() and not path.is_dir():
                raise IsolationViolation("Special files cannot be mounted")
        result = _docker_call([docker, "info", "--format", "{{.OSType}}"],
                                capture_output=True, text=True, timeout=10, check=False)
        if result.returncode or result.stdout.strip() != "linux":
            raise _unavailable("A reachable Linux Docker engine is required")
        result = _docker_call([docker, "image", "inspect", image, "--format", "{{.Id}} {{.Os}}"],
                                capture_output=True, text=True, timeout=10, check=False)
        if result.returncode or not re.fullmatch(r"sha256:[a-f0-9]{64} linux\s*", result.stdout):
            raise _unavailable("Sandbox image must already exist locally and target Linux")
        return context.project_root
    except IsolationViolation as exc:
        raise _unavailable(str(exc)) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise _unavailable(f"Sandbox preflight failed: {exc}") from exc


def _container_identity(docker: str, name: str, run_id: str, timeout: float = 3) -> str | None:
    inspected = _docker_call([docker, "container", "inspect", name, "--format", "{{json .}}"],
                               capture_output=True, text=True, timeout=timeout, check=False)
    if inspected.returncode:
        diagnostic = inspected.stderr.lower()
        if "no such" in diagnostic and ("container" in diagnostic or "object" in diagnostic):
            return None
        raise _unavailable("Cannot attest whether the owned container is absent")
    try:
        data = json.loads(inspected.stdout)
        labels = data.get("Config", {}).get("Labels", {})
        identifier = data["Id"]
        if labels.get("autospec.run_id") != run_id or labels.get("autospec.kind") != "sandbox":
            raise _unavailable("Container ownership identity does not match this run")
        if not re.fullmatch(r"[a-f0-9]{64}", identifier):
            raise ValueError("Invalid Docker container identity")
        return identifier
    except (ValueError, KeyError, TypeError) as exc:
        raise _unavailable("Container identity cannot be verified") from exc


def _cleanup_container(docker: str, name: str, run_id: str) -> None:
    # UUID name + immutable ID + ownership labels; never prune/killall.
    identifier = _container_identity(docker, name, run_id)
    if identifier is None:
        return
    deadline = time.monotonic() + 5
    for action in (["stop", "--time", "1"], ["rm", "--force"]):
        result = _docker_call([docker, "container", *action, identifier],
                                capture_output=True, text=True,
                                timeout=max(.1, deadline - time.monotonic()), check=False)
        if result.returncode and _container_identity(docker, name, run_id) is not None:
            raise _unavailable(f"Owned container cleanup failed ({action[0]})")


def run_isolated(inner_cmd: list[str], ws: str | Path, image: str, *, docker: str = "docker",
                 run_id: str | None = None, timeout: float = 120,
                 input_text: str = "") -> tuple[int, str, str]:
    """Bounded synchronous execution, including cleanup after client timeout."""
    root = require_sandbox(ws, image, docker=docker)
    owner = run_id or uuid.uuid4().hex
    name = f"autospec-sandbox-{uuid.uuid4().hex}"
    command = docker_run_cmd(inner_cmd, str(root), image, docker=docker,
                             run_id=owner, container_name=name)
    try:
        return _run_tracked(command, input_text, str(root), timeout)
    finally:
        _cleanup_container(docker, name, owner)


async def arun_isolated(*args, **kwargs) -> tuple[int, str, str]:
    return await _await_tracked(lambda: run_isolated(*args, **kwargs))
