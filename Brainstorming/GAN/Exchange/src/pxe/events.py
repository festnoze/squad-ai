r"""Event sourcing taxonomy for Prediction Exchange (pxe).

The append only event journal is the single source of truth of a match
(FR-5.1.3). Every state and every metric in the product is a projection that
can be recomputed from the journal alone.

Hard rules
----------
1. **No floats in the journal, ever.** Probabilities are ``*_ppm`` integers,
   real valued latent quantities are ``*_milli`` integers, money is
   ``*_cents`` integers. :func:`canonical_json` raises
   :class:`~pxe.errors.NonCanonicalValueError` on any float, so a violation
   fails loudly instead of silently breaking AC-P1.
2. **Nothing measured from the wall clock or from a provider goes into the
   journal.** Latencies, token counts, dollar costs and retry counts live in
   ``runs/<match_id>/llm_trace.jsonl``, which is explicitly *not* part of the
   journal hash.
3. **Ordering is total.** ``seq`` starts at 1 and increases by exactly 1. Within
   a tick, events appear in phase order P1, P2, P3, P4 and, inside a phase, in
   the deterministic order specified in ``docs/CONTRACTS.md``.
4. **Append only.** No event is ever rewritten. A correction is a new event.

Serialisation
-------------
One event per line, ``canonical_json(event.to_dict()) + "\\n"``, UTF-8, no BOM,
LF line endings. Consequently the blake2b-256 digest of the journal file bytes
equals :func:`journal_hash` over the event list. That digest is the artefact
compared by AC-P1.

**Every writer of a journal file must open it with**
``open(path, mode, encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE)``.
The default text mode of :func:`open` translates ``"\\n"`` into ``"\\r\\n"`` on
Windows, which is the primary development platform here; the file bytes would
then no longer match :func:`journal_hash` and AC-P1 would fail between two
machines while every in-process test still passed. The two constants below
exist so that requirement is code, not prose.
"""

import dataclasses
import hashlib
import json
import math
import types as _pytypes
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from enum import StrEnum
from typing import Any, ClassVar, Union, get_args, get_origin

from pxe.errors import NonCanonicalValueError

__all__ = [
    "EventType",
    "Event",
    "MatchStarted",
    "TickStarted",
    "NewsPublished",
    "SignalDelivered",
    "MarketResolved",
    "MarketCancelled",
    "SettlementApplied",
    "ObservationBuilt",
    "AgentActionReceived",
    "AgentActionRejected",
    "AgentTimedOut",
    "MMQuoted",
    "OrderPlaced",
    "OrderRejected",
    "OrderCancelled",
    "TradeExecuted",
    "STPCancelled",
    "PositionSnapshot",
    "MarkToMarket",
    "PredictionRecorded",
    "MessagePosted",
    "AgentFrozen",
    "IncidentRaised",
    "MatchEnded",
    "EVENT_CLASSES",
    "canonical_json",
    "stable_json",
    "event_from_dict",
    "event_to_line",
    "event_from_line",
    "journal_hash",
    "journal_hash_from_lines",
    "payload_hash",
    "JOURNAL_ENCODING",
    "JOURNAL_NEWLINE",
]

_JSON_SEPARATORS = (",", ":")
_HASH_DIGEST_SIZE = 32

#: Encoding every journal file is opened with. UTF-8 without a BOM.
JOURNAL_ENCODING: str = "utf-8"
#: Newline every journal file is opened with. Passing this to ``open`` disables
#: the platform translation of ``"\n"``, so a journal written on Windows is byte
#: identical to one written on Linux (section 4.2).
JOURNAL_NEWLINE: str = "\n"


class EventType(StrEnum):
    """Stable event type discriminator written as the ``type`` field."""

    MATCH_STARTED = "match_started"
    TICK_STARTED = "tick_started"
    NEWS_PUBLISHED = "news_published"
    SIGNAL_DELIVERED = "signal_delivered"
    MARKET_RESOLVED = "market_resolved"
    MARKET_CANCELLED = "market_cancelled"
    SETTLEMENT_APPLIED = "settlement_applied"
    OBSERVATION_BUILT = "observation_built"
    AGENT_ACTION_RECEIVED = "agent_action_received"
    AGENT_ACTION_REJECTED = "agent_action_rejected"
    AGENT_TIMED_OUT = "agent_timed_out"
    MM_QUOTED = "mm_quoted"
    ORDER_PLACED = "order_placed"
    ORDER_REJECTED = "order_rejected"
    ORDER_CANCELLED = "order_cancelled"
    TRADE_EXECUTED = "trade_executed"
    STP_CANCELLED = "stp_cancelled"
    POSITION_SNAPSHOT = "position_snapshot"
    MARK_TO_MARKET = "mark_to_market"
    PREDICTION_RECORDED = "prediction_recorded"
    MESSAGE_POSTED = "message_posted"
    AGENT_FROZEN = "agent_frozen"
    INCIDENT_RAISED = "incident_raised"
    MATCH_ENDED = "match_ended"


