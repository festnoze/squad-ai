"""A16 acceptance tests: AC-P4, the two scores never touch (PRD 7.2, CONTRACTS 9).

The PRD's anti hacking principle is blunt: "le Brier est calcule uniquement sur
les predictions declarees, le PnL uniquement sur les trades ; **aucun score
n'entre dans le calcul de l'autre**". This file proves it with teeth, in two
directions and in two independent ways.

**Behaviourally**, by mutation. One event family of a real journal is rewritten
and the other metric is asserted **bit identical**, not merely close: the
comparison is over the frozen dataclasses and over their
:func:`~pxe.events.stable_json` bytes, so a single ppm or cent moving anywhere in
any field fails. Each mutation test also asserts that the mutation really did
move the metric it is allowed to move, otherwise a projection that returned
constants would satisfy every invariance claim here.

**Structurally**, by reading the two modules with :mod:`ast`. Mutation testing
proves that today's inputs are disjoint; the structural test proves the code
cannot even reach the other family, so a future edit that starts consulting
``projection.trades`` from the calibration side fails immediately instead of
waiting for a golden journal where it happens to matter.

``test_projection_row_types_are_populated`` also lives here, because CONTRACTS
section 10 names it in this file: five empty tuples satisfy every type annotation
A16, A17 and A18 code against, so the row families are asserted non empty before
any decoupling claim is made.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from pxe.events import (
    Event,
    MarketResolved,
    MarkToMarket,
    MessagePosted,
    OrderCancelled,
    OrderPlaced,
    PositionSnapshot,
    PredictionRecorded,
    SettlementApplied,
    TradeExecuted,
    stable_json,
)
from pxe.journal import read_journal
from pxe.metrics.calibration import CalibrationMetrics, compute_calibration, reliability_curve
from pxe.metrics.performance import PerformanceMetrics, compute_performance, final_ranking
from pxe.metrics.projection import MatchProjection, project
from pxe.types import Outcome
from tests.test_match_runner import GOLDEN_DIR, REFERENCE, SMALL, WIDE, Recipe, of_type

GOLDEN: tuple[Recipe, ...] = (REFERENCE, SMALL, WIDE)

#: The projection row families that belong to the **trading** side of AC-P4.
#: :mod:`pxe.metrics.calibration` may not read any of them, and the structural
#: test below enforces that by reading the module rather than by trusting it.
_TRADING_ROWS = ("trades", "orders", "equity_cents", "cash_cents", "ref_price", "highlights")

#: The projection row family that belongs to the **calibration** side.
#: :mod:`pxe.metrics.performance` may not read it.
_PREDICTION_ROWS = ("predictions",)

_SRC = Path(__file__).resolve().parents[1] / "src" / "pxe" / "metrics"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def golden_events(recipe: Recipe) -> tuple[Event, ...]:
    """Read one frozen journal from ``tests/golden/``."""
    path = GOLDEN_DIR / f"{recipe.name}.journal.jsonl"
    assert path.exists(), f"missing golden journal for {recipe.name}"
    events = read_journal(path)
    assert events, "the golden journal read back empty, so every assertion below would be vacuous"
    return events


def fingerprint(rows: Sequence[Any]) -> str:
    """Return the canonical bytes of a metric block, as text.

    Dataclass equality already compares every field, and this compares the
    serialised form on top of it, which is what "bit identical" means for
    something the store and the API will write to disk.
    """
    return stable_json([asdict(row) for row in rows])


def curves_of(projection: MatchProjection) -> str:
    """Return the canonical bytes of every seat's reliability curve."""
    return stable_json([list(reliability_curve(projection, agent_id)) for agent_id in projection.agent_ids])


def with_rewritten_predictions(events: tuple[Event, ...]) -> tuple[Event, ...]:
    """Return the journal with every declared probability replaced by its mirror.

    Only ``PredictionRecorded`` is touched, and every one of its two payload
    fields is: the probability is mirrored around 0.5 and the carry flag is
    inverted.
    """
    return tuple(
        replace(event, p_yes_ppm=1_000_000 - event.p_yes_ppm, carried=not event.carried)
        if isinstance(event, PredictionRecorded)
        else event
        for event in events
    )


