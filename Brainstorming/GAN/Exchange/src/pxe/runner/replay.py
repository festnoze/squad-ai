"""Rebuild a match from its journal and nothing else (FR-5.1.3, A09).

CONTRACTS section 4.1 states the rule this module implements: **the journal
alone replays a match**. No world generator, no information engine, no agent,
no gateway and no clock. Everything a projection needs is therefore *in* an
event, and this module proves it: if a field were missing, one of the
comparisons in :func:`verify_replay` would fail.

How the rebuild works
---------------------
The journal records two very different kinds of fact and they are treated
differently:

* **Decisions and outcomes are read.** Which order an account placed, which
  order it cancelled, which market resolved and which way, which seat was
  frozen: none of that is derivable, so it is taken verbatim from
  ``OrderPlaced``, ``OrderCancelled``, ``MarketResolved``, ``MarketCancelled``,
  ``AgentFrozen`` and ``PredictionRecorded``.
* **Mechanics are re-derived.** Matching, self trade prevention, IOC residuals,
  collateral, fees and settlement lines are a deterministic function of the
  ledger and the book given those decisions, so they are recomputed by feeding
  the real :class:`~pxe.exchange.exchange.Exchange` and
  :class:`~pxe.exchange.accounts.AccountBook` the recorded order flow. That is
  what makes the replay a *check* of the engine rather than a second
  implementation of it: ``TradeExecuted``, ``STPCancelled``,
  ``SettlementApplied`` and the ``stp``/``ioc_residual`` cancellations are
  deliberately **not** applied, because re-running the submission produces them
  again, and applying both would double count every cent.

The events consumed for their side effects are, exhaustively:

| Event | Effect |
|---|---|
| ``match_started`` | build the config, the scenario, the ledger and the book |
| ``tick_started`` | ``exchange.begin_tick`` |
| ``order_placed`` | ``exchange.submit`` with the recorded intent |
| ``order_cancelled`` (``agent_request``, ``mm_requote``) | ``exchange.cancel`` |
| ``market_resolved`` | ``cancel_all`` + ``apply_settlement`` + ``close_market`` |
| ``market_cancelled`` | ``cancel_all`` + unwind + ``close_market`` |
| ``agent_frozen`` | ``cancel_all`` + ``accounts.freeze`` |
| ``prediction_recorded`` | ``last_prediction_ppm`` |
| ``message_posted`` | the pending message queue |
| ``mark_to_market`` | ``exchange.push_ref_history`` |
| ``match_ended`` | the final tick, which decides what is still pending |

Everything else (``news_published``, ``signal_delivered``,
``observation_built``, ``agent_action_*``, ``agent_timed_out``, ``mm_quoted``,
``trade_executed``, ``stp_cancelled``, ``settlement_applied``,
``position_snapshot``, ``incident_raised``) carries no state a replay has to
apply. Two of those are what :func:`verify_replay` reads back.
"""

from __future__ import annotations

from collections.abc import Sequence

from pxe.errors import ReplayMismatchError
from pxe.events import (
    AgentFrozen,
    Event,
    MarketCancelled,
    MarketResolved,
    MarkToMarket,
    MatchEnded,
    MatchStarted,
    MessagePosted,
    OrderCancelled,
    OrderPlaced,
    PositionSnapshot,
    PredictionRecorded,
    TickStarted,
)
from pxe.exchange.accounts import AccountBook
from pxe.exchange.exchange import Exchange
from pxe.journal import Journal
from pxe.runner.state import MatchState
from pxe.types import (
    CancelReason,
    MarketStatus,
    MatchConfig,
    OrderIntent,
    OrderType,
    Outcome,
    PublicMessage,
    ScenarioSpec,
    Side,
    config_from_journal_dict,
    market_spec_from_dict,
    sorted_ids,
)

__all__ = ["replay_journal", "replay_to_tick", "verify_replay"]

#: The two settlement modes of CONTRACTS section 6.4.
_MODE_RESOLUTION = "resolution"
_MODE_UNWIND = "unwind"