# --------------------------------------------------------------------------
# Canonical serialisation
# --------------------------------------------------------------------------
def _encode(value: Any, path: str) -> Any:
    """Recursively convert ``value`` into a canonical JSON friendly object.

    Args:
        value: Any value found inside an event payload.
        path: Dotted path used in error messages.

    Returns:
        A structure made only of ``dict``, ``list``, ``str``, ``int``, ``bool``
        and ``None``.

    Raises:
        NonCanonicalValueError: On floats, sets, or any unsupported type.
    """
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, StrEnum):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, float):
        raise NonCanonicalValueError(
            "floats are forbidden in the journal, use a *_ppm, *_milli or *_cents integer",
            path=path,
            value=repr(value),
        )
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key in sorted(value.keys()):
            if not isinstance(key, str):
                raise NonCanonicalValueError("journal object keys must be strings", path=path, key=repr(key))
            out[key] = _encode(value[key], f"{path}.{key}")
        return out
    if isinstance(value, (list, tuple)):
        return [_encode(item, f"{path}[{i}]") for i, item in enumerate(value)]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _encode(dataclasses.asdict(value), path)
    if isinstance(value, (set, frozenset)):
        raise NonCanonicalValueError("sets have no stable order, use a sorted tuple", path=path)
    raise NonCanonicalValueError("unsupported type in journal payload", path=path, type=type(value).__name__)


def canonical_json(payload: Any) -> str:
    """Serialise a payload to the one and only canonical JSON form.

    The form is: keys sorted lexicographically by code point, no whitespace,
    ``ensure_ascii=False`` so UTF-8 text stays readable, and no floats at all.

    Args:
        payload: A dict, list or scalar. Dataclasses are converted.

    Returns:
        The canonical JSON string.

    Raises:
        NonCanonicalValueError: If the payload contains a float, a set or an
            unsupported type.
    """
    return json.dumps(
        _encode(payload, "$"),
        sort_keys=True,
        separators=_JSON_SEPARATORS,
        ensure_ascii=False,
        allow_nan=False,
    )


def _encode_stable(value: Any, path: str) -> Any:
    """Like :func:`_encode` but tolerates finite floats, rounded to 6 decimals.

    The rounding goes through an integer, not through the builtin ``round``,
    which is banker's rounding and is banned by section 2.1. The result is an
    exact quotient of an integer by ``10**6``, so its shortest ``repr`` is the
    same on every conforming platform.
    """
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise NonCanonicalValueError("non finite float", path=path, value=repr(value))
        return math.floor(value * 1_000_000 + 0.5) / 1_000_000
    if isinstance(value, Mapping):
        return {key: _encode_stable(value[key], f"{path}.{key}") for key in sorted(value.keys())}
    if isinstance(value, (list, tuple)):
        return [_encode_stable(item, f"{path}[{i}]") for i, item in enumerate(value)]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _encode_stable(dataclasses.asdict(value), path)
    return _encode(value, path)


def stable_json(payload: Any) -> str:
    """Serialise an **agent facing** payload deterministically.

    Unlike :func:`canonical_json` this accepts finite floats and rounds them to
    6 decimals, because observations and actions cross the LLM boundary where
    probabilities are naturally floats. It is used for observation hashing and
    for prompt building; it is **never** used to write the journal.

    Args:
        payload: Any JSON friendly structure.

    Returns:
        The stable JSON string.

    Raises:
        NonCanonicalValueError: On non finite floats, sets, or unsupported types.
    """
    return json.dumps(
        _encode_stable(payload, "$"),
        sort_keys=True,
        separators=_JSON_SEPARATORS,
        ensure_ascii=False,
        allow_nan=False,
    )


def payload_hash(payload: Any) -> str:
    """Return the blake2b-256 hex digest of a stable JSON payload.

    Args:
        payload: Any JSON friendly structure, floats allowed.

    Returns:
        A 64 character lowercase hex digest.
    """
    return hashlib.blake2b(stable_json(payload).encode("utf-8"), digest_size=_HASH_DIGEST_SIZE).hexdigest()


# --------------------------------------------------------------------------
# Base event
# --------------------------------------------------------------------------
#: The three envelope fields declared on :class:`Event` itself. ``type`` is not
#: among them: it is derived from the ``TYPE`` class variable, not a field.
_ENVELOPE_FIELD_NAMES: frozenset[str] = frozenset({"seq", "match_id", "tick"})

#: Per class cache of the payload field names, in declaration order. See
#: :meth:`Event.to_dict`: it runs once per event of every match, and rebuilding
#: the ``dataclasses.fields()`` tuple on each call made journal encoding roughly
#: half the cost of an order end to end. Caching changes no byte, because a
#: dataclass's field order is fixed at class creation and never varies per
#: instance.
_PAYLOAD_FIELD_NAMES: dict[type, tuple[str, ...]] = {}


def _payload_field_names(event_cls: type) -> tuple[str, ...]:
    """Return the payload field names of one event class, in declaration order.

    Args:
        event_cls: A concrete :class:`Event` subclass.

    Returns:
        Every field name except the three envelope ones, in the order the
        dataclass declares them.
    """
    cached = _PAYLOAD_FIELD_NAMES.get(event_cls)
    if cached is None:
        cached = tuple(f.name for f in fields(event_cls) if f.name not in _ENVELOPE_FIELD_NAMES)
        _PAYLOAD_FIELD_NAMES[event_cls] = cached
    return cached


