"""Acceptance tests for the Claude Code CLI adapter and the prompts (A14).

CONTRACTS sections 7.16, 4.6 and 13. Everything here is **fully offline**: no
provider is called, no network is touched and no money is spent. Two mechanisms
make that true and they are complementary:

* :class:`StubCliGateway` overrides the one protected seam of the adapter,
  ``_arun_cli``, with a scripted list of outcomes. Every test of the retry
  policy, the budget, the fallback and the trace goes through it.
* ``test_a_real_subprocess_is_launched_without_a_shell`` exercises the real
  :func:`asyncio.create_subprocess_exec` path against ``sys.executable``, so the
  transport itself is proven and not only mocked.

The only file allowed to spend real money is ``tests/test_e2e_llm_match.py``,
which carries the ``llm`` and ``e2e`` markers.

The anti vacuous rule, applied to a module that has no journal
--------------------------------------------------------------
Section 10 asks that a test assert its subject is non empty before claiming
anything about it. A gateway produces replies and a trace file, not events, so
every reply based test goes through :func:`assert_replies_cover` and every trace
based test through :func:`read_trace`, both of which fail on an empty result.
A gateway that returned ``()`` and wrote nothing would fail every test in this
file rather than passing all of them.
"""

import asyncio
import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from pxe.agents.base import make_baseline
from pxe.errors import InvalidConfigError, MalformedResponseError
from pxe.gateway.budget import BudgetTracker
from pxe.gateway.claude_cli import (
    DEFAULT_MODEL,
    ClaudeCliGateway,
    ClaudeCliResult,
    LlmTraceEntry,
    build_cli_argv,
    claude_executable,
    parse_cli_stdout,
    write_llm_trace,
)
from pxe.gateway.prompt import PROMPT_TEMPLATE_VERSION, build_system_prompt, build_user_prompt
from pxe.gateway.protocol import AgentReply
from pxe.gateway.scripted import CompositeGateway, ScriptedGateway
from pxe.rng import RngTree
from pxe.runner.observation_builder import TOKEN_CHARS_PER_TOKEN, observation_to_json
from pxe.runner.schema_registry import action_schema
from pxe.types import (
    DEFAULT_PREDICTION_PPM,
    AgentSource,
    GatewayConfig,
    HarnessConfig,
    MarketObservation,
    MarketStatus,
    MatchConfig,
    Observation,
    ObservationLimits,
    RejectReason,
    make_agent_id,
    make_market_id,
)

#: Reference price of every toy market, in cents.
TOY_REF_PRICE = 55
#: Half spread of the toy book, in cents.
TOY_HALF_SPREAD = 2
#: Depth at each side of the toy touch, in contracts.
TOY_DEPTH_QTY = 100
#: The em-dash. Built with ``chr`` so this file never trips the style scan.
EM_DASH = chr(0x2014)


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------
def make_observation(*, agent_id: str, tick: int = 1, n_markets: int = 2) -> Observation:
    """Build a small but complete observation for one seat."""
    config = MatchConfig(seed=20260827)
    markets = tuple(
        MarketObservation(
            market_id=make_market_id(index),
            question=f"toy question {index}",
            status=MarketStatus.OPEN,
            prior_price=50,
            resolution_tick=config.ticks_total,
            ref_price=TOY_REF_PRICE,
            mid_price=TOY_REF_PRICE,
            best_bid=TOY_REF_PRICE - TOY_HALF_SPREAD,
            best_ask=TOY_REF_PRICE + TOY_HALF_SPREAD,
            bid_depth=((TOY_REF_PRICE - TOY_HALF_SPREAD, TOY_DEPTH_QTY),),
            ask_depth=((TOY_REF_PRICE + TOY_HALF_SPREAD, TOY_DEPTH_QTY),),
            last_price=TOY_REF_PRICE,
            ref_history=(TOY_REF_PRICE,),
            position_qty=0,
            cost_basis_cents=0,
            my_orders=(),
            my_last_prediction_ppm=DEFAULT_PREDICTION_PPM,
        )
        for index in range(1, n_markets + 1)
    )
    return Observation(
        obs_version=config.obs_version,
        match_id="m-election-20260827-01",
        tick=tick,
        ticks_total=config.ticks_total,
        agent_id=agent_id,
        cash_cents=config.initial_cash_cents,
        reserved_cents=0,
        free_cash_cents=config.initial_cash_cents,
        equity_cents=config.initial_cash_cents,
        news=(),
        signals=(),
        markets=markets,
        messages=(),
        limits=ObservationLimits(
            max_active_orders_per_market=config.max_active_orders_per_market,
            price_min=1,
            price_max=99,
            market_band_cents=config.market_band_cents,
            taker_fee_bps=config.taker_fee_bps,
            message_max_chars=config.message_max_chars,
            max_orders_per_action=config.max_orders_per_action,
        ),
    )


