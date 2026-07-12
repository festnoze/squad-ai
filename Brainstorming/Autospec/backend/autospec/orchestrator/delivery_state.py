"""Small helpers for mutating delivery readiness on ProjectState."""

from __future__ import annotations

from ..models import ProjectState
from .delivery_gate import DefinitionOfDoneResult


def reset(state: ProjectState) -> None:
    state.delivery_ready = False
    state.delivery_issues = []
    state.delivery_partial = False
    # Clear the last docker verdict/detail so a re-run starts fresh, but KEEP the
    # allocated host port and previous image/container names: the old container
    # keeps running while the next iteration rebuilds.
    state.deploy_status = ""
    state.deploy_detail = ""


def mark_ready(state: ProjectState) -> None:
    state.delivery_ready = True
    state.delivery_issues = []
    state.delivery_partial = False


def apply_definition_result(state: ProjectState, result: DefinitionOfDoneResult) -> None:
    state.delivery_ready = result.ready
    state.delivery_issues = result.messages()
    state.delivery_partial = result.partial


def append_issue(state: ProjectState, message: str) -> None:
    state.delivery_ready = False
    state.delivery_issues = [*state.delivery_issues, message]


def set_deploy(
    state: ProjectState,
    *,
    status: str,
    image: str = "",
    container: str = "",
    host_port: int = 0,
    detail: str = "",
) -> None:
    """Single mutation point for docker delivery state. Name/port/image are only
    overwritten when a non-empty value is passed, so a status-only transition
    (e.g. "building" → "deploying") never wipes the allocated port or names."""
    state.deploy_status = status
    if image:
        state.deployed_image = image
    if container:
        state.deployed_container = container
    if host_port:
        state.deploy_host_port = host_port
    state.deploy_detail = detail[:2000]