@dataclass(frozen=True)
class Event:
    """Base class of every journal event.

    Attributes:
        seq: Global position in the journal, starting at 1 and incremented by
            exactly 1 for every event.
        match_id: Match the event belongs to.
        tick: Tick the event belongs to. ``0`` for :class:`MatchStarted`, and
            the last played tick for :class:`MatchEnded`.

    Note:
        Events are frozen but not reliably hashable: some payloads hold ``dict``
        fields. Compare them by value, never put them in a ``set``.
    """

    seq: int
    match_id: str
    tick: int

    #: Discriminator written into the ``type`` field. Set by every subclass.
    TYPE: ClassVar[EventType]

    def to_dict(self) -> dict[str, Any]:
        """Return the flat JSON friendly mapping written to the journal.

        The payload field names come from a per class cache: ``to_dict`` runs
        once per event of every match, and rebuilding the ``fields()`` tuple each
        time made journal encoding roughly half the cost of an order end to end.
        The cache changes no byte, because the field order of a dataclass is
        fixed at class creation.

        Returns:
            A dict holding ``seq``, ``type``, ``match_id``, ``tick`` and every
            payload field of the concrete subclass.
        """
        out: dict[str, Any] = {
            "seq": self.seq,
            "type": str(self.TYPE),
            "match_id": self.match_id,
            "tick": self.tick,
        }
        for name in _payload_field_names(type(self)):
            out[name] = _encode(getattr(self, name), f"$.{name}")
        return out

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Event":
        """Rebuild an event from its journal mapping.

        When called on :class:`Event` itself the concrete class is resolved from
        the ``type`` field. When called on a concrete subclass the ``type``
        field is ignored.

        Args:
            data: The mapping produced by :meth:`to_dict`.

        Returns:
            The reconstructed event.

        Raises:
            KeyError: If a required field is missing.
            ValueError: If ``type`` is unknown.
        """
        if cls is Event:
            return event_from_dict(data)
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            kwargs[f.name] = _coerce(f.type, data[f.name])
        return cls(**kwargs)


def _coerce(annotation: Any, value: Any) -> Any:
    """Convert a JSON value back into the type declared by a dataclass field."""
    if value is None:
        return None
    origin = get_origin(annotation)
    if origin is Union or origin is _pytypes.UnionType:
        candidates = [a for a in get_args(annotation) if a is not type(None)]
        if len(candidates) == 1:
            return _coerce(candidates[0], value)
        return value
    if origin is tuple:
        args = get_args(annotation)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_coerce(args[0], item) for item in value)
        return tuple(_coerce(arg, item) for arg, item in zip(args, value, strict=False))
    if origin is dict or annotation is dict:
        return dict(value)
    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        return annotation(value)
    return value


# --------------------------------------------------------------------------
# P0 - match lifecycle
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MatchStarted(Event):
    """First event of every journal, at ``tick = 0``.

    Attributes:
        seed: Root seed of the match.
        engine_version: Version of the engine that produced the journal.
        obs_version: Observation schema version.
        action_version: Action schema version.
        scenario_template_id: World template identifier.
        scenario_template_version: World template version.
        ticks_total: Number of ticks.
        initial_cash_cents: Starting cash of each agent.
        config: Exactly ``pxe.types.config_to_journal_dict(config)``. That
            function is the one and only encoder, and it contains no float, so
            :func:`canonical_json` accepts it by construction.
            ``pxe.types.config_from_journal_dict`` is its inverse and is what
            makes ``replay_journal`` possible.
        markets: One mapping per market, sorted by ``market_id``, holding the
            :class:`~pxe.types.MarketSpec` fields.
        agents: One mapping per seat, in **canonical account order**
            (``pxe.types.sorted_account_ids``, CONTRACTS section 2.3), holding
            ``agent_id``, ``harness_id``, ``harness_version``, ``config_hash``,
            ``info_profile_kind``, ``ranked``. Not ``sorted_ids``: an unranked
            ``MM`` seat may legally appear here and ``sorted_ids`` raises on
            ``MM`` by design, so the account order is the only helper that can
            order this list.
        mm_config: Canonical mapping of the :class:`~pxe.types.MMConfig`.
    """

    seed: int
    engine_version: str
    obs_version: str
    action_version: str
    scenario_template_id: str
    scenario_template_version: str
    ticks_total: int
    initial_cash_cents: int
    config: dict[str, Any]
    markets: tuple[dict[str, Any], ...]
    agents: tuple[dict[str, Any], ...]
    mm_config: dict[str, Any]

    TYPE: ClassVar[EventType] = EventType.MATCH_STARTED


@dataclass(frozen=True)
class TickStarted(Event):
    """Opens phase P1 of a tick.

    Attributes:
        open_market_ids: Markets still tradable at the start of the tick,
            sorted.
    """

    open_market_ids: tuple[str, ...]

    TYPE: ClassVar[EventType] = EventType.TICK_STARTED


@dataclass(frozen=True)
class MatchEnded(Event):
    """Last event of every journal.

    Attributes:
        reason: ``"completed"`` or ``"aborted"``.
        final_tick: Last tick that was played.
        rankings: Final ranking, best first. Each mapping holds exactly the
            five fields of :class:`~pxe.types.MatchRanking`: ``rank``,
            ``agent_id``, ``pnl_cents``, ``final_cash_cents`` and
            ``pnl_pct_bps``. There is deliberately **no** ``brier_ppm``:
            section 7.1 keeps Brier off the ranking so ``pxe.runner`` never has
            to import ``pxe.metrics`` against the dependency arrow. Reports
            join ``MatchRanking`` and ``CalibrationMetrics`` on ``agent_id``.
        mm_pnl_cents: Reference market maker PnL, the cost of liquidity
            (FR-5.8.5).
        fees_collected_cents: Total taker fees routed to the ``FEES`` account.
        event_count: Number of events in the journal including this one.
    """

    reason: str
    final_tick: int
    rankings: tuple[dict[str, Any], ...]
    mm_pnl_cents: int
    fees_collected_cents: int
    event_count: int

    TYPE: ClassVar[EventType] = EventType.MATCH_ENDED