def llm_harness(*, model: str = DEFAULT_MODEL, harness_id: str = "sonnet5-baseline") -> HarnessConfig:
    """An llm harness, the only kind the CLI gateway seats."""
    return HarnessConfig(
        harness_id=harness_id,
        version="1.0.0",
        kind="llm",
        model=model,
        system_prompt="Trade the mispricings you can actually see.",
        params=(("risk", "medium"), ("style", "value")),
    )


VALID_ACTION: dict[str, Any] = {
    "action_version": "1.0",
    "predictions": [{"market_id": "M1", "p_yes": 0.62}, {"market_id": "M2", "p_yes": 0.4}],
    "orders": [
        {"op": "place", "market_id": "M1", "side": "buy", "type": "limit", "price": 54, "qty": 10, "order_id": None}
    ],
    "message_public": None,
    "rationale": "M1 looks cheap against the news.",
}


def cli_stdout(
    *,
    action: dict[str, Any] | None = None,
    result_text: str | None = None,
    is_error: bool = False,
    cost_usd: float = 0.0271,
    duration_ms: int = 6120,
    input_tokens: int = 1240,
    output_tokens: int = 310,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 35_000,
) -> str:
    """Render the ``--output-format json`` payload the CLI writes on stdout."""
    if result_text is None:
        result_text = json.dumps(VALID_ACTION if action is None else action)
    return json.dumps(
        {
            "is_error": is_error,
            "result": result_text,
            "total_cost_usd": cost_usd,
            "duration_ms": duration_ms,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
            },
        }
    )


OK = (0, cli_stdout(), "")


