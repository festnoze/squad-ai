"""Per market resolution and FR-5.4.5 cancellation (CONTRACTS section 7.11).

The oracle is the only component that ever closes a market, and therefore the
only one that knows which markets are still open without asking anybody
(CONTRACTS section 7.8: ``Exchange.close_market`` has exactly two call sites,
both in this module). Reading a status off the exchange instead would let a
second, disagreeing view of market state exist.

What this module owns, and what it deliberately does not
-------------------------------------------------------
:meth:`Oracle.resolve` performs P1 step 4 sub-steps **a, b, c and e**, in that
order, and returns a :class:`ResolutionReport`. The runner performs only
sub-step **d**, the resolution ``NewsPublished``, because that item comes from
the information engine (which the oracle does not hold) and must join the
tick's other news in the single ``mm.note_news`` handover of P1 step 5b
(decision 29). Implementing a, b, c or e in the runner as well produces two
``cancel_all`` passes and two ``MarketResolved`` events for the same market.

The sub-step order is not cosmetic. Cancelling the resting orders **before**
settling the positions is the only ordering that keeps invariant I4
(``0 <= reserved <= cash``) true throughout: the order collateral is released
first, then the position leg is applied, then the market is closed, and
``Exchange.close_market`` refuses to close a market that still holds resting
orders so the ordering cannot silently drift.

The resolution tick semantics (CONTRACTS section 5.0)
----------------------------------------------------
A market whose ``resolution_tick`` is ``r`` is open and tradable for the whole
of tick ``r`` and is resolved in P1 of tick ``r + 1``. Consequently:

* :meth:`Oracle.due_market_ids` returns the still-open markets whose
  ``resolution_tick < tick``, so at tick ``t`` it resolves what was scheduled
  for ``t - 1`` and it returns ``()`` at tick 1;
* the **envelope** ``tick`` of ``MarketResolved`` is ``r + 1`` while its
  **payload** ``resolution_tick`` is ``r``. They differ by one on purpose, and
  a projection keying on the payload field gets the scheduled tick;
* when ``r == ticks_total`` the resolution happens in finalisation, at the
  virtual tick ``ticks_total + 1``. With the PRD default every market resolves
  there, so that is the normal path and not a defensive one.

A cancellation is different and the difference is deliberate: a cancellation
scheduled at tick ``c`` fires in P1 of tick ``c``, not ``c + 1``. It is a
scripted intervention, not a scheduled maturity, so the market is not tradable
on the tick it is cancelled (FR-5.4.5).

Determinism
-----------
``Oracle(*, world)`` takes **no** :class:`~pxe.rng.RngTree` and there is no
registered ``oracle.*`` substream (CONTRACTS section 3.1): the outcome and the
latent value were frozen by world generation, so the oracle draws nothing. It
reads no clock, no file and no network either.
"""

from __future__ import annotations

from dataclasses import dataclass

from pxe.errors import InvalidConfigError
from pxe.events import MarketCancelled, MarketResolved
from pxe.exchange.accounts import AccountBook, SettlementLine
from pxe.exchange.exchange import Exchange
from pxe.journal import Journal
from pxe.oracle.settlement import settle
from pxe.types import CancelReason, MarketSpec, MarketStatus, Outcome
from pxe.world.generator import World

__all__ = ["ResolutionReport", "Oracle"]

#: The two settlement modes of CONTRACTS section 6.4.
_MODE_RESOLUTION = "resolution"
_MODE_UNWIND = "unwind"


@dataclass(frozen=True)
class ResolutionReport:
    """What one resolution or one cancellation did, for the runner and for tests.

    The report carries no money field of its own: every cent that moved is in
    the ``OrderCancelled`` and ``SettlementApplied`` events already emitted
    (CONTRACTS section 4.5, "one event per money movement"). It exists so the
    runner can build sub-step d's news item and so a test can assert on the
    outcome without re-reading the journal.

    Attributes:
        market_id: The market that was resolved or cancelled.
        outcome: The realised outcome, or ``None`` for a cancellation.
        payout_cents: ``100`` for YES, ``0`` for NO and ``0`` for a
            cancellation, which pays no outcome at all.
        cancelled_order_ids: Ids of the resting orders that left the book in
            sub-step a, in emission order (``priority_key`` order, bids before
            asks).
        settlements: The settlement lines, in canonical account order. Empty
            when nobody held a position, a cost basis or a fee on that market.
    """

    market_id: str
    outcome: Outcome | None
    payout_cents: int
    cancelled_order_ids: tuple[str, ...]
    settlements: tuple[SettlementLine, ...]