#: Cancellations the exchange re-emits by itself when a submission is replayed
#: (``stp`` and ``ioc_residual``) or that a resolution, a cancellation or a
#: freeze produces through ``cancel_all``. Applying them a second time would
#: release the same collateral twice.
_DERIVED_CANCEL_REASONS: frozenset[str] = frozenset(
    {
        str(CancelReason.STP),
        str(CancelReason.IOC_RESIDUAL),
        str(CancelReason.MARKET_RESOLVED),
        str(CancelReason.MARKET_CANCELLED),
        str(CancelReason.AGENT_FROZEN),
    }
)

#: Cancellations a replay must apply itself, because nothing else produces them.
_EXPLICIT_CANCEL_REASONS: frozenset[str] = frozenset(
    {str(CancelReason.AGENT_REQUEST), str(CancelReason.MM_REQUOTE), str(CancelReason.MATCH_ENDED)}
)


class _Replayer:
    """Applies a journal to a fresh :class:`~pxe.runner.state.MatchState`.

    Private on purpose: the three public functions of this module are the whole
    API (CONTRACTS section 7.12) and this class is how they share one
    implementation instead of three drifting ones.
    """

    def __init__(self, *, verify: bool) -> None:
        """Build an empty replayer.

        Args:
            verify: When True, every ``PositionSnapshot`` and ``MarkToMarket``
                of the journal is compared against the rebuilt state and a
                disagreement raises :class:`~pxe.errors.ReplayMismatchError`.
        """
        self._verify = verify
        self._state: MatchState | None = None
        self._messages: list[PublicMessage] = []
        self._final_tick = 0

    # ------------------------------------------------------------------
    # Driving
    # ------------------------------------------------------------------
    def run(self, events: Sequence[Event]) -> MatchState:
        """Apply every event in ``seq`` order and return the terminal state.

        Args:
            events: The journal, in any order: it is sorted by ``seq`` here so
                a caller that concatenated two reads cannot silently replay
                backwards.

        Returns:
            The rebuilt :class:`~pxe.runner.state.MatchState`.

        Raises:
            ReplayMismatchError: If the journal does not start with
                ``MatchStarted``, or (in verify mode) if the rebuilt state
                disagrees with a snapshot.
        """
        for event in sorted(events, key=lambda item: item.seq):
            self._apply(event)
        state = self._state
        if state is None:
            raise ReplayMismatchError("the journal holds no MatchStarted event")
        state.pending_messages = tuple(message for message in self._messages if message.deliver_tick > self._final_tick)
        return state

    def _apply(self, event: Event) -> None:
        """Dispatch one event to its effect, or ignore it.

        Args:
            event: The event to apply.

        Raises:
            ReplayMismatchError: If an event arrives before ``MatchStarted``,
                or (in verify mode) on a disagreement.
        """
        if isinstance(event, MatchStarted):
            self._begin(event)
            return
        state = self._state
        if state is None:
            raise ReplayMismatchError("the journal does not start with MatchStarted", seq=event.seq)
        self._final_tick = max(self._final_tick, event.tick)
        if isinstance(event, TickStarted):
            state.tick = event.tick
            state.exchange.begin_tick(event.tick)
        elif isinstance(event, OrderPlaced):
            self._place(state, event)
        elif isinstance(event, OrderCancelled):
            self._cancel(state, event)
        elif isinstance(event, MarketResolved):
            self._resolve(state, event)
        elif isinstance(event, MarketCancelled):
            self._unwind(state, event)
        elif isinstance(event, AgentFrozen):
            self._freeze(state, event)
        elif isinstance(event, PredictionRecorded):
            state.last_prediction_ppm[event.agent_id, event.market_id] = event.p_yes_ppm
        elif isinstance(event, MessagePosted):
            self._messages.append(
                PublicMessage(
                    agent_id=event.agent_id,
                    tick=event.tick,
                    text=event.text,
                    deliver_tick=event.deliver_tick,
                )
            )
        elif isinstance(event, MarkToMarket):
            self._mark(state, event)
        elif isinstance(event, PositionSnapshot):
            if self._verify:
                _check_snapshot(state, event)
        elif isinstance(event, MatchEnded):
            state.tick = event.tick
            self._final_tick = event.final_tick

    # ------------------------------------------------------------------
    # Effects
    # ------------------------------------------------------------------
    def _begin(self, event: MatchStarted) -> None:
        """Rebuild the config, the scenario, the ledger and the book.

        The scenario carries ``correlations=()``, ``cancellations=()``,
        ``held_out=False`` and ``notes=""``: those four are world generation
        metadata that no engine decision reads after ``MatchStarted``, so they
        are deliberately not journalled and deliberately not recovered. The
        cancellations that actually happened are in the journal as
        ``MarketCancelled`` events.

        Args:
            event: The first event of the journal.
        """
        config = config_from_journal_dict(event.config)
        scenario = ScenarioSpec(
            template_id=event.scenario_template_id,
            template_version=event.scenario_template_version,
            seed=event.seed,
            ticks_total=event.ticks_total,
            markets=tuple(market_spec_from_dict(row) for row in event.markets),
            talking_mode=config.talking_mode,
            liquidity_profile_name=config.liquidity_profile_name,
        )
        agent_ids = _ranked_agent_ids(event, config)
        accounts = AccountBook(agent_ids=agent_ids, market_ids=[m.market_id for m in scenario.markets], config=config)
        # The replay journal is in memory and thrown away: the exchange is the
        # single emitter of the order and trade events (CONTRACTS section 4.5)
        # and re-emits them while it re-derives the mechanics. Nothing reads it.
        shadow = Journal(event.match_id)
        exchange = Exchange(config=config, scenario=scenario, accounts=accounts, journal=shadow)
        self._state = MatchState(
            config=config,
            scenario=scenario,
            match_id=event.match_id,
            tick=event.tick,
            accounts=accounts,
            exchange=exchange,
        )

    def _place(self, state: MatchState, event: OrderPlaced) -> None:
        """Resubmit one recorded order through the real matching engine.

        Args:
            state: The state being rebuilt.
            event: The ``OrderPlaced`` to replay.
        """
        order_type = OrderType(event.requested_type)
        intent = OrderIntent(
            op="place",
            market_id=event.market_id,
            side=Side(event.side),
            order_type=order_type,
            # A market order's journalled price is the FR-5.4.3 band converted
            # one, which the exchange recomputes from the same book state.
            price=event.price if order_type is OrderType.LIMIT else None,
            qty=event.qty,
        )
        state.exchange.submit(tick=event.tick, agent_id=event.agent_id, intent=intent, item_index=0)

    def _cancel(self, state: MatchState, event: OrderCancelled) -> None:
        """Apply an explicit cancellation, ignore a derived one.

        Args:
            state: The state being rebuilt.
            event: The ``OrderCancelled`` to consider.
        """
        if event.reason in _DERIVED_CANCEL_REASONS:
            return
        if event.reason not in _EXPLICIT_CANCEL_REASONS:
            raise ReplayMismatchError(
                "unknown cancellation reason",
                seq=event.seq,
                reason=event.reason,
            )
        state.exchange.cancel(
            tick=event.tick,
            agent_id=event.agent_id,
            order_id=event.order_id,
            reason=CancelReason(event.reason),
        )

    def _resolve(self, state: MatchState, event: MarketResolved) -> None:
        """Replay one resolution: cancel, settle, close (P1 step 4 a, c, e).

        Args:
            state: The state being rebuilt.
            event: The ``MarketResolved`` to replay.
        """
        outcome = Outcome(event.outcome)
        state.exchange.cancel_all(
            tick=event.tick,
            market_id=event.market_id,
            reason=CancelReason.MARKET_RESOLVED,
        )
        state.accounts.apply_settlement(market_id=event.market_id, outcome=outcome, mode=_MODE_RESOLUTION)
        state.exchange.close_market(tick=event.tick, market_id=event.market_id, status=MarketStatus.RESOLVED)
        state.outcomes[event.market_id] = outcome

    def _unwind(self, state: MatchState, event: MarketCancelled) -> None:
        """Replay one FR-5.4.5 cancellation and its unwind.

        Args:
            state: The state being rebuilt.
            event: The ``MarketCancelled`` to replay.
        """
        state.exchange.cancel_all(
            tick=event.tick,
            market_id=event.market_id,
            reason=CancelReason.MARKET_CANCELLED,
        )
        state.accounts.apply_settlement(market_id=event.market_id, outcome=None, mode=_MODE_UNWIND)
        state.exchange.close_market(tick=event.tick, market_id=event.market_id, status=MarketStatus.CANCELLED)

    def _freeze(self, state: MatchState, event: AgentFrozen) -> None:
        """Replay one bankruptcy freeze (P4 step 14).

        Args:
            state: The state being rebuilt.
            event: The ``AgentFrozen`` to replay.
        """
        state.exchange.cancel_all(tick=event.tick, agent_id=event.agent_id, reason=CancelReason.AGENT_FROZEN)
        state.accounts.freeze(event.agent_id)
        state.frozen_agent_ids = state.frozen_agent_ids | {event.agent_id}

    def _mark(self, state: MatchState, event: MarkToMarket) -> None:
        """Compare the public price state, then push the reference price.

        Args:
            state: The state being rebuilt.
            event: The ``MarkToMarket`` to replay.

        Raises:
            ReplayMismatchError: In verify mode, on any disagreement.
        """
        if self._verify:
            _check_mark(state, event)
        state.exchange.push_ref_history(event.market_id, event.ref_price)