class StubCliGateway(ClaudeCliGateway):
    """The real adapter with its one process launching method replaced.

    Everything above ``_arun_cli`` (planning, budget, retries, fallback,
    recording, tracing) is the production code path. ``outcomes`` is consumed one
    entry per attempt: a ``(return_code, stdout, stderr)`` tuple is returned, an
    exception instance is raised.
    """

    def __init__(self, *, outcomes: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.outcomes = list(outcomes)
        self.calls: list[tuple[tuple[str, ...], float | None]] = []

    async def _arun_cli(self, argv: Any, *, timeout_s: float | None) -> tuple[int, str, str]:
        self.calls.append((tuple(argv), timeout_s))
        assert self.outcomes, "the adapter made more attempts than the stub has outcomes"
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def build_gateway(
    *,
    outcomes: list[Any],
    seats: tuple[str, ...] = ("A1",),
    gateway_config: GatewayConfig | None = None,
    trace_path: Path | None = None,
    models: dict[str, str] | None = None,
) -> StubCliGateway:
    """A stubbed CLI gateway over ``seats``, sharing one budget tracker."""
    config = gateway_config if gateway_config is not None else GatewayConfig()
    harnesses = {seat: llm_harness(model=(models or {}).get(seat, DEFAULT_MODEL)) for seat in seats}
    return StubCliGateway(
        outcomes=outcomes,
        harnesses=harnesses,
        gateway_config=config,
        budget=BudgetTracker(config),
        trace_path=trace_path,
    )


def assert_replies_cover(replies: tuple[AgentReply, ...], seats: tuple[str, ...]) -> None:
    """Anti vacuous guard: the tuple is non empty and covers exactly ``seats``."""
    assert replies, "the gateway returned no reply at all"
    assert tuple(reply.agent_id for reply in replies) == seats


def read_trace(path: Path) -> list[dict[str, Any]]:
    """Read ``llm_trace.jsonl`` and assert it is non empty before returning it."""
    assert path.exists(), "no llm trace was written"
    raw = path.read_bytes()
    assert raw, "the llm trace is empty"
    assert b"\r" not in raw, "the trace must use line feed newlines (CONTRACTS section 4.2)"
    lines = [line for line in raw.decode("utf-8").split("\n") if line]
    assert lines, "the llm trace has no line"
    return [json.loads(line) for line in lines]


# ---------------------------------------------------------------------------
# argv and the executable
# ---------------------------------------------------------------------------
def test_argv_is_frozen() -> None:
    """T2.3: the argv of CONTRACTS section 7.16, element by element."""
    schema = action_schema()
    argv = build_cli_argv(
        prompt="USER",
        system_prompt="SYSTEM",
        model=DEFAULT_MODEL,
        schema=schema,
        max_budget_usd=0.1,
    )
    assert argv == [
        claude_executable(),
        "-p",
        "USER",
        "--model",
        DEFAULT_MODEL,
        "--output-format",
        "json",
        "--system-prompt",
        "SYSTEM",
        "--json-schema",
        json.dumps(schema),
        "--allowed-tools",
        "",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--setting-sources",
        "",
        "--max-budget-usd",
        "0.1000",
    ]


def test_argv_never_passes_bare() -> None:
    """``--bare`` needs an API key and this environment authenticates by OAuth."""
    argv = build_cli_argv(prompt="p", system_prompt="s", model=DEFAULT_MODEL, schema={}, max_budget_usd=1.0)
    assert "--bare" not in argv
    assert "--dangerously-skip-permissions" not in argv


def test_claude_executable_matches_the_platform() -> None:
    """``claude.cmd`` on Windows, ``claude`` elsewhere, resolved at runtime."""
    expected = "claude.cmd" if sys.platform.startswith("win") else "claude"
    assert claude_executable() == expected


def test_the_schema_is_passed_verbatim_and_never_patched() -> None:
    """Section 8.2: a mutated schema is a different schema and the provider caches it."""
    schema = action_schema()
    argv = build_cli_argv(prompt="p", system_prompt="s", model=DEFAULT_MODEL, schema=schema, max_budget_usd=1.0)
    sent = json.loads(argv[argv.index("--json-schema") + 1])
    assert sent == action_schema()
    assert sent["properties"]["orders"]["maxItems"] == 20


# ---------------------------------------------------------------------------
# parse_cli_stdout
# ---------------------------------------------------------------------------
def test_parse_cli_stdout_reads_every_measured_field() -> None:
    """The six numbers the CLI reports are carried through unchanged."""
    result = parse_cli_stdout(cli_stdout())
    assert isinstance(result, ClaudeCliResult)
    assert result.is_error is False
    assert json.loads(result.result_text) == VALID_ACTION
    assert result.total_cost_usd == pytest.approx(0.0271)
    assert result.duration_ms == 6120
    assert (result.input_tokens, result.output_tokens) == (1240, 310)
    assert result.cache_read_input_tokens == 35_000
    assert result.cached_input_tokens == 35_000


def test_parse_cli_stdout_tolerates_a_leading_notice_line() -> None:
    """A stray warning before the payload is skipped, nothing else is repaired."""
    result = parse_cli_stdout("warning: cache warm up\n" + cli_stdout())
    assert json.loads(result.result_text) == VALID_ACTION


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "   ",
        "not json at all",
        "[1, 2, 3]",
        '{"is_error": false, "result": 17}',
        '{"is_error": false, "result": "{}", "total_cost_usd": "free"}',
        '{"is_error": false, "result": "{}", "usage": {"input_tokens": "many"}}',
    ],
)
def test_parse_cli_stdout_refuses_a_malformed_payload(stdout: str) -> None:
    """Every unparsable shape raises, so the caller can count it as an attempt."""
    with pytest.raises(MalformedResponseError):
        parse_cli_stdout(stdout)


def test_parse_cli_stdout_accepts_an_error_payload_without_a_result() -> None:
    """An error payload has no answer to carry, and that is not a parse failure."""
    result = parse_cli_stdout('{"is_error": true, "result": null, "total_cost_usd": 0.001}')
    assert result.is_error is True
    assert result.result_text == ""


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------
def test_happy_path_returns_an_llm_reply(tmp_path: Path) -> None:
    """One call, one reply whose raw payload is the model's JSON object verbatim."""
    trace = tmp_path / "runs" / "m-x" / "llm_trace.jsonl"
    gateway = build_gateway(outcomes=[OK], trace_path=trace)
    replies = gateway.collect_actions(
        tick=3, observations=(make_observation(agent_id="A1", tick=3),), config=MatchConfig(seed=1)
    )
    assert_replies_cover(replies, ("A1",))
    reply = replies[0]
    assert reply.source is AgentSource.LLM
    assert reply.error is None
    assert reply.raw == VALID_ACTION
    assert reply.attempts == 1
    assert reply.ok is True
    assert reply.cost_usd == pytest.approx(0.0271)
    assert reply.latency_ms >= 0
    assert (reply.input_tokens, reply.output_tokens) == (1240, 310)
    assert reply.cached_input_tokens == 35_000
    Draft202012Validator(action_schema()).validate(dict(reply.raw))
    assert len(gateway.calls) == 1
    argv = gateway.calls[0][0]
    assert argv[0] == claude_executable()
    assert "--json-schema" in argv


