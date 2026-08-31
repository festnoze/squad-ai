"""Shared vocabulary for Prediction Exchange (pxe).

This module is the type contract every other module codes against. It holds
enumerations, frozen dataclasses and pure arithmetic helpers. It contains no
engine logic, no I/O, no randomness and no clock access.

Units, once and for all
-----------------------
* **Money** is an ``int`` number of **cents** (written ``*_cents``). There is no
  float anywhere in money arithmetic. A YES contract pays exactly
  :data:`PAYOUT_YES_CENTS` (100) cents, a NO contract pays 0.
* **Price** is an ``int`` in ``[PRICE_MIN, PRICE_MAX]`` = ``[1, 99]`` cents,
  tick size 1 cent (FR-5.4.5).
* **Quantity** is an ``int`` number of contracts, always ``>= 1`` for an order.
* **Probability** is stored as an ``int`` in parts per million (``*_ppm``,
  range ``[0, 1_000_000]``). Floats only exist at the agent boundary and are
  converted immediately. The journal never contains a float (see
  :mod:`pxe.events`).
* **Real valued latent quantities** (latent states, signal values) are stored as
  ``int`` thousandths (``*_milli``), signed.

Naming
------
Field suffixes are load bearing and MUST be respected by every module:
``_cents``, ``_ppm``, ``_milli``, ``_bps``, ``_qty``, ``_tick``, ``_id``.
"""

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pxe.errors import (
    InvalidConfigError,
    InvalidOrderError,
    InvariantViolationError,
    PxeError,
    UnknownProfileError,
)

__all__ = [
    # constants
    "ENGINE_VERSION",
    "OBS_VERSION",
    "ACTION_VERSION",
    "PRICE_MIN",
    "PRICE_MAX",
    "PAYOUT_YES_CENTS",
    "PAYOUT_NO_CENTS",
    "PPM_ONE",
    "MILLI_ONE",
    "BPS_ONE",
    "MM_ACCOUNT_ID",
    "FEES_ACCOUNT_ID",
    "DEPTH_LEVELS",
    "MAX_ORDERS_PER_ACTION_CEILING",
    "SEED_SPACE",
    "MAX_PREDICTIONS_PER_ACTION",
    "MAX_ORDER_QTY",
    "MESSAGE_MAX_CHARS_CEILING",
    "REF_HISTORY_MAX",
    "DEFAULT_PREDICTION_PPM",
    # id patterns
    "RE_MARKET_ID",
    "RE_AGENT_ID",
    "RE_SEAT_ID",
    "RE_ACCOUNT_ID",
    "RE_ORDER_ID",
    "RE_MATCH_ID",
    # enums
    "Side",
    "OrderType",
    "TimeInForce",
    "OrderStatus",
    "MarketStatus",
    "Outcome",
    "NewsImpact",
    "SignalKind",
    "InfoProfileKind",
    "LiquidityProfileName",
    "AccountKind",
    "AgentSource",
    "RejectReason",
    "CancelReason",
    "IncidentKind",
    "TournamentFormat",
    # arithmetic helpers
    "round_half_up",
    "ppm_from_prob",
    "prob_from_ppm",
    "milli_from_float",
    "float_from_milli",
    "bps_ratio",
    "clamp_price",
    "taker_fee_cents",
    "max_taker_fee_cents",
    "order_collateral_cents",
    "position_collateral_cents",
    "brier_term_ppm",
    # id factories
    "make_order_id",
    "make_trade_id",
    "make_market_id",
    "make_agent_id",
    "make_news_id",
    "make_signal_id",
    "make_incident_id",
    # ordering helpers
    "sorted_ids",
    "sorted_account_ids",
    # dataclasses
    "MarketSpec",
    "BookLevel",
    "BookSnapshot",
    "Order",
    "Trade",
    "Position",
    "AccountState",
    "MarketState",
    "NewsItem",
    "NewsPlanItem",
    "Signal",
    "PredictionIntent",
    "OrderIntent",
    "AgentAction",
    "MarketObservation",
    "ObservationLimits",
    "PublicMessage",
    "Observation",
    "InventoryView",
    "MMConfig",
    "LiquidityProfile",
    "MatchConfig",
    "InfoProfile",
    "AgentSpec",
    "HarnessConfig",
    "GatewayConfig",
    "ScenarioSpec",
    "MatchRanking",
    "MatchResult",
    "Incident",
    "RatingRecord",
    "MatchTask",
    "TournamentConfig",
    "TournamentResult",
    # journal encoding of configuration and agent intents
    "market_spec_to_dict",
    "market_spec_from_dict",
    "config_to_journal_dict",
    "config_from_journal_dict",
    "scenario_to_journal_dict",
    "scenario_from_journal_dict",
    "order_intent_to_dict",
    "order_intent_from_dict",
    "prediction_intent_to_dict",
    "prediction_intent_to_wire_dict",
    "action_to_payload",
    "action_to_journal_dict",
    # harness identity
    "harness_config_hash",
    "harness_key",
    # error mapping
    "reject_reason_of",
    # incident detail encoding
    "incident_detail_to_dict",
    "incident_detail_from_dict",
    # profile registry
    "LIQUIDITY_PROFILES",
    "liquidity_profile",
]

# --------------------------------------------------------------------------
# Versions and constants
# --------------------------------------------------------------------------
#: Bumped whenever a change would alter the journal of an existing seed.
ENGINE_VERSION = "1.0.0"
#: Version tag carried by every observation payload (PRD section 6.1).
OBS_VERSION = "1.0"
#: Version tag carried by every agent action payload (PRD section 6.2).
ACTION_VERSION = "1.0"

#: Exclusive upper bound of every persisted seed (section 3.1). A seed is an
#: unsigned **63** bit integer and not a 64 bit one, because ``pxe.store``
#: mirrors it into a portable ``BigInteger`` column, which is signed on both
#: SQLite and Postgres: a value at or above ``2**63`` raises ``OverflowError``
#: on insert and no tournament that produced one could ever be persisted
#: (section 7.20). ``pxe.rng.RngTree`` still accepts the whole 64 bit space,
#: because a derived tree root is never written anywhere.
SEED_SPACE: int = 2**63

PRICE_MIN: int = 1
PRICE_MAX: int = 99
PAYOUT_YES_CENTS: int = 100
PAYOUT_NO_CENTS: int = 0
PPM_ONE: int = 1_000_000
MILLI_ONE: int = 1_000
BPS_ONE: int = 10_000

#: Reserved account id of the reference market maker (out of ranking, FR-5.8.5).
MM_ACCOUNT_ID = "MM"
#: Reserved account id of the fee vault (out of ranking, FR-5.4.7).
FEES_ACCOUNT_ID = "FEES"
#: Number of aggregated book levels exposed in an observation (PRD section 6.1).
DEPTH_LEVELS: int = 3

#: Hard ceiling on ``orders`` entries per action. ``schemas/action.v1.json``
#: encodes this exact number as ``maxItems``, so ``MatchConfig`` may never be
#: configured above it (see :meth:`MatchConfig.__post_init__`).
MAX_ORDERS_PER_ACTION_CEILING: int = 20
#: Hard ceiling on ``predictions`` entries per action, one per market at most.
MAX_PREDICTIONS_PER_ACTION: int = 8
#: Hard ceiling on the quantity of a single order intent, mirrored by the
#: action schema so the validator and the schema reject exactly the same thing.
MAX_ORDER_QTY: int = 100_000
#: Hard ceiling on ``message_public``. ``schemas/action.v1.json`` encodes it as
#: ``maxLength`` and ``schemas/observation.v1.json`` as the ``messages`` item
#: ``maxLength``, and both files are handed verbatim to the provider CLI, so
#: ``MatchConfig.message_max_chars`` may lower it and never raise it
#: (FR-5.6.1 states the same 280).
MESSAGE_MAX_CHARS_CEILING: int = 280
#: Hard ceiling on the ``ref_history`` sparkline of one market block.
#: ``schemas/observation.v1.json`` encodes it as ``maxItems``, so
#: ``MatchConfig.ref_history_len`` may lower it and never raise it.
REF_HISTORY_MAX: int = 32
#: Probability carried at the first tick when an agent never declared one
#: (FR-6.2.4), in parts per million.
DEFAULT_PREDICTION_PPM: int = 500_000

#: A ranked seat, ``A1``..``A8``. The market maker is deliberately excluded.
RE_AGENT_ID = re.compile(r"^A[1-9][0-9]?$")
#: A seat at the table: a ranked agent or the reference market maker. This is
#: the set that can appear in an observation (``schemas/observation.v1.json``).
RE_SEAT_ID = re.compile(r"^(A[1-9][0-9]?|MM)$")
#: An account held by :class:`AccountBook`: a seat, or the fee vault.
RE_ACCOUNT_ID = re.compile(r"^(A[1-9][0-9]?|MM|FEES)$")
RE_MARKET_ID = re.compile(r"^M[1-9][0-9]?$")
RE_ORDER_ID = re.compile(r"^o-[0-9]{6}$")
RE_MATCH_ID = re.compile(r"^m-[a-z0-9_]+-[0-9]{1,20}-[0-9]{2}$")


def _id_sort_key(value: str) -> tuple[int, str, int]:
    """Sort key for the canonical market and ranked-agent order (section 2.3).

    ``M1 < M2 < ... < M10`` and ``A1 < A2 < ... < A10``: the suffix is compared
    as an integer, never as text. Plain ``sorted()`` puts ``M10`` before ``M2``,
    which is a different journal byte order, so this is the single
    implementation of the ordering and both :func:`sorted_ids` and every
    ``__post_init__`` order check in this module go through it. Anything that is
    not an ``M``/``A`` id falls back to code point order, after every id that
    is one.

    Args:
        value: An id.

    Returns:
        A tuple ordering ``value`` against other ids.
    """
    if len(value) > 1 and value[0] in ("M", "A") and value[1:].isdigit():
        return (0, value[0], int(value[1:]))
    return (1, value, 0)


def _is_sorted_by_id(ids: Sequence[str]) -> bool:
    """Return True when ``ids`` is already in canonical id order.

    Args:
        ids: Market ids or ranked agent ids.

    Returns:
        True when ``ids`` equals its canonical ordering.
    """
    return list(ids) == sorted(ids, key=_id_sort_key)


# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------
class Side(StrEnum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"

    @property
    def opposite(self) -> "Side":
        """Return the opposite side."""
        return Side.SELL if self is Side.BUY else Side.BUY

    @property
    def sign(self) -> int:
        """Return +1 for a buy, -1 for a sell."""
        return 1 if self is Side.BUY else -1


class OrderType(StrEnum):
    """Order type accepted by the exchange (FR-5.4.2)."""

    LIMIT = "limit"
    MARKET = "market"


class TimeInForce(StrEnum):
    """Time in force.

    ``GTC`` is the only resting mode (FR-5.4.2). ``IOC`` is used internally for
    ``market`` orders converted to a bounded marketable limit (FR-5.4.3): the
    residual is cancelled, never left resting.
    """

    GTC = "gtc"
    IOC = "ioc"


class OrderStatus(StrEnum):
    """Lifecycle state of an order."""

    NEW = "new"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

    @property
    def is_resting(self) -> bool:
        """True when the order still sits in the book."""
        return self in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)

    @property
    def is_terminal(self) -> bool:
        """True when the order can no longer change."""
        return self in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED)


class MarketStatus(StrEnum):
    """Market lifecycle state (FR-5.4.5)."""

    OPEN = "open"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"

    @property
    def is_tradable(self) -> bool:
        """True when orders may be accepted on this market."""
        return self is MarketStatus.OPEN


class Outcome(StrEnum):
    """Binary event outcome decided by the oracle."""

    YES = "yes"
    NO = "no"

    @property
    def payout_cents(self) -> int:
        """Return the per contract payout in cents (100 for YES, 0 for NO)."""
        return PAYOUT_YES_CENTS if self is Outcome.YES else PAYOUT_NO_CENTS


