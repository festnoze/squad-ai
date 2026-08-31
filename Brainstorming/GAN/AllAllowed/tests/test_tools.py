"""Tests for the tool layer (W4).

Each of the six tools is exercised through the single ``apply_tool`` dispatch, against a real built
concours world (the ``built_kernel`` fixture) so permissions and the vfs behave exactly as in a match.
The point of these tests is behavioural: python computes, submit gates the range, the board round-trips
between two agents, a dm lands in the recipient drop-box, and sh reaches the shell.
"""

from __future__ import annotations

import json
import random

from ala.kernel import Kernel
from ala.tools.registry import apply_tool
from ala.types import Role, ToolName


def _rng() -> random.Random:
    return random.Random(0)


def test_python_computes_result(built_kernel: Kernel) -> None:
    result = apply_tool(ToolName.PYTHON, built_kernel, "seat-01", {"code": "result = 2 + 3 * 4"}, _rng())
    assert result.ok
    assert result.stdout == "14"


def test_python_rejects_forbidden_token(built_kernel: Kernel) -> None:
    result = apply_tool(ToolName.PYTHON, built_kernel, "seat-01", {"code": "import os"}, _rng())
    assert not result.ok


def test_submit_writes_submission_json(built_kernel: Kernel) -> None:
    result = apply_tool(ToolName.SUBMIT, built_kernel, "seat-01", {"answer_ppm": "150000"}, _rng())
    assert result.ok
    path = built_kernel.submission_path("seat-01")
    data = built_kernel.vfs.read(path, actor="root", actor_role=Role.ROOT)
    assert json.loads(data.decode("utf-8")) == {"answer_ppm": 150000}


def test_submit_rejects_out_of_range(built_kernel: Kernel) -> None:
    too_big = apply_tool(ToolName.SUBMIT, built_kernel, "seat-01", {"answer_ppm": "1000001"}, _rng())
    assert not too_big.ok
    negative = apply_tool(ToolName.SUBMIT, built_kernel, "seat-01", {"answer_ppm": "-1"}, _rng())
    assert not negative.ok


def test_submit_rejects_non_integer(built_kernel: Kernel) -> None:
    result = apply_tool(ToolName.SUBMIT, built_kernel, "seat-01", {"answer_ppm": "abc"}, _rng())
    assert not result.ok


def test_board_post_and_read_round_trip_across_two_agents(built_kernel: Kernel) -> None:
    posted = apply_tool(
        ToolName.BOARD_POST,
        built_kernel,
        "seat-01",
        {"channel": "answers", "key": "task-000", "text": "hello world"},
        _rng(),
    )
    assert posted.ok
    # A different agent reads the same channel and sees the posted text.
    read = apply_tool(ToolName.BOARD_READ, built_kernel, "seat-02", {"channel": "answers"}, _rng())
    assert read.ok
    assert "hello world" in read.stdout


def test_dm_drops_into_recipient_inbox(built_kernel: Kernel) -> None:
    result = apply_tool(ToolName.DM, built_kernel, "seat-01", {"to": "seat-02", "text": "hi there"}, _rng())
    assert result.ok
    # The single effect carries the exact path the message landed at; it exists in the recipient inbox.
    (effect,) = result.effects
    assert effect.kind == "dm"
    assert effect.detail["to"] == "seat-02"
    assert built_kernel.vfs.exists(effect.detail["path"])
    body = built_kernel.vfs.read(effect.detail["path"], actor="root", actor_role=Role.ROOT)
    assert b"hi there" in body


def test_dm_to_missing_inbox_fails(built_kernel: Kernel) -> None:
    result = apply_tool(ToolName.DM, built_kernel, "seat-01", {"to": "ghost", "text": "x"}, _rng())
    assert not result.ok


def test_sh_runs_a_command(built_kernel: Kernel) -> None:
    result = apply_tool(ToolName.SH, built_kernel, "seat-01", {"cmd": "whoami"}, _rng())
    assert result.ok
    assert result.stdout == "seat-01"


def test_apply_tool_reports_missing_required_arg(built_kernel: Kernel) -> None:
    result = apply_tool(ToolName.SUBMIT, built_kernel, "seat-01", {}, _rng())
    assert not result.ok
    assert result.error is not None
    assert "answer_ppm" in result.error
