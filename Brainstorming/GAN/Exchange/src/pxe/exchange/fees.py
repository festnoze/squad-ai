"""Taker fee helpers bound to a :class:`~pxe.types.MatchConfig` (FR-5.4.7).

Fee arithmetic has exactly one owner, :func:`pxe.types.taker_fee_cents` and
:func:`pxe.types.max_taker_fee_cents`. The two functions here are thin
delegations that read ``config.taker_fee_bps`` and call them: they may not
re-derive, re-round or re-clamp anything (CONTRACTS section 6.1). Two roundings
of the same fee is how a closed system starts creating money.

They exist so that no call site has to reach for ``config.taker_fee_bps``
itself, which is what made two modules disagree about which price the fee is
charged on. The fee is per fill, on that fill's own price and quantity: for a
marketable order walking two price levels, ``floor(f1) + floor(f2)`` differs
from ``floor(f1 + f2)`` by up to a cent, and charging the aggregate while
journalling the parts breaks invariant I5.
"""

from __future__ import annotations

from pxe.types import MatchConfig, max_taker_fee_cents, taker_fee_cents

__all__ = [
    "taker_fee_for",
    "reserve_fee_for",
]


def taker_fee_for(config: MatchConfig, *, price: int, qty: int) -> int:
    """Fee charged to the taker of one fill (FR-5.4.7).

    Args:
        config: The match configuration, read only for ``taker_fee_bps``.
        price: Execution price of the fill in cents.
        qty: Executed quantity of the fill in contracts.

    Returns:
        The fee in cents, floored so it never creates money.

    Raises:
        ValueError: If ``price`` or ``qty`` is negative.
    """
    return taker_fee_cents(config.taker_fee_bps, price, qty)


def reserve_fee_for(config: MatchConfig, *, qty: int) -> int:
    """Worst case fee the pre-trade solvency check must hold back (CONTRACTS 6.1).

    Computed at the maximum conceivable execution price (100 cents), so a
    better fill can never defeat the check.

    Args:
        config: The match configuration, read only for ``taker_fee_bps``.
        qty: Order quantity in contracts.

    Returns:
        The reserved fee in cents.
    """
    return max_taker_fee_cents(config.taker_fee_bps, qty)
