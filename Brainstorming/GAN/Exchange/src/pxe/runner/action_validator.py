"""Action validation: JSON Schema plus semantics, truncation, prediction carry (A11).

This module is the **only** door between a raw agent payload and the engine
(CONTRACTS section 5 P2 step 8b: the runner is the single call site of
:func:`validate_action`, and no gateway ever calls it). Three rules shape
everything below.

**FR-6.2.2, truncation.** A partially invalid action keeps its valid elements
and rejects the rest with a logged reason. :func:`validate_action` never raises
on agent input: not on a ``None`` payload, not on deeply nested junk, not on a
NaN, not on a 10 000 digit integer. A payload the validator cannot interpret at
all becomes :meth:`AgentAction.no_action` plus exactly one ``scope="action"``
rejection.

**FR-6.2.4, prediction carry.** A missing or invalid prediction for an open
market carries the last declared value, defaulting to
:data:`~pxe.types.DEFAULT_PREDICTION_PPM` (500 000 ppm) at the first tick, and
the carried flag travels to ``PredictionRecorded.carried``. That is
:func:`resolve_predictions`, which the runner calls at P2 step 8c.

**P2 is structural, P3 is authoritative** (CONTRACTS section 7.14). Liveness is
never validated here: ``open_market_ids`` catches a market that never existed or
had already resolved when the observation was built, and ``resting_order_ids``
catches an ``order_id`` the agent never owned. An order that legitimately went
away between P2 and P3 is the exchange's ``OrderRejected``, never an
``AgentActionRejected``.

Two readings of the contract had to be resolved to make the section 7.14 table
reachable, and they are stated here because they are observable in a journal:

1. "fails ``schemas/action.v1.json`` **outright**" is read as *the envelope
   fails*. Schema errors located inside an ``orders`` or ``predictions`` **item**
   are not fatal: the item is dropped with its precise semantic reason, which is
   what the table asks for (``INVALID_PRICE``, ``INVALID_QTY``, ... would be
   unreachable otherwise, since the schema already pins those ranges). An
   over-long ``orders``/``predictions`` array and an over-long
   ``message_public``/``rationale`` are likewise not fatal, because the table
   asks for truncation there. Everything else the schema rejects (not an object,
   a missing top level key, an unknown top level key, a wrongly typed
   ``predictions``) is fatal, as FR-6.2.2's "validation stricte par JSON Schema"
   requires.
2. The action produced by a fatal rejection is ``AgentAction.no_action(...)``,
   whose ``source`` is therefore :attr:`~pxe.types.AgentSource.FALLBACK` and not
   the ``source`` argument: it *is* the FR-5.1.1 no-action fallback, and a
   projection counting fallbacks would otherwise be unable to see it.
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeGuard

from pxe.errors import PxeError
from pxe.runner.schema_registry import action_schema, validator_for
from pxe.types import (
    ACTION_VERSION,
    DEFAULT_PREDICTION_PPM,
    MAX_ORDER_QTY,
    MAX_PREDICTIONS_PER_ACTION,
    PPM_ONE,
    PRICE_MAX,
    PRICE_MIN,
    AgentAction,
    AgentSource,
    MatchConfig,
    OrderIntent,
    OrderType,
    PredictionIntent,
    RejectReason,
    Side,
    ppm_from_prob,
    sorted_ids,
)

__all__ = ["Rejection", "ValidationOutcome", "resolve_predictions", "sanitise_message", "validate_action"]

_LOG = logging.getLogger("pxe.runner.action_validator")

#: Accepted ``side`` values, compared with ``in`` over a tuple so that an
#: unhashable payload value (a list, a dict) cannot raise ``TypeError`` the way
#: an enum lookup would.
_SIDE_VALUES: tuple[str, ...] = (Side.BUY.value, Side.SELL.value)

#: Accepted ``type`` values, same reasoning.
_ORDER_TYPE_VALUES: tuple[str, ...] = (OrderType.LIMIT.value, OrderType.MARKET.value)

#: Accepted ``op`` values.
_OP_VALUES: tuple[str, ...] = ("place", "cancel")

#: Top level keys whose own schema failures are tolerated (see rule 1 above).
_TOLERATED_ARRAY_KEYS: tuple[str, ...] = ("orders", "predictions")
_TOLERATED_TEXT_KEYS: tuple[str, ...] = ("message_public", "rationale")

#: Longest ``detail`` excerpt of a payload value written into a journal or a
#: log line. Section 2.5 caps raw model output in a log at 200 characters; a
#: rejection detail is far shorter than that on purpose, because a hostile
#: payload must not be able to inflate the journal.
_DETAIL_MAX_CHARS = 80

#: Hard ceiling on a whole ``detail`` string. ``AgentActionRejected.detail`` is
#: documented as "at most 200 characters" (:mod:`pxe.events`), and a journal
#: field that an agent can inflate is a journal field an agent can weaponise, so
#: the cap is enforced in :class:`Rejection` itself and not left to the caller.
_REJECTION_DETAIL_MAX_CHARS = 200

#: A trailing HTML entity cut in half by truncation, removed by
#: :func:`sanitise_message` so the message never ends on ``&l``.
_PARTIAL_ENTITY_RE = re.compile(r"&(?:#[0-9]{0,4}|[a-zA-Z]{0,5})$")


@dataclass(frozen=True)
class Rejection:
    """One rejected element of an agent action (``AgentActionRejected`` payload).

    Attributes:
        scope: ``"action"``, ``"order"``, ``"prediction"`` or ``"message"``.
        item_index: Index inside ``orders`` or ``predictions``, ``None`` for a
            whole action rejection and for the message.
        reason: Stable rejection code, one of the members listed in the
            CONTRACTS section 7.14 table and no other.
        detail: Short English explanation, truncated to 200 characters by
            ``__post_init__`` so that ``AgentActionRejected.detail`` always
            honours its documented ceiling.
    """

    scope: str
    item_index: int | None
    reason: RejectReason
    detail: str

    def __post_init__(self) -> None:
        """Enforce the 200 character ceiling of ``AgentActionRejected.detail``."""
        if len(self.detail) > _REJECTION_DETAIL_MAX_CHARS:
            object.__setattr__(self, "detail", self.detail[:_REJECTION_DETAIL_MAX_CHARS])


@dataclass(frozen=True)
class ValidationOutcome:
    """What survived validation, and what did not.

    Attributes:
        action: The action the engine will execute. Its ``orders`` are in the
            exact order the agent submitted them (P3 applies them in that
            order); its ``predictions`` are sorted by ``market_id``.
        rejections: Every rejected element, in item order. The runner emits one
            ``AgentActionRejected`` per entry, before ``AgentActionReceived``.
    """

    action: AgentAction
    rejections: tuple[Rejection, ...]


# --------------------------------------------------------------------------
# Small pure helpers
# --------------------------------------------------------------------------
def _brief(value: Any) -> str:
    """Render a payload value for a rejection ``detail``, length bounded.

    Args:
        value: Any payload fragment, possibly enormous or hostile.

    Returns:
        A ``repr`` truncated to :data:`_DETAIL_MAX_CHARS` characters.
    """
    try:
        text = repr(value)
    except Exception:  # a hostile __repr__ must not abort validation
        return "<unrepresentable>"
    if len(text) > _DETAIL_MAX_CHARS:
        return text[:_DETAIL_MAX_CHARS] + "..."
    return text


def _is_plain_int(value: Any) -> TypeGuard[int]:
    """Return whether a payload value is an integer and not a boolean.

    ``bool`` is a subclass of ``int`` in Python and ``true`` is not an integer
    in JSON Schema, so the two must not be confused.

    Args:
        value: Payload value.

    Returns:
        ``True`` for an ``int`` that is not a ``bool``.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def _ppm_from_payload(value: Any) -> int | None:
    """Convert a payload ``p_yes`` into parts per million.

    Args:
        value: Payload value, anything at all.

    Returns:
        The probability in ppm, or ``None`` when the value is not a finite
        number inside ``[0, 1]``. Booleans are rejected: JSON Schema's
        ``number`` excludes them.
    """
    if isinstance(value, bool):
        return None
    if _is_plain_int(value):
        return None if not 0 <= value <= 1 else ppm_from_prob(float(value))
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return None if not 0.0 <= value <= 1.0 else ppm_from_prob(value)
    return None


