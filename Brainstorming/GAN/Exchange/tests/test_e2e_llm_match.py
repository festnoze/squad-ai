"""AC-P2: a real LLM match, end to end, through the Claude Code CLI.

**This is the only file in the repository allowed to spend money.** It carries
both the ``llm`` and the ``e2e`` markers, so CI deselects it
(``pytest -m "not llm and not slow and not statistical"``) and the fast loop
never touches it.

Markers alone are not enough, because two developer entry points run the whole
suite without a marker expression (``make test`` is ``pytest -q`` and ``make
cov`` is the same suite under coverage). A test that costs about 1.30 USD must
not fire because somebody typed ``make test``, so this module **also** opts in
explicitly:

* ``PXE_LLM_E2E=1`` must be set in the environment, and
* the Claude Code CLI must be on ``PATH``.

Without both it skips with a named reason. Reading an environment variable is a
test scaffolding decision and not an engine one: CONTRACTS section 2.6 forbids a
**library module** from reading the environment, and nothing under ``src/`` does.

How to run it, and what it costs
--------------------------------
From the repository root, with the CLI already authenticated (OAuth, no
``ANTHROPIC_API_KEY``):

    PXE_LLM_E2E=1 .venv/Scripts/python.exe -m pytest -q -m "llm and e2e" tests/test_e2e_llm_match.py

or, on PowerShell:

    $env:PXE_LLM_E2E="1"; .venv\\Scripts\\python.exe -m pytest -q -m "llm and e2e" tests\\test_e2e_llm_match.py

Estimated cost: **two LLM seats times twenty-four ticks equals 48 calls at about
0.027 USD, that is about 1.30 USD**, in about five minutes of wall clock (six
seconds per call, two calls in parallel per tick). ``GatewayConfig`` caps the run
at 3.00 USD per match, so a provider price change cannot turn this into a
surprise: the budget tracker refuses the remaining calls and the match finishes
on the FR-5.1.1 fallback instead of on the credit card.

What it asserts (AC-P2)
-----------------------
1. the journal is non empty and internally consistent (``verify_journal``);
2. every LLM seat really acted: at least one ``AgentActionReceived`` with
   ``source == "llm"`` per seat, so a match that fell back on every tick fails
   instead of passing;
3. the validation was clean: no ``AgentActionRejected`` with a schema level
   reason, which is what ``--json-schema`` is for;
4. settlement is exact to the cent: cash is conserved to the unit (I2) and every
   position is flat at the end (I11);
5. the cost and latency of every call are in ``llm_trace.jsonl``, one line per
   call (T2.3), and none of it is in the journal (CONTRACTS section 3.5).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from pxe.events import AgentActionReceived, AgentActionRejected, AgentTimedOut, MatchEnded, PositionSnapshot
from pxe.gateway.budget import BudgetTracker
from pxe.gateway.claude_cli import DEFAULT_MODEL, ClaudeCliGateway, claude_executable
from pxe.gateway.protocol import AgentGateway
from pxe.gateway.scripted import CompositeGateway, ScriptedGateway
from pxe.info.profiles import build_profile, default_profile_kinds
from pxe.journal import read_journal, verify_journal
from pxe.rng import RngTree
from pxe.runner.match_runner import run_match
from pxe.types import (
    FEES_ACCOUNT_ID,
    MM_ACCOUNT_ID,
    AgentSpec,
    GatewayConfig,
    HarnessConfig,
    MatchConfig,
    RejectReason,
    make_agent_id,
)
from pxe.world.generator import generate_world

pytestmark = [pytest.mark.llm, pytest.mark.e2e]

#: The smallest legal match that still exercises everything: four seats, two
#: markets, twenty-four ticks (``MatchConfig.__post_init__`` refuses less).
TICKS_TOTAL = 24
N_MARKETS = 2
SEED = 20260827
#: Seats behind the CLI. Two, not four, so the bill is halved and a mixed table
#: (LLM plus scripted) is exercised at the same time.
LLM_SEATS = ("A1", "A2")
SCRIPTED_SEATS = ("A3", "A4")
#: Hard ceiling on the run, in USD. About 1.30 is expected.
MATCH_USD_CAP = 3.00
#: Schema level rejections are what ``--json-schema`` exists to prevent.
SCHEMA_REASONS = frozenset({RejectReason.SCHEMA_INVALID, RejectReason.ACTION_INVALID})


def _skip_unless_opted_in() -> None:
    """Skip the module unless a human explicitly asked to spend money."""
    if os.environ.get("PXE_LLM_E2E") != "1":
        pytest.skip("set PXE_LLM_E2E=1 to run the paid LLM end to end match (about 1.30 USD)")
    if shutil.which(claude_executable()) is None:
        pytest.skip(f"{claude_executable()} is not on PATH, so no LLM call can be made")


def _gateway(*, trace_path: Path, config: MatchConfig) -> tuple[AgentGateway, BudgetTracker]:
    """Build the mixed table: two CLI seats, two scripted seats."""
    from pxe.agents.base import make_baseline

    gateway_config = GatewayConfig(
        timeout_s=120.0,
        retries=2,
        max_budget_usd_per_call=0.20,
        max_budget_usd_per_match=MATCH_USD_CAP,
        max_budget_usd_per_tournament=MATCH_USD_CAP,
        max_parallel_calls=len(LLM_SEATS),
    )
    budget = BudgetTracker(gateway_config)
    harnesses = {
        seat: HarnessConfig(
            harness_id="sonnet5-e2e",
            version="1.0.0",
            kind="llm",
            model=DEFAULT_MODEL,
            system_prompt="You are a careful, well calibrated trader. Prefer small positions.",
        )
        for seat in LLM_SEATS
    }
    llm = ClaudeCliGateway(
        harnesses=harnesses,
        gateway_config=gateway_config,
        budget=budget,
        trace_path=trace_path,
    )
    rng = RngTree(config.seed)
    scripted = ScriptedGateway(
        agents={
            seat: make_baseline(
                "mute",
                agent_id=seat,
                config=config,
                rng=rng.child(f"agent/{seat}").substream(f"agent.{seat}"),
            )
            for seat in SCRIPTED_SEATS
        }
    )
    return CompositeGateway(gateways=[(LLM_SEATS, llm), (SCRIPTED_SEATS, scripted)]), budget


@pytest.fixture(scope="module")
def llm_match(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, tuple[object, ...], BudgetTracker]:
    """Run the paid match exactly once and share it with every test here."""
    _skip_unless_opted_in()
    out_dir = tmp_path_factory.mktemp("llm_match")
    config = MatchConfig(seed=SEED, ticks_total=TICKS_TOTAL, n_agents=4, n_markets=N_MARKETS)
    world = generate_world(template_id="election", seed=SEED, ticks_total=TICKS_TOTAL, n_markets=N_MARKETS)
    kinds = default_profile_kinds(config.n_agents)
    market_ids = world.market_ids()
    specs = tuple(
        AgentSpec(
            agent_id=make_agent_id(index),
            harness=HarnessConfig(
                harness_id="sonnet5-e2e" if make_agent_id(index) in LLM_SEATS else "mute",
                version="1.0.0",
                kind="llm" if make_agent_id(index) in LLM_SEATS else "scripted",
                model=DEFAULT_MODEL if make_agent_id(index) in LLM_SEATS else "",
            ),
            info_profile=build_profile(kinds[index - 1], market_ids=market_ids),
        )
        for index in range(1, config.n_agents + 1)
    )
    trace_path = out_dir / "llm_trace.jsonl"
    gateway, budget = _gateway(trace_path=trace_path, config=config)
    result = run_match(
        config=config,
        world=world,
        agents=specs,
        gateway=gateway,
        out_dir=out_dir,
        rng=RngTree(config.seed),
    )
    gateway.close()
    events = read_journal(out_dir / "journal.jsonl")
    assert events, "the LLM match produced an empty journal"
    assert result.event_count == len(events)
    return out_dir, tuple(events), budget


def test_llm_match_completes(llm_match: tuple[Path, tuple[object, ...], BudgetTracker]) -> None:
    """AC-P2: the match runs to the end and its journal is consistent."""
    out_dir, events, budget = llm_match
    assert events, "the journal is empty"
    verify_journal(events)  # type: ignore[arg-type]
    endings = [event for event in events if isinstance(event, MatchEnded)]
    assert len(endings) == 1
    assert endings[0].reason == "completed"
    assert endings[0].final_tick == TICKS_TOTAL
    assert budget.spent_usd("match") <= MATCH_USD_CAP
    assert (out_dir / "journal.jsonl").exists()


def test_every_llm_seat_actually_acted(llm_match: tuple[Path, tuple[object, ...], BudgetTracker]) -> None:
    """Anti vacuous: a match that fell back on every tick is not a passing match."""
    _out_dir, events, _budget = llm_match
    received = [event for event in events if isinstance(event, AgentActionReceived)]
    assert received, "no AgentActionReceived at all"
    llm_actions = {event.agent_id for event in received if event.source == "llm"}
    assert set(LLM_SEATS) <= llm_actions, f"seats that never produced an llm action: {set(LLM_SEATS) - llm_actions}"
    timeouts = [event for event in events if isinstance(event, AgentTimedOut)]
    # A provider hiccup is tolerated; a match that is mostly fallback is not.
    assert len(timeouts) < len(LLM_SEATS) * TICKS_TOTAL // 4, f"too many fallbacks: {len(timeouts)}"


def test_validation_is_clean(llm_match: tuple[Path, tuple[object, ...], BudgetTracker]) -> None:
    """AC-P2: ``--json-schema`` means no schema level rejection ever fires."""
    _out_dir, events, _budget = llm_match
    rejections = [event for event in events if isinstance(event, AgentActionRejected)]
    fatal = [event for event in rejections if event.reason in {reason.value for reason in SCHEMA_REASONS}]
    assert not fatal, f"structurally invalid payloads reached the validator: {fatal}"


def test_settlement_is_exact_to_the_cent(llm_match: tuple[Path, tuple[object, ...], BudgetTracker]) -> None:
    """I2 and I11 from the journal alone: cash conserved, every position flat."""
    _out_dir, events, _budget = llm_match
    snapshots = [event for event in events if isinstance(event, PositionSnapshot)]
    assert snapshots, "no PositionSnapshot was emitted"
    config = MatchConfig(seed=SEED, ticks_total=TICKS_TOTAL, n_agents=4, n_markets=N_MARKETS)
    expected_total = config.n_agents * config.initial_cash_cents + config.mm_initial_cash_cents
    last_tick = max(event.tick for event in snapshots)
    final = [event for event in snapshots if event.tick == last_tick]
    assert {event.account_id for event in final} >= {MM_ACCOUNT_ID, FEES_ACCOUNT_ID}
    assert sum(event.cash_cents for event in final) == expected_total
    for event in final:
        # ``positions`` holds one mapping per NON FLAT market, so I11 (every
        # position flat after the last settlement) is exactly an empty tuple.
        assert event.positions == (), f"{event.account_id} is not flat: {event.positions}"
        assert event.equity_cents == event.cash_cents


def test_cost_and_latency_are_traced_and_not_journalled(
    llm_match: tuple[Path, tuple[object, ...], BudgetTracker],
) -> None:
    """T2.3 and CONTRACTS section 3.5: the trace carries what the journal must not."""
    out_dir, events, budget = llm_match
    trace_path = out_dir / "llm_trace.jsonl"
    raw = trace_path.read_bytes()
    assert raw, "no llm trace was written"
    assert b"\r" not in raw
    entries = [json.loads(line) for line in raw.decode("utf-8").split("\n") if line]
    assert entries, "the llm trace has no line"
    assert {entry["agent_id"] for entry in entries} == set(LLM_SEATS)
    assert all(entry["latency_ms"] >= 0 for entry in entries)
    assert sum(entry["latency_ms"] for entry in entries) > 0
    assert sum(entry["cost_usd"] for entry in entries) > 0.0
    assert sum(entry["cost_usd"] for entry in entries) == pytest.approx(budget.spent_usd("match"), abs=1e-6)
    # Not one of those numbers is in the journal.
    text = "\n".join(json.dumps(event.to_dict(), sort_keys=True) for event in events)  # type: ignore[attr-defined]
    for forbidden in ("cost_usd", "latency_ms", "input_tokens", "attempts", "duration_ms"):
        assert forbidden not in text
