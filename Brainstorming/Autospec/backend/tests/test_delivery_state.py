"""Helpers that mutate ProjectState delivery readiness."""

from autospec.models import ProjectState
from autospec.orchestrator import delivery_state
from autospec.orchestrator.delivery_gate import DefinitionOfDoneResult


def test_delivery_state_helpers():
    state = ProjectState(id="p-del-state", name="n", goal="g")
    delivery_state.mark_ready(state)
    assert state.delivery_ready is True
    assert state.delivery_issues == []

    delivery_state.append_issue(state, "boom")
    assert state.delivery_ready is False
    assert state.delivery_issues == ["boom"]

    delivery_state.reset(state)
    assert state.delivery_ready is False
    assert state.delivery_issues == []

    delivery_state.apply_definition_result(state, DefinitionOfDoneResult(True, ()))
    assert state.delivery_ready is True
    assert state.delivery_issues == []
