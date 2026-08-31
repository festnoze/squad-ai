"""The live state of one match (CONTRACTS section 7.12, A09).

:class:`MatchState` is the single object every phase of the tick loop reads
and the single object :func:`pxe.runner.replay.replay_journal` rebuilds from
the journal alone (FR-5.1.3). It owns no behaviour of its own: it holds the
two mutable engines (:class:`~pxe.exchange.accounts.AccountBook` and
:class:`~pxe.exchange.exchange.Exchange`) plus the handful of facts that live
nowhere else (the published outcomes, the last prediction of every seat, the
messages not yet delivered and the frozen seats), and it exposes the derived
views the runner, the observation builder (A10) and the action validator (A11)
all need.

Why the accessors are methods and not fields
--------------------------------------------
``open_market_ids``, ``ref_prices``, ``ranked_agent_ids``, ``active_agent_ids``
and ``resting_order_ids`` are all derivable from the exchange and the ledger.
Storing them would create a second, staler copy of state that the P3 order flow
silently invalidates halfway through a tick. They are computed on demand, and
every one of them returns a **canonically ordered** result (CONTRACTS section
2.3), because their output reaches the journal:

* ``ranked_agent_ids()`` is the list the P3 fairness shuffle consumes
  (section 3.4). It holds **every** seat, frozen ones included: the full list
  is shuffled and the frozen seats are dropped afterwards, so the permutation
  stays a function of ``(seed, tick)`` and never of agent behaviour.
* ``active_agent_ids()`` is for P1 step 6 and P2, where no RNG ordering is at
  stake.
* ``resting_order_ids(agent_id)`` is the one argument P2 step 8b hands to
  ``validate_action(resting_order_ids=...)``. ``AccountBook`` deliberately
  exposes a resting order **count** and not a list, because the ids live in
  the book and not in the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pxe.exchange.accounts import AccountBook
from pxe.exchange.exchange import Exchange
from pxe.types import (
    MatchConfig,
    Outcome,
    PublicMessage,
    ScenarioSpec,
    sorted_ids,
)

__all__ = ["MatchState"]


@dataclass
class MatchState:
    """Everything the engine knows about one match at one instant.

    Attributes:
        config: The authoritative match configuration (CONTRACTS section 2.6).
        scenario: The public description of the world being played.
        match_id: Match id every event of this match carries.
        tick: The tick currently being played, ``0`` before the first one and
            ``ticks_total + 1`` once finalisation has run.
        accounts: The ledger. Cash, collateral, positions and fees.
        exchange: The CLOB facade. Books, market status and reference prices.
        outcomes: Published outcomes, ``market_id`` to
            :class:`~pxe.types.Outcome`. A market is absent until the oracle
            resolves it, and a cancelled market never enters this mapping (it
            has no outcome). Iterated through
            :func:`~pxe.types.sorted_ids` (section 2.3).
        last_prediction_ppm: ``(agent_id, market_id)`` to the last probability
            declared or carried, in parts per million (FR-6.2.4). Lookup only
            in the engine; any loop over it goes through
            :func:`~pxe.types.sorted_ids`.
        pending_messages: Public messages posted but not yet delivered, in
            posting order (FR-5.6.1). A message posted at tick ``t`` is
            delivered in the observation of tick ``t + 1`` and leaves this
            tuple there.
        frozen_agent_ids: Seats frozen by the FR-5.5.5 bankruptcy rule. A
            freeze is permanent.
    """

    config: MatchConfig
    scenario: ScenarioSpec
    match_id: str
    tick: int
    accounts: AccountBook
    exchange: Exchange
    outcomes: dict[str, Outcome] = field(default_factory=dict)
    last_prediction_ppm: dict[tuple[str, str], int] = field(default_factory=dict)
    pending_messages: tuple[PublicMessage, ...] = ()
    frozen_agent_ids: frozenset[str] = frozenset()

    def open_market_ids(self) -> tuple[str, ...]:
        """Markets still tradable, in canonical market order.

        Returns:
            The ids whose status is ``OPEN``, ascending by numeric suffix. A
            market resolved or cancelled in P1 has already left this tuple.
        """
        return sorted_ids(self.exchange.open_market_ids())

    def ref_prices(self) -> dict[str, int]:
        """The FR-5.4.6 reference price of every open market.

        This is what P4 step 15 hands to ``AccountBook.check_invariants`` and
        what every mark to market in the match is valued at. A settled market
        is deliberately absent: its positions are flat, so it contributes
        nothing to an equity, and including it would make a closed market look
        like a live one.

        Returns:
            A mapping built in canonical market order, ``market_id`` to price
            in cents.
        """
        return {market_id: self.exchange.reference_price(market_id)[0] for market_id in self.open_market_ids()}

    def ranked_agent_ids(self) -> tuple[str, ...]:
        """Every ranked seat, frozen ones included, ascending.

        This is the list the P3 fairness shuffle consumes (CONTRACTS section
        3.4). Shuffling the already filtered list instead would make the
        permutation depend on which agents are frozen, that is on agent
        behaviour, and FR-5.1.5 would be lost.

        Returns:
            The seat ids ``A1``..``A8``, ascending by numeric suffix.
        """
        return sorted_ids(self.accounts.ranked_agent_ids())

    def active_agent_ids(self) -> tuple[str, ...]:
        """The ranked seats that are not frozen, ascending.

        Used by P1 step 6 (which builds one observation per active seat) and by
        P2. No RNG ordering is at stake here, which is why the P3 shuffle uses
        :meth:`ranked_agent_ids` instead.

        Returns:
            The active seat ids, ascending by numeric suffix.
        """
        return tuple(agent_id for agent_id in self.ranked_agent_ids() if agent_id not in self.frozen_agent_ids)

    def resting_order_ids(self, agent_id: str) -> tuple[str, ...]:
        """Every order id this account currently rests, over every market.

        Markets ascending, and inside a market ``Order.priority_key`` order
        (best price first, then lowest ``seq``), which is exactly the order
        ``Exchange.book_view()`` returns. This is the one accessor for those
        ids: it is what P2 step 8b hands to
        ``validate_action(resting_order_ids=...)``.

        Args:
            agent_id: Account to read, an agent id or ``MM``.

        Returns:
            The resting order ids, possibly empty.
        """
        view = self.exchange.book_view()
        ids: list[str] = []
        for market_id in sorted_ids(tuple(view.keys())):
            ids.extend(order.order_id for order in view[market_id] if order.agent_id == agent_id)
        return tuple(ids)