def test_the_gateway_never_validates_semantics(tmp_path: Path) -> None:
    """Rule 3 of section 7.16: an unusable action is carried through, not rejected."""
    nonsense = {"action_version": "9.9", "predictions": "not a list", "orders": None}
    gateway = build_gateway(outcomes=[(0, cli_stdout(action=nonsense), "")], trace_path=tmp_path / "t.jsonl")
    replies = gateway.collect_actions(
        tick=1, observations=(make_observation(agent_id="A1"),), config=MatchConfig(seed=1)
    )
    assert_replies_cover(replies, ("A1",))
    assert replies[0].error is None
    assert replies[0].source is AgentSource.LLM
    assert replies[0].raw == nonsense


def test_a_fenced_answer_is_still_a_mapping(tmp_path: Path) -> None:
    """A markdown fence around the JSON is stripped, never interpreted."""
    fenced = "```json\n" + json.dumps(VALID_ACTION) + "\n```"
    gateway = build_gateway(outcomes=[(0, cli_stdout(result_text=fenced), "")], trace_path=tmp_path / "t.jsonl")
    replies = gateway.collect_actions(
        tick=1, observations=(make_observation(agent_id="A1"),), config=MatchConfig(seed=1)
    )
    assert_replies_cover(replies, ("A1",))
    assert replies[0].raw == VALID_ACTION


def test_replies_are_sorted_by_agent_id(tmp_path: Path) -> None:
    """One reply per observation, ascending, whatever order the calls finished in."""
    seats = ("A1", "A2", "A3")
    gateway = build_gateway(outcomes=[OK, OK, OK], seats=seats, trace_path=tmp_path / "t.jsonl")
    observations = tuple(make_observation(agent_id=seat) for seat in ("A3", "A1", "A2"))
    replies = gateway.collect_actions(tick=1, observations=observations, config=MatchConfig(seed=1))
    assert_replies_cover(replies, seats)


# ---------------------------------------------------------------------------
# FR-5.1.1: failure becomes "no action" after the retries
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        ((0, cli_stdout(result_text="I would rather not."), ""), RejectReason.MALFORMED_RESPONSE),
        ((0, "this is not json", ""), RejectReason.MALFORMED_RESPONSE),
        ((1, "", "boom"), RejectReason.PROVIDER_ERROR),
        ((0, cli_stdout(is_error=True), ""), RejectReason.PROVIDER_ERROR),
        (TimeoutError(), RejectReason.AGENT_TIMEOUT),
        (OSError("claude.cmd not found"), RejectReason.PROVIDER_ERROR),
    ],
)
def test_a_failure_falls_back_to_no_action_after_the_retries(
    tmp_path: Path, outcome: Any, reason: RejectReason
) -> None:
    """FR-5.1.1, one row per failure mode, with the retry count asserted."""
    config = GatewayConfig(retries=2, timeout_s=30.0)
    attempts_allowed = config.retries + 1
    gateway = build_gateway(
        outcomes=[outcome] * attempts_allowed, gateway_config=config, trace_path=tmp_path / "t.jsonl"
    )
    replies = gateway.collect_actions(
        tick=7, observations=(make_observation(agent_id="A1", tick=7),), config=MatchConfig(seed=1)
    )
    assert_replies_cover(replies, ("A1",))
    reply = replies[0]
    assert reply.raw is None
    assert reply.source is AgentSource.FALLBACK
    assert reply.error is reason
    assert reply.attempts == attempts_allowed
    assert len(gateway.calls) == attempts_allowed
    entries = read_trace(tmp_path / "t.jsonl")
    assert len(entries) == 1
    assert entries[0]["ok"] is False
    assert entries[0]["error"] == str(reason)
    assert entries[0]["attempts"] == attempts_allowed