class NewsImpact(StrEnum):
    """Impact tag attached to a public news item (PRD section 5.3).

    Only ``HIGH`` triggers the market maker spread widening of FR-5.8.4.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SignalKind(StrEnum):
    """Shape of a private signal delivered to a single agent."""

    POINT_ESTIMATE = "point_estimate"
    DIRECTION = "direction"
    THRESHOLD = "threshold"


class InfoProfileKind(StrEnum):
    """Information profile permuted across agents by the Latin square (FR-5.3.2)."""

    GENERALIST = "generalist"
    SPECIALIST = "specialist"
    DELAYED = "delayed"


class LiquidityProfileName(StrEnum):
    """Named market maker preset (FR-5.8.6)."""

    LIQUID = "liquid"
    STANDARD = "standard"
    ILLIQUID = "illiquid"


class AccountKind(StrEnum):
    """Kind of account held by the accounting module."""

    AGENT = "agent"
    MARKET_MAKER = "market_maker"
    FEES = "fees"


class AgentSource(StrEnum):
    """Where an action came from, recorded on every accepted action."""

    SCRIPTED = "scripted"
    LLM = "llm"
    FALLBACK = "fallback"  # FR-5.1.1 no-action fallback


class RejectReason(StrEnum):
    """Stable rejection codes written into the journal.

    Mirrors the ``code`` of the matching exception in :mod:`pxe.errors`.
    """

    SCHEMA_INVALID = "SCHEMA_INVALID"
    ACTION_INVALID = "ACTION_INVALID"
    INVALID_ORDER = "INVALID_ORDER"
    UNKNOWN_MARKET = "UNKNOWN_MARKET"
    MARKET_NOT_OPEN = "MARKET_NOT_OPEN"
    INVALID_PRICE = "INVALID_PRICE"
    INVALID_QTY = "INVALID_QTY"
    INVALID_SIDE = "INVALID_SIDE"
    INVALID_TYPE = "INVALID_TYPE"
    MISSING_FIELD = "MISSING_FIELD"
    UNKNOWN_ORDER = "UNKNOWN_ORDER"
    NOT_ORDER_OWNER = "NOT_ORDER_OWNER"
    ORDER_LIMIT_EXCEEDED = "ORDER_LIMIT_EXCEEDED"
    INSUFFICIENT_COLLATERAL = "INSUFFICIENT_COLLATERAL"
    AGENT_FROZEN = "AGENT_FROZEN"
    TOO_MANY_ORDERS_IN_ACTION = "TOO_MANY_ORDERS_IN_ACTION"
    TOO_MANY_PREDICTIONS = "TOO_MANY_PREDICTIONS"
    DUPLICATE_PREDICTION = "DUPLICATE_PREDICTION"
    INVALID_PROBABILITY = "INVALID_PROBABILITY"
    MESSAGE_TOO_LONG = "MESSAGE_TOO_LONG"
    TALKING_MODE_OFF = "TALKING_MODE_OFF"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"


class CancelReason(StrEnum):
    """Why a resting order left the book."""

    AGENT_REQUEST = "agent_request"
    MM_REQUOTE = "mm_requote"
    STP = "stp"
    IOC_RESIDUAL = "ioc_residual"
    MARKET_RESOLVED = "market_resolved"
    MARKET_CANCELLED = "market_cancelled"
    AGENT_FROZEN = "agent_frozen"
    MATCH_ENDED = "match_ended"


class IncidentKind(StrEnum):
    """Integrity alert families (PRD section 7.5)."""

    COLLUSION = "collusion"
    WASH_TRADING = "wash_trading"
    SPOOFING = "spoofing"
    PREDICTION_POSITION_MISMATCH = "prediction_position_mismatch"
    OFF_MARKET_TRANSFER = "off_market_transfer"
    TECHNICAL = "technical"


class TournamentFormat(StrEnum):
    """Supported tournament formats (PRD section 8)."""

    ROUND_ROBIN = "round_robin"
    SWISS = "swiss"
    EXHIBITION = "exhibition"


# --------------------------------------------------------------------------
# Pure arithmetic helpers. No float ever reaches money or the journal.
# --------------------------------------------------------------------------
def round_half_up(value: float) -> int:
    """Round a float to the nearest integer, halves going toward positive infinity.

    Python's builtin :func:`round` uses banker's rounding, which is a hidden
    source of surprise. Every rounding in pxe goes through this function.

    Args:
        value: The value to round.

    Returns:
        The rounded integer.

    Raises:
        ValueError: If ``value`` is NaN or infinite.
    """
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"cannot round non finite value {value!r}")
    return math.floor(value + 0.5)


def ppm_from_prob(p: float) -> int:
    """Convert a probability in ``[0, 1]`` to parts per million.

    Args:
        p: Probability, must be finite and inside ``[0, 1]``.

    Returns:
        An integer in ``[0, 1_000_000]``.

    Raises:
        ValueError: If ``p`` is not finite or is out of range.
    """
    if math.isnan(p) or math.isinf(p):
        raise ValueError(f"probability must be finite, got {p!r}")
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"probability must be in [0, 1], got {p!r}")
    return min(PPM_ONE, max(0, round_half_up(p * PPM_ONE)))


def prob_from_ppm(ppm: int) -> float:
    """Convert parts per million back to a probability in ``[0, 1]``.

    The result is the IEEE-754 quotient of an integer by ``10**6``. Division is
    a correctly rounded operation on every conforming platform and CPython's
    ``repr`` prints the shortest string that round trips, so the textual form is
    identical everywhere. No rounding call is needed, and in particular the
    banned builtin ``round`` is not used (section 2.1).

    Args:
        ppm: Integer in ``[0, 1_000_000]``.

    Returns:
        The probability, with at most 6 decimal digits in its ``repr``.
    """
    return ppm / PPM_ONE


def milli_from_float(value: float) -> int:
    """Convert a real valued quantity to signed thousandths.

    Args:
        value: A finite float.

    Returns:
        ``round_half_up(value * 1000)``.

    Raises:
        ValueError: If ``value`` is not finite.
    """
    return round_half_up(value * MILLI_ONE)


def float_from_milli(value_milli: int) -> float:
    """Convert signed thousandths back to a float.

    Like :func:`prob_from_ppm` this is an exact IEEE-754 division of an integer
    by a power of ten, so it needs no rounding and never calls the banned
    builtin ``round``.

    Args:
        value_milli: Signed integer thousandths.

    Returns:
        The float value, with at most 3 decimal digits in its ``repr``.
    """
    return value_milli / MILLI_ONE


def bps_ratio(numerator_cents: int, denominator_cents: int) -> int:
    """Return ``numerator / denominator`` in basis points, exactly and symmetrically.

    Floor division on a signed numerator rounds toward minus infinity, which
    would overstate every loss by up to one basis point and understate every
    gain. This helper rounds half **away from zero**, so a gain and the mirror
    loss report the same magnitude. It is the only way ``pnl_pct_bps``,
    ``max_drawdown_bps`` and every other ``*_bps`` ratio may be computed
    (PRD section 9).

    Args:
        numerator_cents: Signed numerator in cents.
        denominator_cents: Strictly positive denominator in cents.

    Returns:
        The ratio in basis points, signed.

    Raises:
        InvalidConfigError: If ``denominator_cents`` is not strictly positive.
    """
    if denominator_cents <= 0:
        raise InvalidConfigError("bps denominator must be > 0", denominator=denominator_cents)
    sign = -1 if numerator_cents < 0 else 1
    magnitude = abs(numerator_cents)
    return sign * ((magnitude * 2 * BPS_ONE + denominator_cents) // (2 * denominator_cents))


def clamp_price(price: int) -> int:
    """Clamp a price into the tradable band ``[1, 99]``.

    Args:
        price: Any integer price in cents.

    Returns:
        The clamped price.
    """
    return max(PRICE_MIN, min(PRICE_MAX, int(price)))


def taker_fee_cents(fee_bps: int, price: int, qty: int) -> int:
    """Compute the taker fee of one execution (FR-5.4.7).

    The fee is a floor division so it never creates money, and the maker never
    pays a fee.

    Args:
        fee_bps: Fee in basis points, ``0`` to ``200`` (0 % to 2 %).
        price: Execution price in cents.
        qty: Executed quantity in contracts.

    Returns:
        The fee in cents, always ``>= 0``.

    Raises:
        ValueError: If any argument is negative.
    """
    if fee_bps < 0 or price < 0 or qty < 0:
        raise ValueError("fee inputs must be non negative")
    return (fee_bps * price * qty) // BPS_ONE


def max_taker_fee_cents(fee_bps: int, qty: int) -> int:
    """Worst case taker fee reserved before matching an aggressive order.

    Computed at the maximum conceivable execution price (100 cents), so the
    pre-trade solvency check can never be defeated by a better fill.

    Args:
        fee_bps: Fee in basis points.
        qty: Order quantity in contracts.

    Returns:
        The reserved fee in cents.
    """
    return taker_fee_cents(fee_bps, PAYOUT_YES_CENTS, qty)


def order_collateral_cents(side: Side, price: int, remaining_qty: int) -> int:
    """Collateral locked by a resting order (FR-5.5.1).

    ``buy`` at ``p`` locks ``p * qty`` (the cash needed to pay).
    ``sell`` at ``p`` locks ``(100 - p) * qty`` (the worst case top up if the
    event resolves YES, given the ``p * qty`` that will be received).

    Args:
        side: Order side.
        price: Limit price in cents, ``1..99``.
        remaining_qty: Unfilled quantity in contracts, ``>= 0``.

    Returns:
        The locked collateral in cents.

    Raises:
        InvalidOrderError: If price or quantity is out of range.
    """
    if not PRICE_MIN <= price <= PRICE_MAX:
        raise InvalidOrderError("price out of range", price=price)
    if remaining_qty < 0:
        raise InvalidOrderError("negative remaining quantity", qty=remaining_qty)
    if side is Side.BUY:
        return price * remaining_qty
    return (PAYOUT_YES_CENTS - price) * remaining_qty


def position_collateral_cents(net_qty: int) -> int:
    """Collateral locked by an open position on one market (FR-5.5.1, FR-5.5.2).

    A long position is already fully paid, so it locks nothing. A short position
    locks the full ``100`` cent payout per contract, because the ``p`` cents per
    contract received at execution are already sitting in cash.

    Args:
        net_qty: Signed net position in contracts.

    Returns:
        The locked collateral in cents, always ``>= 0``.
    """
    return PAYOUT_YES_CENTS * max(0, -int(net_qty))


def brier_term_ppm(p_yes_ppm: int, outcome: Outcome) -> int:
    """One Brier term ``(p - y)^2`` expressed in parts per million (PRD section 7.2).

    Kept integral so calibration metrics stay exactly reproducible.

    Args:
        p_yes_ppm: Declared probability in parts per million.
        outcome: Realised outcome.

    Returns:
        ``(p - y)^2`` in parts per million, in ``[0, 1_000_000]``.
    """
    y_ppm = PPM_ONE if outcome is Outcome.YES else 0
    diff = p_yes_ppm - y_ppm
    return (diff * diff) // PPM_ONE


# --------------------------------------------------------------------------
# Id factories. Every id is derived from counters, never from a clock or uuid4.
# --------------------------------------------------------------------------
def make_order_id(seq: int) -> str:
    """Build an order id from the per match order counter.

    Args:
        seq: Strictly positive counter, unique within a match.

    Returns:
        ``"o-000001"`` style id.
    """
    return f"o-{seq:06d}"


def make_trade_id(seq: int) -> str:
    """Build a trade id from the per match trade counter.

    Args:
        seq: Strictly positive counter, unique within a match.

    Returns:
        ``"t-000001"`` style id.
    """
    return f"t-{seq:06d}"


def make_market_id(index: int) -> str:
    """Build a market id from its 1 based index in the scenario.

    Args:
        index: 1 based market index.

    Returns:
        ``"M1"`` style id.
    """
    return f"M{index}"


def make_agent_id(index: int) -> str:
    """Build an agent id from its 1 based seat index.

    Args:
        index: 1 based seat index.

    Returns:
        ``"A1"`` style id.
    """
    return f"A{index}"


def make_news_id(tick: int, index: int) -> str:
    """Build a news id.

    Args:
        tick: Tick of publication.
        index: 0 based index within the tick.

    Returns:
        ``"n-003-00"`` style id.
    """
    return f"n-{tick:03d}-{index:02d}"


def make_signal_id(tick: int, agent_id: str, index: int) -> str:
    """Build a private signal id.

    Args:
        tick: Tick of delivery.
        agent_id: Recipient agent id.
        index: 0 based index within the tick for this agent.

    Returns:
        ``"s-003-A2-00"`` style id.
    """
    return f"s-{tick:03d}-{agent_id}-{index:02d}"


def make_incident_id(seq: int) -> str:
    """Build an incident id.

    Args:
        seq: Strictly positive counter.

    Returns:
        ``"i-0001"`` style id.
    """
    return f"i-{seq:04d}"


# --------------------------------------------------------------------------
# Market and book
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class MarketSpec:
    """Static definition of one binary market, fixed at world generation.

    Attributes:
        market_id: ``M1``..``M8``.
        question: Human readable question, shown to agents and spectators.
        prior_price: Public opening prior in cents, ``1..99`` (FR-5.2.4).
        resolution_tick: Tick at which the oracle resolves it, ``1..T``
            (FR-5.2.3).
        latent_key: Name of the latent variable driving the outcome. Never
            exposed to agents or to the market maker.
        correlation_group: Group tag shared by correlated markets (FR-5.2.1).
            Empty string when the market is independent.
        tags: Free form ordered tags used by templates and reports.
    """

    market_id: str
    question: str
    prior_price: int
    resolution_tick: int
    latent_key: str
    correlation_group: str = ""
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not RE_MARKET_ID.match(self.market_id):
            raise InvalidConfigError("bad market id", market_id=self.market_id)
        if not PRICE_MIN <= self.prior_price <= PRICE_MAX:
            raise InvalidConfigError("prior out of range", prior_price=self.prior_price)
        if self.resolution_tick < 1:
            raise InvalidConfigError("resolution tick must be >= 1", tick=self.resolution_tick)


@dataclass(frozen=True, slots=True)
class BookLevel:
    """One aggregated price level of a book side.

    Attributes:
        price: Price in cents.
        qty: Total resting quantity at that price.
        order_count: Number of resting orders at that price.
    """

    price: int
    qty: int
    order_count: int

    def __post_init__(self) -> None:
        if not PRICE_MIN <= self.price <= PRICE_MAX:
            raise InvalidOrderError("book level price out of range", price=self.price)
        if self.qty < 1 or self.order_count < 1:
            raise InvalidOrderError("empty book level", qty=self.qty, count=self.order_count)


@dataclass(frozen=True, slots=True)
class BookSnapshot:
    """Immutable view of one market's book at a point in time.

    Attributes:
        market_id: Market id.
        bids: Levels sorted by descending price (best first).
        asks: Levels sorted by ascending price (best first).
        last_price: Last executed price in cents, ``None`` before any trade.
        ref_price: Reference price in cents (FR-5.4.6), always defined.
        mid_price: Rounded mid, ``None`` when the book is not two sided.
    """

    market_id: str
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    last_price: int | None
    ref_price: int
    mid_price: int | None

    @property
    def best_bid(self) -> int | None:
        """Best bid price, or ``None`` when the bid side is empty."""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> int | None:
        """Best ask price, or ``None`` when the ask side is empty."""
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> int | None:
        """Best ask minus best bid, or ``None`` when the book is one sided."""
        if self.bids and self.asks:
            return self.asks[0].price - self.bids[0].price
        return None


@dataclass(frozen=True, slots=True)
class Order:
    """An order as tracked by the exchange.

    Instances are immutable: any state change produces a new instance through
    :meth:`with_fill` or :meth:`with_status`.

    Attributes:
        order_id: ``o-000001`` style id assigned at acceptance.
        agent_id: Owning account id (an agent, or ``MM``).
        market_id: Target market.
        side: Buy or sell.
        order_type: Original type requested by the agent.
        price: Effective limit price in cents. For a ``market`` order this is
            the price after the protection band conversion (FR-5.4.3).
        qty: Original quantity in contracts.
        remaining_qty: Unfilled quantity in contracts.
        status: Lifecycle state.
        tif: ``GTC`` for limits, ``IOC`` for converted market orders.
        created_tick: Tick at which the order was accepted.
        seq: Monotonic acceptance counter, used for time priority.
    """

    order_id: str
    agent_id: str
    market_id: str
    side: Side
    order_type: OrderType
    price: int
    qty: int
    remaining_qty: int
    status: OrderStatus
    tif: TimeInForce
    created_tick: int
    seq: int

    def __post_init__(self) -> None:
        if not PRICE_MIN <= self.price <= PRICE_MAX:
            raise InvalidOrderError("price out of range", price=self.price, order_id=self.order_id)
        if self.qty < 1:
            raise InvalidOrderError("quantity must be >= 1", qty=self.qty, order_id=self.order_id)
        if not 0 <= self.remaining_qty <= self.qty:
            raise InvalidOrderError(
                "remaining quantity out of range",
                remaining=self.remaining_qty,
                qty=self.qty,
                order_id=self.order_id,
            )

    @property
    def filled_qty(self) -> int:
        """Quantity already executed."""
        return self.qty - self.remaining_qty

    @property
    def collateral_cents(self) -> int:
        """Collateral currently locked by the unfilled part (FR-5.5.1)."""
        if not self.status.is_resting:
            return 0
        return order_collateral_cents(self.side, self.price, self.remaining_qty)

    @property
    def priority_key(self) -> tuple[int, int]:
        """Price-time priority key within a side.

        Returns:
            ``(-price, seq)`` for a buy and ``(price, seq)`` for a sell, so that
            sorting ascending yields best price first then oldest first
            (FR-5.4.1).
        """
        return (-self.price, self.seq) if self.side is Side.BUY else (self.price, self.seq)

    def with_fill(self, qty: int) -> "Order":
        """Return a copy with ``qty`` contracts executed.

        Args:
            qty: Executed quantity, ``1 <= qty <= remaining_qty``.

        Returns:
            A new :class:`Order` with an updated remaining quantity and status.

        Raises:
            InvalidOrderError: If ``qty`` exceeds the remaining quantity.
        """
        if not 1 <= qty <= self.remaining_qty:
            raise InvalidOrderError("fill exceeds remaining", qty=qty, order_id=self.order_id)
        remaining = self.remaining_qty - qty
        status = OrderStatus.FILLED if remaining == 0 else OrderStatus.PARTIALLY_FILLED
        return _replace_order(self, remaining_qty=remaining, status=status)

    def with_status(self, status: OrderStatus) -> "Order":
        """Return a copy carrying a new status.

        Args:
            status: New lifecycle state.

        Returns:
            A new :class:`Order`.
        """
        return _replace_order(self, status=status)


def _replace_order(order: Order, **changes: Any) -> Order:
    """Build a modified copy of an order (``dataclasses.replace`` for slots)."""
    values: dict[str, Any] = {
        "order_id": order.order_id,
        "agent_id": order.agent_id,
        "market_id": order.market_id,
        "side": order.side,
        "order_type": order.order_type,
        "price": order.price,
        "qty": order.qty,
        "remaining_qty": order.remaining_qty,
        "status": order.status,
        "tif": order.tif,
        "created_tick": order.created_tick,
        "seq": order.seq,
    }
    values.update(changes)
    return Order(**values)


@dataclass(frozen=True, slots=True)
class Trade:
    """One execution between a resting maker and an incoming taker.

    The execution always happens at the maker price (FR-5.4.1), and only the
    taker pays a fee (FR-5.4.7).

    Attributes:
        trade_id: ``t-000001`` style id.
        market_id: Market on which the trade happened.
        price: Maker price in cents.
        qty: Executed quantity.
        maker_order_id: Resting order id.
        maker_agent_id: Resting order owner.
        maker_side: Side of the resting order.
        taker_order_id: Incoming order id.
        taker_agent_id: Incoming order owner.
        taker_fee_cents: Fee debited from the taker, credited to ``FEES``.
        tick: Tick of execution.
        seq: Monotonic execution counter within the match.
    """

    trade_id: str
    market_id: str
    price: int
    qty: int
    maker_order_id: str
    maker_agent_id: str
    maker_side: Side
    taker_order_id: str
    taker_agent_id: str
    taker_fee_cents: int
    tick: int
    seq: int

    def __post_init__(self) -> None:
        if not PRICE_MIN <= self.price <= PRICE_MAX:
            raise InvalidOrderError("trade price out of range", price=self.price)
        if self.qty < 1:
            raise InvalidOrderError("trade quantity must be >= 1", qty=self.qty)

    @property
    def taker_side(self) -> Side:
        """Side of the aggressive order."""
        return self.maker_side.opposite

    @property
    def notional_cents(self) -> int:
        """Cash exchanged, excluding fees."""
        return self.price * self.qty


@dataclass(frozen=True, slots=True)
class Position:
    """Net position of one account on one market.

    Attributes:
        market_id: Market id.
        qty: Signed net quantity. Positive is long YES, negative is short.
        cost_basis_cents: Signed net cash paid to build the position, fees
            excluded. Buying 10 at 40 gives ``+4000``; selling 10 at 40 gives
            ``-4000``. Realised PnL on a market equals
            ``settlement_cash - cost_basis_cents`` over the market's life.
            Summed over every account of one market it is exactly zero
            (invariant I12), which is what makes the FR-5.4.5 unwind a zero sum
            operation.
        fees_paid_cents: Taker fees this account paid on this market, always
            ``>= 0``. Tracked per (account, market) because an unwind refunds
            them (FR-5.4.5: "l'annulation ... restitue le cash"), and because
            ``fees_paid_cents`` is the per market part of the
            ``PerformanceMetrics.fees_paid_cents`` total.
    """

    market_id: str
    qty: int
    cost_basis_cents: int
    fees_paid_cents: int = 0

    @property
    def collateral_cents(self) -> int:
        """Collateral locked by this position (FR-5.5.1)."""
        return position_collateral_cents(self.qty)

    def value_cents(self, ref_price: int) -> int:
        """Mark to market value of the position (FR-5.5.4).

        Args:
            ref_price: Reference price of the market in cents (FR-5.4.6).

        Returns:
            ``qty * ref_price``, signed.
        """
        return self.qty * ref_price


@dataclass(frozen=True, slots=True)
class AccountState:
    """Immutable snapshot of one account.

    Attributes:
        account_id: Agent id, ``MM`` or ``FEES``.
        kind: Account kind.
        cash_cents: Total cash owned, **including** the part locked as
            collateral. Never negative (FR-5.5.5).
        reserved_cents: Cash locked by resting orders and open short positions.
        positions: Positions sorted by ``market_id``. Markets with a null
            position and a null cost basis are omitted.
        frozen: True once the account went bankrupt (FR-5.5.5).

    Note:
        This is a **snapshot** type, not a mutable ledger. It may only be
        constructed at a consistent point, never in the middle of a settlement
        (debit the short before releasing its collateral and I4 is transiently
        false). Constructing it at an inconsistent point raises
        :class:`~pxe.errors.InvariantViolationError`, which is exit code 4, not
        a configuration error.
    """

    account_id: str
    kind: AccountKind
    cash_cents: int
    reserved_cents: int
    positions: tuple[Position, ...] = ()
    frozen: bool = False

    def __post_init__(self) -> None:
        if self.cash_cents < 0:
            raise InvariantViolationError("I9: negative cash", account_id=self.account_id, cash=self.cash_cents)
        if self.reserved_cents < 0 or self.reserved_cents > self.cash_cents:
            raise InvariantViolationError(
                "I4: reserved outside [0, cash]",
                account_id=self.account_id,
                reserved=self.reserved_cents,
                cash=self.cash_cents,
            )
        ids = [p.market_id for p in self.positions]
        if not _is_sorted_by_id(ids):
            raise InvalidConfigError("positions must be sorted by market_id", account_id=self.account_id)

    @property
    def free_cash_cents(self) -> int:
        """Cash available for new collateral: ``cash_cents - reserved_cents``."""
        return self.cash_cents - self.reserved_cents

    def position(self, market_id: str) -> Position:
        """Return the position on ``market_id``, or a flat one.

        Args:
            market_id: Market id.

        Returns:
            The stored :class:`Position`, or a zero position when absent.
        """
        for pos in self.positions:
            if pos.market_id == market_id:
                return pos
        return Position(market_id=market_id, qty=0, cost_basis_cents=0)

    def equity_cents(self, ref_prices: Mapping[str, int]) -> int:
        """Mark to market equity (FR-5.5.4).

        Args:
            ref_prices: Reference price per market id. Missing markets are
                treated as already settled and contribute nothing.

        Returns:
            ``cash_cents + sum(qty * ref_price)``.
        """
        total = self.cash_cents
        for pos in self.positions:
            ref = ref_prices.get(pos.market_id)
            if ref is not None:
                total += pos.value_cents(ref)
        return total


@dataclass(frozen=True, slots=True)
class MarketState:
    """Full public state of one market at a point in time.

    Attributes:
        spec: Static definition.
        status: Lifecycle state.
        book: Current book snapshot.
        outcome: Resolved outcome, ``None`` while open.
        resolved_tick: Tick of resolution, ``None`` while open.
        ref_history: Reference prices of the last ticks, oldest first.
    """

    spec: MarketSpec
    status: MarketStatus
    book: BookSnapshot
    outcome: Outcome | None = None
    resolved_tick: int | None = None
    ref_history: tuple[int, ...] = ()

    @property
    def market_id(self) -> str:
        """Convenience accessor for ``spec.market_id``."""
        return self.spec.market_id

    @property
    def ref_price(self) -> int:
        """Reference price in cents (FR-5.4.6)."""
        return self.book.ref_price


# --------------------------------------------------------------------------
# Information
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class NewsItem:
    """A public news item, visible to every agent at the same tick.

    Attributes:
        news_id: ``n-003-00`` style id.
        tick: Tick of publication.
        market_ids: Markets the item refers to, sorted. May be empty for pure
            noise items.
        headline: Short line, at most 120 characters.
        body: Optional detail, at most 400 characters.
        impact: Impact tag. Only ``HIGH`` widens the market maker spread
            (FR-5.8.4). The tag describes the *fact* that information landed,
            never its direction.
        is_noise: True when the item carries no information about the latent
            state. Never exposed to agents; used by reports and tests.
    """

    news_id: str
    tick: int
    market_ids: tuple[str, ...]
    headline: str
    body: str
    impact: NewsImpact
    is_noise: bool = False

    def __post_init__(self) -> None:
        if len(self.headline) > 120:
            raise InvalidConfigError("headline too long", news_id=self.news_id)
        if len(self.body) > 400:
            raise InvalidConfigError("body too long", news_id=self.news_id)
        if not _is_sorted_by_id(self.market_ids):
            raise InvalidConfigError("market_ids must be sorted", news_id=self.news_id)


@dataclass(frozen=True, slots=True)
class NewsPlanItem:
    """One scheduled slot of a world's news calendar (A03 to A04 handover).

    The world generator produces the calendar; the information engine turns
    each slot into a concrete :class:`NewsItem`. It is a named type rather than
    a positional tuple because it crosses a workstream boundary.

    Attributes:
        tick: Tick at which the item is published, ``>= 1``.
        market_ids: Markets the item refers to, sorted. Several ids is the
            normal case for a correlated group (FR-5.2.1); an empty tuple is a
            pure noise item about nothing in particular.
        impact: Impact tag. Only ``HIGH`` widens the market maker spread
            (FR-5.8.4).
        is_noise: True when the slot carries no information about the latent
            state.
    """

    tick: int
    market_ids: tuple[str, ...]
    impact: NewsImpact
    is_noise: bool = False

    def __post_init__(self) -> None:
        if self.tick < 1:
            raise InvalidConfigError("news plan tick must be >= 1", tick=self.tick)
        if not _is_sorted_by_id(self.market_ids):
            raise InvalidConfigError("market_ids must be sorted", tick=self.tick)


@dataclass(frozen=True, slots=True)
class Signal:
    """A private signal delivered to exactly one agent.

    Attributes:
        signal_id: ``s-003-A2-00`` style id.
        tick: Tick of delivery.
        agent_id: Recipient.
        market_id: Market the signal is about.
        kind: Signal shape.
        value_milli: Signed thousandths. For ``POINT_ESTIMATE`` this is a noisy
            probability in thousandths of a unit (``0..1000``). For
            ``DIRECTION`` it is ``-1000`` or ``+1000``. For ``THRESHOLD`` it is
            the threshold value in thousandths.
        precision_ppm: Self declared reliability of the signal in parts per
            million, ``0..1_000_000``.
    """

    signal_id: str
    tick: int
    agent_id: str
    market_id: str
    kind: SignalKind
    value_milli: int
    precision_ppm: int

    def __post_init__(self) -> None:
        if not 0 <= self.precision_ppm <= PPM_ONE:
            raise InvalidConfigError("precision out of range", signal_id=self.signal_id)

    @property
    def value(self) -> float:
        """The signal value as a float rounded to 3 decimals."""
        return float_from_milli(self.value_milli)

    @property
    def precision(self) -> float:
        """The reliability as a float in ``[0, 1]``."""
        return prob_from_ppm(self.precision_ppm)


@dataclass(frozen=True, slots=True)
class InfoProfile:
    """Information profile assigned to one seat, permuted by the Latin square.

    Attributes:
        kind: Profile family (FR-5.3.2).
        focus_market_ids: For ``SPECIALIST``, the markets the agent is expert
            on. Sorted. Empty for other kinds.
        signals_min: Minimum number of signals per tick, ``>= 0``.
        signals_max: Maximum number of signals per tick, ``<= 2`` by default
            (PRD section 5.7).
        delay_ticks: For ``DELAYED``, how many ticks late signals arrive.
        noise_scale_ppm: Multiplier applied to the base signal noise, in parts
            per million. ``1_000_000`` means the nominal noise level.
    """

    kind: InfoProfileKind
    focus_market_ids: tuple[str, ...] = ()
    signals_min: int = 0
    signals_max: int = 2
    delay_ticks: int = 0
    noise_scale_ppm: int = PPM_ONE

    def __post_init__(self) -> None:
        if self.signals_min < 0 or self.signals_max < self.signals_min:
            raise InvalidConfigError("bad signal count range", kind=str(self.kind))
        if self.delay_ticks < 0:
            raise InvalidConfigError("delay must be >= 0", kind=str(self.kind))


# --------------------------------------------------------------------------
# Agent facing payloads
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PredictionIntent:
    """One validated ``predictions`` entry of an agent action (PRD section 6.2).

    Attributes:
        market_id: Target market.
        p_yes_ppm: Declared probability in parts per million.
    """

    market_id: str
    p_yes_ppm: int

    def __post_init__(self) -> None:
        if not 0 <= self.p_yes_ppm <= PPM_ONE:
            raise InvalidOrderError("p_yes out of range", market_id=self.market_id)


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """One validated ``orders`` entry of an agent action (PRD section 6.2).

    Semantic rules enforced by :mod:`pxe.runner.action_validator`:

    * ``op == "place"`` requires ``market_id``, ``side``, ``order_type`` and
      ``qty``; ``price`` is required when ``order_type`` is ``limit`` and must
      be ``None`` when it is ``market``.
    * ``op == "cancel"`` requires ``order_id`` and ignores every other field.

    Attributes:
        op: ``"place"`` or ``"cancel"``.
        market_id: Target market, ``None`` for a cancel.
        side: Order side, ``None`` for a cancel.
        order_type: Order type, ``None`` for a cancel.
        price: Limit price in cents, ``None`` for a market order or a cancel.
        qty: Quantity in contracts, ``None`` for a cancel.
        order_id: Order to cancel, ``None`` for a place.
    """

    op: str
    market_id: str | None = None
    side: Side | None = None
    order_type: OrderType | None = None
    price: int | None = None
    qty: int | None = None
    order_id: str | None = None

    def __post_init__(self) -> None:
        if self.op not in ("place", "cancel"):
            raise InvalidOrderError("op must be place or cancel", op=self.op)


@dataclass(frozen=True, slots=True)
class AgentAction:
    """A fully validated action of one agent for one tick (PRD section 6.2).

    Attributes:
        agent_id: Acting agent.
        tick: Tick the action belongs to.
        action_version: Schema version echoed by the agent.
        predictions: Validated predictions, sorted by ``market_id``.
        orders: Validated order intents, in the exact order submitted by the
            agent. The engine applies them in that order (P3).
        message_public: Public message, already truncated and escaped, or
            ``None``. Only meaningful when talking mode is on (FR-5.6.1).
        rationale: Optional short reasoning excerpt kept for the decision
            journal (PRD section 9). Never interpreted by the engine.
        source: Where the action came from.
    """

    agent_id: str
    tick: int
    action_version: str
    predictions: tuple[PredictionIntent, ...] = ()
    orders: tuple[OrderIntent, ...] = ()
    message_public: str | None = None
    rationale: str | None = None
    source: AgentSource = AgentSource.SCRIPTED

    @staticmethod
    def no_action(agent_id: str, tick: int, source: AgentSource = AgentSource.FALLBACK) -> "AgentAction":
        """Build the empty action used by the FR-5.1.1 fallback.

        Args:
            agent_id: Agent that failed to answer.
            tick: Current tick.
            source: Usually :attr:`AgentSource.FALLBACK`.

        Returns:
            An action with no predictions, no orders and no message.
        """
        return AgentAction(agent_id=agent_id, tick=tick, action_version=ACTION_VERSION, source=source)


@dataclass(frozen=True, slots=True)
class PublicMessage:
    """A public message posted at tick ``t`` and delivered at tick ``t + 1``.

    Attributes:
        agent_id: Author.
        tick: Tick of posting.
        text: Escaped and truncated text, at most 280 characters (FR-5.6.1).
        deliver_tick: ``tick + 1``.
    """

    agent_id: str
    tick: int
    text: str
    deliver_tick: int


@dataclass(frozen=True, slots=True)
class ObservationLimits:
    """Engine limits echoed inside every observation so agents can self police.

    Attributes:
        max_active_orders_per_market: FR-5.4.2 cap.
        price_min: Lowest tradable price.
        price_max: Highest tradable price.
        market_band_cents: Protection band of ``market`` orders (FR-5.4.3).
        taker_fee_bps: Taker fee in basis points (FR-5.4.7).
        message_max_chars: Public message cap (FR-5.6.1).
        max_orders_per_action: Maximum ``orders`` entries per tick.
    """

    max_active_orders_per_market: int
    price_min: int
    price_max: int
    market_band_cents: int
    taker_fee_bps: int
    message_max_chars: int
    max_orders_per_action: int


@dataclass(frozen=True, slots=True)
class MarketObservation:
    """Per market block of an observation (PRD section 6.1).

    Attributes:
        market_id: Market id.
        question: Human readable question.
        status: ``open`` while tradable.
        prior_price: Public prior in cents (FR-5.2.4).
        resolution_tick: Tick of resolution (FR-5.2.3).
        ref_price: Reference price in cents (FR-5.4.6).
        mid_price: Rounded mid, ``None`` when the book is one sided.
        best_bid: Best bid in cents or ``None``.
        best_ask: Best ask in cents or ``None``.
        bid_depth: Up to :data:`DEPTH_LEVELS` ``(price, qty)`` pairs, best first.
        ask_depth: Up to :data:`DEPTH_LEVELS` ``(price, qty)`` pairs, best first.
        last_price: Last executed price or ``None``.
        ref_history: Reference prices of the last ticks, oldest first.
        position_qty: The agent's signed net position.
        cost_basis_cents: The agent's signed net cash paid on this market.
        my_orders: The agent's resting orders on this market, sorted by
            ``order_id``.
        my_last_prediction_ppm: Last declared or carried probability
            (FR-6.2.4), in parts per million.
    """

    market_id: str
    question: str
    status: MarketStatus
    prior_price: int
    resolution_tick: int
    ref_price: int
    mid_price: int | None
    best_bid: int | None
    best_ask: int | None
    bid_depth: tuple[tuple[int, int], ...]
    ask_depth: tuple[tuple[int, int], ...]
    last_price: int | None
    ref_history: tuple[int, ...]
    position_qty: int
    cost_basis_cents: int
    my_orders: tuple[Order, ...]
    my_last_prediction_ppm: int


@dataclass(frozen=True, slots=True)
class Observation:
    """The complete payload handed to one agent at one tick (PRD section 6.1).

    The concrete JSON encoding is produced by
    :mod:`pxe.runner.observation_builder` and validated against
    ``schemas/observation.v1.json``.

    Attributes:
        obs_version: Schema version.
        match_id: Match id.
        tick: Current tick, 1 based.
        ticks_total: Total number of ticks in the match.
        agent_id: Recipient.
        cash_cents: Total cash.
        reserved_cents: Locked collateral.
        free_cash_cents: ``cash_cents - reserved_cents``.
        equity_cents: Mark to market equity (FR-5.5.4).
        news: Public news of this tick, in publication order.
        signals: Private signals of this tick, in delivery order.
        markets: One block per market, sorted by ``market_id``. Resolved
            markets are dropped from the observation after their resolution
            tick.
        messages: Public messages of the previous tick (FR-5.6.1), sorted by
            ``agent_id``. Empty when talking mode is off.
        limits: Engine limits.
    """

    obs_version: str
    match_id: str
    tick: int
    ticks_total: int
    agent_id: str
    cash_cents: int
    reserved_cents: int
    free_cash_cents: int
    equity_cents: int
    news: tuple[NewsItem, ...]
    signals: tuple[Signal, ...]
    markets: tuple[MarketObservation, ...]
    messages: tuple[PublicMessage, ...]
    limits: ObservationLimits


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class MMConfig:
    """Reference market maker parameters (PRD section 5.8).

    Attributes:
        base_spread_cents: Base spread ``s`` (FR-5.8.1).
        quote_qty: Quoted size ``q`` per side, in contracts.
        inventory_max: ``I_max``, absolute inventory cap per market (FR-5.8.3).
        skew_cents: ``k``, inventory reversion applied at full inventory
            (FR-5.8.3).
        post_news_widen_ticks: ``w``, number of ticks the spread stays widened
            after a high impact news item (FR-5.8.4).
        widen_multiplier: Spread multiplier during the widening window, 2 by
            default (FR-5.8.4).
        enabled: When False the market maker never quotes. Used only by
            degenerate-market tests.
    """

    base_spread_cents: int
    quote_qty: int
    inventory_max: int
    skew_cents: int
    post_news_widen_ticks: int
    widen_multiplier: int = 2
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.base_spread_cents < 1:
            raise InvalidConfigError("spread must be >= 1", spread=self.base_spread_cents)
        if self.quote_qty < 1:
            raise InvalidConfigError("quote size must be >= 1", qty=self.quote_qty)
        if self.inventory_max < 1:
            raise InvalidConfigError("inventory max must be >= 1", i_max=self.inventory_max)
        if self.skew_cents < 0:
            raise InvalidConfigError("skew must be >= 0", skew=self.skew_cents)
        if self.post_news_widen_ticks < 0:
            raise InvalidConfigError("widen window must be >= 0", w=self.post_news_widen_ticks)
        if self.widen_multiplier < 1:
            raise InvalidConfigError("widen multiplier must be >= 1", m=self.widen_multiplier)

    def half_spread_cents(self, *, widened: bool = False) -> int:
        """Half of the effective spread, rounded up so an odd spread never narrows.

        This is a method and not a property on purpose: the post news widening
        of FR-5.8.4 multiplies the spread, and a property reading only
        ``base_spread_cents`` was a trap that silently produced a market maker
        that never widens.

        Args:
            widened: True during the FR-5.8.4 widening window. Callers get it
                from :meth:`ReferenceMarketMaker.is_widened`.

        Returns:
            ``ceil(spread / 2)`` with
            ``spread = base_spread_cents * (widen_multiplier if widened else 1)``.
        """
        spread = self.base_spread_cents * (self.widen_multiplier if widened else 1)
        return (spread + 1) // 2


@dataclass(frozen=True, slots=True)
class LiquidityProfile:
    """A named market maker preset (FR-5.8.6).

    Attributes:
        name: Preset name.
        mm: The market maker configuration of the preset.
    """

    name: LiquidityProfileName
    mm: MMConfig


#: The three presets of FR-5.8.6, in a fixed order.
LIQUIDITY_PROFILES: tuple[LiquidityProfile, ...] = (
    LiquidityProfile(
        name=LiquidityProfileName.LIQUID,
        mm=MMConfig(base_spread_cents=4, quote_qty=50, inventory_max=500, skew_cents=2, post_news_widen_ticks=1),
    ),
    LiquidityProfile(
        name=LiquidityProfileName.STANDARD,
        mm=MMConfig(base_spread_cents=6, quote_qty=25, inventory_max=300, skew_cents=4, post_news_widen_ticks=2),
    ),
    LiquidityProfile(
        name=LiquidityProfileName.ILLIQUID,
        mm=MMConfig(base_spread_cents=12, quote_qty=10, inventory_max=150, skew_cents=8, post_news_widen_ticks=3),
    ),
)


def liquidity_profile(name: str | LiquidityProfileName) -> LiquidityProfile:
    """Look up a liquidity preset by name.

    Args:
        name: ``"liquid"``, ``"standard"`` or ``"illiquid"``.

    Returns:
        The matching :class:`LiquidityProfile`.

    Raises:
        UnknownProfileError: If the name is not one of the three presets.
    """
    wanted = str(name)
    for profile in LIQUIDITY_PROFILES:
        if str(profile.name) == wanted:
            return profile
    raise UnknownProfileError("unknown liquidity profile", name=wanted)


@dataclass(frozen=True, slots=True)
class MatchConfig:
    """Everything the engine needs to run one match, PRD section 5.7 defaults.

    Every field is part of the journal: ``MatchStarted.config`` is exactly
    ``config_to_journal_dict(config)``. Changing a default changes the hash of
    every replay, so bump :data:`ENGINE_VERSION` when you do.

    **No field of this class may be a float.** The journal encoder rejects
    floats structurally, so a float here would crash the first event of every
    match. Wall clock and cost settings live in :class:`GatewayConfig`, which is
    never journalled. ``tests/test_types.py::test_match_config_is_journal_encodable``
    pins this.

    Attributes:
        seed: Unsigned 64 bit root seed of the match. It defaults to ``0`` so
            that ``MatchConfig()`` is constructible with no argument, which is
            what the determinism tests and ``config_from_journal_dict`` rely on;
            every real caller passes an explicit seed.
        ticks_total: Number of ticks ``T``, 24 to 96.
        n_agents: Number of ranked agents, 4 to 8.
        n_markets: Number of markets in the world, 2 to 8 (FR-5.2.1). The
            runner asserts ``len(scenario.markets) == n_markets``.
        initial_cash_cents: Starting cash of every agent, in cents. The PRD's
            "10 000" is read as 10 000 contract units, hence 1 000 000 cents.
        mm_initial_cash_cents: Starting cash of the ``MM`` account. Defaults to
            ten times an agent's cash so the market maker is never the binding
            liquidity constraint (FR-5.8.5). It enters invariant I2 and is the
            baseline of ``mm_pnl_cents``, the published cost of liquidity.
        taker_fee_bps: Taker fee in basis points, 0 to 200 (FR-5.4.7).
        max_active_orders_per_market: FR-5.4.2 cap, 5 to 20.
        market_band_cents: Protection band of ``market`` orders, 5 to 20
            (FR-5.4.3).
        ref_history_len: Number of past reference prices exposed in the
            observation sparkline, ``0..REF_HISTORY_MAX``. The schema's
            ``maxItems`` is the hard ceiling and this may only lower it.
        talking_mode: FR-5.6.1 flag, off by default. Authoritative: the copy on
            :class:`ScenarioSpec` is informational and must agree.
        message_max_chars: Public message cap, ``0..MESSAGE_MAX_CHARS_CEILING``.
            The action schema's ``maxLength`` is the hard ceiling and this may
            only lower it (FR-5.6.1).
        max_orders_per_action: Maximum ``orders`` entries accepted per tick,
            ``1..MAX_ORDERS_PER_ACTION_CEILING``. The ceiling exists because
            ``schemas/action.v1.json`` hard codes it as ``maxItems`` and that
            file is handed verbatim to the provider CLI.
        mm: Market maker parameters. Authoritative over the scenario's preset
            name.
        liquidity_profile_name: Name of the preset ``mm`` came from.
        bankruptcy_free_cash_floor_cents: Free cash at or below which an agent
            that also holds no resting order is frozen (FR-5.5.5, "cash et
            collateral libres epuises"). This is the reachable bankruptcy gate.
        bankruptcy_equity_floor_cents: Equity at or below which an agent is
            frozen. Given I4 and I9 this is a defensive backstop that normally
            never fires; it is kept as a tripwire, not as the main rule.
        obs_version: Observation schema version.
        action_version: Action schema version.
        engine_version: Engine version stamped into the journal.
    """

    seed: int = 0
    ticks_total: int = 48
    n_agents: int = 6
    n_markets: int = 5
    initial_cash_cents: int = 1_000_000
    mm_initial_cash_cents: int = 10_000_000
    taker_fee_bps: int = 0
    max_active_orders_per_market: int = 10
    market_band_cents: int = 10
    ref_history_len: int = 12
    talking_mode: bool = False
    message_max_chars: int = 280
    max_orders_per_action: int = 20
    mm: MMConfig = field(default_factory=lambda: LIQUIDITY_PROFILES[1].mm)
    liquidity_profile_name: LiquidityProfileName = LiquidityProfileName.STANDARD
    bankruptcy_free_cash_floor_cents: int = 0
    bankruptcy_equity_floor_cents: int = 0
    obs_version: str = OBS_VERSION
    action_version: str = ACTION_VERSION
    engine_version: str = ENGINE_VERSION

    def __post_init__(self) -> None:
        if not 0 <= self.seed < SEED_SPACE:
            raise InvalidConfigError("seed must fit in 63 unsigned bits", seed=self.seed)
        if not 24 <= self.ticks_total <= 96:
            raise InvalidConfigError("ticks_total out of range", ticks_total=self.ticks_total)
        if not 4 <= self.n_agents <= 8:
            raise InvalidConfigError("n_agents out of range", n_agents=self.n_agents)
        if not 2 <= self.n_markets <= 8:
            raise InvalidConfigError("n_markets out of range", n_markets=self.n_markets)
        if self.initial_cash_cents < 1:
            raise InvalidConfigError("initial cash must be >= 1", cash=self.initial_cash_cents)
        if self.mm_initial_cash_cents < self.initial_cash_cents:
            raise InvalidConfigError(
                "market maker cash must be >= an agent's cash",
                mm_cash=self.mm_initial_cash_cents,
                agent_cash=self.initial_cash_cents,
            )
        if not 0 <= self.taker_fee_bps <= 200:
            raise InvalidConfigError("taker fee out of range", bps=self.taker_fee_bps)
        if not 5 <= self.max_active_orders_per_market <= 20:
            raise InvalidConfigError("order cap out of range", cap=self.max_active_orders_per_market)
        if not 5 <= self.market_band_cents <= 20:
            raise InvalidConfigError("protection band out of range", band=self.market_band_cents)
        if not 0 <= self.ref_history_len <= REF_HISTORY_MAX:
            raise InvalidConfigError(
                "ref history length must be in [0, REF_HISTORY_MAX]",
                n=self.ref_history_len,
                ceiling=REF_HISTORY_MAX,
            )
        if not 0 <= self.message_max_chars <= MESSAGE_MAX_CHARS_CEILING:
            raise InvalidConfigError(
                "message length must be in [0, MESSAGE_MAX_CHARS_CEILING]",
                n=self.message_max_chars,
                ceiling=MESSAGE_MAX_CHARS_CEILING,
            )
        if not 1 <= self.max_orders_per_action <= MAX_ORDERS_PER_ACTION_CEILING:
            raise InvalidConfigError(
                "max orders per action must be in [1, MAX_ORDERS_PER_ACTION_CEILING]",
                n=self.max_orders_per_action,
                ceiling=MAX_ORDERS_PER_ACTION_CEILING,
            )
        if self.bankruptcy_free_cash_floor_cents < 0 or self.bankruptcy_equity_floor_cents < 0:
            raise InvalidConfigError("bankruptcy floors must be >= 0")


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    """A generated world, fully derived from ``seed`` (PRD section 5.2).

    Attributes:
        template_id: World template identifier, for example ``"election"``.
        template_version: Version of the template, part of the journal.
        seed: Seed the world was drawn from.
        ticks_total: Number of ticks.
        markets: Market definitions, sorted by ``market_id``.
        correlations: Ordered ``(market_a, market_b, rho_milli)`` triples
            describing the pairwise latent correlations (FR-5.2.1), sorted by
            ``(market_a, market_b)``.
        cancellations: Ordered ``(tick, market_id, reason)`` triples, sorted by
            ``(tick, market_id)``. This is the **only** way a market can be
            cancelled (FR-5.4.5: "un marche ne peut etre annule que par le
            script du scenario"). The oracle serves them through
            ``due_cancellations(tick)``.
        talking_mode: Informational copy of :attr:`MatchConfig.talking_mode`.
            The runner refuses to start when the two disagree.
        liquidity_profile_name: Informational copy of
            :attr:`MatchConfig.liquidity_profile_name`, same rule.
        held_out: True when the scenario comes from the sealed bank (PRD section 8).
        notes: Free form description used by reports and the UI.
    """

    template_id: str
    template_version: str
    seed: int
    ticks_total: int
    markets: tuple[MarketSpec, ...]
    correlations: tuple[tuple[str, str, int], ...] = ()
    cancellations: tuple[tuple[int, str, str], ...] = ()
    talking_mode: bool = False
    liquidity_profile_name: LiquidityProfileName = LiquidityProfileName.STANDARD
    held_out: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if not 2 <= len(self.markets) <= 8:
            raise InvalidConfigError("a world holds 2 to 8 markets", n=len(self.markets))
        ids = [m.market_id for m in self.markets]
        if ids != sorted(ids, key=lambda mid: int(mid[1:])):
            raise InvalidConfigError("markets must be sorted by index", ids=ids)
        if len(set(ids)) != len(ids):
            raise InvalidConfigError("duplicate market id", ids=ids)
        for market in self.markets:
            if market.resolution_tick > self.ticks_total:
                raise InvalidConfigError(
                    "resolution tick beyond horizon",
                    market_id=market.market_id,
                    tick=market.resolution_tick,
                )
        known = set(ids)
        seen: list[tuple[int, str]] = []
        for tick, market_id, _reason in self.cancellations:
            if market_id not in known:
                raise InvalidConfigError("cancellation of an unknown market", market_id=market_id)
            if not 1 <= tick <= self.ticks_total:
                raise InvalidConfigError("cancellation tick out of range", market_id=market_id, tick=tick)
            if tick > self.market(market_id).resolution_tick:
                raise InvalidConfigError(
                    "cancellation after resolution",
                    market_id=market_id,
                    tick=tick,
                )
            seen.append((tick, market_id))
        if seen != sorted(seen, key=lambda pair: (pair[0], _id_sort_key(pair[1]))):
            raise InvalidConfigError("cancellations must be sorted by (tick, market_id)")
        if len({mid for _t, mid in seen}) != len(seen):
            raise InvalidConfigError("a market may be cancelled at most once")

    def market(self, market_id: str) -> MarketSpec:
        """Return the spec of ``market_id``.

        Args:
            market_id: Market id.

        Returns:
            The :class:`MarketSpec`.

        Raises:
            InvalidConfigError: If the market is unknown.
        """
        for market in self.markets:
            if market.market_id == market_id:
                return market
        raise InvalidConfigError("unknown market", market_id=market_id)


@dataclass(frozen=True, slots=True)
class HarnessConfig:
    """Versioned definition of an agent's brain (PRD section 4, glossary).

    Attributes:
        harness_id: Stable identifier, for example ``"sonnet5-baseline"``.
        version: Semantic version of the harness.
        kind: ``"scripted"`` or ``"llm"``.
        model: Provider model id, ``"claude-sonnet-5"`` for the CLI gateway.
            Empty for scripted agents.
        system_prompt: System prompt handed to the provider. Empty for scripted
            agents.
        params: Ordered ``(key, value)`` pairs of extra parameters. Kept as a
            tuple so hashing is order stable.
        config_hash: 16 hex characters of a blake2b digest over the canonical
            JSON of ``{harness_id, version, kind, model, system_prompt,
            params}``. Filled automatically by :meth:`__post_init__` when left
            empty, so it is never the empty string in a journal. This is the
            "hash config+prompt" of WBS task T3.4, and it is what makes a
            frozen Hall of Fame version replayable.
    """

    harness_id: str
    version: str
    kind: str
    model: str = ""
    system_prompt: str = ""
    params: tuple[tuple[str, str], ...] = ()
    config_hash: str = ""

    def __post_init__(self) -> None:
        if not self.harness_id or not self.version:
            raise InvalidConfigError("harness_id and version are mandatory", harness_id=self.harness_id)
        if self.kind not in ("scripted", "llm"):
            raise InvalidConfigError("harness kind must be scripted or llm", kind=self.kind)
        keys = [k for k, _v in self.params]
        if keys != sorted(keys):
            raise InvalidConfigError("harness params must be sorted by key", harness_id=self.harness_id)
        if not self.config_hash:
            object.__setattr__(self, "config_hash", harness_config_hash(self))

    @property
    def key(self) -> str:
        """The harness key used by ratings, elites and tournaments."""
        return harness_key(self)


@dataclass(frozen=True, slots=True)
class GatewayConfig:
    """Runtime budget and reliability settings of the agent gateway.

    None of these fields ever reaches the journal: they are wall clock and cost
    dependent and would break AC-P1.

    Attributes:
        timeout_s: Per call timeout in seconds.
        retries: Number of retries before falling back to "no action"
            (FR-5.1.1).
        max_budget_usd_per_call: Cap passed to the provider CLI.
        max_budget_usd_per_match: Cap enforced by the gateway across a match.
        max_budget_usd_per_tournament: Cap enforced by the orchestrator.
        max_input_tokens_per_call: FR-6.2.3 token budget, input side. A call
            whose prompt is estimated above this is refused before it is sent.
        max_output_tokens_per_call: FR-6.2.3 token budget, output side. Passed
            to the provider and enforced by :class:`BudgetTracker`.
        max_tokens_per_match: Cumulative input plus output token cap for one
            match, per agent. ``0`` disables the cumulative cap.
        max_parallel_calls: Number of concurrent provider calls.
        trace_dir: Directory receiving provider traces, separate from the
            journal.
    """

    timeout_s: float = 60.0
    retries: int = 2
    max_budget_usd_per_call: float = 0.10
    max_budget_usd_per_match: float = 5.0
    max_budget_usd_per_tournament: float = 200.0
    max_input_tokens_per_call: int = 8_192
    max_output_tokens_per_call: int = 2_048
    max_tokens_per_match: int = 0
    max_parallel_calls: int = 6
    trace_dir: str = "runs/traces"


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """One seat at the table of a match.

    Attributes:
        agent_id: Seat id ``A1``..``A8``, or ``MM`` for the market maker.
        harness: The harness occupying the seat.
        info_profile: The information profile assigned to the seat
            (FR-5.3.2).
        ranked: False for the reference market maker (FR-5.8.5).
    """

    agent_id: str
    harness: HarnessConfig
    info_profile: InfoProfile
    ranked: bool = True

    def __post_init__(self) -> None:
        if not RE_SEAT_ID.match(self.agent_id):
            raise InvalidConfigError("bad seat id", agent_id=self.agent_id)
        if self.agent_id == MM_ACCOUNT_ID and self.ranked:
            raise InvalidConfigError("the market maker is never ranked (FR-5.8.5)")


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class MatchRanking:
    """One line of the final ranking, computed after settlement (FR-5.5.4).

    Attributes:
        rank: 1 based rank, ties share the lowest rank.
        agent_id: Ranked agent.
        pnl_cents: ``final_cash_cents - initial_cash_cents``.
        final_cash_cents: Cash after the last settlement.
        pnl_pct_bps: PnL as basis points of the initial capital, computed with
            :func:`bps_ratio` so a gain and the mirror loss report the same
            magnitude.

    Note:
        There is deliberately **no** ``brier_ppm`` here. The Brier score is
        owned by :mod:`pxe.metrics.calibration`, which is strictly downstream of
        the runner; putting it on the ranking would force the runner to import
        a metrics module (a dependency inversion) or to reimplement the metric
        (two definitions of the headline calibration number, which AC-P4
        forbids). The report joins the two.
    """

    rank: int
    agent_id: str
    pnl_cents: int
    final_cash_cents: int
    pnl_pct_bps: int


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Everything a caller needs after a match completed.

    Attributes:
        match_id: Match id.
        seed: Root seed.
        scenario: The world that was played.
        rankings: Final ranking, best first. Excludes ``MM`` and ``FEES``.
        journal_path: Path of the written journal file.
        journal_hash: blake2b-256 hex digest of the journal (see
            :func:`pxe.events.journal_hash`).
        event_count: Number of events in the journal.
        mm_pnl_cents: Reference market maker PnL, the published cost of
            liquidity (FR-5.8.5).
        fees_collected_cents: Cash sitting in the ``FEES`` account.

    Note:
        There is deliberately **no** ``incident_count``. Integrity detectors run
        offline over a finished journal and write
        ``runs/<match_id>/incidents.jsonl``; the runner cannot know the count
        while the match is still running, and making it try would put a
        detector version inside a match artefact.
    """

    match_id: str
    seed: int
    scenario: ScenarioSpec
    rankings: tuple[MatchRanking, ...]
    journal_path: str
    journal_hash: str
    event_count: int
    mm_pnl_cents: int
    fees_collected_cents: int


@dataclass(frozen=True, slots=True)
class Incident:
    """An integrity alert produced by a detector (PRD section 7.5).

    Attributes:
        incident_id: ``i-0001`` style id.
        kind: Detector family.
        severity: ``"low"``, ``"medium"`` or ``"high"``.
        tick: Tick the alert points at, or the last tick of the window.
        agent_ids: Implicated agents, sorted.
        market_ids: Implicated markets, sorted.
        score_ppm: Detector score in parts per million, comparable to the
            detector threshold.
        detail: Ordered ``(key, value)`` pairs of detector specific evidence.
            Values must be JSON scalars, never floats.
        detector_version: Version of the detector that raised the alert.
        match_id: The match the alert belongs to, or ``""`` when the producer
            has not stamped it. It is last and defaulted because a detector
            works from a :class:`~pxe.metrics.projection.MatchProjection` and
            already knows the match, while the file the alert lands in
            (``runs/<match_id>/incidents.jsonl``) carries the same value in its
            directory name. It exists because
            ``Store.load_incidents(tournament_id=...)`` returns alerts from many
            matches at once and section 7.21's ``Incident`` payload has a
            ``match_id``: without a field here the API could only serve an empty
            string, and the UI could not link an alert to its replay.
    """

    incident_id: str
    kind: IncidentKind
    severity: str
    tick: int
    agent_ids: tuple[str, ...]
    market_ids: tuple[str, ...]
    score_ppm: int
    detail: tuple[tuple[str, Any], ...]
    detector_version: str
    match_id: str = ""


def sorted_ids(ids: Sequence[str]) -> tuple[str, ...]:
    """Return market or agent ids in canonical order (section 2.3).

    Market and agent ids sort by their numeric suffix, so ``M10`` follows
    ``M9``. Any other id sorts lexicographically.

    This function must **never** be used on account ids. Lexicographic ordering
    would place ``FEES`` before ``MM``, which is not the canonical account order
    and would silently produce a different journal byte stream. Passing
    ``MM`` or ``FEES`` is therefore an error, not a fallback: use
    :func:`sorted_account_ids`.

    Args:
        ids: Sequence of market ids or agent ids.

    Returns:
        A sorted tuple.

    Raises:
        InvalidConfigError: If ``MM`` or ``FEES`` appears in ``ids``.
    """
    for value in ids:
        if value in (MM_ACCOUNT_ID, FEES_ACCOUNT_ID):
            raise InvalidConfigError(
                "sorted_ids is for markets and ranked agents only; "
                "account ids go through sorted_account_ids (section 2.3)",
                id=value,
            )

    return tuple(sorted(ids, key=_id_sort_key))


#: Rank of the two reserved accounts in the canonical account order. Ranked
#: agents share rank 0 and are then ordered by their numeric suffix.
_ACCOUNT_RANK: Mapping[str, int] = {MM_ACCOUNT_ID: 1, FEES_ACCOUNT_ID: 2}


def sorted_account_ids(ids: Sequence[str]) -> tuple[str, ...]:
    """Return account ids in **the** canonical account order (section 2.3).

    The order is: ranked agents by ascending numeric suffix (``A1`` .. ``A8``),
    then ``MM``, then ``FEES``. It is normative and there is exactly one
    implementation, this one. ``AccountBook.account_ids`` returns exactly this,
    and every per account event loop (``SettlementApplied``,
    ``PositionSnapshot``) walks exactly this, so the order is literally the
    journal byte order and therefore part of the AC-P1 hash.

    Args:
        ids: Account ids: ranked agents, ``MM`` and/or ``FEES``. Duplicates are
            preserved; unknown ids are rejected.

    Returns:
        The ids in canonical account order.

    Raises:
        InvalidConfigError: If an id is neither ``A<n>`` nor ``MM`` nor
            ``FEES``.
    """
    for value in ids:
        if not RE_ACCOUNT_ID.match(value):
            raise InvalidConfigError("not an account id", id=value)

    def key(value: str) -> tuple[int, int]:
        rank = _ACCOUNT_RANK.get(value, 0)
        return (rank, int(value[1:]) if rank == 0 else 0)

    return tuple(sorted(ids, key=key))


# --------------------------------------------------------------------------
# Journal encoding of the configuration
#
# ``MatchStarted.config`` is exactly ``config_to_journal_dict(config)``. There
# is one encoder and one decoder, here, so A02 (journal), A09 (runner) and A22
# (API) cannot each invent a shape. Both are pure and total: they contain no
# float, so the result is always accepted by ``pxe.events.canonical_json``.
# --------------------------------------------------------------------------
def config_to_journal_dict(config: "MatchConfig") -> dict[str, Any]:
    """Encode a :class:`MatchConfig` for ``MatchStarted.config``.

    The result contains only ``int``, ``str`` and ``bool`` values plus one
    nested mapping for the market maker block, so
    :func:`pxe.events.canonical_json` accepts it by construction. Enumerations
    become their string value.

    Args:
        config: The match configuration.

    Returns:
        A JSON compatible mapping, float free.
    """
    return {
        "seed": int(config.seed),
        "ticks_total": int(config.ticks_total),
        "n_agents": int(config.n_agents),
        "n_markets": int(config.n_markets),
        "initial_cash_cents": int(config.initial_cash_cents),
        "mm_initial_cash_cents": int(config.mm_initial_cash_cents),
        "taker_fee_bps": int(config.taker_fee_bps),
        "max_active_orders_per_market": int(config.max_active_orders_per_market),
        "market_band_cents": int(config.market_band_cents),
        "ref_history_len": int(config.ref_history_len),
        "talking_mode": bool(config.talking_mode),
        "message_max_chars": int(config.message_max_chars),
        "max_orders_per_action": int(config.max_orders_per_action),
        "bankruptcy_free_cash_floor_cents": int(config.bankruptcy_free_cash_floor_cents),
        "bankruptcy_equity_floor_cents": int(config.bankruptcy_equity_floor_cents),
        "liquidity_profile_name": str(config.liquidity_profile_name),
        "obs_version": str(config.obs_version),
        "action_version": str(config.action_version),
        "engine_version": str(config.engine_version),
        "mm": {
            "base_spread_cents": int(config.mm.base_spread_cents),
            "quote_qty": int(config.mm.quote_qty),
            "inventory_max": int(config.mm.inventory_max),
            "skew_cents": int(config.mm.skew_cents),
            "post_news_widen_ticks": int(config.mm.post_news_widen_ticks),
            "widen_multiplier": int(config.mm.widen_multiplier),
            "enabled": bool(config.mm.enabled),
        },
    }


def config_from_journal_dict(data: Mapping[str, Any]) -> "MatchConfig":
    """Rebuild a :class:`MatchConfig` from ``MatchStarted.config``.

    This is the inverse of :func:`config_to_journal_dict` and is what makes
    FR-5.1.3 ("the journal alone replays a match") implementable:
    ``replay_journal`` cannot rebuild a :class:`MatchState` without it.

    Args:
        data: The mapping stored in ``MatchStarted.config``.

    Returns:
        The reconstructed configuration.

    Raises:
        InvalidConfigError: If a key is missing or a value is out of range.
    """
    try:
        mm_data = data["mm"]
        mm = MMConfig(
            base_spread_cents=int(mm_data["base_spread_cents"]),
            quote_qty=int(mm_data["quote_qty"]),
            inventory_max=int(mm_data["inventory_max"]),
            skew_cents=int(mm_data["skew_cents"]),
            post_news_widen_ticks=int(mm_data["post_news_widen_ticks"]),
            widen_multiplier=int(mm_data["widen_multiplier"]),
            enabled=bool(mm_data["enabled"]),
        )
        return MatchConfig(
            seed=int(data["seed"]),
            ticks_total=int(data["ticks_total"]),
            n_agents=int(data["n_agents"]),
            n_markets=int(data["n_markets"]),
            initial_cash_cents=int(data["initial_cash_cents"]),
            mm_initial_cash_cents=int(data["mm_initial_cash_cents"]),
            taker_fee_bps=int(data["taker_fee_bps"]),
            max_active_orders_per_market=int(data["max_active_orders_per_market"]),
            market_band_cents=int(data["market_band_cents"]),
            ref_history_len=int(data["ref_history_len"]),
            talking_mode=bool(data["talking_mode"]),
            message_max_chars=int(data["message_max_chars"]),
            max_orders_per_action=int(data["max_orders_per_action"]),
            mm=mm,
            liquidity_profile_name=LiquidityProfileName(str(data["liquidity_profile_name"])),
            bankruptcy_free_cash_floor_cents=int(data["bankruptcy_free_cash_floor_cents"]),
            bankruptcy_equity_floor_cents=int(data["bankruptcy_equity_floor_cents"]),
            obs_version=str(data["obs_version"]),
            action_version=str(data["action_version"]),
            engine_version=str(data["engine_version"]),
        )
    except KeyError as exc:
        raise InvalidConfigError("missing key in journalled config", key=str(exc.args[0])) from exc


# --------------------------------------------------------------------------
# Journal encoding of the scenario
#
# ``MatchStarted.markets`` is exactly ``[market_spec_to_dict(m) for m in
# scenario.markets]``. There is one encoder and one decoder, here, so A02, A09,
# A15 and A22 cannot each invent a shape. Both are float free.
# --------------------------------------------------------------------------
def market_spec_to_dict(spec: "MarketSpec") -> dict[str, Any]:
    """Encode a :class:`MarketSpec` for ``MatchStarted.markets``.

    Args:
        spec: The market definition.

    Returns:
        A JSON compatible mapping holding only ``int``, ``str`` and ``list``.
    """
    return {
        "market_id": str(spec.market_id),
        "question": str(spec.question),
        "prior_price": int(spec.prior_price),
        "resolution_tick": int(spec.resolution_tick),
        "latent_key": str(spec.latent_key),
        "correlation_group": str(spec.correlation_group),
        "tags": [str(tag) for tag in spec.tags],
    }


def market_spec_from_dict(data: Mapping[str, Any]) -> "MarketSpec":
    """Rebuild a :class:`MarketSpec` from one ``MatchStarted.markets`` entry.

    Args:
        data: One entry of ``MatchStarted.markets``.

    Returns:
        The reconstructed spec.

    Raises:
        InvalidConfigError: If a key is missing or a value is out of range.
    """
    try:
        return MarketSpec(
            market_id=str(data["market_id"]),
            question=str(data["question"]),
            prior_price=int(data["prior_price"]),
            resolution_tick=int(data["resolution_tick"]),
            latent_key=str(data["latent_key"]),
            correlation_group=str(data.get("correlation_group", "")),
            tags=tuple(str(tag) for tag in data.get("tags", ())),
        )
    except KeyError as exc:
        raise InvalidConfigError("missing key in journalled market", key=str(exc.args[0])) from exc


def scenario_to_journal_dict(scenario: "ScenarioSpec") -> dict[str, Any]:
    """Encode a :class:`ScenarioSpec` as a float free mapping.

    Used by :mod:`pxe.store` and by report tooling. ``MatchStarted`` itself
    carries only the subset an engine replay needs (``scenario_template_id``,
    ``scenario_template_version``, ``ticks_total``, ``seed`` and ``markets``);
    see :func:`scenario_from_match_started`.

    Args:
        scenario: The generated world specification.

    Returns:
        A JSON compatible mapping, float free.
    """
    return {
        "template_id": str(scenario.template_id),
        "template_version": str(scenario.template_version),
        "seed": int(scenario.seed),
        "ticks_total": int(scenario.ticks_total),
        "markets": [market_spec_to_dict(m) for m in scenario.markets],
        "correlations": [[str(a), str(b), int(rho)] for a, b, rho in scenario.correlations],
        "cancellations": [[int(t), str(mid), str(reason)] for t, mid, reason in scenario.cancellations],
        "talking_mode": bool(scenario.talking_mode),
        "liquidity_profile_name": str(scenario.liquidity_profile_name),
        "held_out": bool(scenario.held_out),
        "notes": str(scenario.notes),
    }


def scenario_from_journal_dict(data: Mapping[str, Any]) -> "ScenarioSpec":
    """Inverse of :func:`scenario_to_journal_dict`.

    Args:
        data: A mapping produced by :func:`scenario_to_journal_dict`.

    Returns:
        The reconstructed scenario.

    Raises:
        InvalidConfigError: If a key is missing or a value is out of range.
    """
    try:
        return ScenarioSpec(
            template_id=str(data["template_id"]),
            template_version=str(data["template_version"]),
            seed=int(data["seed"]),
            ticks_total=int(data["ticks_total"]),
            markets=tuple(market_spec_from_dict(m) for m in data["markets"]),
            correlations=tuple((str(a), str(b), int(rho)) for a, b, rho in data.get("correlations", ())),
            cancellations=tuple((int(t), str(mid), str(r)) for t, mid, r in data.get("cancellations", ())),
            talking_mode=bool(data.get("talking_mode", False)),
            liquidity_profile_name=LiquidityProfileName(
                str(data.get("liquidity_profile_name", LiquidityProfileName.STANDARD))
            ),
            held_out=bool(data.get("held_out", False)),
            notes=str(data.get("notes", "")),
        )
    except KeyError as exc:
        raise InvalidConfigError("missing key in journalled scenario", key=str(exc.args[0])) from exc


# --------------------------------------------------------------------------
# Journal and wire encoding of agent intents
#
# There are two shapes and they are not the same shape:
#
# * the **wire** shape is ``schemas/action.v1.json``, which the provider CLI
#   validates. It carries ``p_yes`` as a float in ``[0, 1]``.
# * the **journal** shape is ``AgentActionReceived.predictions`` /
#   ``.orders``, which must be float free (section 3.5). It carries
#   ``p_yes_ppm`` as an integer.
#
# Order items are identical in both shapes, and the key is ``type``, the
# spelling of ``schemas/action.v1.json``, never ``order_type``.
# --------------------------------------------------------------------------
def order_intent_to_dict(intent: "OrderIntent") -> dict[str, Any]:
    """Encode one :class:`OrderIntent` for the wire and for the journal.

    Every key of ``schemas/action.v1.json`` is present, with ``None`` for the
    fields that do not apply: dropping them would make the journal shape differ
    from the wire shape and would break the strict provider schema.

    Args:
        intent: The validated order intent.

    Returns:
        A JSON compatible mapping with the seven keys ``op``, ``market_id``,
        ``side``, ``type``, ``price``, ``qty``, ``order_id``.
    """
    return {
        "op": str(intent.op),
        "market_id": None if intent.market_id is None else str(intent.market_id),
        "side": None if intent.side is None else str(intent.side),
        "type": None if intent.order_type is None else str(intent.order_type),
        "price": None if intent.price is None else int(intent.price),
        "qty": None if intent.qty is None else int(intent.qty),
        "order_id": None if intent.order_id is None else str(intent.order_id),
    }


def order_intent_from_dict(data: Mapping[str, Any]) -> "OrderIntent":
    """Inverse of :func:`order_intent_to_dict`.

    Args:
        data: One entry of ``orders``, in either shape.

    Returns:
        The reconstructed intent.
    """
    side = data.get("side")
    order_type = data.get("type")
    price = data.get("price")
    qty = data.get("qty")
    return OrderIntent(
        op=str(data["op"]),
        market_id=None if data.get("market_id") is None else str(data["market_id"]),
        side=None if side is None else Side(str(side)),
        order_type=None if order_type is None else OrderType(str(order_type)),
        price=None if price is None else int(price),
        qty=None if qty is None else int(qty),
        order_id=None if data.get("order_id") is None else str(data["order_id"]),
    )


def prediction_intent_to_dict(intent: "PredictionIntent") -> dict[str, Any]:
    """Encode one :class:`PredictionIntent` for the **journal** (float free).

    Args:
        intent: The validated prediction intent.

    Returns:
        ``{"market_id": str, "p_yes_ppm": int}``.
    """
    return {"market_id": str(intent.market_id), "p_yes_ppm": int(intent.p_yes_ppm)}


def prediction_intent_to_wire_dict(intent: "PredictionIntent") -> dict[str, Any]:
    """Encode one :class:`PredictionIntent` for ``schemas/action.v1.json``.

    Args:
        intent: The validated prediction intent.

    Returns:
        ``{"market_id": str, "p_yes": float}``. The float never enters a
        journal: only :func:`prediction_intent_to_dict` does.
    """
    return {"market_id": str(intent.market_id), "p_yes": prob_from_ppm(intent.p_yes_ppm)}


def action_to_payload(action: "AgentAction") -> dict[str, Any]:
    """Encode an :class:`AgentAction` in the ``schemas/action.v1.json`` shape.

    This is what a scripted gateway puts in ``AgentReply.raw`` so that scripted
    and LLM agents reach ``validate_action`` through exactly the same door
    (section 7.16). It contains floats and must never be journalled.

    Args:
        action: The action to encode.

    Returns:
        A payload that validates against ``schemas/action.v1.json``.
    """
    return {
        "action_version": str(action.action_version),
        "predictions": [prediction_intent_to_wire_dict(p) for p in action.predictions],
        "orders": [order_intent_to_dict(o) for o in action.orders],
        "message_public": action.message_public,
        "rationale": action.rationale,
    }


def action_to_journal_dict(action: "AgentAction", *, n_rejected: int = 0) -> dict[str, Any]:
    """Encode an :class:`AgentAction` as the ``AgentActionReceived`` payload.

    Float free by construction: probabilities are ``p_yes_ppm`` integers. This
    is the one and only producer of that payload, so A09 and A13 cannot spell
    the keys differently and move the journal hash.

    Args:
        action: The surviving action after validation.
        n_rejected: Number of items already reported by ``AgentActionRejected``
            events for this agent and tick.

    Returns:
        A mapping holding ``agent_id``, ``action_version``, ``source``,
        ``predictions``, ``orders``, ``message_public``, ``rationale`` and
        ``n_rejected``.
    """
    return {
        "agent_id": str(action.agent_id),
        "action_version": str(action.action_version),
        "source": str(action.source),
        "predictions": [prediction_intent_to_dict(p) for p in action.predictions],
        "orders": [order_intent_to_dict(o) for o in action.orders],
        "message_public": action.message_public,
        "rationale": action.rationale,
        "n_rejected": int(n_rejected),
    }


# --------------------------------------------------------------------------
# Harness identity (T3.4)
# --------------------------------------------------------------------------
def harness_config_hash(harness: "HarnessConfig") -> str:
    """Return the stable content hash of a harness, 16 hex characters.

    blake2b-256 over the canonical JSON of ``harness_id``, ``version``,
    ``kind``, ``model``, ``system_prompt`` and ``params``, truncated to 16 hex
    characters. ``config_hash`` itself is excluded, so the function is
    idempotent. This is the "hash config+prompt" of WBS task T3.4: two harnesses
    with the same hash are the same brain and replay identically.

    Args:
        harness: The harness definition.

    Returns:
        16 lowercase hex characters.
    """
    payload = json.dumps(
        {
            "harness_id": harness.harness_id,
            "version": harness.version,
            "kind": harness.kind,
            "model": harness.model,
            "system_prompt": harness.system_prompt,
            "params": [[k, v] for k, v in harness.params],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=32).hexdigest()[:16]


def harness_key(harness: "HarnessConfig") -> str:
    """Return the tournament wide identity of a harness (section 2.2).

    The format is ``<harness_id>@<version>+<config_hash first 8 chars>``. The
    hash suffix is what stops two different prompts shipped under the same
    version tag from sharing a TrueSkill rating, a MAP-Elites cell or a Hall of
    Fame slot.

    Args:
        harness: The harness definition.

    Returns:
        The harness key.
    """
    digest = harness.config_hash or harness_config_hash(harness)
    return f"{harness.harness_id}@{harness.version}+{digest[:8]}"


# --------------------------------------------------------------------------
# Error code mapping
# --------------------------------------------------------------------------
def reject_reason_of(error: PxeError) -> RejectReason:
    """Map an exception onto the :class:`RejectReason` written to the journal.

    Section 2.4 promises that every ``code`` that can appear in a journal is a
    :class:`RejectReason` member. This function is that promise made
    executable, and ``tests/test_types.py::test_every_exchange_error_maps``
    walks every :class:`~pxe.errors.ExchangeError` subclass through it.

    Args:
        error: The raised error.

    Returns:
        The matching reject reason.

    Raises:
        InvalidConfigError: If the code has no reason. That is a contract bug,
            never an agent behaviour: add the member.
    """
    try:
        return RejectReason(error.code)
    except ValueError as exc:
        raise InvalidConfigError(
            "no RejectReason for this error code (section 2.4)",
            code=error.code,
            error=type(error).__name__,
        ) from exc


# --------------------------------------------------------------------------
# Incident detail: one shape in Python, one encoding in JSON
# --------------------------------------------------------------------------
def incident_detail_to_dict(detail: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    """Encode :attr:`Incident.detail` for ``IncidentRaised.detail``.

    :class:`Incident` carries ``detail`` as an ordered tuple of pairs, because
    that is the shape a detector builds and compares. ``IncidentRaised`` carries
    it as a mapping, because ``canonical_json`` sorts object keys and therefore
    makes the mapping byte stable anyway. These two functions are the only legal
    crossing between the two shapes, so A18 never writes a conversion of its
    own.

    Args:
        detail: Ordered ``(key, value)`` pairs. Keys must be unique.

    Returns:
        The equivalent mapping.

    Raises:
        InvalidConfigError: On a duplicate key, which the mapping would silently
            collapse.
    """
    out: dict[str, Any] = {}
    for key, value in detail:
        if key in out:
            raise InvalidConfigError("duplicate key in incident detail", key=key)
        out[str(key)] = value
    return out


def incident_detail_from_dict(data: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    """Inverse of :func:`incident_detail_to_dict`, in sorted key order.

    Args:
        data: The mapping stored in ``IncidentRaised.detail``.

    Returns:
        Ordered ``(key, value)`` pairs, sorted by key, which is the order
        ``canonical_json`` used when the mapping was written.
    """
    return tuple((str(key), data[key]) for key in sorted(data))


# --------------------------------------------------------------------------
# Read only views handed across a workstream boundary
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class InventoryView:
    """What one account owns, as a read only snapshot (section 7.10).

    The reference market maker needs its own inventory to skew and to cap
    (FR-5.8.3), and its free cash to know whether a quote can be
    collateralised. Handing it the whole ``AccountBook`` would give a pure
    quoting component a mutation handle on the ledger and would make
    :mod:`pxe.mm` import :mod:`pxe.exchange.accounts`. This snapshot is the
    boundary instead: A06 produces it, A07 consumes it, and it lives in
    :mod:`pxe.types` so neither imports the other.

    Attributes:
        account_id: The account described.
        cash_cents: Total cash.
        reserved_cents: Cash locked as collateral.
        free_cash_cents: ``cash_cents - reserved_cents``.
        inventory_qty_by_market: Signed net position per market, one entry per
            market of the match, sorted by ``market_id``.
    """

    account_id: str
    cash_cents: int
    reserved_cents: int
    free_cash_cents: int
    inventory_qty_by_market: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        ids = [mid for mid, _qty in self.inventory_qty_by_market]
        if tuple(ids) != sorted_ids(ids):
            raise InvalidConfigError("inventory view must be sorted by market_id", account_id=self.account_id)

    def inventory_qty(self, market_id: str) -> int:
        """Return the signed net position on ``market_id``, ``0`` when flat.

        Args:
            market_id: Market to look up.

        Returns:
            The signed quantity.
        """
        for mid, qty in self.inventory_qty_by_market:
            if mid == market_id:
                return qty
        return 0


# --------------------------------------------------------------------------
# Tournament data carriers
#
# These four are pure data with no behaviour. They live here, and not in
# :mod:`pxe.tournament`, because :mod:`pxe.store` persists them and
# :mod:`pxe.tournament` uses the store: defining them on either side makes the
# two packages import each other (section 7, dependency arrow).
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class RatingRecord:
    """One line of the TrueSkill leaderboard (PRD section 8, WBS T3.2).

    Attributes:
        harness_key: Identity of the rated brain, :func:`harness_key`. ``MM``
            and ``FEES`` are never rated (FR-5.8.5).
        mu: TrueSkill mean skill.
        sigma: TrueSkill standard deviation.
        matches: Number of rated matches behind the estimate.
    """

    harness_key: str
    mu: float
    sigma: float
    matches: int


@dataclass(frozen=True, slots=True)
class MatchTask:
    """One unit of tournament work, planned before it is run (T3.1).

    Attributes:
        task_id: Stable identifier of the unit of work, used by the idempotent
            resume.
        match_id: Id the match will carry, section 2.2.
        template_id: World template to generate.
        seed: Root seed of the match.
        agent_ids: Seats, ascending.
        harness_keys: Harness occupying each seat, aligned with ``agent_ids``.
        profile_assignment: Latin square assignment, ``(agent_id, kind)`` pairs
            sorted by ``agent_id`` (FR-5.3.2).
        held_out: True when the seed comes from the sealed bank (AC-P5).
    """

    task_id: str
    match_id: str
    template_id: str
    seed: int
    agent_ids: tuple[str, ...]
    harness_keys: tuple[str, ...]
    profile_assignment: tuple[tuple[str, InfoProfileKind], ...]
    held_out: bool = False

    def __post_init__(self) -> None:
        if len(self.agent_ids) != len(self.harness_keys):
            raise InvalidConfigError("one harness per seat", task_id=self.task_id)
        if tuple(self.agent_ids) != sorted_ids(self.agent_ids):
            raise InvalidConfigError("agent_ids must be sorted", task_id=self.task_id)


@dataclass(frozen=True, slots=True)
class TournamentConfig:
    """Everything the orchestrator needs to plan and run a tournament.

    Attributes:
        tournament_id: ``T-<name>-<nnnn>``.
        format: Round robin, Swiss or exhibition (PRD section 8).
        harnesses: Competing brains.
        template_ids: World templates in rotation.
        seeds: Root seeds, at least three per matchup (T3.3).
        agents_per_match: Seats per match, 4 to 8.
        rounds: Number of Swiss rounds, ``1`` for the other formats.
        gateway: Wall clock and budget settings, never journalled.
        match_defaults: Base :class:`MatchConfig`; the orchestrator overrides
            only ``seed`` per task.
        background_baselines: Scripted agents filling the empty seats.
        max_cost_usd: Hard cost cap of the whole tournament (AC-P3).
    """

    tournament_id: str
    format: TournamentFormat
    harnesses: tuple[HarnessConfig, ...]
    template_ids: tuple[str, ...]
    seeds: tuple[int, ...]
    agents_per_match: int
    rounds: int
    gateway: GatewayConfig
    match_defaults: MatchConfig
    background_baselines: tuple[str, ...] = ()
    max_cost_usd: float = 0.0

    def __post_init__(self) -> None:
        """Enforce the two config-local checks of CONTRACTS section 7.19 rule 5.

        Rule 5 lists three refusals. Two of them are properties of this object
        alone and live here, so an invalid tournament cannot even be
        constructed. The third ("the population is smaller than one match") is
        **not** here on purpose: ``harnesses`` holds the competitors only, while
        the seats are filled by the competitors plus ``background_baselines``,
        and ``configs/exhibition.toml`` ships one challenger against a field of
        four. Only :class:`~pxe.tournament.orchestrator.TournamentOrchestrator`
        knows the assembled population, so it owns that check.

        Raises:
            InvalidConfigError: On fewer than three seeds per matchup (PRD
                section 5.7, T3.3, AC-P3) or an ``agents_per_match`` outside
                4..8 (PRD section 5.7).
        """
        if len(self.seeds) < 3:
            raise InvalidConfigError(
                "at least three seeds per matchup (PRD section 5.7, T3.3, AC-P3)",
                seeds=len(self.seeds),
            )
        if not 4 <= self.agents_per_match <= 8:
            raise InvalidConfigError(
                "a match seats 4 to 8 agents (PRD section 5.7)",
                agents_per_match=self.agents_per_match,
            )


@dataclass(frozen=True, slots=True)
class TournamentResult:
    """Outcome of a finished tournament.

    Attributes:
        tournament_id: The tournament.
        match_results: Every match that ran, in planning order.
        ratings: Final leaderboard, best ``mu`` first.
        total_cost_usd: Sum of the provider costs.
        report_path: Path of the generated Markdown report (T3.6).
    """

    tournament_id: str
    match_results: tuple[MatchResult, ...]
    ratings: tuple[RatingRecord, ...]
    total_cost_usd: float
    report_path: str
