"""Compact, faithful observation rendering for one agent at one tick (A10).

This module is the single producer of the payload an agent sees (PRD section
6.1, CONTRACTS section 7.13 and 8.1). Three properties are contractual and each
one is pinned by a named test in ``tests/test_observation_builder.py``:

* **Faithful.** The observation carries 100 % of the agent's resting orders and
  100 % of its non flat positions on every open market (T2.4). Compaction is
  allowed on depth (three aggregated levels), on ``ref_history`` length and on
  text lengths, and on nothing else.
* **Compact.** Under 2000 estimated tokens at the median tick (T2.4), measured
  with the documented rule of :func:`estimate_tokens`.
* **Outside the journal.** ``obs_hash`` and ``obs_bytes`` are written to
  ``runs/<match_id>/observations.jsonl`` only (CONTRACTS section 3.5 and
  decision 11), so recompacting an observation cannot move a golden journal
  hash.

Which markets appear is CONTRACTS section 5.0 and nothing else: the runner
resolves the markets due at this tick (P1 step 4) *before* it builds the
observations (P1 step 6), so ``MatchState.open_market_ids()`` is exactly the
set an agent may trade this tick. A market whose ``resolution_tick`` is ``r``
is therefore present at tick ``r`` and gone from tick ``r + 1``, where its
outcome arrives as a news item instead. The ``markets`` array may legally be
empty (FR-5.2.3), which ``schemas/observation.v1.json`` allows on purpose.

Nothing here reads a clock, a socket, ``sys.argv`` or an environment variable,
and nothing here draws a random number: an observation is a pure projection of
``(config, state, news, signals, messages)``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from pxe.errors import InvalidConfigError, ObservationValidationError
from pxe.events import JOURNAL_ENCODING, JOURNAL_NEWLINE, payload_hash, stable_json
from pxe.runner.schema_registry import validator_for
from pxe.types import (
    DEFAULT_PREDICTION_PPM,
    DEPTH_LEVELS,
    MAX_PREDICTIONS_PER_ACTION,
    PRICE_MAX,
    PRICE_MIN,
    MarketObservation,
    MarketSpec,
    MarketStatus,
    MatchConfig,
    NewsItem,
    Observation,
    ObservationLimits,
    Order,
    PublicMessage,
    Signal,
    prob_from_ppm,
    sorted_ids,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import cycle
    from pathlib import Path

    # A09 owns pxe/runner/state.py. The ignore keeps this module type checkable
    # while that file is still being written, and ``unused-ignore`` keeps it
    # correct the moment it lands (CONTRACTS section 1: submodules import by
    # full path, never through the shared runner/__init__.py).
    from pxe.runner.state import MatchState  # type: ignore[import-not-found, unused-ignore]

__all__ = [
    # schema mirrors and the counting rule
    "BODY_MAX_CHARS",
    "HEADLINE_MAX_CHARS",
    "MESSAGES_MAX_ITEMS",
    "NEWS_MAX_ITEMS",
    "OBSERVATION_SCHEMA_NAME",
    "QUESTION_MAX_CHARS",
    "SIGNALS_MAX_ITEMS",
    "TOKEN_BUDGET",
    "TOKEN_CHARS_PER_TOKEN",
    # public API (CONTRACTS section 7.13)
    "build_observation",
    "estimate_tokens",
    "observation_bytes",
    "observation_hash",
    "observation_to_json",
    "validate_observation",
    "write_observation",
]

#: Name under which ``schemas/observation.v1.json`` is registered (A11).
OBSERVATION_SCHEMA_NAME = "observation.v1"

#: ``news.maxItems`` of the observation schema.
NEWS_MAX_ITEMS: int = 20
#: ``signals.maxItems`` of the observation schema. One per market at most, so it
#: is the same ceiling as ``MAX_PREDICTIONS_PER_ACTION``.
SIGNALS_MAX_ITEMS: int = MAX_PREDICTIONS_PER_ACTION
#: ``messages.maxItems`` of the observation schema.
MESSAGES_MAX_ITEMS: int = 8
#: ``news.items.headline.maxLength`` of the observation schema.
HEADLINE_MAX_CHARS: int = 120
#: ``news.items.body.maxLength`` of the observation schema.
BODY_MAX_CHARS: int = 400
#: ``marketBlock.question.maxLength`` of the observation schema.
QUESTION_MAX_CHARS: int = 200

#: Characters per token of the documented counting rule (see
#: :func:`estimate_tokens`).
TOKEN_CHARS_PER_TOKEN: float = 3.6
#: The T2.4 budget, in estimated tokens, at the median tick.
TOKEN_BUDGET: int = 2000


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------
def build_observation(
    *,
    config: MatchConfig,
    state: MatchState,
    agent_id: str,
    tick: int,
    news: Sequence[NewsItem],
    signals: Sequence[Signal],
    messages: Sequence[PublicMessage],
) -> Observation:
    """Render the payload one agent receives at one tick (P1 step 6).

    The market blocks are built over ``state.open_market_ids()`` in canonical
    order, which by CONTRACTS section 5.0 is exactly the set tradable in P3 of
    this tick: the resolutions due at ``tick`` already ran at P1 step 4.

    Fidelity (T2.4) is a hard requirement and is not subject to any compaction
    lever: every resting order of ``agent_id`` and every position it holds on
    an open market appears, whatever the size of the payload.

    Args:
        config: The authoritative :class:`~pxe.types.MatchConfig` of the match.
            Its limits are echoed into the payload so the agent can self police.
        state: Live match state. Read only: this function mutates nothing.
        agent_id: Recipient seat, ``A1``..``A8``.
        tick: Current tick, ``>= 1``.
        news: Public news published at this tick, in publication order. Items
            about a market that has just resolved are kept on purpose: that is
            the channel through which an outcome is announced (P1 step 4d).
        signals: Private signals of this tick. Entries addressed to another
            agent, and entries about a market that is not tradable this tick,
            are dropped so the payload never holds a dangling ``market_id``
            (CONTRACTS section 5.0, P1 step 3).
        messages: Public messages due at this tick, that is the ones posted at
            ``tick - 1`` and therefore carrying ``deliver_tick == tick``. An
            item whose ``deliver_tick`` is still ahead is never shown, which is
            what stops a message posted this tick from reaching anybody before
            the next one. The recipient's own message is not echoed back
            (FR-5.6.1 delivers a message to the *other* agents), and nothing is
            delivered at all when talking mode is off.

    Returns:
        The :class:`~pxe.types.Observation`.

    Raises:
        InvalidConfigError: If an open market is absent from the scenario, which
            is an engine bug and never an agent behaviour.
    """
    specs: dict[str, MarketSpec] = {spec.market_id: spec for spec in state.scenario.markets}
    open_ids = sorted_ids(state.open_market_ids())
    resting = _resting_orders_by_market(state, agent_id)

    markets = tuple(
        _market_block(
            config=config,
            state=state,
            agent_id=agent_id,
            spec=_require_spec(specs, market_id),
            my_orders=resting.get(market_id, ()),
        )
        for market_id in open_ids
    )
    return Observation(
        obs_version=config.obs_version,
        match_id=state.match_id,
        tick=tick,
        ticks_total=config.ticks_total,
        agent_id=agent_id,
        cash_cents=state.accounts.cash_cents(agent_id),
        reserved_cents=state.accounts.reserved_cents(agent_id),
        free_cash_cents=state.accounts.free_cash_cents(agent_id),
        equity_cents=state.accounts.equity_cents(agent_id, state.ref_prices()),
        news=tuple(news)[:NEWS_MAX_ITEMS],
        signals=_visible_signals(signals, agent_id=agent_id, open_ids=open_ids),
        markets=markets,
        messages=_delivered_messages(messages, config=config, agent_id=agent_id, tick=tick),
        limits=ObservationLimits(
            max_active_orders_per_market=config.max_active_orders_per_market,
            price_min=PRICE_MIN,
            price_max=PRICE_MAX,
            market_band_cents=config.market_band_cents,
            taker_fee_bps=config.taker_fee_bps,
            message_max_chars=config.message_max_chars,
            max_orders_per_action=config.max_orders_per_action,
        ),
    )


def _require_spec(specs: Mapping[str, MarketSpec], market_id: str) -> MarketSpec:
    """Return the static spec of an open market.

    Args:
        specs: Scenario markets keyed by id.
        market_id: Market to look up.

    Returns:
        The :class:`~pxe.types.MarketSpec`.

    Raises:
        InvalidConfigError: If the market is not part of the scenario.
    """
    spec = specs.get(market_id)
    if spec is None:
        raise InvalidConfigError("open market is absent from the scenario", market_id=market_id)
    return spec


def _resting_orders_by_market(state: MatchState, agent_id: str) -> dict[str, tuple[Order, ...]]:
    """Group one agent's resting orders by market.

    ``Exchange.book_view()`` is a ``Mapping``, so section 2.3 applies: it is
    iterated through :func:`~pxe.types.sorted_ids` and never through
    ``.items()``. Inside a market the book's own ``priority_key`` order is
    replaced by ``order_id`` order, which is what
    :class:`~pxe.types.MarketObservation` documents and what makes the payload
    independent of how the book happens to be laid out.

    Args:
        state: Live match state.
        agent_id: Owner of the orders.

    Returns:
        A mapping from market id to that agent's resting orders, ascending by
        ``order_id``. Markets holding none of its orders are absent.
    """
    view = state.exchange.book_view()
    grouped: dict[str, tuple[Order, ...]] = {}
    for market_id in sorted_ids(tuple(view.keys())):
        mine = tuple(order for order in view[market_id] if order.agent_id == agent_id and order.status.is_resting)
        if mine:
            grouped[market_id] = tuple(sorted(mine, key=lambda order: order.order_id))
    return grouped


def _market_block(
    *,
    config: MatchConfig,
    state: MatchState,
    agent_id: str,
    spec: MarketSpec,
    my_orders: tuple[Order, ...],
) -> MarketObservation:
    """Render one market block.

    Args:
        config: The match configuration.
        state: Live match state.
        agent_id: Recipient seat.
        spec: Static definition of the market.
        my_orders: The agent's resting orders on it, ascending by ``order_id``.

    Returns:
        The :class:`~pxe.types.MarketObservation`.
    """
    market_id = spec.market_id
    snapshot = state.exchange.snapshot(market_id)
    position = state.accounts.position(agent_id, market_id)
    history = state.exchange.ref_history(market_id)
    keep = config.ref_history_len
    return MarketObservation(
        market_id=market_id,
        question=_clip(spec.question, QUESTION_MAX_CHARS),
        status=MarketStatus.OPEN,
        prior_price=spec.prior_price,
        resolution_tick=spec.resolution_tick,
        ref_price=snapshot.ref_price,
        mid_price=snapshot.mid_price,
        best_bid=snapshot.best_bid,
        best_ask=snapshot.best_ask,
        bid_depth=tuple((level.price, level.qty) for level in snapshot.bids[:DEPTH_LEVELS]),
        ask_depth=tuple((level.price, level.qty) for level in snapshot.asks[:DEPTH_LEVELS]),
        last_price=snapshot.last_price,
        ref_history=tuple(history[-keep:]) if keep > 0 else (),
        position_qty=position.qty,
        cost_basis_cents=position.cost_basis_cents,
        my_orders=my_orders,
        my_last_prediction_ppm=state.last_prediction_ppm.get((agent_id, market_id), DEFAULT_PREDICTION_PPM),
    )


def _visible_signals(signals: Sequence[Signal], *, agent_id: str, open_ids: Sequence[str]) -> tuple[Signal, ...]:
    """Keep the signals this agent may act on, in delivery order.

    Args:
        signals: Signals handed by the runner.
        agent_id: Recipient seat.
        open_ids: Markets tradable this tick.

    Returns:
        At most :data:`SIGNALS_MAX_ITEMS` signals.
    """
    tradable = frozenset(open_ids)
    kept = [s for s in signals if s.agent_id == agent_id and s.market_id in tradable]
    return tuple(kept[:SIGNALS_MAX_ITEMS])


def _delivered_messages(
    messages: Sequence[PublicMessage],
    *,
    config: MatchConfig,
    agent_id: str,
    tick: int,
) -> tuple[PublicMessage, ...]:
    """Keep the public messages delivered to this agent at this tick.

    Args:
        messages: Messages handed by the runner.
        config: The match configuration, read for ``talking_mode`` and
            ``message_max_chars``.
        agent_id: Recipient seat, whose own message is never echoed back.
        tick: Current tick. A message posted at ``t`` carries
            ``deliver_tick == t + 1`` (FR-5.6.1), so the ones due now are those
            with ``deliver_tick <= tick``. The bound is inclusive and not an
            equality on purpose: it is exactly the predicate the runner uses to
            drain ``MatchState.pending_messages`` (P1 step 6), so no message can
            be popped from the queue by one and dropped by the other.

    Returns:
        At most :data:`MESSAGES_MAX_ITEMS` messages, ascending by ``agent_id``.
    """
    if not config.talking_mode:
        return ()
    kept = [m for m in messages if m.agent_id != agent_id and m.deliver_tick <= tick]
    kept.sort(key=lambda m: sorted_ids((m.agent_id,)))
    return tuple(
        PublicMessage(
            agent_id=m.agent_id,
            tick=m.tick,
            text=_clip(m.text, config.message_max_chars),
            deliver_tick=m.deliver_tick,
        )
        for m in kept[:MESSAGES_MAX_ITEMS]
    )


def _clip(text: str, max_chars: int) -> str:
    """Truncate text to a character ceiling.

    Args:
        text: Source text.
        max_chars: Maximum number of characters kept.

    Returns:
        ``text`` unchanged when short enough, truncated otherwise.
    """
    return text if len(text) <= max_chars else text[:max_chars]


# --------------------------------------------------------------------------
# Encoding
# --------------------------------------------------------------------------
def observation_to_json(obs: Observation) -> dict[str, Any]:
    """Encode an observation exactly as ``schemas/observation.v1.json``.

    Args:
        obs: The observation to encode.

    Returns:
        A JSON friendly dict holding only ``dict``, ``list``, ``str``, ``int``,
        ``float``, ``bool`` and ``None``. The three floats it may contain
        (``value``, ``precision``, ``my_last_prediction``) are exact quotients
        of an integer by a power of ten, so :func:`~pxe.events.stable_json`
        renders them identically on every platform.
    """
    return {
        "obs_version": obs.obs_version,
        "match_id": obs.match_id,
        "tick": obs.tick,
        "ticks_total": obs.ticks_total,
        "agent_id": obs.agent_id,
        "cash_cents": obs.cash_cents,
        "reserved_cents": obs.reserved_cents,
        "free_cash_cents": obs.free_cash_cents,
        "equity_cents": obs.equity_cents,
        "news": [_news_to_json(item) for item in obs.news],
        "signals": [_signal_to_json(signal) for signal in obs.signals],
        "markets": [_market_to_json(market) for market in obs.markets],
        "messages": [{"agent_id": m.agent_id, "text": m.text} for m in obs.messages],
        "limits": {
            "max_active_orders_per_market": obs.limits.max_active_orders_per_market,
            "price_min": obs.limits.price_min,
            "price_max": obs.limits.price_max,
            "market_band_cents": obs.limits.market_band_cents,
            "taker_fee_bps": obs.limits.taker_fee_bps,
            "message_max_chars": obs.limits.message_max_chars,
            "max_orders_per_action": obs.limits.max_orders_per_action,
        },
    }


def _news_to_json(item: NewsItem) -> dict[str, Any]:
    """Encode one news item.

    ``is_noise`` is deliberately absent: it is a generation fact, and telling an
    agent which item carries no information would hand it the answer key.

    Args:
        item: The news item.

    Returns:
        A JSON friendly dict.
    """
    return {
        "news_id": item.news_id,
        "market_ids": list(item.market_ids),
        "headline": _clip(item.headline, HEADLINE_MAX_CHARS),
        "body": _clip(item.body, BODY_MAX_CHARS),
        "impact": item.impact.value,
    }


def _signal_to_json(signal: Signal) -> dict[str, Any]:
    """Encode one private signal.

    Args:
        signal: The signal.

    Returns:
        A JSON friendly dict carrying the float form of the stored integers.
    """
    return {
        "signal_id": signal.signal_id,
        "market_id": signal.market_id,
        "kind": signal.kind.value,
        "value": signal.value,
        "precision": signal.precision,
    }


def _market_to_json(market: MarketObservation) -> dict[str, Any]:
    """Encode one market block.

    Args:
        market: The market block.

    Returns:
        A JSON friendly dict.
    """
    return {
        "market_id": market.market_id,
        "question": market.question,
        "status": market.status.value,
        "prior_price": market.prior_price,
        "resolution_tick": market.resolution_tick,
        "ref_price": market.ref_price,
        "mid_price": market.mid_price,
        "best_bid": market.best_bid,
        "best_ask": market.best_ask,
        "bid_depth": [[price, qty] for price, qty in market.bid_depth],
        "ask_depth": [[price, qty] for price, qty in market.ask_depth],
        "last_price": market.last_price,
        "ref_history": list(market.ref_history),
        "position_qty": market.position_qty,
        "cost_basis_cents": market.cost_basis_cents,
        "my_orders": [
            {
                "order_id": order.order_id,
                "side": order.side.value,
                "price": order.price,
                "qty_remaining": order.remaining_qty,
            }
            for order in market.my_orders
        ],
        "my_last_prediction": prob_from_ppm(market.my_last_prediction_ppm),
    }


# --------------------------------------------------------------------------
# Digest, size and budget
# --------------------------------------------------------------------------
def observation_hash(obs: Observation) -> str:
    """Digest of the rendered payload.

    Args:
        obs: The observation.

    Returns:
        The 64 character blake2b-256 hex digest of
        ``stable_json(observation_to_json(obs))``. It is written to
        ``observations.jsonl`` and is never journalled (decision 11).
    """
    return payload_hash(observation_to_json(obs))


def observation_bytes(obs: Observation) -> int:
    """Size of the rendered payload.

    Args:
        obs: The observation.

    Returns:
        The number of UTF-8 bytes of ``stable_json(observation_to_json(obs))``,
        that is the exact length of the ``payload`` as it is hashed and stored.
    """
    return len(stable_json(observation_to_json(obs)).encode(JOURNAL_ENCODING))


def estimate_tokens(payload: Mapping[str, Any]) -> int:
    """Estimate the token cost of a payload with the T2.4 counting rule.

    The rule is stated once, here, and is deliberately provider independent so
    the budget test cannot move when a tokeniser is updated:
    ``ceil(len(stable_json(payload)) / 3.6)``, counting **characters** of the
    stable JSON form and not bytes (a non ASCII character is one character and
    one character's worth of text, while UTF-8 would count it two or three
    times). The 3.6 divisor is the usual characters per token ratio of a JSON
    payload dense in short keys, digits and punctuation, and it is conservative
    for the kind of English prose an observation carries.

    Args:
        payload: Any JSON friendly mapping, typically
            :func:`observation_to_json` output.

    Returns:
        The estimated number of tokens, rounded up.
    """
    return math.ceil(len(stable_json(payload)) / TOKEN_CHARS_PER_TOKEN)


# --------------------------------------------------------------------------
# Validation and the observations.jsonl artefact
# --------------------------------------------------------------------------
def validate_observation(payload: Mapping[str, Any]) -> None:
    """Check a rendered payload against ``schemas/observation.v1.json``.

    A failure is an **engine bug**, never an agent behaviour: the observation is
    produced by this module alone (CONTRACTS section 2.4). Errors are ordered by
    their path so two runs report the same first breach.

    Args:
        payload: The rendered payload, typically :func:`observation_to_json`
            output.

    Raises:
        ObservationValidationError: If the payload violates the schema.
    """
    validator = validator_for(OBSERVATION_SCHEMA_NAME)
    errors = sorted(
        validator.iter_errors(dict(payload)), key=lambda err: (list(map(str, err.absolute_path)), err.message)
    )
    if errors:
        first = errors[0]
        raise ObservationValidationError(
            "observation does not match its schema",
            path="/".join(str(part) for part in first.absolute_path),
            detail=first.message,
        )


def write_observation(path: Path, obs: Observation) -> None:
    """Append one observation to ``runs/<match_id>/observations.jsonl``.

    This is the one writer of that artefact (CONTRACTS section 4.6). The line
    holds the five contracted keys ``agent_id``, ``tick``, ``obs_hash``,
    ``obs_bytes`` and ``payload``; :func:`~pxe.events.stable_json` sorts object
    keys, so no writer chooses a key order. The file is outside the journal
    hash (section 3.5), which is what lets this module recompact an observation
    without moving a golden fixture.

    Args:
        path: Target file. Its parent directory is created when missing.
        obs: The observation to record.
    """
    payload = observation_to_json(obs)
    line = stable_json(
        {
            "agent_id": obs.agent_id,
            "tick": obs.tick,
            "obs_hash": payload_hash(payload),
            "obs_bytes": len(stable_json(payload).encode(JOURNAL_ENCODING)),
            "payload": payload,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        handle.write(line + JOURNAL_NEWLINE)
