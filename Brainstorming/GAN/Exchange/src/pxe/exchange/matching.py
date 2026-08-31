"""Pure matching, the reference price chain and the protection band (section 7.7).

Nothing here mutates a book, an account or a journal. :func:`plan_match` reads
the book and returns a plan; :mod:`pxe.exchange.exchange` is the only module
allowed to act on it. Keeping the walk pure is what makes FR-5.4.1 testable
without a ledger, and it is what lets the exchange evaluate the FR-5.5.1
solvency check before a single fill is applied.

Three rules are implemented here and stated once:

* **FR-5.4.1** price-time priority with partial fills, every execution at the
  **resting (maker) price**.
* **FR-5.4.4** self-trade prevention: a resting order of the incoming order's
  own account is marked for cancellation and **the walk continues**. The
  marked quantity is not consumed, so the incoming order keeps its full size
  for the next maker by priority.
* **FR-5.4.6** the reference price fallback chain, mid then last then prior,
  and **FR-5.4.3** the protection band a ``market`` order is converted to.
"""

from __future__ import annotations

from dataclasses import dataclass

from pxe.errors import InvalidOrderError
from pxe.exchange.book import OrderBook
from pxe.types import (
    PRICE_MAX,
    PRICE_MIN,
    Side,
    clamp_price,
    taker_fee_cents,
)

__all__ = [
    "Fill",
    "MatchPlan",
    "plan_match",
    "reference_price",
    "band_limit_price",
]

#: The three branches of FR-5.4.6, in the order they are tried.
_REF_SOURCE_MID = "mid"
_REF_SOURCE_LAST = "last"
_REF_SOURCE_PRIOR = "prior"


@dataclass(frozen=True)
class Fill:
    """One planned execution against one resting order.

    Attributes:
        maker_order_id: The resting order that would be hit.
        maker_agent_id: Its owner.
        maker_side: Its side. The taker's side is the opposite.
        price: The **maker** price in cents (FR-5.4.1). The taker's limit is
            never the execution price, which is what makes a marketable order
            walking several levels produce several different prices.
        qty: Executed quantity in contracts.
    """

    maker_order_id: str
    maker_agent_id: str
    maker_side: Side
    price: int
    qty: int


@dataclass(frozen=True)
class MatchPlan:
    """What an incoming order would do to a book, computed without touching it.

    Attributes:
        fills: The executions, in walk order (price-time priority).
        stp_order_ids: Resting orders of the incoming order's own account that
            the walk crossed, in ``priority_key`` order (FR-5.4.4). The
            exchange cancels each of them and emits, per order, one
            ``OrderCancelled(reason=STP)`` then one ``STPCancelled``.
        residual_qty: Quantity left unexecuted. It rests for a ``GTC`` limit
            and is cancelled for an ``IOC`` (a converted ``market`` order,
            FR-5.4.3).
        notional_cents: ``sum(fill.price * fill.qty)``, cash exchanged before
            fees.
        fee_cents: Sum of the **per fill** taker fees. Informational only: the
            fee that is charged and journalled is recomputed per fill, because
            ``taker_fee_cents`` floors and ``floor(f1) + floor(f2)`` differs
            from ``floor(f1 + f2)`` by up to a cent, which would break
            invariant I5 (CONTRACTS section 6.1).
    """

    fills: tuple[Fill, ...]
    stp_order_ids: tuple[str, ...]
    residual_qty: int
    notional_cents: int
    fee_cents: int