def _rationale_max_chars() -> int:
    """Return the ``rationale`` ceiling declared by ``schemas/action.v1.json``.

    Read from the schema rather than duplicated as a literal: the schema is the
    hard ceiling (CONTRACTS section 8.2) and a second copy of the number is a
    second place for it to drift.

    Returns:
        The ``maxLength`` of ``rationale``, or 0 if the schema ever drops it.
    """
    rationale = action_schema().get("properties", {}).get("rationale", {})
    ceiling = rationale.get("maxLength", 0)
    return ceiling if _is_plain_int(ceiling) and ceiling >= 0 else 0


def sanitise_message(text: str | None, *, max_chars: int) -> str | None:
    """Make an agent authored string safe to hand to other agents (FR-5.6.2).

    In order: control, format and separator characters become spaces, runs of
    whitespace collapse to one space, backticks and angle brackets are escaped,
    and the result is truncated to ``max_chars``. Truncation is last, so the
    returned string is never longer than ``max_chars`` even though escaping
    expands it. The content is never interpreted: this is an escaper, not a
    filter.

    Args:
        text: Raw message, or ``None``.
        max_chars: Hard ceiling, normally ``config.message_max_chars``.

    Returns:
        The sanitised message, or ``None`` when there is nothing left to say.
    """
    if text is None:
        return None
    if max_chars <= 0:
        return None
    flattened = "".join(" " if unicodedata.category(ch)[0] in ("C", "Z") else ch for ch in text)
    collapsed = " ".join(flattened.split())
    escaped = collapsed.replace("`", "&#96;").replace("<", "&lt;").replace(">", "&gt;")
    if len(escaped) > max_chars:
        escaped = _PARTIAL_ENTITY_RE.sub("", escaped[:max_chars]).rstrip()
    return escaped or None