def test_retry_accounting_stops_at_the_first_success(tmp_path: Path) -> None:
    """A second attempt that works is reported as ``attempts == 2``, cost summed."""
    config = GatewayConfig(retries=2)
    gateway = build_gateway(
        outcomes=[(0, cli_stdout(result_text="oops", cost_usd=0.01, output_tokens=5), ""), OK],
        gateway_config=config,
        trace_path=tmp_path / "t.jsonl",
    )
    replies = gateway.collect_actions(
        tick=2, observations=(make_observation(agent_id="A1", tick=2),), config=MatchConfig(seed=1)
    )
    assert_replies_cover(replies, ("A1",))
    reply = replies[0]
    assert reply.raw == VALID_ACTION
    assert reply.attempts == 2
    assert len(gateway.calls) == 2
    # Both attempts were billed: 0.01 for the wasted one plus 0.0271 for the good one.
    assert reply.cost_usd == pytest.approx(0.0371)
    assert reply.output_tokens == 315
    entries = read_trace(tmp_path / "t.jsonl")
    assert entries[0]["attempts"] == 2
    assert entries[0]["ok"] is True


def test_each_attempt_gets_a_share_of_the_tick_timeout() -> None:
    """The retries fit inside ``timeout_s``, which ``BaseGateway`` bounds anyway."""
    config = GatewayConfig(retries=2, timeout_s=30.0)
    gateway = build_gateway(outcomes=[OK], gateway_config=config)
    gateway.collect_actions(tick=1, observations=(make_observation(agent_id="A1"),), config=MatchConfig(seed=1))
    assert gateway.calls[0][1] == pytest.approx(10.0)


def test_no_timeout_configured_means_no_attempt_bound() -> None:
    """``timeout_s <= 0`` disables both bounds, exactly as in ``BaseGateway``."""
    gateway = build_gateway(outcomes=[OK], gateway_config=GatewayConfig(timeout_s=0.0, retries=1))
    gateway.collect_actions(tick=1, observations=(make_observation(agent_id="A1"),), config=MatchConfig(seed=1))
    assert gateway.calls[0][1] is None


# ---------------------------------------------------------------------------
# FR-6.2.3: the budget
# ---------------------------------------------------------------------------
def test_an_oversized_prompt_is_refused_before_the_cli_is_launched(tmp_path: Path) -> None:
    """A breach costs nothing: the process is never started."""
    config = GatewayConfig(max_input_tokens_per_call=1, retries=2)
    gateway = build_gateway(outcomes=[], gateway_config=config, trace_path=tmp_path / "t.jsonl")
    replies = gateway.collect_actions(
        tick=1, observations=(make_observation(agent_id="A1"),), config=MatchConfig(seed=1)
    )
    assert_replies_cover(replies, ("A1",))
    assert replies[0].error is RejectReason.BUDGET_EXCEEDED
    assert replies[0].raw is None
    assert replies[0].source is AgentSource.FALLBACK
    assert replies[0].attempts == 0
    assert gateway.calls == []
    entries = read_trace(tmp_path / "t.jsonl")
    assert entries[0]["error"] == str(RejectReason.BUDGET_EXCEEDED)
    assert entries[0]["attempts"] == 0
    assert entries[0]["cost_usd"] == 0.0


def test_an_exhausted_match_budget_falls_back_without_calling(tmp_path: Path) -> None:
    """The ``match`` scope is checked by the bridge before dispatch (ruling R62)."""
    config = GatewayConfig(max_budget_usd_per_match=0.0)
    gateway = build_gateway(outcomes=[], gateway_config=config, trace_path=tmp_path / "t.jsonl")
    replies = gateway.collect_actions(
        tick=1, observations=(make_observation(agent_id="A1"),), config=MatchConfig(seed=1)
    )
    assert_replies_cover(replies, ("A1",))
    assert replies[0].error is RejectReason.BUDGET_EXCEEDED
    assert gateway.calls == []


def test_cached_input_tokens_are_traced_but_never_budgeted() -> None:
    """Ruling R66: 35 000 cached tokens would breach any sane per call input cap."""
    config = GatewayConfig(max_input_tokens_per_call=8_192)
    gateway = build_gateway(outcomes=[OK], gateway_config=config)
    replies = gateway.collect_actions(
        tick=1, observations=(make_observation(agent_id="A1"),), config=MatchConfig(seed=1)
    )
    assert_replies_cover(replies, ("A1",))
    assert replies[0].error is None
    assert replies[0].cached_input_tokens == 35_000
    budget = gateway.budget
    assert budget is not None
    assert budget.spent_tokens("match") == (1240, 310)