# --------------------------------------------------------------------------
# P1 - diffusion
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class NewsPublished(Event):
    """A public news item is published (PRD section 5.3).

    Attributes:
        news_id: News id.
        market_ids: Markets referenced, sorted. Empty for pure noise.
        headline: Short line.
        body: Optional detail.
        impact: ``"low"``, ``"medium"`` or ``"high"``. Only ``"high"`` widens
            the market maker spread (FR-5.8.4).
        is_noise: True when the item carries no latent information. Kept in the
            journal for reports and tests; never shown to agents.
        origin: ``"info_engine"`` for a scheduled item (P1 step 2),
            ``"resolution"`` for the announcement of a market outcome
            (P1 step 4d, FR-5.2.3) and ``"cancellation"`` for the
            announcement of a scripted market cancellation (P1 step 5,
            FR-5.4.5). Those three values are exhaustive.
    """

    news_id: str
    market_ids: tuple[str, ...]
    headline: str
    body: str
    impact: str
    is_noise: bool
    origin: str

    TYPE: ClassVar[EventType] = EventType.NEWS_PUBLISHED


@dataclass(frozen=True)
class SignalDelivered(Event):
    """A private signal is delivered to exactly one agent (PRD section 5.3).

    Attributes:
        signal_id: Signal id.
        agent_id: Recipient.
        market_id: Market the signal is about.
        kind: :class:`~pxe.types.SignalKind` value.
        value_milli: Signal value in signed thousandths.
        precision_ppm: Declared reliability in parts per million.
    """

    signal_id: str
    agent_id: str
    market_id: str
    kind: str
    value_milli: int
    precision_ppm: int

    TYPE: ClassVar[EventType] = EventType.SIGNAL_DELIVERED


@dataclass(frozen=True)
class MarketResolved(Event):
    """The oracle resolved a market at its resolution tick (FR-5.2.3).

    Attributes:
        market_id: Resolved market.
        outcome: ``"yes"`` or ``"no"``.
        payout_cents: ``100`` for YES, ``0`` for NO.
        resolution_tick: The tick ``r`` planned in the scenario. It is **not**
            the envelope ``tick``: a market is tradable for the whole of
            tick ``r`` and is resolved in P1 of tick ``r + 1``, so the
            envelope carries ``r + 1`` (CONTRACTS section 5.0). When
            ``r == ticks_total`` the resolution happens in finalisation, at
            the virtual tick ``ticks_total + 1``.
        latent_value_milli: The latent value that decided the outcome, revealed
            for replay and analysis only. Agents never see it.

            It is read at the **payload** tick ``resolution_tick`` (that is
            ``r``), never at the envelope tick ``r + 1``: the outcome was drawn
            from ``latent.probability_ppm(latent_key, resolution_tick)``, so any
            other tick would journal a number that did not decide anything. This
            value is inside the AC-P1 hash, so the tick it is read at is
            contractual and not an implementation detail.
    """

    market_id: str
    outcome: str
    payout_cents: int
    resolution_tick: int
    latent_value_milli: int

    TYPE: ClassVar[EventType] = EventType.MARKET_RESOLVED


@dataclass(frozen=True)
class MarketCancelled(Event):
    """A market was cancelled by the scenario script (FR-5.4.5).

    Every execution is unwound and cash restored through
    :class:`SettlementApplied` events carrying ``mode = "unwind"``.

    Attributes:
        market_id: Cancelled market.
        reason: Free form scenario reason.
    """

    market_id: str
    reason: str

    TYPE: ClassVar[EventType] = EventType.MARKET_CANCELLED


@dataclass(frozen=True)
class SettlementApplied(Event):
    """Cash settlement of one account on one market.

    Emitted once per account holding a non zero position or a non zero cost
    basis, in the **canonical account order** of CONTRACTS section 2.3
    (ranked agents ascending, then ``MM``, then ``FEES``), driven by
    :func:`pxe.types.sorted_account_ids`. Lexicographic ``account_id`` order
    is a different order and a different journal hash. The sum of
    ``cash_delta_cents`` over all accounts of a settlement is exactly zero
    (FR-5.5.3).

    Attributes:
        market_id: Settled market.
        account_id: Settled account.
        mode: ``"resolution"`` or ``"unwind"``.
        position_qty: Signed position that was settled.
        cash_delta_cents: Signed cash movement.
        cash_before_cents: Cash before settlement.
        cash_after_cents: Cash after settlement.
        released_collateral_cents: Collateral released by closing the position.
    """

    market_id: str
    account_id: str
    mode: str
    position_qty: int
    cash_delta_cents: int
    cash_before_cents: int
    cash_after_cents: int
    released_collateral_cents: int

    TYPE: ClassVar[EventType] = EventType.SETTLEMENT_APPLIED