def _rewrite_trading_event(event: Event) -> Event:
    """Return one trading side event with every metric relevant field moved."""
    if isinstance(event, TradeExecuted):
        return replace(
            event,
            price=100 - event.price,
            qty=event.qty + 7,
            taker_fee_cents=event.taker_fee_cents + 13,
            maker_cash_delta_cents=-event.maker_cash_delta_cents,
            taker_cash_delta_cents=-event.taker_cash_delta_cents - 13,
            maker_agent_id=event.taker_agent_id,
            taker_agent_id=event.maker_agent_id,
            maker_side=event.taker_side,
            taker_side=event.maker_side,
        )
    if isinstance(event, OrderPlaced):
        return replace(event, price=100 - event.price, qty=event.qty + 5, reserved_cents=event.reserved_cents + 11)
    if isinstance(event, OrderCancelled):
        return replace(event, remaining_qty=event.remaining_qty + 3, released_cents=event.released_cents + 17)
    if isinstance(event, PositionSnapshot):
        return replace(
            event,
            cash_cents=event.cash_cents + 1_000,
            equity_cents=event.equity_cents - 1_000,
            reserved_cents=event.reserved_cents + 19,
        )
    if isinstance(event, MarkToMarket):
        return replace(event, ref_price=100 - event.ref_price, tick_volume_qty=event.tick_volume_qty + 23)
    if isinstance(event, SettlementApplied):
        return replace(event, cash_delta_cents=-event.cash_delta_cents, position_qty=-event.position_qty)
    return event


def with_rewritten_trading_side(events: tuple[Event, ...]) -> tuple[Event, ...]:
    """Return the journal with the whole trading side rewritten.

    Every event family a performance number is built from moves: the executions,
    the order lifecycle, the per tick snapshots, the marks and the settlements.
    ``MarketResolved`` is deliberately **not** touched: an outcome is a shared and
    legitimate input of both scores, not a score, and mutating it is the subject
    of its own test below.
    """
    return tuple(_rewrite_trading_event(event) for event in events)


def changed_types(before: tuple[Event, ...], after: tuple[Event, ...]) -> set[str]:
    """Return the names of the event classes that differ between two journals."""
    assert len(before) == len(after), "a mutation added or removed an event, so it is not a field rewrite"
    return {type(old).__name__ for old, new in zip(before, after, strict=True) if old != new}


def _module_ast(name: str) -> ast.Module:
    """Parse one module of ``src/pxe/metrics`` and refuse an empty parse."""
    path = _SRC / name
    assert path.exists(), f"missing module {path}"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert tree.body, f"{name} parsed empty, so the structural scan below would be vacuous"
    return tree


def attributes_read_in(name: str) -> set[str]:
    """Return every attribute name one module reads, whatever the object."""
    return {node.attr for node in ast.walk(_module_ast(name)) if isinstance(node, ast.Attribute)}


def modules_imported_by(name: str) -> set[str]:
    """Return every module one module imports."""
    found: set[str] = set()
    for node in ast.walk(_module_ast(name)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module)
    return found


def names_imported_by(name: str) -> set[str]:
    """Return every symbol one module imports from somewhere else."""
    return {
        alias.asname or alias.name
        for node in ast.walk(_module_ast(name))
        if isinstance(node, ast.ImportFrom | ast.Import)
        for alias in node.names
    }


# ---------------------------------------------------------------------------
# The anti vacuous gate CONTRACTS section 10 names in this file
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_projection_row_types_are_populated(recipe: Recipe) -> None:
    """Section 10: a projection of five empty tuples types check perfectly.

    ``messages`` is the one family no baseline produces (FR-5.6.1 needs an agent
    that talks, and none of the six does), so the claim about it is that the rows
    match the journal rather than that they are non empty;
    ``test_metrics_performance.py::test_messages_are_projected_when_talking_mode_is_on``
    is the one that populates it.
    """
    events = golden_events(recipe)
    projection = project(events)
    assert projection.trades, "no trade row"
    assert projection.orders, "no order row"
    assert projection.predictions, "no prediction row"
    assert projection.signals, "no signal row"
    assert projection.highlights, "no highlight"
    assert projection.equity_cents and projection.cash_cents and projection.ref_price
    assert projection.outcomes and projection.resolution_ticks
    assert len(projection.messages) == len(of_type(events, MessagePosted))
    assert compute_calibration(projection), "no calibration block"
    assert compute_performance(projection), "no performance block"


