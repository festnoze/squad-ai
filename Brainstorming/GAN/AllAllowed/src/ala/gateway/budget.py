"""The USD budget of the LLM gateway (W8, CONTRACTS section 11).

One public name: :class:`BudgetTracker`. It is a pure integer accumulator with no
clock, no network and no I/O. It is what makes "the LLM path is bounded before a
cent is spent" a checkable property.

Why integers, and why micro-dollars
------------------------------------
Money that reaches the journal is an integer number of credits (golden rule 1),
and while a provider reports its cost as a float, we refuse to carry that float
into any accounting. The tracker therefore works in **micro-dollars**: one USD is
:data:`MICRO_PER_USD` micro-dollars, so a call that cost ``0.027`` USD is
``27_000`` micro. Every comparison and every sum here is integer arithmetic, so
no floating point noise ever turns a legal call into a refused one, or the
reverse.

Why a non-positive cap forbids spending
---------------------------------------
There is deliberately no "unlimited" spelling for money. A ceiling of zero (the
:class:`~ala.gateway.protocol.GatewayConfig` default) means "no budget is
configured", and :meth:`BudgetTracker.check` answers ``False`` for it: the paid
path is opt-in and a match that forgot to set a budget must make no calls rather
than spend without a bound. The runaway tournament is the exact failure this
class exists to prevent.

A breach is never an exception
------------------------------
Nothing here raises. :meth:`check` returns a boolean and the gateway decides what
to do with it (it makes the agent idle for the tick). The match never stops
because one agent's next call would breach a cap.
"""

from __future__ import annotations

__all__ = ["MICRO_PER_USD", "BudgetTracker", "usd_to_micro"]

#: Micro-dollars in one USD. All accounting in this module is in these units so
#: no float ever touches the arithmetic.
MICRO_PER_USD = 1_000_000


def usd_to_micro(cost_usd: float) -> int:
    """Convert a provider reported USD cost into micro-dollars.

    The provider is the only place a float appears, and it is quarantined here:
    the returned integer is what the tracker accounts in. Rounding is to nearest,
    so a reported ``0.0000004`` USD does not silently vanish across a long match.

    Args:
        cost_usd: The USD cost the CLI reported for a call. A negative value
            (which a provider should never send) is clamped to zero.

    Returns:
        The cost in micro-dollars, never negative.
    """
    if cost_usd <= 0.0:
        return 0
    return round(cost_usd * MICRO_PER_USD)


class BudgetTracker:
    """Accumulates spend in micro-dollars and answers whether a call fits.

    One tracker is built per match and shared by every seat, because the caps are
    per call and per match quantities, not per agent objects. It holds two
    ceilings, both in micro-dollars, and the running match total.

    Attributes:
        per_call_micro: The most a single call may cost. Non-positive forbids
            every call (see the module docstring).
        per_match_micro: The most the whole match may cost. Non-positive forbids
            every call.
    """

    __slots__ = ("_per_call_micro", "_per_match_micro", "_spent_micro")

    def __init__(self, per_call_micro: int, per_match_micro: int) -> None:
        """Build an empty tracker over two integer ceilings.

        Args:
            per_call_micro: Per call ceiling, in micro-dollars.
            per_match_micro: Per match ceiling, in micro-dollars.
        """
        self._per_call_micro = int(per_call_micro)
        self._per_match_micro = int(per_match_micro)
        self._spent_micro = 0

    def check(self, cost_micro: int) -> bool:
        """Answer whether a call costing ``cost_micro`` may be sent.

        Evaluated **before** the call is sent, so a refusal costs nothing. Both
        ceilings must be positive and both must absorb the cost; a negative cost
        is refused as malformed.

        Args:
            cost_micro: The (estimated worst case) cost of the call, in
                micro-dollars.

        Returns:
            ``True`` if the call is within both the per call and the per match
            ceilings, ``False`` otherwise. Never raises: the gateway decides.
        """
        if cost_micro < 0:
            return False
        if self._per_call_micro <= 0 or cost_micro > self._per_call_micro:
            return False
        if self._per_match_micro <= 0:
            return False
        return self._spent_micro + cost_micro <= self._per_match_micro

    def record(self, cost_micro: int) -> None:
        """Add the actual cost of a completed call to the match total.

        Called after a call returns, with the cost the provider reported. A
        negative value is clamped to zero rather than crediting the budget, so a
        misbehaving provider can never make room for more spend.

        Args:
            cost_micro: The cost the call actually incurred, in micro-dollars.
        """
        self._spent_micro += max(0, int(cost_micro))

    def spent_micro(self) -> int:
        """Return what the match has spent so far, in micro-dollars.

        Returns:
            The cumulative match spend, an integer never below zero.
        """
        return self._spent_micro

    def remaining_micro(self) -> int:
        """Return what is left to spend this match, in micro-dollars.

        Returns:
            ``per_match_micro - spent``, never below zero. Zero when no match
            ceiling is configured, because a non-positive ceiling forbids
            spending rather than allowing it without bound.
        """
        if self._per_match_micro <= 0:
            return 0
        return max(0, self._per_match_micro - self._spent_micro)