@dataclass(frozen=True)
class ObservationBuilt(Event):
    """An observation was handed to an agent (end of P1).

    The observation itself is a pure projection of engine state and is written
    to ``runs/<match_id>/observations.jsonl``, outside the journal hash.

    **The digest and the byte size are deliberately not here.** They are
    properties of the observation *renderer*, which is owned by A10 and is free
    to recompact text and depth at any time; journalling them would make every
    golden hash in ``tests/golden/`` move whenever the renderer is touched, and
    would route the only float bearing payload of the system into the AC-P1
    hash chain through :func:`stable_json`. ``obs_hash`` and ``obs_bytes`` are
    written as the first two fields of each line of ``observations.jsonl``
    instead (section 4.6, decision 11).

    What stays here are engine facts: who was served and how much state existed
    at that tick. They are integers the runner already knows, and they are what
    a replay needs to assert that no agent was skipped.

    Attributes:
        agent_id: Recipient.
        obs_version: Schema version.
        n_markets: Number of market blocks.
        n_news: Number of news items.
        n_signals: Number of private signals.
    """

    agent_id: str
    obs_version: str
    n_markets: int
    n_news: int
    n_signals: int

    TYPE: ClassVar[EventType] = EventType.OBSERVATION_BUILT


# --------------------------------------------------------------------------
# P2 - decision
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class AgentActionReceived(Event):
    """A validated agent action was accepted for execution (PRD section 6.2).

    The whole payload is produced by exactly one function,
    :func:`pxe.types.action_to_journal_dict`. Nobody hand-builds it: two
    spellings of one key are two journal hashes.

    Attributes:
        agent_id: Acting agent.
        action_version: Version echoed by the agent.
        source: ``"scripted"``, ``"llm"`` or ``"fallback"``.
        predictions: One mapping per accepted prediction, sorted by
            ``market_id``, holding ``market_id`` and ``p_yes_ppm``. Never
            ``p_yes``: the journal is float free (section 3.5).
        orders: One mapping per accepted order intent, **in submission order**,
            holding ``op``, ``market_id``, ``side``, ``type``, ``price``,
            ``qty``, ``order_id``. The key is ``type``, the spelling of
            ``schemas/action.v1.json``, never ``order_type``. Fields that do
            not apply are ``null`` and are kept, not dropped.
        message_public: Escaped and truncated message, or ``null``.
        rationale: Optional reasoning excerpt, truncated, never interpreted.
        n_rejected: Number of items of the raw action that were dropped
            (FR-6.2.2). Each drop also emits an :class:`AgentActionRejected`.
    """

    agent_id: str
    action_version: str
    source: str
    predictions: tuple[dict[str, Any], ...]
    orders: tuple[dict[str, Any], ...]
    message_public: str | None
    rationale: str | None
    n_rejected: int

    TYPE: ClassVar[EventType] = EventType.AGENT_ACTION_RECEIVED


@dataclass(frozen=True)
class AgentActionRejected(Event):
    """A whole action, or one item of it, was rejected (FR-6.2.2).

    Attributes:
        agent_id: Acting agent.
        scope: ``"action"``, ``"order"``, ``"prediction"`` or ``"message"``.
        item_index: 0 based index inside the offending array, ``null`` when
            ``scope`` is ``"action"``.
        reason: A :class:`~pxe.types.RejectReason` value.
        detail: Short English explanation, at most 200 characters.
    """

    agent_id: str
    scope: str
    item_index: int | None
    reason: str
    detail: str

    TYPE: ClassVar[EventType] = EventType.AGENT_ACTION_REJECTED


@dataclass(frozen=True)
class AgentTimedOut(Event):
    """An agent produced no usable answer and fell back to no action (FR-5.1.1).

    Attempt counts and latencies are deliberately absent: they are wall clock
    dependent and would break AC-P1. They live in the LLM trace file.

    Attributes:
        agent_id: Agent that failed.
        reason: A :class:`~pxe.types.RejectReason` value, typically
            ``AGENT_TIMEOUT``, ``PROVIDER_ERROR``, ``BUDGET_EXCEEDED`` or
            ``MALFORMED_RESPONSE``.
    """

    agent_id: str
    reason: str

    TYPE: ClassVar[EventType] = EventType.AGENT_TIMED_OUT


@dataclass(frozen=True)
class PredictionRecorded(Event):
    """One declared or carried probability, recorded in P2 (PRD section 7.2).

    Emitted inside the emitting agent's own P2 block, never as one global
    block: for each agent in ascending ``agent_id``, the runner emits that
    agent's ``AgentActionRejected`` items, then its ``AgentActionReceived``,
    then one ``PredictionRecorded`` per open market in ascending ``market_id``,
    then its ``MessagePosted`` if any. The relative position of the prediction
    and message events shifts every following ``seq``, so it is normative
    (section 5, P2 step 8).

    Attributes:
        agent_id: Declaring agent.
        market_id: Market.
        p_yes_ppm: Probability in parts per million.
        carried: True when the value was carried from a previous tick
            (FR-6.2.4). The very first carried value is 500 000 ppm.
    """

    agent_id: str
    market_id: str
    p_yes_ppm: int
    carried: bool

    TYPE: ClassVar[EventType] = EventType.PREDICTION_RECORDED


