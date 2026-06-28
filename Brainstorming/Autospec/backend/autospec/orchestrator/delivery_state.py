"""Small helpers for mutating delivery readiness on ProjectState."""

from __future__ import annotations

from ..models import ProjectState
from .delivery_gate import DefinitionOfDoneResult


def reset(state: ProjectState) -> None:
    state.delivery_ready = False
    state.delivery_issues = []


def mark_ready(state: ProjectState) -> None:
    state.delivery_ready = True
    state.delivery_issues = []


def apply_definition_result(state: ProjectState, result: DefinitionOfDoneResult) -> None:
    state.delivery_ready = result.ready
    state.delivery_issues = result.messages()


def append_issue(state: ProjectState, message: str) -> None:
    state.delivery_ready = False
    state.delivery_issues = [*state.delivery_issues, message]