def plan_match(
    book: OrderBook,
    *,
    agent_id: str,
    side: Side,
    limit_price: int,
    qty: int,
    fee_bps: int,
) -> MatchPlan:
    """Walk price-time priority and plan the executions (FR-5.4.1, FR-5.4.4).

    Pure. The book is read and never mutated, so the caller may run the
    solvency check of CONTRACTS section 6.1 against the plan before applying
    anything, and so the STP releases cannot leak into that check (decision
    21).

    Args:
        book: The book of the target market.
        agent_id: The incoming order's owner. A resting order of this account
            is marked in ``stp_order_ids`` instead of being matched, and the
            walk continues to the next maker without consuming any of ``qty``.
        side: Side of the incoming order.
        limit_price: Its limit price in cents, ``1..99``. For a ``market``
            order this is already the band converted price
            (:func:`band_limit_price`).
        qty: Its quantity in contracts, ``>= 1``.
        fee_bps: Taker fee rate in basis points, used only for the
            informational ``fee_cents`` total.

    Returns:
        The :class:`MatchPlan`.

    Raises:
        InvalidOrderError: If ``limit_price`` is outside ``1..99``, ``qty`` is
            below one, or ``fee_bps`` is negative.
    """
    if not PRICE_MIN <= limit_price <= PRICE_MAX:
        raise InvalidOrderError("limit price out of range", price=limit_price, market_id=book.market_id)
    if qty < 1:
        raise InvalidOrderError("quantity must be >= 1", qty=qty, market_id=book.market_id)
    if fee_bps < 0:
        raise InvalidOrderError("fee rate must be >= 0", fee_bps=fee_bps, market_id=book.market_id)

    remaining = qty
    fills: list[Fill] = []
    stp_ids: list[str] = []
    notional = 0
    fees = 0
    # A private accessor of OrderBook on purpose: the walk needs the level
    # arrays and both modules belong to the same work package, so exposing it
    # publicly would widen the section 7.7 surface for no outside caller.
    for maker in book._crossable(side, limit_price):
        if remaining == 0:
            break
        if maker.agent_id == agent_id:
            # FR-5.4.4: the resting order is cancelled, the incoming order is
            # not stopped and keeps its whole remaining quantity.
            stp_ids.append(maker.order_id)
            continue
        traded = min(remaining, maker.remaining_qty)
        fills.append(
            Fill(
                maker_order_id=maker.order_id,
                maker_agent_id=maker.agent_id,
                maker_side=maker.side,
                price=maker.price,
                qty=traded,
            )
        )
        remaining -= traded
        notional += maker.price * traded
        fees += taker_fee_cents(fee_bps, maker.price, traded)
    return MatchPlan(
        fills=tuple(fills),
        stp_order_ids=tuple(stp_ids),
        residual_qty=remaining,
        notional_cents=notional,
        fee_cents=fees,
    )


def reference_price(book: OrderBook, prior_price: int) -> tuple[int, str]:
    """The FR-5.4.6 reference price and the branch that produced it.

    The chain is: the rounded mid when the book is two sided, else the last
    executed price, else the market's public opening prior (FR-5.2.4). The last
    branch is why the reference price is **always** defined, which is what
    AC-P9 asserts and what makes the mark to market of FR-5.5.4 and the
    protection band of FR-5.4.3 total functions.

    Args:
        book: The book to read.
        prior_price: The market's public prior in cents, ``1..99``.

    Returns:
        ``(price, source)`` with ``source`` in ``{"mid", "last", "prior"}``.

    Raises:
        InvalidOrderError: If ``prior_price`` is outside ``1..99``. A prior out
            of band would let an undefended fallback produce an untradable
            reference price.
    """
    if not PRICE_MIN <= prior_price <= PRICE_MAX:
        raise InvalidOrderError("prior price out of range", market_id=book.market_id, prior_price=prior_price)
    mid = book.mid_price()
    if mid is not None:
        return (mid, _REF_SOURCE_MID)
    last = book.last_price()
    if last is not None:
        return (last, _REF_SOURCE_LAST)
    return (prior_price, _REF_SOURCE_PRIOR)


def band_limit_price(ref_price: int, side: Side, band_cents: int) -> int:
    """Convert a ``market`` order into a bounded marketable limit (FR-5.4.3).

    A buy may pay at most ``ref_price + band_cents`` and a sell may accept at
    least ``ref_price - band_cents``, both clamped into the tradable band
    ``1..99``. The quantity that is not executable inside that bound is
    cancelled by the caller and never left resting, which is the second half of
    FR-5.4.3.

    Args:
        ref_price: Reference price in cents (FR-5.4.6), ``1..99``.
        side: Side of the incoming order.
        band_cents: Protection band in cents, ``>= 0``.

    Returns:
        The effective limit price in cents, ``1..99``.

    Raises:
        InvalidOrderError: If ``ref_price`` is outside ``1..99`` or
            ``band_cents`` is negative.
    """
    if not PRICE_MIN <= ref_price <= PRICE_MAX:
        raise InvalidOrderError("reference price out of range", ref_price=ref_price)
    if band_cents < 0:
        raise InvalidOrderError("protection band must be >= 0", band_cents=band_cents)
    if side is Side.BUY:
        return clamp_price(ref_price + band_cents)
    return clamp_price(ref_price - band_cents)