@dataclass(frozen=True)
class MessagePosted(Event):
    """A public message was posted (FR-5.6.1), delivered at ``tick + 1``.

    Attributes:
        agent_id: Author.
        text: Escaped and truncated text, at most 280 characters.
        deliver_tick: Tick at which recipients will see it.
    """

    agent_id: str
    text: str
    deliver_tick: int

    TYPE: ClassVar[EventType] = EventType.MESSAGE_POSTED


# --------------------------------------------------------------------------
# P3 - execution
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MMQuoted(Event):
    """The reference market maker requoted one market (FR-5.8.1).

    Emitted at the very start of P3, before the fairness shuffle, once per open
    market in ascending ``market_id`` order.

    Attributes:
        market_id: Quoted market.
        ref_price: Public reference price used as the quoting anchor
            (FR-5.4.6, FR-5.8.2).
        anchor_price: ``ref_price`` after the inventory skew of FR-5.8.3.
        bid_price: Quoted bid, ``null`` when that side is suppressed by the
            inventory cap or by price clamping.
        ask_price: Quoted ask, ``null`` under the same conditions.
        quote_qty: Size quoted on each active side.
        effective_spread: ``ask_price - bid_price`` when both sides quote, else
            ``null``.
        inventory_qty: Signed market maker inventory on this market.
        skew_cents: Signed inventory skew applied to the anchor.
        widened: True while the post news widening of FR-5.8.4 is active.
        widen_until_tick: Last tick of the widening window, ``0`` when inactive.
    """

    market_id: str
    ref_price: int
    anchor_price: int
    bid_price: int | None
    ask_price: int | None
    quote_qty: int
    effective_spread: int | None
    inventory_qty: int
    skew_cents: int
    widened: bool
    widen_until_tick: int

    TYPE: ClassVar[EventType] = EventType.MM_QUOTED


@dataclass(frozen=True)
class OrderPlaced(Event):
    """An order was accepted by the exchange.

    Emitted before any resulting :class:`TradeExecuted`. For a ``market`` order,
    ``price`` is the converted band limited price (FR-5.4.3) and
    ``requested_type`` records the original type.

    Attributes:
        order_id: Assigned order id.
        agent_id: Owner.
        market_id: Market.
        side: ``"buy"`` or ``"sell"``.
        requested_type: ``"limit"`` or ``"market"``.
        price: Effective limit price in cents.
        qty: Requested quantity.
        tif: ``"gtc"`` or ``"ioc"``.
        reserved_cents: Collateral locked at acceptance (FR-5.5.1), before
            matching.
        ref_price: Reference price used for the band conversion, ``null`` for a
            plain limit order.
        active_orders_after: Number of the agent's resting orders on this market
            after acceptance, used to audit the FR-5.4.2 cap.
    """

    order_id: str
    agent_id: str
    market_id: str
    side: str
    requested_type: str
    price: int
    qty: int
    tif: str
    reserved_cents: int
    ref_price: int | None
    active_orders_after: int

    TYPE: ClassVar[EventType] = EventType.ORDER_PLACED


@dataclass(frozen=True)
class OrderRejected(Event):
    """An order intent was refused by the exchange.

    Attributes:
        agent_id: Owner.
        market_id: Target market, ``null`` when unknown.
        side: ``"buy"``, ``"sell"`` or ``null``.
        requested_type: ``"limit"``, ``"market"`` or ``null``.
        price: Requested price or ``null``.
        qty: Requested quantity or ``null``.
        reason: A :class:`~pxe.types.RejectReason` value.
        detail: Short English explanation, at most 200 characters.
        item_index: Position of the intent inside the agent's ``orders`` array.
    """

    agent_id: str
    market_id: str | None
    side: str | None
    requested_type: str | None
    price: int | None
    qty: int | None
    reason: str
    detail: str
    item_index: int

    TYPE: ClassVar[EventType] = EventType.ORDER_REJECTED


@dataclass(frozen=True)
class OrderCancelled(Event):
    """A resting order left the book.

    Attributes:
        order_id: Cancelled order.
        agent_id: Owner.
        market_id: Market.
        side: Side of the cancelled order.
        price: Limit price of the cancelled order.
        remaining_qty: Quantity that was still resting.
        reason: A :class:`~pxe.types.CancelReason` value.
        released_cents: Collateral released back to free cash.
    """

    order_id: str
    agent_id: str
    market_id: str
    side: str
    price: int
    remaining_qty: int
    reason: str
    released_cents: int

    TYPE: ClassVar[EventType] = EventType.ORDER_CANCELLED


@dataclass(frozen=True)
class TradeExecuted(Event):
    """One execution at the maker price (FR-5.4.1).

    Attributes:
        trade_id: Trade id.
        market_id: Market.
        price: Maker price in cents.
        qty: Executed quantity.
        maker_order_id: Resting order.
        maker_agent_id: Resting owner.
        maker_side: ``"buy"`` or ``"sell"``.
        taker_order_id: Incoming order.
        taker_agent_id: Incoming owner.
        taker_side: Side of the incoming order.
        taker_fee_cents: Fee debited from the taker (FR-5.4.7). The maker pays
            nothing.
        maker_cash_delta_cents: Signed cash movement of the maker.
        taker_cash_delta_cents: Signed cash movement of the taker, fee included.
        maker_position_after: Maker net position after the trade.
        taker_position_after: Taker net position after the trade.
    """

    trade_id: str
    market_id: str
    price: int
    qty: int
    maker_order_id: str
    maker_agent_id: str
    maker_side: str
    taker_order_id: str
    taker_agent_id: str
    taker_side: str
    taker_fee_cents: int
    maker_cash_delta_cents: int
    taker_cash_delta_cents: int
    maker_position_after: int
    taker_position_after: int

    TYPE: ClassVar[EventType] = EventType.TRADE_EXECUTED