def resolve_predictions(
    *, declared: Mapping[str, int], previous: Mapping[str, int], open_market_ids: Sequence[str]
) -> tuple[tuple[str, int, bool], ...]:
    """Apply the FR-6.2.4 prediction carry over every open market.

    Args:
        declared: What this tick's action actually declared, ``market_id`` to
            ppm. Only used for lookup, never iterated (CONTRACTS section 2.3).
        previous: The last value declared or carried for each market,
            ``MatchState.last_prediction_ppm``. Lookup only.
        open_market_ids: Markets open this tick. Iterated through
            :func:`~pxe.types.sorted_ids`, duplicates collapsed, so the result
            holds exactly one row per market in canonical order.

    Returns:
        One ``(market_id, p_yes_ppm, carried)`` triple per open market,
        ascending by ``market_id``. ``carried`` is ``True`` whenever the value
        did not come from this tick's action, including the 500 000 ppm default
        of the very first tick.
    """
    unique = tuple(dict.fromkeys(open_market_ids))
    rows: list[tuple[str, int, bool]] = []
    for market_id in sorted_ids(unique):
        if market_id in declared:
            value = declared[market_id]
            carried = False
        elif market_id in previous:
            value = previous[market_id]
            carried = True
        else:
            value = DEFAULT_PREDICTION_PPM
            carried = True
        rows.append((market_id, min(PPM_ONE, max(0, value)), carried))
    return tuple(rows)


