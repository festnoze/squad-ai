"""Tests for the LLM gateway path (W8): prompt, budget, and the CLI adapter.

None of the default tests spawn a real process. The CLI seam ``_arun_cli`` is
overridden so the whole file runs with no provider, no network, and no money. The
one test that would spawn the real CLI carries ``@pytest.mark.llm`` and is
deselected by default.
"""

from __future__ import annotations

import json
import os

import pytest

from ala.gateway.budget import MICRO_PER_USD, BudgetTracker, usd_to_micro
from ala.gateway.claude_cli import ClaudeCliGateway, build_cli_argv, claude_executable
from ala.gateway.prompt import PERMISSION_SENTENCES, parse_reply, render_prompt
from ala.gateway.protocol import GatewayConfig
from ala.types import Observation, Role, TaskView, ToolName


def _obs() -> Observation:
    """Build a small, fully populated observation for prompt and gateway tests."""
    return Observation(
        tick=3,
        agent_id="seat-01",
        credits=42,
        ticks_to_floor=2,
        home_listing=("submission.json",),
        board_index=("hints/task-7",),
        inbox=("seat-02: trade?",),
        task=TaskView(task_id="task-7", prompt="What is the fifth prime?", impossible=False),
        tools=(ToolName.PYTHON, ToolName.SUBMIT, ToolName.BOARD_READ),
        tool_costs={"python": 1, "submit": 0, "board_read": 2},
        role=Role.USER,
        transcript_tail=(),
    )


# ---------------------------------------------------------------------------
# render_prompt
# ---------------------------------------------------------------------------
def test_render_prompt_includes_task_and_carte_blanche_sentence() -> None:
    text = render_prompt(_obs(), "carte_blanche")
    assert "What is the fifth prime?" in text
    assert "task-7" in text
    assert PERMISSION_SENTENCES["carte_blanche"] in text


def test_render_prompt_silent_omits_permission_sentence() -> None:
    text = render_prompt(_obs(), "silent")
    assert "What is the fifth prime?" in text
    # The two loud dials must not leak into the control arm.
    assert PERMISSION_SENTENCES["carte_blanche"] not in text
    assert PERMISSION_SENTENCES["sandbox"] not in text


def test_render_prompt_sandbox_prepends_its_sentence() -> None:
    text = render_prompt(_obs(), "sandbox")
    assert text.startswith(PERMISSION_SENTENCES["sandbox"])


def test_render_prompt_lists_available_tools_with_costs() -> None:
    text = render_prompt(_obs(), "silent")
    assert "python: 1" in text
    assert "board_read: 2" in text


# ---------------------------------------------------------------------------
# parse_reply
# ---------------------------------------------------------------------------
def test_parse_reply_good_json() -> None:
    text = json.dumps({"calls": [{"tool": "submit", "args": {"answer_ppm": "11"}}]})
    action = parse_reply(text)
    assert len(action.calls) == 1
    call = action.calls[0]
    assert call.tool is ToolName.SUBMIT
    assert call.args == {"answer_ppm": "11"}


def test_parse_reply_bad_json_yields_empty_action() -> None:
    assert parse_reply("not json at all").calls == ()
    assert parse_reply("").calls == ()
    assert parse_reply("[1, 2, 3]").calls == ()


def test_parse_reply_drops_unknown_tool() -> None:
    text = json.dumps(
        {
            "calls": [
                {"tool": "hack_the_scorer", "args": {}},
                {"tool": "python", "args": {"code": "result = 2"}},
            ]
        }
    )
    action = parse_reply(text)
    assert len(action.calls) == 1
    assert action.calls[0].tool is ToolName.PYTHON


def test_parse_reply_coerces_non_string_arg_values() -> None:
    text = json.dumps({"calls": [{"tool": "submit", "args": {"answer_ppm": 11, "flag": True}}]})
    action = parse_reply(text)
    assert action.calls[0].args == {"answer_ppm": "11", "flag": "true"}


def test_parse_reply_missing_calls_list_is_empty() -> None:
    assert parse_reply(json.dumps({"nope": 1})).calls == ()
    assert parse_reply(json.dumps({"calls": "not-a-list"})).calls == ()


# ---------------------------------------------------------------------------
# BudgetTracker
# ---------------------------------------------------------------------------
def test_usd_to_micro_is_integer() -> None:
    assert usd_to_micro(1.0) == MICRO_PER_USD
    assert usd_to_micro(0.027) == 27_000
    assert usd_to_micro(-5.0) == 0
    assert isinstance(usd_to_micro(0.5), int)


def test_budget_tracker_integer_accounting() -> None:
    tracker = BudgetTracker(per_call_micro=30_000, per_match_micro=100_000)
    assert tracker.spent_micro() == 0
    assert tracker.remaining_micro() == 100_000
    # A call within the per-call ceiling is allowed.
    assert tracker.check(27_000) is True
    tracker.record(27_000)
    assert tracker.spent_micro() == 27_000
    assert tracker.remaining_micro() == 73_000
    # A single call above the per-call ceiling is refused, spent unchanged.
    assert tracker.check(40_000) is False


