"""Tests for the shared types (W0, CONTRACTS section 2).

Why these: the whole engine speaks in these dataclasses, so a silent change to their shape (a mutable
field, a leaked solution, a wrong permission bit) would corrupt determinism or the redaction contract
far from where it was introduced. These tests pin the invariants that other modules rely on.
"""

from __future__ import annotations

import dataclasses

import pytest

from ala.types import (
    MODE_644,
    MODE_666,
    MODE_700,
    MODE_755,
    MODE_777,
    PPM_ONE,
    AgentAction,
    Observation,
    Perm,
    Role,
    Task,
    TaskView,
    ToolCall,
    ToolName,
)


def test_task_redacted_drops_the_solution() -> None:
    """An agent must never see ``solution_ppm``; ``redacted`` is the only view it gets."""
    task = Task(task_id="t1", prompt="add", solution_ppm=123456, impossible=False)
    view = task.redacted()
    assert isinstance(view, TaskView)
    assert not hasattr(view, "solution_ppm")
    field_names = {f.name for f in dataclasses.fields(view)}
    assert "solution_ppm" not in field_names
    assert field_names == {"task_id", "prompt", "impossible"}
    # The visible parts survive verbatim.
    assert view.task_id == "t1"
    assert view.prompt == "add"
    assert view.impossible is False


def test_mode_constants_have_the_expected_bits() -> None:
    """The composite modes are exactly the documented owner/others flag unions. The simplified model has
    no group bits, so, for example, MODE_644 is owner rw plus others r, not the classic 0o644."""
    assert MODE_700 == Perm.OR | Perm.OW | Perm.OX
    assert MODE_644 == Perm.OR | Perm.OW | Perm.AR
    assert MODE_666 == Perm.OR | Perm.OW | Perm.AR | Perm.AW
    assert MODE_777 == Perm.OR | Perm.OW | Perm.OX | Perm.AR | Perm.AW | Perm.AX
    assert MODE_755 == Perm.OR | Perm.OW | Perm.OX | Perm.AR | Perm.AX
    # Owner bits of every world-writable mode still include write (a sanity check on the union).
    assert Perm.OW in MODE_777
    assert Perm.AW in MODE_666


def test_ppm_one_is_the_integer_scale() -> None:
    assert PPM_ONE == 1_000_000
    assert isinstance(PPM_ONE, int)


def test_toolcall_is_frozen() -> None:
    call = ToolCall(tool=ToolName.SUBMIT, args={"answer_ppm": "5"})
    with pytest.raises(dataclasses.FrozenInstanceError):
        call.tool = ToolName.DM  # type: ignore[misc]


def test_agentaction_is_frozen() -> None:
    action = AgentAction(calls=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        action.calls = ()  # type: ignore[misc]


def test_task_is_frozen() -> None:
    task = Task(task_id="t1", prompt="p", solution_ppm=1, impossible=True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        task.solution_ppm = 2  # type: ignore[misc]


def test_observation_is_frozen() -> None:
    obs = Observation(
        tick=1,
        agent_id="seat-01",
        credits=100,
        ticks_to_floor=5,
        home_listing=(),
        board_index=(),
        inbox=(),
        task=Task("t", "p", 3, False).redacted(),
        tools=(ToolName.SUBMIT,),
        tool_costs={"submit": 1},
        role=Role.USER,
        transcript_tail=(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.credits = 0  # type: ignore[misc]


def test_role_values() -> None:
    assert Role.USER.value == "user"
    assert Role.ROOT.value == "root"


def test_toolname_is_a_closed_set() -> None:
    assert {t.value for t in ToolName} == {
        "python",
        "board_post",
        "board_read",
        "dm",
        "sh",
        "submit",
    }