# ---------------------------------------------------------------------------
# AC-P4, first direction: mutate the predictions, the PnL does not move
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_mutating_only_the_predictions_leaves_the_pnl_bit_identical(recipe: Recipe) -> None:
    """AC-P4: no declared probability reaches a performance number."""
    events = golden_events(recipe)
    assert of_type(events, PredictionRecorded), "no prediction to mutate, so this test would be vacuous"
    mutated = with_rewritten_predictions(events)
    assert changed_types(events, mutated) == {"PredictionRecorded"}, "the mutation escaped its event family"

    original = project(events)
    altered = project(mutated)
    assert altered.predictions != original.predictions, "the mutation did not change the prediction rows"
    assert altered.trades == original.trades, "the projection changed a trade row for a prediction rewrite"

    before: tuple[PerformanceMetrics, ...] = compute_performance(original)
    after: tuple[PerformanceMetrics, ...] = compute_performance(altered)
    assert after == before
    assert fingerprint(after) == fingerprint(before)
    assert final_ranking(altered) == final_ranking(original)
    assert fingerprint(final_ranking(altered)) == fingerprint(final_ranking(original))

    # Teeth: the mutation is real, and it moves the metric it is allowed to move.
    assert compute_calibration(altered) != compute_calibration(original)


# ---------------------------------------------------------------------------
# AC-P4, second direction: mutate the trades, the Brier does not move
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_mutating_only_the_trades_leaves_the_brier_bit_identical(recipe: Recipe) -> None:
    """AC-P4, the direction the PRD states first: no trade reaches the Brier."""
    events = golden_events(recipe)
    assert of_type(events, TradeExecuted), "no trade to mutate, so this test would be vacuous"
    mutated = tuple(_rewrite_trading_event(event) if isinstance(event, TradeExecuted) else event for event in events)
    assert changed_types(events, mutated) == {"TradeExecuted"}, "the mutation escaped its event family"

    original = project(events)
    altered = project(mutated)
    assert altered.trades != original.trades, "the mutation did not change the trade rows"
    assert altered.predictions == original.predictions

    before: tuple[CalibrationMetrics, ...] = compute_calibration(original)
    after: tuple[CalibrationMetrics, ...] = compute_calibration(altered)
    assert after == before
    assert fingerprint(after) == fingerprint(before)
    assert curves_of(altered) == curves_of(original)

    # Teeth: the mutation is real, and it moves the metric it is allowed to move.
    assert compute_performance(altered) != compute_performance(original)


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_rewriting_the_whole_trading_side_leaves_the_brier_bit_identical(recipe: Recipe) -> None:
    """The stronger claim: every money bearing event may move, the Brier may not.

    Executions, order lifecycle, per tick snapshots, marks and settlements are all
    rewritten at once. Nothing a calibration number is made of is in that list, so
    the Brier and every reliability curve must come out byte for byte the same.
    """
    events = golden_events(recipe)
    mutated = with_rewritten_trading_side(events)
    moved = changed_types(events, mutated)
    assert moved == {
        "TradeExecuted",
        "OrderPlaced",
        "OrderCancelled",
        "PositionSnapshot",
        "MarkToMarket",
        "SettlementApplied",
    }, moved
    assert "PredictionRecorded" not in moved and "MarketResolved" not in moved

    original = project(events)
    altered = project(mutated)
    assert altered.orders != original.orders and altered.equity_cents != original.equity_cents
    assert altered.predictions == original.predictions
    assert fingerprint(compute_calibration(altered)) == fingerprint(compute_calibration(original))
    assert curves_of(altered) == curves_of(original)
    assert compute_performance(altered) != compute_performance(original)


def test_the_brier_still_depends_on_the_realised_outcome() -> None:
    """An outcome is a shared input of both scores, and it is not a score.

    Flipping every ``MarketResolved.outcome`` must move the Brier, because
    ``(p - y)^2`` is a function of ``y``. Without this the two invariance tests
    above would be satisfied by a Brier that ignores the journal entirely.
    """
    events = golden_events(SMALL)
    resolutions = [event for event in of_type(events, MarketResolved) if isinstance(event, MarketResolved)]
    assert resolutions, "no market resolved, so there is no outcome to flip"
    flipped = tuple(
        replace(event, outcome=(Outcome.NO if Outcome(event.outcome) is Outcome.YES else Outcome.YES).value)
        if isinstance(event, MarketResolved)
        else event
        for event in events
    )
    assert changed_types(events, flipped) == {"MarketResolved"}

    original = compute_calibration(project(events))
    mirrored = compute_calibration(project(flipped))
    assert [row.n_terms for row in mirrored] == [row.n_terms for row in original], "flipping y changed the denominator"
    assert mirrored != original
    # A Brier term is (p - y)^2, so mirroring y mirrors the term around the
    # midpoint of the range for a match whose markets all share one outcome.
    for before_row, after_row in zip(original, mirrored, strict=True):
        assert after_row.brier_ppm != before_row.brier_ppm or before_row.brier_ppm == 250_000