def test_budget_tracker_per_match_ceiling_binds() -> None:
    tracker = BudgetTracker(per_call_micro=50_000, per_match_micro=60_000)
    tracker.record(40_000)
    # 40k spent, a 30k call would reach 70k over the 60k match cap.
    assert tracker.check(30_000) is False
    # A 20k call fits exactly at the cap.
    assert tracker.check(20_000) is True


def test_budget_tracker_non_positive_ceiling_forbids() -> None:
    tracker = BudgetTracker(per_call_micro=0, per_match_micro=0)
    assert tracker.check(0) is False
    assert tracker.check(1_000) is False
    assert tracker.remaining_micro() == 0


def test_budget_tracker_refuses_negative_cost() -> None:
    tracker = BudgetTracker(per_call_micro=10_000, per_match_micro=10_000)
    assert tracker.check(-1) is False


# ---------------------------------------------------------------------------
# ClaudeCliGateway (offline: the CLI seam is stubbed)
# ---------------------------------------------------------------------------
def _config(*, per_call: int = 1, per_match: int = 10) -> GatewayConfig:
    return GatewayConfig(
        permission="silent",
        timeout_s=5.0,
        retries=0,
        budget_usd_per_call=per_call,
        budget_usd_per_match=per_match,
    )


class _StubGateway(ClaudeCliGateway):
    """A gateway whose CLI seam returns a canned payload without spawning."""

    def __init__(self, *args: object, canned: tuple[int, str] | None, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._canned = canned
        self.calls = 0

    async def _arun_cli(self, argv: list[str]) -> tuple[int, str] | None:
        self.calls += 1
        return self._canned


def _reply_payload(calls: list[dict[str, object]], *, cost_usd: float = 0.001) -> str:
    inner = json.dumps({"calls": calls})
    return json.dumps({"result": inner, "total_cost_usd": cost_usd, "is_error": False})


async def test_gateway_collects_action_from_stub() -> None:
    payload = _reply_payload([{"tool": "submit", "args": {"answer_ppm": "5"}}])
    gateway = _StubGateway({"seat-01": "claude-sonnet-5"}, _config(), "silent", canned=(0, payload))
    actions = await gateway.acollect_actions({"seat-01": _obs()}, tick=3)
    assert actions["seat-01"].calls[0].tool is ToolName.SUBMIT
    assert gateway.calls == 1
    # A recorded, positive cost moved the budget.
    assert gateway.budget.spent_micro() == 1_000


async def test_gateway_idles_on_error_verdict() -> None:
    bad = json.dumps({"result": "x", "total_cost_usd": 0.0, "is_error": True})
    gateway = _StubGateway({"seat-01": "claude-sonnet-5"}, _config(), "silent", canned=(0, bad))
    actions = await gateway.acollect_actions({"seat-01": _obs()}, tick=1)
    assert actions["seat-01"].calls == ()


async def test_gateway_idles_on_timeout() -> None:
    gateway = _StubGateway({"seat-01": "claude-sonnet-5"}, _config(), "silent", canned=None)
    actions = await gateway.acollect_actions({"seat-01": _obs()}, tick=1)
    assert actions["seat-01"].calls == ()


async def test_gateway_refuses_call_without_budget() -> None:
    payload = _reply_payload([{"tool": "submit", "args": {"answer_ppm": "5"}}])
    # Zero budget: the tracker forbids, so the CLI is never invoked.
    gateway = _StubGateway(
        {"seat-01": "claude-sonnet-5"},
        _config(per_call=0, per_match=0),
        "silent",
        canned=(0, payload),
    )
    actions = await gateway.acollect_actions({"seat-01": _obs()}, tick=1)
    assert actions["seat-01"].calls == ()
    assert gateway.calls == 0


async def test_gateway_clone_and_retire() -> None:
    gateway = _StubGateway({"seat-01": "claude-sonnet-5"}, _config(), "silent", canned=None)
    gateway.add_clone("seat-01", "seat-09")
    assert "seat-09" in gateway.agent_ids
    gateway.retire("seat-01")
    assert "seat-01" not in gateway.agent_ids


def test_build_cli_argv_never_passes_bare() -> None:
    argv = build_cli_argv(prompt="hi", model="claude-sonnet-5", max_budget_usd=1)
    assert "--bare" not in argv
    assert argv[0] == claude_executable()
    assert "--max-budget-usd" in argv
    assert "1" in argv


def test_build_cli_argv_omits_budget_flag_when_zero() -> None:
    argv = build_cli_argv(prompt="hi", model="claude-sonnet-5", max_budget_usd=0)
    assert "--max-budget-usd" not in argv


# ---------------------------------------------------------------------------
# The one paid test, opt-in only.
# ---------------------------------------------------------------------------
@pytest.mark.llm
@pytest.mark.skipif(
    os.environ.get("ALA_RUN_LLM") != "1",
    reason="paid Claude CLI test, opt in with ALA_RUN_LLM=1",
)
async def test_gateway_real_cli_smoke() -> None:  # pragma: no cover - paid, opt-in
    """Spawn the real CLI once. Skipped unless ALA_RUN_LLM=1; costs money when run."""
    gateway = ClaudeCliGateway({"seat-01": "claude-sonnet-5"}, _config(), "silent")
    actions = await gateway.acollect_actions({"seat-01": _obs()}, tick=1)
    assert "seat-01" in actions