@dataclass(frozen=True)
class STPCancelled(Event):
    """Self trade prevention cancelled a resting order (FR-5.4.4).

    The incoming order is not stopped: matching continues against the next
    order by price-time priority.

    **This event carries no money.** The resting order leaves the book through
    an ``OrderCancelled(reason=STP)`` emitted immediately before this one, and
    that event is the single place where the released collateral is reported.
    Having a ``released_cents`` here too would let any projection that sums
    releases credit the same collateral twice (section 5, P3 step 11).

    Attributes:
        agent_id: The agent that would have traded with itself.
        market_id: Market.
        incoming_order_id: The aggressive order.
        resting_order_id: The resting order that was cancelled.
        cancelled_qty: Remaining quantity of the resting order at cancellation.
        cancel_seq: ``seq`` of the ``OrderCancelled`` that moved the money, so a
            projection can join the two without re-deriving them.
    """

    agent_id: str
    market_id: str
    incoming_order_id: str
    resting_order_id: str
    cancelled_qty: int
    cancel_seq: int

    TYPE: ClassVar[EventType] = EventType.STP_CANCELLED


@dataclass(frozen=True)
class AgentFrozen(Event):
    """An agent went bankrupt and is frozen until the end (FR-5.5.5).

    Attributes:
        agent_id: Frozen agent.
        equity_cents: Equity that triggered the freeze.
        cancelled_order_ids: Resting orders cancelled by the freeze, sorted.
    """

    agent_id: str
    equity_cents: int
    cancelled_order_ids: tuple[str, ...]

    TYPE: ClassVar[EventType] = EventType.AGENT_FROZEN


# --------------------------------------------------------------------------
# P4 - close
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MarkToMarket(Event):
    """End of tick public price state of one market (FR-5.5.4).

    Emitted once per open market in ascending ``market_id`` order.

    Attributes:
        market_id: Market.
        ref_price: Reference price used for the mark (FR-5.4.6).
        ref_source: ``"mid"``, ``"last"`` or ``"prior"``, the branch of
            FR-5.4.6 that produced ``ref_price``.
        best_bid: Best bid or ``null``.
        best_ask: Best ask or ``null``.
        mid_price: Rounded mid or ``null``.
        last_price: Last executed price or ``null``.
        bid_depth_qty: Total resting bid quantity.
        ask_depth_qty: Total resting ask quantity.
        tick_volume_qty: Contracts traded during this tick.
    """

    market_id: str
    ref_price: int
    ref_source: str
    best_bid: int | None
    best_ask: int | None
    mid_price: int | None
    last_price: int | None
    bid_depth_qty: int
    ask_depth_qty: int
    tick_volume_qty: int

    TYPE: ClassVar[EventType] = EventType.MARK_TO_MARKET


@dataclass(frozen=True)
class PositionSnapshot(Event):
    """End of tick snapshot of one account.

    Emitted once per account in the **canonical account order** of section 2.3:
    ranked agents by ascending numeric suffix, then ``MM``, then ``FEES``. The
    loop must be driven by :func:`pxe.types.sorted_account_ids`, which is the
    only implementation of that order.

    Attributes:
        account_id: Account.
        cash_cents: Total cash, collateral included.
        reserved_cents: Locked collateral.
        free_cash_cents: ``cash_cents - reserved_cents``.
        equity_cents: Mark to market equity.
        frozen: True once the account is bankrupt.
        positions: One mapping per non flat market, sorted by ``market_id``,
            holding ``market_id``, ``qty``, ``cost_basis_cents``,
            ``value_cents``.
        resting_order_count: Number of resting orders across all markets.
    """

    account_id: str
    cash_cents: int
    reserved_cents: int
    free_cash_cents: int
    equity_cents: int
    frozen: bool
    positions: tuple[dict[str, Any], ...]
    resting_order_count: int

    TYPE: ClassVar[EventType] = EventType.POSITION_SNAPSHOT


@dataclass(frozen=True)
class IncidentRaised(Event):
    """An integrity detector raised an alert (PRD section 7.5).

    Detectors run offline over a finished journal. When they do, incidents are
    appended to ``runs/<match_id>/incidents.jsonl``, not to the match journal,
    so a detector version bump never changes a journal hash. The engine itself
    only ever emits this event for technical incidents detected in flight.

    Attributes:
        incident_id: Incident id.
        kind: A :class:`~pxe.types.IncidentKind` value.
        severity: ``"low"``, ``"medium"`` or ``"high"``.
        agent_ids: Implicated agents, sorted.
        market_ids: Implicated markets, sorted.
        score_ppm: Detector score in parts per million.
        detector_version: Version of the detector.
        detail: Detector specific evidence, JSON scalars only, never a float.
            :class:`pxe.types.Incident` carries the same evidence as an ordered
            ``(key, value)`` tuple. The two shapes are equivalent because
            :func:`canonical_json` sorts object keys by code point, but they are
            never converted by hand: use
            :func:`pxe.types.incident_detail_to_dict` here and
            :func:`pxe.types.incident_detail_from_dict` to go back. Those two
            functions are the only legal crossing (section 7.18).
    """

    incident_id: str
    kind: str
    severity: str
    agent_ids: tuple[str, ...]
    market_ids: tuple[str, ...]
    score_ppm: int
    detector_version: str
    detail: dict[str, Any]

    TYPE: ClassVar[EventType] = EventType.INCIDENT_RAISED


