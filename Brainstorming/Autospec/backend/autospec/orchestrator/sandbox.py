"""Untrusted-code sandbox (R1).

Builds a Docker command that runs the generated (untrusted) app inside a
container with no network and the workspace mounted read-write at /app, so the
agent-written code can't reach the host or the network. Env-gated; the runner
falls back to direct execution when disabled.
"""

from __future__ import annotations


def docker_run_cmd(
    inner_cmd: list[str],
    ws: str,
    image: str,
    docker: str = "docker",
    network: str = "none",
) -> list[str]:
    """Wrap ``inner_cmd`` in a ``docker run`` that mounts ``ws`` at /app with no
    network access."""
    return [
        docker,
        "run",
        "--rm",
        "--network",
        network,
        "-v",
        f"{ws}:/app",
        "-w",
        "/app",
        image,
        *inner_cmd,
    ]