def _ranked_agent_ids(event: MatchStarted, config: MatchConfig) -> tuple[str, ...]:
    """Return the ranked seats of a match, from ``MatchStarted.agents``.

    Args:
        event: The first event of the journal.
        config: The rebuilt configuration, used only for the error context.

    Returns:
        The ranked seat ids, ascending.

    Raises:
        ReplayMismatchError: If the event names no ranked seat, which would
            leave the ledger with nothing to fund.
    """
    ids = [str(row["agent_id"]) for row in event.agents if bool(row.get("ranked", True))]
    if not ids:
        raise ReplayMismatchError(
            "MatchStarted names no ranked seat",
            match_id=event.match_id,
            n_agents=config.n_agents,
        )
    return sorted_ids(ids)


def _check_snapshot(state: MatchState, event: PositionSnapshot) -> None:
    """Compare the rebuilt ledger against one ``PositionSnapshot``.

    Args:
        state: The rebuilt state.
        event: The journalled snapshot.

    Raises:
        ReplayMismatchError: On the first field that disagrees.
    """
    accounts = state.accounts
    account_id = event.account_id
    ref_prices = state.ref_prices()
    observed: tuple[tuple[str, int | bool], ...] = (
        ("cash_cents", accounts.cash_cents(account_id)),
        ("reserved_cents", accounts.reserved_cents(account_id)),
        ("free_cash_cents", accounts.free_cash_cents(account_id)),
        ("equity_cents", accounts.equity_cents(account_id, ref_prices)),
        ("frozen", accounts.is_frozen(account_id)),
        ("resting_order_count", accounts.resting_order_count(account_id)),
    )
    expected: dict[str, int | bool] = {
        "cash_cents": event.cash_cents,
        "reserved_cents": event.reserved_cents,
        "free_cash_cents": event.free_cash_cents,
        "equity_cents": event.equity_cents,
        "frozen": event.frozen,
        "resting_order_count": event.resting_order_count,
    }
    for name, value in observed:
        if value != expected[name]:
            raise ReplayMismatchError(
                "replayed account state disagrees with the journal",
                seq=event.seq,
                account_id=account_id,
                field=name,
                journalled=expected[name],
                replayed=value,
            )
    for row in event.positions:
        market_id = str(row["market_id"])
        position = accounts.position(account_id, market_id)
        if position.qty != int(row["qty"]) or position.cost_basis_cents != int(row["cost_basis_cents"]):
            raise ReplayMismatchError(
                "replayed position disagrees with the journal",
                seq=event.seq,
                account_id=account_id,
                market_id=market_id,
                journalled_qty=int(row["qty"]),
                replayed_qty=position.qty,
            )