# --------------------------------------------------------------------------
# Order items
# --------------------------------------------------------------------------
def _validate_cancel_item(
    item: Mapping[Any, Any], *, index: int, resting_ids: frozenset[str]
) -> OrderIntent | Rejection:
    """Validate one ``op == "cancel"`` entry.

    Args:
        item: The payload entry.
        index: Its position in ``orders``.
        resting_ids: Order ids this agent had resting when the observation was
            built. Membership only, never iterated.

    Returns:
        The intent, or the :class:`Rejection` that drops the entry.
    """
    order_id = item.get("order_id")
    if not isinstance(order_id, str) or not order_id:
        return Rejection(
            scope="order",
            item_index=index,
            reason=RejectReason.MISSING_FIELD,
            detail=f"cancel needs order_id, got {_brief(order_id)}",
        )
    if order_id not in resting_ids:
        return Rejection(
            scope="order",
            item_index=index,
            reason=RejectReason.UNKNOWN_ORDER,
            detail=f"order_id {_brief(order_id)} is not resting for this agent",
        )
    return OrderIntent(op="cancel", order_id=order_id)


def _validate_price(price: Any, order_type: str, *, index: int) -> int | Rejection | None:
    """Validate the ``price`` of a ``place`` entry against its ``type``.

    Args:
        price: Payload value.
        order_type: Already validated ``"limit"`` or ``"market"``.
        index: Position in ``orders``.

    Returns:
        The limit price, ``None`` for a market order, or a :class:`Rejection`.
    """
    if order_type == OrderType.MARKET.value:
        if price is None:
            return None
        return Rejection(
            scope="order",
            item_index=index,
            reason=RejectReason.INVALID_PRICE,
            detail=f"a market order carries no price, got {_brief(price)}",
        )
    if price is None:
        return Rejection(
            scope="order", item_index=index, reason=RejectReason.MISSING_FIELD, detail="a limit order needs a price"
        )
    if not _is_plain_int(price) or not PRICE_MIN <= price <= PRICE_MAX:
        return Rejection(
            scope="order",
            item_index=index,
            reason=RejectReason.INVALID_PRICE,
            detail=f"price must be an integer in {PRICE_MIN}..{PRICE_MAX}, got {_brief(price)}",
        )
    return price


def _validate_place_item(item: Mapping[Any, Any], *, index: int, open_ids: frozenset[str]) -> OrderIntent | Rejection:
    """Validate one ``op == "place"`` entry.

    The check order is fixed and normative for the journal, because the reason
    reported for an entry wrong in two ways depends on it: required fields
    first (``market_id``, ``side``, ``type``, ``qty``, in that order), then
    ``side``, ``type``, ``qty``, ``price``, and finally market membership.

    Args:
        item: The payload entry.
        index: Its position in ``orders``.
        open_ids: Markets open when the observation was built. Membership only.

    Returns:
        The intent, or the :class:`Rejection` that drops the entry.
    """
    for name in ("market_id", "side", "type", "qty"):
        if item.get(name) is None:
            return Rejection(
                scope="order", item_index=index, reason=RejectReason.MISSING_FIELD, detail=f"place needs {name}"
            )
    side = item.get("side")
    if side not in _SIDE_VALUES:
        return Rejection(
            scope="order",
            item_index=index,
            reason=RejectReason.INVALID_SIDE,
            detail=f"side must be buy or sell, got {_brief(side)}",
        )
    order_type = item.get("type")
    if order_type not in _ORDER_TYPE_VALUES:
        return Rejection(
            scope="order",
            item_index=index,
            reason=RejectReason.INVALID_TYPE,
            detail=f"type must be limit or market, got {_brief(order_type)}",
        )
    qty = item.get("qty")
    if not _is_plain_int(qty) or not 1 <= qty <= MAX_ORDER_QTY:
        return Rejection(
            scope="order",
            item_index=index,
            reason=RejectReason.INVALID_QTY,
            detail=f"qty must be an integer in 1..{MAX_ORDER_QTY}, got {_brief(qty)}",
        )
    price = _validate_price(item.get("price"), str(order_type), index=index)
    if isinstance(price, Rejection):
        return price
    market_id = item.get("market_id")
    if not isinstance(market_id, str) or market_id not in open_ids:
        return Rejection(
            scope="order",
            item_index=index,
            reason=RejectReason.UNKNOWN_MARKET,
            detail=f"market {_brief(market_id)} is not open in this observation",
        )
    return OrderIntent(
        op="place",
        market_id=market_id,
        side=Side(str(side)),
        order_type=OrderType(str(order_type)),
        price=price,
        qty=int(qty),
    )