class Oracle:
    """Resolves markets at their own tick and unwinds the cancelled ones.

    One instance per match, built by the runner as ``Oracle(world=world)`` and
    by nobody else (CONTRACTS section 7.12). It keeps the only record of which
    markets it has already closed, which is what makes
    :meth:`due_market_ids` answerable without an ``Exchange`` handle.
    """

    def __init__(self, *, world: World) -> None:
        """Build the oracle over an already generated world.

        Args:
            world: The generated world. Its scenario supplies the per market
                ``resolution_tick`` (FR-5.2.3) and the scripted cancellations
                (FR-5.4.5), and its latent process supplies the value that
                decided each outcome.
        """
        self._world = world
        self._market_ids: tuple[str, ...] = world.market_ids()
        self._closed: dict[str, MarketStatus] = {}

    def __repr__(self) -> str:
        """Render as ``Oracle(markets=5, closed=2)``."""
        return f"Oracle(markets={len(self._market_ids)}, closed={len(self._closed)})"

    # ------------------------------------------------------------------
    # What is due, and when (CONTRACTS section 5.0)
    # ------------------------------------------------------------------
    def due_market_ids(self, tick: int) -> tuple[str, ...]:
        """Return the still-OPEN markets whose ``resolution_tick < tick``, ascending.

        At tick ``t`` this resolves the markets scheduled for ``t - 1``, because
        a market whose resolution tick is ``r`` is tradable for the whole of
        tick ``r`` and resolves in P1 of tick ``r + 1`` (CONTRACTS section
        5.0). It therefore returns ``()`` at tick 1, and at the virtual tick
        ``ticks_total + 1`` it returns everything left, which is the normal
        finalisation path.

        "Still-OPEN" needs no ``Exchange`` handle and there is none in the
        signature: this class is the only thing that ever closes a market, so
        it knows what it has already resolved or cancelled from its own
        history.

        Args:
            tick: The tick whose P1 is running, or ``ticks_total + 1`` in
                finalisation.

        Returns:
            Market ids in ascending numeric suffix order (section 2.3).
        """
        return tuple(
            market_id
            for market_id in self._market_ids
            if market_id not in self._closed and self._spec(market_id).resolution_tick < tick
        )

    def due_cancellations(self, tick: int) -> tuple[tuple[str, str], ...]:
        """Return the ``(market_id, reason)`` pairs scripted for exactly this tick.

        ``ScenarioSpec.cancellations`` is the only source of a cancellation
        (FR-5.4.5: a market can only be cancelled by the scenario script), and
        a cancellation fires at tick ``c`` and not ``c + 1``: it is a scripted
        intervention, not a maturity.

        Args:
            tick: The tick whose P1 is running.

        Returns:
            Pairs in ascending ``market_id`` order. ``ScenarioSpec`` already
            validates that its cancellations are sorted by ``(tick, market_id)``
            and that no market is cancelled twice, so filtering on the tick
            preserves that order.
        """
        return tuple(
            (market_id, reason)
            for scheduled_tick, market_id, reason in self._world.scenario.cancellations
            if scheduled_tick == tick
        )

    def outcome(self, market_id: str) -> Outcome:
        """Return the outcome the world froze for ``market_id``.

        Args:
            market_id: Market id, ``M1``..``M8``.

        Returns:
            The outcome the oracle publishes at resolution. Agents never see
            it before the ``MarketResolved`` event.

        Raises:
            InvalidConfigError: If the market is not part of the world.
        """
        return self._world.outcome(market_id)

    # ------------------------------------------------------------------
    # P1 step 4 (a, b, c, e) and P1 step 5
    # ------------------------------------------------------------------
    def resolve(
        self,
        *,
        tick: int,
        market_id: str,
        exchange: Exchange,
        accounts: AccountBook,
        journal: Journal,
    ) -> ResolutionReport:
        """Resolve one market: P1 step 4 sub-steps a, b, c and e, in that order.

        Emits ``OrderCancelled`` (through the exchange, which is that event's
        single emitter), then ``MarketResolved``, then one
        ``SettlementApplied`` per settlement line (through
        :func:`pxe.oracle.settlement.settle`). It does **not** emit the
        resolution ``NewsPublished``: that is sub-step d and belongs to the
        runner, which owns the information engine and the single
        ``mm.note_news`` handover of P1 step 5b.

        Args:
            tick: The tick whose P1 is running, that is ``resolution_tick + 1``
                for a scheduled maturity and ``ticks_total + 1`` in
                finalisation. This is the envelope tick of every event emitted
                here; the payload ``resolution_tick`` stays the scheduled one.
            market_id: Market to resolve. Normally one of
                :meth:`due_market_ids`.
            exchange: The book. Its resting orders on this market are cancelled
                with ``CancelReason.MARKET_RESOLVED`` and the market is then
                closed as ``RESOLVED``.
            accounts: The ledger, mutated by the settlement.
            journal: Journal every event is appended to.

        Returns:
            The :class:`ResolutionReport` of this resolution.

        Raises:
            InvalidConfigError: If the market is unknown, if it is already
                closed, or if ``tick`` is not strictly after the market's
                ``resolution_tick`` (a market is tradable for the whole of its
                own resolution tick, so resolving it there would drop its
                Brier term and make it untradable a tick early).
            InvariantViolationError: If the settlement breaches I6 or I9.
        """
        spec = self._require_open(market_id)
        if tick <= spec.resolution_tick:
            raise InvalidConfigError(
                "a market is tradable for the whole of its resolution tick and resolves at r + 1",
                market_id=market_id,
                tick=tick,
                resolution_tick=spec.resolution_tick,
            )
        outcome = self._world.outcome(market_id)
        cancelled_order_ids = exchange.cancel_all(
            tick=tick,
            market_id=market_id,
            reason=CancelReason.MARKET_RESOLVED,
        )
        journal.emit(
            MarketResolved,
            tick=tick,
            market_id=market_id,
            outcome=str(outcome),
            payout_cents=outcome.payout_cents,
            resolution_tick=spec.resolution_tick,
            latent_value_milli=self._world.latent.value_milli(spec.latent_key, spec.resolution_tick),
        )
        settlements = settle(
            tick=tick,
            market_id=market_id,
            outcome=outcome,
            accounts=accounts,
            journal=journal,
            mode=_MODE_RESOLUTION,
        )
        exchange.close_market(tick=tick, market_id=market_id, status=MarketStatus.RESOLVED)
        self._closed[market_id] = MarketStatus.RESOLVED
        return ResolutionReport(
            market_id=market_id,
            outcome=outcome,
            payout_cents=outcome.payout_cents,
            cancelled_order_ids=cancelled_order_ids,
            settlements=settlements,
        )

    def cancel_market(
        self,
        *,
        tick: int,
        market_id: str,
        reason: str,
        exchange: Exchange,
        accounts: AccountBook,
        journal: Journal,
    ) -> ResolutionReport:
        """Cancel one market and unwind every execution on it (FR-5.4.5).

        Same shape as :meth:`resolve`, emitting ``MarketCancelled`` instead of
        ``MarketResolved`` and settling with ``mode="unwind"``: every account
        gets its cost basis back and every taker fee paid on that market is
        refunded out of the ``FEES`` vault (CONTRACTS section 6.4). The runner
        then emits the cancellation ``NewsPublished``, exactly as it does for a
        resolution.

        A cancellation fires at the tick it was scheduled for, so ``tick`` is
        ``c`` and not ``c + 1``.

        Args:
            tick: The tick whose P1 is running, that is the scheduled
                cancellation tick.
            market_id: Market to cancel. Normally one of
                :meth:`due_cancellations`.
            reason: Free form scenario reason, journalled verbatim on
                ``MarketCancelled``.
            exchange: The book. Its resting orders on this market are cancelled
                with ``CancelReason.MARKET_CANCELLED`` and the market is then
                closed as ``CANCELLED``.
            accounts: The ledger, mutated by the unwind.
            journal: Journal every event is appended to.

        Returns:
            The :class:`ResolutionReport` of this cancellation, with
            ``outcome=None`` and ``payout_cents=0``.

        Raises:
            InvalidConfigError: If the market is unknown or already closed.
            InvariantViolationError: If the unwind breaches I6 or I9.
        """
        self._require_open(market_id)
        cancelled_order_ids = exchange.cancel_all(
            tick=tick,
            market_id=market_id,
            reason=CancelReason.MARKET_CANCELLED,
        )
        journal.emit(MarketCancelled, tick=tick, market_id=market_id, reason=reason)
        settlements = settle(
            tick=tick,
            market_id=market_id,
            outcome=None,
            accounts=accounts,
            journal=journal,
            mode=_MODE_UNWIND,
        )
        exchange.close_market(tick=tick, market_id=market_id, status=MarketStatus.CANCELLED)
        self._closed[market_id] = MarketStatus.CANCELLED
        return ResolutionReport(
            market_id=market_id,
            outcome=None,
            payout_cents=0,
            cancelled_order_ids=cancelled_order_ids,
            settlements=settlements,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _spec(self, market_id: str) -> MarketSpec:
        """Return the scenario spec of ``market_id``.

        Args:
            market_id: Market id.

        Returns:
            The :class:`~pxe.types.MarketSpec`.

        Raises:
            InvalidConfigError: If the market is not part of the world.
        """
        return self._world.scenario.market(market_id)

    def _require_open(self, market_id: str) -> MarketSpec:
        """Return the spec of a market this oracle has not closed yet.

        Args:
            market_id: Market id.

        Returns:
            The :class:`~pxe.types.MarketSpec`.

        Raises:
            InvalidConfigError: If the market is unknown or already closed. A
                second resolution of the same market would emit a second
                ``MarketResolved`` and settle an already flattened position,
                so it is refused rather than made idempotent.
        """
        spec = self._spec(market_id)
        closed = self._closed.get(market_id)
        if closed is not None:
            raise InvalidConfigError(
                "market is already closed",
                market_id=market_id,
                status=str(closed),
            )
        return spec