def _check_mark(state: MatchState, event: MarkToMarket) -> None:
    """Compare the rebuilt book against one ``MarkToMarket``.

    Args:
        state: The rebuilt state.
        event: The journalled mark.

    Raises:
        ReplayMismatchError: On the first field that disagrees.
    """
    exchange = state.exchange
    ref_price, ref_source = exchange.reference_price(event.market_id)
    book = exchange.book(event.market_id)
    observed: tuple[tuple[str, int | str | None], ...] = (
        ("ref_price", ref_price),
        ("ref_source", ref_source),
        ("best_bid", book.best_bid()),
        ("best_ask", book.best_ask()),
        ("mid_price", book.mid_price()),
        ("last_price", book.last_price()),
        ("bid_depth_qty", book.total_qty(Side.BUY)),
        ("ask_depth_qty", book.total_qty(Side.SELL)),
        ("tick_volume_qty", exchange.tick_volume(event.market_id)),
    )
    expected: dict[str, int | str | None] = {
        "ref_price": event.ref_price,
        "ref_source": event.ref_source,
        "best_bid": event.best_bid,
        "best_ask": event.best_ask,
        "mid_price": event.mid_price,
        "last_price": event.last_price,
        "bid_depth_qty": event.bid_depth_qty,
        "ask_depth_qty": event.ask_depth_qty,
        "tick_volume_qty": event.tick_volume_qty,
    }
    for name, value in observed:
        if value != expected[name]:
            raise ReplayMismatchError(
                "replayed market state disagrees with the journal",
                seq=event.seq,
                market_id=event.market_id,
                field=name,
                journalled=expected[name],
                replayed=value,
            )