def _validate_order_item(
    item: Any, *, index: int, open_ids: frozenset[str], resting_ids: frozenset[str]
) -> OrderIntent | Rejection:
    """Validate one ``orders`` entry, whatever it is.

    Args:
        item: The payload entry, possibly not even an object.
        index: Its position in ``orders``.
        open_ids: Markets open when the observation was built.
        resting_ids: Order ids this agent had resting.

    Returns:
        The intent, or the :class:`Rejection` that drops the entry.
    """
    if not isinstance(item, Mapping):
        return Rejection(
            scope="order",
            item_index=index,
            reason=RejectReason.INVALID_ORDER,
            detail=f"order entry is not an object: {_brief(item)}",
        )
    op = item.get("op")
    if op not in _OP_VALUES:
        return Rejection(
            scope="order",
            item_index=index,
            reason=RejectReason.INVALID_ORDER,
            detail=f"op must be place or cancel, got {_brief(op)}",
        )
    if op == "cancel":
        return _validate_cancel_item(item, index=index, resting_ids=resting_ids)
    return _validate_place_item(item, index=index, open_ids=open_ids)


# --------------------------------------------------------------------------
# Prediction items
# --------------------------------------------------------------------------
def _validate_predictions(
    entries: Sequence[Any], *, open_ids: frozenset[str], rejections: list[Rejection]
) -> dict[str, int]:
    """Validate the ``predictions`` array, truncating and de-duplicating.

    Args:
        entries: The raw array.
        open_ids: Markets open when the observation was built.
        rejections: Accumulator, appended to in item order.

    Returns:
        ``market_id`` to ppm for the entries that survived, first occurrence
        winning a duplicate.
    """
    kept: dict[str, int] = {}
    for index, item in enumerate(entries):
        if index >= MAX_PREDICTIONS_PER_ACTION:
            rejections.append(
                Rejection(
                    scope="prediction",
                    item_index=index,
                    reason=RejectReason.TOO_MANY_PREDICTIONS,
                    detail=f"at most {MAX_PREDICTIONS_PER_ACTION} predictions per action",
                )
            )
            continue
        if not isinstance(item, Mapping):
            rejections.append(
                Rejection(
                    scope="prediction",
                    item_index=index,
                    reason=RejectReason.UNKNOWN_MARKET,
                    detail=f"prediction entry is not an object: {_brief(item)}",
                )
            )
            continue
        market_id = item.get("market_id")
        if not isinstance(market_id, str) or market_id not in open_ids:
            rejections.append(
                Rejection(
                    scope="prediction",
                    item_index=index,
                    reason=RejectReason.UNKNOWN_MARKET,
                    detail=f"market {_brief(market_id)} is not open in this observation",
                )
            )
            continue
        if market_id in kept:
            rejections.append(
                Rejection(
                    scope="prediction",
                    item_index=index,
                    reason=RejectReason.DUPLICATE_PREDICTION,
                    detail=f"{market_id} was already declared in this action",
                )
            )
            continue
        ppm = _ppm_from_payload(item.get("p_yes"))
        if ppm is None:
            rejections.append(
                Rejection(
                    scope="prediction",
                    item_index=index,
                    reason=RejectReason.INVALID_PROBABILITY,
                    detail=f"p_yes must be a number in [0, 1], got {_brief(item.get('p_yes'))}",
                )
            )
            continue
        kept[market_id] = ppm
    return kept