# ---------------------------------------------------------------------------
# The structural half: neither module can reach the other family
# ---------------------------------------------------------------------------
def test_calibration_reads_no_trading_row() -> None:
    """AC-P4 as a property of the code, not of today's golden journals."""
    read = attributes_read_in("calibration.py")
    assert "predictions" in read, "the scan found no projection access at all, so it proves nothing"
    for row in _TRADING_ROWS:
        assert row not in read, f"pxe.metrics.calibration reads projection.{row}"


def test_performance_reads_no_prediction_row() -> None:
    """The mirror image, asserted on A15's module because AC-P4 has two halves."""
    read = attributes_read_in("performance.py")
    assert "trades" in read, "the scan found no projection access at all, so it proves nothing"
    for row in _PREDICTION_ROWS:
        assert row not in read, f"pxe.metrics.performance reads projection.{row}"
    imported = names_imported_by("performance.py")
    assert "PredictionRow" not in imported, "A15's performance module imports a prediction row type"


def test_the_two_metric_modules_do_not_import_each_other() -> None:
    """Section 13: A16 may read ``pxe.metrics.projection`` and nothing else here.

    ``aggregate`` is the one module allowed to import both (section 7.17), which
    is why the check is on the two leaves and not on the package.
    """
    calibration = modules_imported_by("calibration.py")
    performance = modules_imported_by("performance.py")
    assert "pxe.metrics.projection" in calibration
    assert "pxe.metrics.performance" not in calibration
    assert "pxe.metrics.behavioral" not in calibration
    assert "pxe.metrics.aggregate" not in calibration
    assert "pxe.metrics.calibration" not in performance
    inside_metrics = {name for name in calibration if name.startswith("pxe.metrics")}
    assert inside_metrics == {"pxe.metrics.projection"}, inside_metrics
    engine = {name for name in calibration if name.startswith(("pxe.runner", "pxe.exchange", "pxe.world", "pxe.mm"))}
    assert engine == set(), f"calibration reached into the engine: {engine}"


# ---------------------------------------------------------------------------
# The name CONTRACTS section 11 cites for O2 and for AC-P4
# ---------------------------------------------------------------------------
def test_scores_are_independent() -> None:
    """AC-P4 and O2 in one place, both directions, on the reference match.

    The two parametrized tests above are the same two claims over all three
    golden matches; this is the single named test the traceability rows of
    section 11 point at, so a reader following the table lands on one function
    that states the whole acceptance criterion:

    * rewriting every declared probability moves no performance number and no
      ranking line, by value and by serialised bytes;
    * rewriting every execution moves no Brier and no reliability curve, by
      value and by serialised bytes;
    * and each mutation does move its own side, so neither invariance is the
      invariance of a constant.
    """
    events = golden_events(REFERENCE)
    assert of_type(events, PredictionRecorded) and of_type(events, TradeExecuted)
    base = project(events)
    assert base.predictions and base.trades

    predictions_moved = project(with_rewritten_predictions(events))
    trades_moved = project(
        tuple(_rewrite_trading_event(event) if isinstance(event, TradeExecuted) else event for event in events)
    )
    assert predictions_moved.predictions != base.predictions
    assert trades_moved.trades != base.trades

    # The Brier does not see a trade.
    assert compute_calibration(trades_moved) == compute_calibration(base)
    assert fingerprint(compute_calibration(trades_moved)) == fingerprint(compute_calibration(base))
    assert curves_of(trades_moved) == curves_of(base)

    # The PnL does not see a prediction.
    assert compute_performance(predictions_moved) == compute_performance(base)
    assert fingerprint(compute_performance(predictions_moved)) == fingerprint(compute_performance(base))
    assert final_ranking(predictions_moved) == final_ranking(base)

    # Neither side is inert.
    assert compute_calibration(predictions_moved) != compute_calibration(base)
    assert compute_performance(trades_moved) != compute_performance(base)