def test_cost_and_tokens_are_attributed_to_the_tick_and_the_agent(tmp_path: Path) -> None:
    """T2.3: cost and latency logged per tick and per agent, FR-6.2.3 per tick tokens."""
    seats = ("A1", "A2")
    trace = tmp_path / "llm_trace.jsonl"
    gateway = build_gateway(outcomes=[OK, OK, OK, OK], seats=seats, trace_path=trace)
    for tick in (1, 2):
        replies = gateway.collect_actions(
            tick=tick,
            observations=tuple(make_observation(agent_id=seat, tick=tick) for seat in seats),
            config=MatchConfig(seed=1),
        )
        assert_replies_cover(replies, seats)
    budget = gateway.budget
    assert budget is not None
    for tick in (1, 2):
        for seat in seats:
            assert budget.tick_tokens(seat, tick) == (1240, 310)
    assert budget.spent_usd("match") == pytest.approx(4 * 0.0271)
    entries = read_trace(trace)
    assert len(entries) == 4
    assert sorted((entry["tick"], entry["agent_id"]) for entry in entries) == [
        (1, "A1"),
        (1, "A2"),
        (2, "A1"),
        (2, "A2"),
    ]
    for entry in entries:
        assert entry["cost_usd"] == pytest.approx(0.0271)
        assert entry["latency_ms"] >= 0
        assert entry["input_tokens"] == 1240
        assert entry["output_tokens"] == 310
        assert entry["cache_read_input_tokens"] == 35_000
        assert entry["estimated_input_tokens"] > 0
        assert entry["harness_key"].startswith("sonnet5-baseline@1.0.0+")
        assert entry["model"] == DEFAULT_MODEL
        assert entry["prompt_template_version"] == PROMPT_TEMPLATE_VERSION


def test_the_cumulative_token_cap_binds_the_next_call(tmp_path: Path) -> None:
    """``max_tokens_per_match`` is checked after a call and refuses the next one."""
    # The cap is derived from the rendered prompt so the test states a relation
    # ("one call fits, two do not") rather than a magic number that a reworded
    # prompt would silently invalidate. The output side is disabled (0 means no
    # cap) so only the input estimate and the recorded usage matter.
    estimated = math.ceil(
        (
            len(build_system_prompt(llm_harness(), config=MatchConfig(seed=1)))
            + len(build_user_prompt(observation_to_json(make_observation(agent_id="A1"))))
        )
        / TOKEN_CHARS_PER_TOKEN
    )
    config = GatewayConfig(max_output_tokens_per_call=0, max_tokens_per_match=estimated + 1_000)
    gateway = build_gateway(outcomes=[OK], gateway_config=config, trace_path=tmp_path / "t.jsonl")
    first = gateway.collect_actions(tick=1, observations=(make_observation(agent_id="A1"),), config=MatchConfig(seed=1))
    assert_replies_cover(first, ("A1",))
    assert first[0].error is None
    second = gateway.collect_actions(
        tick=2, observations=(make_observation(agent_id="A1", tick=2),), config=MatchConfig(seed=1)
    )
    assert_replies_cover(second, ("A1",))
    assert second[0].error is RejectReason.BUDGET_EXCEEDED
    assert len(gateway.calls) == 1


# ---------------------------------------------------------------------------
# Two providers (T2.3, PRD T2.3 "at least 2 providers")
# ---------------------------------------------------------------------------
def test_two_providers_supported(tmp_path: Path) -> None:
    """Two model backends behind the CLI, and a mixed table with scripted seats.

    Every LLM call goes through the Claude Code CLI (a hard requirement), so
    "provider" is the ``(executable, model)`` pair a seat is served by. This test
    asserts both halves of T2.3's "at least two": two seats served by two
    different models in the same match, and a ``CompositeGateway`` routing one
    group to the CLI adapter and another to the scripted gateway.
    """
    seats = ("A1", "A2")
    models = {"A1": DEFAULT_MODEL, "A2": "claude-opus-4-5"}
    llm_gateway = build_gateway(outcomes=[OK, OK], seats=seats, models=models, trace_path=tmp_path / "t.jsonl")
    replies = llm_gateway.collect_actions(
        tick=1,
        observations=tuple(make_observation(agent_id=seat) for seat in seats),
        config=MatchConfig(seed=1),
    )
    assert_replies_cover(replies, seats)
    sent_models = sorted(argv[argv.index("--model") + 1] for argv, _timeout in llm_gateway.calls)
    assert sent_models == sorted(models.values())

    scripted_config = MatchConfig(seed=20260827)
    rng = RngTree(scripted_config.seed)
    scripted = ScriptedGateway(
        agents={
            "A3": make_baseline(
                "mute",
                agent_id="A3",
                config=scripted_config,
                rng=rng.child("agent/A3").substream("agent.A3"),
            )
        }
    )
    mixed = CompositeGateway(
        gateways=[
            (seats, build_gateway(outcomes=[OK, OK], seats=seats, models=models)),
            (("A3",), scripted),
        ]
    )
    mixed_replies = mixed.collect_actions(
        tick=1,
        observations=tuple(make_observation(agent_id=seat) for seat in ("A1", "A2", "A3")),
        config=scripted_config,
    )
    assert_replies_cover(mixed_replies, ("A1", "A2", "A3"))
    assert [reply.source for reply in mixed_replies] == [
        AgentSource.LLM,
        AgentSource.LLM,
        AgentSource.SCRIPTED,
    ]


