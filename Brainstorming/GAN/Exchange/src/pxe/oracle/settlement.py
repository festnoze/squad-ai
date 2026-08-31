"""The one and only emitter of ``SettlementApplied`` (CONTRACTS section 7.11).

Why this is a module of its own, and not a method of :class:`AccountBook` or of
:class:`~pxe.oracle.resolver.Oracle`:

* ``AccountBook`` (A06) holds **no** :class:`~pxe.journal.Journal` and emits
  nothing (CONTRACTS section 4.5, decision 30). It mutates the ledger and
  returns the facts as :class:`~pxe.exchange.accounts.SettlementLine` values.
* An event with two possible emitters is an event emitted twice or not at all.
  ``SettlementApplied`` therefore has exactly one emitter, this function, and
  both of the oracle's two paths (a resolution and an FR-5.4.5 unwind) reach
  the journal through it.

The split is also what makes the ordering testable: the ledger decides *what*
moves, this function decides *in which order it is written down*, and the order
is the canonical account order of CONTRACTS section 2.3 (ranked agents
ascending, then ``MM``, then ``FEES``). That order is literally the journal byte
order and therefore part of the AC-P1 hash, so it is checked here rather than
assumed.
"""

from __future__ import annotations

from pxe.errors import InvariantViolationError
from pxe.events import SettlementApplied
from pxe.exchange.accounts import AccountBook, SettlementLine
from pxe.journal import Journal
from pxe.types import Outcome, sorted_account_ids

__all__ = ["settle"]

#: The two settlement modes of CONTRACTS section 6.4. ``"resolution"`` pays the
#: binary outcome, ``"unwind"`` restores the cash of a cancelled market.
_MODE_RESOLUTION = "resolution"


def settle(
    *,
    tick: int,
    market_id: str,
    outcome: Outcome | None,
    accounts: AccountBook,
    journal: Journal,
    mode: str = _MODE_RESOLUTION,
) -> tuple[SettlementLine, ...]:
    """Settle one market and journal every line of the group.

    Mutates the ledger through :meth:`AccountBook.apply_settlement` (which
    emits nothing and checks invariant I6 before returning) and then emits one
    :class:`~pxe.events.SettlementApplied` per returned line, in canonical
    account order.

    Args:
        tick: Envelope tick of every emitted event. For a resolution scheduled
            at tick ``r`` this is ``r + 1`` (CONTRACTS section 5.0), and for a
            finalisation resolution it is ``ticks_total + 1``. For an FR-5.4.5
            cancellation scheduled at tick ``c`` it is ``c``.
        market_id: Market being settled.
        outcome: The realised outcome, or ``None`` for an unwind.
        accounts: The ledger. It is mutated: every position on ``market_id``
            is flattened and every cost basis cleared.
        journal: Journal the ``SettlementApplied`` events are appended to.
        mode: ``"resolution"`` or ``"unwind"``. It must agree with ``outcome``;
            :meth:`AccountBook.apply_settlement` raises when it does not.

    Returns:
        The settlement lines exactly as the ledger produced them, in canonical
        account order. The tuple is empty when nobody held a position, a cost
        basis or (on an unwind) a fee to refund on that market, in which case
        no event is emitted at all.

    Raises:
        InvalidConfigError: If the market is unknown, ``mode`` is not one of
            the two modes, or ``mode`` and ``outcome`` disagree.
        InvariantViolationError: If the group is not zero sum (I6), if an
            account's cash would go negative (I9), or if the lines did not
            arrive in canonical account order.
    """
    lines = accounts.apply_settlement(market_id=market_id, outcome=outcome, mode=mode)
    _require_canonical_order(lines)
    for line in lines:
        journal.emit(
            SettlementApplied,
            tick=tick,
            market_id=line.market_id,
            account_id=line.account_id,
            mode=line.mode,
            position_qty=line.position_qty,
            cash_delta_cents=line.cash_delta_cents,
            cash_before_cents=line.cash_before_cents,
            cash_after_cents=line.cash_after_cents,
            released_collateral_cents=line.released_collateral_cents,
        )
    return lines


def _require_canonical_order(lines: tuple[SettlementLine, ...]) -> None:
    """Refuse to journal a settlement group that is not in canonical order.

    The emission order of ``SettlementApplied`` is the journal byte order and
    therefore part of the AC-P1 hash (CONTRACTS section 2.3). Re-sorting here
    would hide a ledger regression behind a passing determinism test, so a
    group that arrives out of order is an engine bug and aborts the match.

    Args:
        lines: The group as the ledger returned it.

    Raises:
        InvariantViolationError: If the ids are not in canonical account order.
    """
    ids = tuple(line.account_id for line in lines)
    canonical = sorted_account_ids(ids)
    if ids != canonical:
        raise InvariantViolationError(
            "settlement lines are not in canonical account order",
            got=list(ids),
            expected=list(canonical),
        )