def replay_journal(events: Sequence[Event]) -> MatchState:
    """FR-5.1.3: rebuild the terminal state from the journal alone.

    Args:
        events: Every event of one match, ``MatchStarted`` first and
            ``MatchEnded`` last.

    Returns:
        The terminal :class:`~pxe.runner.state.MatchState`.

    Raises:
        ReplayMismatchError: If the journal does not start with
            ``MatchStarted``, or holds a cancellation reason no replay can
            interpret.
    """
    return _Replayer(verify=False).run(events)


def replay_to_tick(events: Sequence[Event], tick: int) -> MatchState:
    """Rebuild the state as it was at the end of ``tick``.

    Every event whose envelope tick is at most ``tick`` is applied, which cuts
    on a phase boundary because a tick's events are contiguous (CONTRACTS
    section 4.4). ``tick = 0`` therefore yields the state right after
    ``MatchStarted``, and ``tick >= ticks_total + 1`` is exactly
    :func:`replay_journal`.

    Args:
        events: Every event of one match.
        tick: The last tick to apply, ``>= 0``.

    Returns:
        The :class:`~pxe.runner.state.MatchState` at the end of that tick.

    Raises:
        ReplayMismatchError: If the journal does not start with
            ``MatchStarted``.
    """
    return _Replayer(verify=False).run([event for event in events if event.tick <= tick])


def verify_replay(events: Sequence[Event]) -> None:
    """Replay the journal and check it against its own snapshots.

    Every ``PositionSnapshot`` is compared field by field against the rebuilt
    ledger and every ``MarkToMarket`` against the rebuilt book, at the exact
    point of the journal where it was emitted. Scenario metadata is never
    compared: ``correlations``, ``cancellations``, ``held_out`` and ``notes``
    are deliberately not journalled (CONTRACTS section 7.12).

    Args:
        events: Every event of one match.

    Raises:
        ReplayMismatchError: If the replayed state disagrees with the
            ``PositionSnapshot`` and ``MarkToMarket`` events in the journal.
    """
    _Replayer(verify=True).run(events)