# --------------------------------------------------------------------------
# The envelope
# --------------------------------------------------------------------------
def _fatal_schema_error(payload: Mapping[Any, Any]) -> str | None:
    """Return the reason the payload envelope is unusable, or ``None``.

    Item level schema failures, over-long arrays and over-long text are
    tolerated here and handled by the semantic layer (rule 1 of the module
    docstring). Everything else is fatal.

    Args:
        payload: The raw payload, already known to be a mapping.

    Returns:
        A short English description of the first fatal error in a stable order,
        or ``None`` when the envelope is usable.
    """
    validator = validator_for("action.v1")
    try:
        errors = list(validator.iter_errors(dict(payload)))
    except PxeError:
        raise
    except Exception as exc:  # jsonschema on a hostile instance must not crash a match
        return f"schema validation failed: {type(exc).__name__}"
    fatal = [error for error in errors if not _is_tolerated(error)]
    if not fatal:
        return None
    fatal.sort(
        key=lambda error: (len(error.absolute_path), [str(part) for part in error.absolute_path], str(error.validator))
    )
    first = fatal[0]
    location = "/".join(str(part) for part in first.absolute_path) or "<root>"
    return f"{location}: {first.validator} ({_brief(first.message)})"


def _is_tolerated(error: Any) -> bool:
    """Return whether one schema error must not fail the whole action.

    Args:
        error: A ``jsonschema.ValidationError``.

    Returns:
        ``True`` when the semantic layer handles this failure instead.
    """
    path = tuple(error.absolute_path)
    keyword = str(error.validator)
    if len(path) >= 2 and path[0] in _TOLERATED_ARRAY_KEYS:
        return True
    if len(path) == 1 and path[0] in _TOLERATED_ARRAY_KEYS and keyword == "maxItems":
        return True
    return len(path) == 1 and path[0] in _TOLERATED_TEXT_KEYS and keyword == "maxLength"


def _no_action(agent_id: str, tick: int, reason: RejectReason, detail: str) -> ValidationOutcome:
    """Build the whole-action rejection outcome.

    Args:
        agent_id: The agent.
        tick: The tick.
        reason: ``SCHEMA_INVALID`` or ``ACTION_INVALID``.
        detail: Short English explanation.

    Returns:
        ``AgentAction.no_action`` plus exactly one ``scope="action"`` rejection.
    """
    _LOG.warning(
        "action rejected in full: %s", detail[:200], extra={"agent_id": agent_id, "tick": tick, "reason": str(reason)}
    )
    return ValidationOutcome(
        action=AgentAction.no_action(agent_id, tick),
        rejections=(Rejection(scope="action", item_index=None, reason=reason, detail=detail),),
    )


def _resolve_message(payload: Mapping[Any, Any], *, config: MatchConfig, rejections: list[Rejection]) -> str | None:
    """Apply the talking mode and length rules to ``message_public``.

    Args:
        payload: The raw payload.
        config: Match configuration; ``talking_mode`` and ``message_max_chars``.
        rejections: Accumulator.

    Returns:
        The sanitised message, or ``None``.
    """
    raw_message = payload.get("message_public")
    if not isinstance(raw_message, str):
        return None
    if not config.talking_mode:
        rejections.append(
            Rejection(
                scope="message",
                item_index=None,
                reason=RejectReason.TALKING_MODE_OFF,
                detail="talking mode is off for this match",
            )
        )
        return None
    if len(raw_message) > config.message_max_chars:
        rejections.append(
            Rejection(
                scope="message",
                item_index=None,
                reason=RejectReason.MESSAGE_TOO_LONG,
                detail=f"message is {len(raw_message)} characters, truncated to {config.message_max_chars}",
            )
        )
    return sanitise_message(raw_message, max_chars=config.message_max_chars)