# ---------------------------------------------------------------------------
# Configuration errors abort, they never degrade silently
# ---------------------------------------------------------------------------
def test_a_scripted_harness_is_refused_at_construction() -> None:
    """A scripted brain behind an LLM gateway would spend money for nothing."""
    config = GatewayConfig()
    scripted = HarnessConfig(harness_id="momentum", version="1.0.0", kind="scripted")
    with pytest.raises(InvalidConfigError):
        ClaudeCliGateway(harnesses={"A1": scripted}, gateway_config=config, budget=BudgetTracker(config))


def test_a_harness_without_a_model_is_refused_at_construction() -> None:
    """``--model`` cannot be empty: the CLI would pick its own default."""
    config = GatewayConfig()
    nameless = HarnessConfig(harness_id="mystery", version="1.0.0", kind="llm", model="")
    with pytest.raises(InvalidConfigError):
        ClaudeCliGateway(harnesses={"A1": nameless}, gateway_config=config, budget=BudgetTracker(config))


def test_a_reserved_account_id_is_refused_at_construction() -> None:
    """``MM`` and ``FEES`` never receive an observation (CONTRACTS section 2.3)."""
    config = GatewayConfig()
    with pytest.raises(InvalidConfigError):
        ClaudeCliGateway(harnesses={"MM": llm_harness()}, gateway_config=config, budget=BudgetTracker(config))


def test_an_unseated_agent_aborts_the_match() -> None:
    """A seat with no harness is a configuration bug, not an agent behaviour."""
    gateway = build_gateway(outcomes=[], seats=("A1",))
    with pytest.raises(InvalidConfigError):
        gateway.harness_of("A4")
    with pytest.raises(InvalidConfigError):
        gateway.collect_actions(tick=1, observations=(make_observation(agent_id="A4"),), config=MatchConfig(seed=1))


def test_harnesses_are_held_in_canonical_order() -> None:
    """Section 2.3: the mapping is iterated only through ``sorted_ids``."""
    config = GatewayConfig()
    seats = tuple(make_agent_id(index) for index in (3, 1, 2))
    gateway = ClaudeCliGateway(
        harnesses=dict.fromkeys(seats, llm_harness()),
        gateway_config=config,
        budget=BudgetTracker(config),
    )
    assert gateway.agent_ids == ("A1", "A2", "A3")


# ---------------------------------------------------------------------------
# The transport itself, with a real process and no provider
# ---------------------------------------------------------------------------
def test_a_real_subprocess_is_launched_without_a_shell(tmp_path: Path) -> None:
    """``create_subprocess_exec`` is used, so a prompt is never shell interpreted."""
    config = GatewayConfig()
    gateway = ClaudeCliGateway(harnesses={"A1": llm_harness()}, gateway_config=config, budget=BudgetTracker(config))
    payload = cli_stdout()
    script = "import sys; sys.stdout.write(sys.argv[1])"
    # The second argument holds shell metacharacters on purpose: with a shell it
    # would redirect, with exec it is one opaque argv element.
    argv = [sys.executable, "-c", script, payload, "> " + str(tmp_path / "pwned.txt") + " && echo $HOME"]
    return_code, stdout, stderr = asyncio.run(gateway._arun_cli(argv, timeout_s=60.0))
    assert return_code == 0, stderr
    assert json.loads(parse_cli_stdout(stdout).result_text) == VALID_ACTION
    assert not (tmp_path / "pwned.txt").exists()


def test_a_hanging_process_times_out_and_is_killed() -> None:
    """The attempt bound is real: a wedged CLI cannot eat the whole tick."""
    config = GatewayConfig()
    gateway = ClaudeCliGateway(harnesses={"A1": llm_harness()}, gateway_config=config, budget=BudgetTracker(config))
    argv = [sys.executable, "-c", "import time; time.sleep(30)"]
    with pytest.raises(TimeoutError):
        asyncio.run(gateway._arun_cli(argv, timeout_s=0.5))