# --------------------------------------------------------------------------
# Registry and journal helpers
# --------------------------------------------------------------------------
#: Mapping from :class:`EventType` to the concrete event class.
EVENT_CLASSES: dict[EventType, type[Event]] = {
    EventType.MATCH_STARTED: MatchStarted,
    EventType.TICK_STARTED: TickStarted,
    EventType.NEWS_PUBLISHED: NewsPublished,
    EventType.SIGNAL_DELIVERED: SignalDelivered,
    EventType.MARKET_RESOLVED: MarketResolved,
    EventType.MARKET_CANCELLED: MarketCancelled,
    EventType.SETTLEMENT_APPLIED: SettlementApplied,
    EventType.OBSERVATION_BUILT: ObservationBuilt,
    EventType.AGENT_ACTION_RECEIVED: AgentActionReceived,
    EventType.AGENT_ACTION_REJECTED: AgentActionRejected,
    EventType.AGENT_TIMED_OUT: AgentTimedOut,
    EventType.MM_QUOTED: MMQuoted,
    EventType.ORDER_PLACED: OrderPlaced,
    EventType.ORDER_REJECTED: OrderRejected,
    EventType.ORDER_CANCELLED: OrderCancelled,
    EventType.TRADE_EXECUTED: TradeExecuted,
    EventType.STP_CANCELLED: STPCancelled,
    EventType.POSITION_SNAPSHOT: PositionSnapshot,
    EventType.MARK_TO_MARKET: MarkToMarket,
    EventType.PREDICTION_RECORDED: PredictionRecorded,
    EventType.MESSAGE_POSTED: MessagePosted,
    EventType.AGENT_FROZEN: AgentFrozen,
    EventType.INCIDENT_RAISED: IncidentRaised,
    EventType.MATCH_ENDED: MatchEnded,
}


def event_from_dict(data: Mapping[str, Any]) -> Event:
    """Rebuild the right concrete event from a journal mapping.

    Args:
        data: Mapping holding at least a ``type`` key.

    Returns:
        The reconstructed event.

    Raises:
        ValueError: If ``type`` is missing or unknown.
    """
    raw_type = data.get("type")
    if raw_type is None:
        raise ValueError("event mapping has no 'type' field")
    try:
        event_type = EventType(raw_type)
    except ValueError as exc:
        raise ValueError(f"unknown event type {raw_type!r}") from exc
    return EVENT_CLASSES[event_type].from_dict(data)


def event_to_line(event: Event) -> str:
    r"""Serialise one event to its journal line, newline included.

    Args:
        event: The event.

    Returns:
        ``canonical_json(event.to_dict()) + "\\n"``.
    """
    return canonical_json(event.to_dict()) + "\n"


def event_from_line(line: str) -> Event:
    """Parse one journal line back into an event.

    Args:
        line: A single JSONL line, with or without its trailing newline.

    Returns:
        The reconstructed event.

    Raises:
        ValueError: If the line is not a valid event object.
    """
    return event_from_dict(json.loads(line))


def journal_hash(events: Iterable[Event]) -> str:
    """Compute the journal digest compared by AC-P1.

    The digest is ``blake2b-256`` over the concatenation of every canonical
    event line, which is byte for byte the content of the ``.jsonl`` file.

    Args:
        events: Events in ``seq`` order.

    Returns:
        A 64 character lowercase hex digest.
    """
    digest = hashlib.blake2b(digest_size=_HASH_DIGEST_SIZE)
    for event in events:
        digest.update(event_to_line(event).encode("utf-8"))
    return digest.hexdigest()


def journal_hash_from_lines(lines: Iterable[str]) -> str:
    r"""Compute the journal digest from raw file lines.

    A carriage return anywhere in a line is rejected rather than normalised
    away. Reading a CRLF file in Python's universal newline mode hands back
    clean ``"\\n"`` lines, so a journal accidentally written in the platform
    default text mode on Windows would hash *correctly* here while its bytes on
    disk hash differently, and AC-P1 would only fail once two machines compared
    files. Failing loudly here is the point.

    Args:
        lines: Journal lines, each with or without its trailing newline, in file
            order.

    Returns:
        A 64 character lowercase hex digest, identical to :func:`journal_hash`
        over the same events.

    Raises:
        NonCanonicalValueError: If a line contains a carriage return.
    """
    digest = hashlib.blake2b(digest_size=_HASH_DIGEST_SIZE)
    for index, line in enumerate(lines):
        if "\r" in line:
            raise NonCanonicalValueError(
                "journal lines must use LF endings; open the file with newline=JOURNAL_NEWLINE",
                path=f"$[{index}]",
                value="carriage return",
            )
        text = line if line.endswith("\n") else line + "\n"
        digest.update(text.encode(JOURNAL_ENCODING))
    return digest.hexdigest()