def validate_action(
    raw: Any,
    *,
    agent_id: str,
    tick: int,
    config: MatchConfig,
    open_market_ids: Sequence[str],
    resting_order_ids: Sequence[str],
    source: AgentSource,
) -> ValidationOutcome:
    """Turn one raw agent payload into a validated action (FR-6.2.2).

    Never raises on agent input: a fully invalid payload yields
    ``AgentAction.no_action`` plus one :class:`Rejection` with
    ``scope="action"``. A partially invalid payload keeps its valid elements and
    reports one rejection per dropped element, in item order.

    Args:
        raw: Whatever the gateway returned, including ``None`` after a timeout.
        agent_id: The acting seat.
        tick: The tick the action belongs to.
        config: Match configuration. ``max_orders_per_action``,
            ``message_max_chars`` and ``talking_mode`` are read here.
        open_market_ids: Markets that were open when the observation was built.
            Used for membership only: this is a structural check, not a liveness
            check (CONTRACTS section 7.14).
        resting_order_ids: Order ids this agent had resting at the same moment.
            Membership only, same reason.
        source: Where the payload came from, recorded on the surviving action.

    Returns:
        The :class:`ValidationOutcome` the runner journals at P2 step 8b.
    """
    if not isinstance(raw, Mapping):
        return _no_action(agent_id, tick, RejectReason.SCHEMA_INVALID, f"payload is not a JSON object: {_brief(raw)}")
    version = raw.get("action_version")
    if "action_version" in raw and version != ACTION_VERSION:
        return _no_action(agent_id, tick, RejectReason.ACTION_INVALID, f"unsupported action_version {_brief(version)}")
    fatal = _fatal_schema_error(raw)
    if fatal is not None:
        return _no_action(agent_id, tick, RejectReason.SCHEMA_INVALID, fatal)

    open_ids = frozenset(open_market_ids)
    resting_ids = frozenset(resting_order_ids)
    rejections: list[Rejection] = []

    raw_predictions = raw.get("predictions")
    declared = _validate_predictions(
        raw_predictions if isinstance(raw_predictions, list) else [], open_ids=open_ids, rejections=rejections
    )

    raw_orders = raw.get("orders")
    entries: Sequence[Any] = raw_orders if isinstance(raw_orders, list) else []
    intents: list[OrderIntent] = []
    for index, item in enumerate(entries):
        if index >= config.max_orders_per_action:
            rejections.append(
                Rejection(
                    scope="order",
                    item_index=index,
                    reason=RejectReason.TOO_MANY_ORDERS_IN_ACTION,
                    detail=f"at most {config.max_orders_per_action} orders per action",
                )
            )
            continue
        result = _validate_order_item(item, index=index, open_ids=open_ids, resting_ids=resting_ids)
        if isinstance(result, Rejection):
            rejections.append(result)
            continue
        intents.append(result)

    message = _resolve_message(raw, config=config, rejections=rejections)
    rationale = sanitise_message(
        raw.get("rationale") if isinstance(raw.get("rationale"), str) else None, max_chars=_rationale_max_chars()
    )

    for rejection in rejections:
        _LOG.info(
            "action item rejected: %s",
            rejection.detail[:200],
            extra={
                "agent_id": agent_id,
                "tick": tick,
                "scope": rejection.scope,
                "item_index": rejection.item_index,
                "reason": str(rejection.reason),
            },
        )

    action = AgentAction(
        agent_id=agent_id,
        tick=tick,
        action_version=ACTION_VERSION,
        predictions=tuple(
            PredictionIntent(market_id=market_id, p_yes_ppm=declared[market_id])
            for market_id in sorted_ids(tuple(declared))
        ),
        orders=tuple(intents),
        message_public=message,
        rationale=rationale,
        source=source,
    )
    return ValidationOutcome(action=action, rejections=tuple(rejections))