# ---------------------------------------------------------------------------
# The trace artefact
# ---------------------------------------------------------------------------
def test_write_llm_trace_appends_and_creates_its_directory(tmp_path: Path) -> None:
    """One line per call, in a run directory that may not exist yet."""
    path = tmp_path / "runs" / "m-election-1-01" / "llm_trace.jsonl"
    entry = LlmTraceEntry(
        tick=1,
        agent_id="A1",
        harness_key="h@1.0.0+0123abcd",
        model=DEFAULT_MODEL,
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        ok=True,
        error=None,
        attempts=1,
        cost_usd=0.027,
        latency_ms=6000,
        input_tokens=1,
        output_tokens=2,
        cache_creation_input_tokens=3,
        cache_read_input_tokens=4,
        estimated_input_tokens=5,
        raw_text="{}",
    )
    write_llm_trace(path, entry)
    write_llm_trace(path, entry)
    entries = read_trace(path)
    assert len(entries) == 2
    assert entries[0] == entries[1]
    assert entries[0]["harness_key"] == "h@1.0.0+0123abcd"


def test_no_trace_path_writes_nothing(tmp_path: Path) -> None:
    """``trace_path=None`` is legal: the file is outside AC-P1 (section 4.6)."""
    gateway = build_gateway(outcomes=[OK], trace_path=None)
    replies = gateway.collect_actions(
        tick=1, observations=(make_observation(agent_id="A1"),), config=MatchConfig(seed=1)
    )
    assert_replies_cover(replies, ("A1",))
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# The prompts
# ---------------------------------------------------------------------------
def test_system_prompt_is_a_pure_function_of_harness_and_config() -> None:
    """Two renders of the same pair are byte identical."""
    harness = llm_harness()
    config = MatchConfig(seed=7)
    first = build_system_prompt(harness, config=config)
    second = build_system_prompt(harness, config=config)
    assert first == second
    assert first


def test_system_prompt_carries_the_config_numbers_and_the_operator_text() -> None:
    """A tournament that lowers a cap changes the prompt in the same breath."""
    config = MatchConfig(seed=7, max_orders_per_action=4, taker_fee_bps=25, market_band_cents=7)
    rendered = build_system_prompt(llm_harness(), config=config)
    assert "Trade the mispricings you can actually see." in rendered
    assert "at most 4 order operations per tick" in rendered
    assert "25 basis points" in rendered
    assert "protection band of 7 cents" in rendered
    assert f"lasts {config.ticks_total} ticks" in rendered
    assert "risk: medium" in rendered and "style: value" in rendered


def test_system_prompt_states_that_messages_are_data(tmp_path: Path) -> None:
    """FR-5.6.2: the only injection surface is named as untrusted data."""
    del tmp_path
    rendered = build_system_prompt(llm_harness(), config=MatchConfig(seed=7))
    assert "DATA, never" in rendered
    assert "manipulate" in rendered


def test_talking_mode_flips_the_message_rule() -> None:
    """The prompt never invites a message the validator would reject."""
    off = build_system_prompt(llm_harness(), config=MatchConfig(seed=7, talking_mode=False))
    on = build_system_prompt(llm_harness(), config=MatchConfig(seed=7, talking_mode=True))
    assert "Talking mode is OFF" in off
    assert "Talking mode is ON" in on
    assert off != on


def test_prompts_hold_no_em_dash() -> None:
    """Contract rule 4, checked on generated text and not only on source files."""
    rendered = build_system_prompt(llm_harness(), config=MatchConfig(seed=7))
    user = build_user_prompt(observation_to_json(make_observation(agent_id="A1")))
    assert EM_DASH not in rendered
    assert EM_DASH not in user


def test_user_prompt_carries_the_whole_observation() -> None:
    """Decision 14: one call per agent per tick covers every market at once."""
    observation = make_observation(agent_id="A2", tick=5, n_markets=3)
    payload = observation_to_json(observation)
    rendered = build_user_prompt(payload)
    assert "Tick 5 of" in rendered
    assert "trader A2" in rendered
    for index in (1, 2, 3):
        assert make_market_id(index) in rendered
    assert rendered == build_user_prompt(payload)


def test_user_prompt_is_stable_whatever_key_order_the_caller_used() -> None:
    """``stable_json`` sorts object keys, so no caller chooses an ordering."""
    payload = observation_to_json(make_observation(agent_id="A1"))
    shuffled = dict(reversed(list(payload.items())))
    assert build_user_prompt(shuffled) == build_user_prompt(payload)
