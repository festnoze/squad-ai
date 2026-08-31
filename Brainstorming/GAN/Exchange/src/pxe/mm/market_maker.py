"""The reference market maker (A07, CONTRACTS section 7.10, PRD section 5.8).

The market maker is the difficulty thermostat of the arena. It is the only
guaranteed source of exogenous liquidity, so the spread it shows is the price an
agent pays to express a belief. Four properties are load bearing and each one is
a functional requirement rather than a design taste:

* **FR-5.8.1, two sided every tick.** ``requote`` runs at the very start of P3,
  *before* the fairness shuffle, and performs a full cancel/replace on every
  open market. The displayed liquidity is therefore identical whatever order the
  agents happen to be called in that tick.
* **FR-5.8.2, uninformed.** The only market datum this module reads is
  ``Exchange.reference_price``, the public FR-5.4.6 fallback chain. It never
  sees a private signal, a latent value, a prediction or a news *body*: the one
  news field it touches is the impact tag, and it reacts to the fact that
  information landed, never to its content.
* **FR-5.8.3, inventory skew and a hard cap.** Inventory lives in the ledger,
  and this module deliberately cannot reach it: it is handed a frozen
  :class:`~pxe.types.InventoryView` (decision 28). Keeping a second inventory
  count here would drift from :class:`~pxe.exchange.accounts.AccountBook` and
  break invariant I10, which is checked on every tick.
* **FR-5.8.4, post news widening.** A HIGH impact item multiplies the spread for
  ``w`` ticks on the markets the item names.

This module imports :mod:`pxe.exchange.exchange` and :mod:`pxe.journal` and
never :mod:`pxe.exchange.accounts` (CONTRACTS section 13, decision 28).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from pxe.errors import InvalidConfigError
from pxe.events import MMQuoted
from pxe.exchange.exchange import Exchange
from pxe.journal import Journal
from pxe.rng import RngTree, bernoulli
from pxe.types import (
    MM_ACCOUNT_ID,
    CancelReason,
    InventoryView,
    MMConfig,
    NewsImpact,
    NewsItem,
    OrderIntent,
    OrderType,
    Side,
    clamp_price,
    round_half_up,
    sorted_ids,
)

__all__ = [
    "Quote",
    "ReferenceMarketMaker",
]

#: ``item_index`` carried by the two quote submissions of one requote. The
#: market maker has no ``orders`` array, so the index is simply the position of
#: the side inside its own two sided quote: the bid first, then the ask
#: (CONTRACTS section 5, P3 step 9).
_BID_ITEM_INDEX = 0
_ASK_ITEM_INDEX = 1


@dataclass(frozen=True)
class Quote:
    """One market maker quote for one market at one tick.

    This is exactly the payload of :class:`pxe.events.MMQuoted`, returned to the
    caller so a test or a study can read the decision without re-parsing the
    journal.

    Attributes:
        market_id: Quoted market.
        ref_price: Public reference price the quote was built off (FR-5.4.6),
            read *after* the previous quote left the book so the market maker
            never anchors on itself.
        anchor_price: ``ref_price`` shifted by :attr:`skew_cents` and clamped
            into the tradable band (FR-5.8.3).
        bid_price: Quoted bid, ``None`` when the side is suppressed.
        ask_price: Quoted ask, ``None`` when the side is suppressed.
        quote_qty: Size quoted on each active side, ``MMConfig.quote_qty``.
        effective_spread: ``ask_price - bid_price`` when both sides quote, else
            ``None``.
        inventory_qty: Signed market maker inventory on this market, as read
            from the :class:`~pxe.types.InventoryView` snapshot.
        skew_cents: Signed inventory reversion applied to the anchor.
        widened: True while the FR-5.8.4 window is open on this market.
        widen_until_tick: Last tick of that window, ``0`` when it never opened.
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


class ReferenceMarketMaker:
    """The neutral, uninformed, out of ranking liquidity provider (PRD section 5.8).

    One instance per match. It holds no ledger handle, no world handle and no
    inventory of its own: everything it needs arrives as an argument, which is
    what makes its quotes a pure function of the public state plus the
    :class:`~pxe.types.InventoryView` snapshot.
    """

    #: The reserved account the quotes are submitted under. It is out of the
    #: ranking and out of the ratings (FR-5.8.5).
    ACCOUNT_ID: ClassVar[str] = MM_ACCOUNT_ID

    def __init__(self, *, config: MMConfig, market_ids: Sequence[str], rng: RngTree) -> None:
        """Build the market maker for one match.

        Args:
            config: The FR-5.8.6 preset in force. It is authoritative and comes
                from ``MatchConfig.mm``, never from the scenario's preset name
                (CONTRACTS section 2.6).
            market_ids: Every market of the match. Stored in canonical market
                order, so the requote loop cannot depend on the caller's
                iteration order.
            rng: The ``mm`` sub-tree, built by the runner as
                ``rng.child("mm")`` (CONTRACTS section 3.1). Only the
                ``mm.tiebreak`` substream is registered for this module, and it
                is consumed only by the defensive crossed quote branch of
                :meth:`compute_quote`: every quoting decision is otherwise
                deterministic arithmetic over public state.

        Raises:
            InvalidConfigError: If ``market_ids`` is empty or holds a duplicate.
                A market maker with no market is a configuration bug that would
                otherwise show up as a silently liquidity-free match.
        """
        if not market_ids:
            raise InvalidConfigError("a market maker needs at least one market")
        ordered = sorted_ids(market_ids)
        if len(set(ordered)) != len(ordered):
            raise InvalidConfigError("duplicate market id", market_ids=list(market_ids))
        self._config = config
        self._market_ids = ordered
        self._rng = rng
        # Last tick of the FR-5.8.4 widening window, per market. Absent means
        # "never widened", which is journalled as widen_until_tick = 0.
        self._widen_until: dict[str, int] = {}

    def note_news(self, *, tick: int, items: Sequence[NewsItem]) -> None:
        """Record the FR-5.8.4 widening window opened by this tick's news.

        A ``HIGH`` impact item sets ``widen_until_tick = tick + w`` for every
        market it names, where ``w`` is ``MMConfig.post_news_widen_ticks``. The
        market maker reads the **impact tag only** and never the headline, the
        body or the direction: it reacts to the fact that information landed
        (FR-5.8.2, FR-5.8.4).

        There is exactly one call site, P1 step 5b, after every
        ``NewsPublished`` of the tick exists (the info engine's items, the
        resolution announcements and the cancellation announcements). Splitting
        it into two calls is how decision 12 became untrue while this module's
        test still passed.

        An item naming no market widens nothing: the contracted rule is "for its
        markets", and a pure noise item with an empty ``market_ids`` has none.
        An item naming a market outside this match is ignored for the same
        reason.

        Args:
            tick: The tick the items were published at.
            items: Every news item published this tick, in emission order.
        """
        window = self._config.post_news_widen_ticks
        if window <= 0:
            return
        for item in items:
            if item.impact is not NewsImpact.HIGH:
                continue
            for market_id in item.market_ids:
                if market_id not in self._market_ids:
                    continue
                until = tick + window
                if until > self._widen_until.get(market_id, 0):
                    self._widen_until[market_id] = until

    def is_widened(self, market_id: str, tick: int) -> bool:
        """Whether the FR-5.8.4 window is open on ``market_id`` at ``tick``.

        The window is inclusive of its last tick, which is what
        ``MMQuoted.widen_until_tick`` ("last tick of the widening window")
        means: a HIGH impact item at tick ``t`` widens ticks ``t`` through
        ``t + w``. The news lands in P1 and the requote happens in P3 of the
        same tick, so tick ``t`` itself is widened.

        Args:
            market_id: Market to test.
            tick: Tick to test.

        Returns:
            True while the spread is multiplied on that market.
        """
        return tick <= self._widen_until.get(market_id, 0)

    def compute_quote(self, *, tick: int, market_id: str, ref_price: int, inventory_qty: int) -> Quote:
        """Build the quote of one market from public state only (FR-5.8.1 to FR-5.8.4).

        The arithmetic is the normative one of CONTRACTS section 7.10::

            half   = ceil(spread / 2), spread = base_spread * (multiplier if widened else 1)
            skew   = round_half_up(-k * inventory_qty / I_max)
            anchor = clamp_price(ref_price + skew)
            bid    = clamp_price(anchor - half)   suppressed if inventory_qty + q > I_max
            ask    = clamp_price(anchor + half)   suppressed if inventory_qty - q < -I_max

        The two suppressions are the FR-5.8.3 hard cap, and they are expressed
        on the **full** quoted size: the market maker refuses to show a side
        that a complete fill would push past ``I_max``. That is what makes
        invariant I10 (``abs(position(MM, m)) <= inventory_max``) hold by
        construction rather than by luck, since the market maker is the only
        thing that ever moves the ``MM`` inventory.

        A side is also suppressed when clamping would leave ``bid >= ask``. With
        prices confined to ``1..99`` and a half spread of at least one cent that
        branch is unreachable, and it is the only consumer of the
        ``mm.tiebreak`` substream: which of the two sides survives a crossed
        quote is not derivable from the public state, so it is drawn rather than
        chosen by an arbitrary constant.

        Args:
            tick: Current tick, used only to test the widening window.
            market_id: Market to quote.
            ref_price: Public reference price in cents, ``1..99``.
            inventory_qty: Signed market maker inventory on this market.

        Returns:
            The :class:`Quote`, with ``None`` on every suppressed side.

        Raises:
            InvalidConfigError: If ``market_id`` is not a market of this match,
                or if ``ref_price`` is outside the tradable band. A reference
                price out of band means FR-5.4.6's fallback chain returned
                something untradable, which is an engine bug and not an agent
                behaviour.
        """
        if market_id not in self._market_ids:
            raise InvalidConfigError("unknown market", market_id=market_id)
        if clamp_price(ref_price) != ref_price:
            raise InvalidConfigError("reference price out of band", market_id=market_id, ref_price=ref_price)

        widened = self.is_widened(market_id, tick)
        half = self._config.half_spread_cents(widened=widened)
        cap = self._config.inventory_max
        size = self._config.quote_qty

        skew_cents = round_half_up(-self._config.skew_cents * inventory_qty / cap)
        anchor_price = clamp_price(ref_price + skew_cents)

        bid_price: int | None = None if inventory_qty + size > cap else clamp_price(anchor_price - half)
        ask_price: int | None = None if inventory_qty - size < -cap else clamp_price(anchor_price + half)

        if bid_price is not None and ask_price is not None and bid_price >= ask_price:
            # Unreachable with clamp_price bounded to 1..99 and half >= 1, kept
            # because a crossed quote must never reach the book: it would trade
            # with itself through the STP path on the very next submission.
            if bernoulli(self._rng.substream("mm.tiebreak"), 0.5):
                bid_price = None
            else:
                ask_price = None

        effective_spread = None if bid_price is None or ask_price is None else ask_price - bid_price
        return Quote(
            market_id=market_id,
            ref_price=ref_price,
            anchor_price=anchor_price,
            bid_price=bid_price,
            ask_price=ask_price,
            quote_qty=size,
            effective_spread=effective_spread,
            inventory_qty=inventory_qty,
            skew_cents=skew_cents,
            widened=widened,
            widen_until_tick=self._widen_until.get(market_id, 0),
        )

    def requote(
        self,
        *,
        tick: int,
        exchange: Exchange,
        inventory: InventoryView,
        journal: Journal,
    ) -> tuple[Quote, ...]:
        """Cancel and replace every quote on every open market (FR-5.8.1, P3 step 9).

        Runs at the very start of P3, **before** the fairness shuffle, so the
        liquidity an agent meets does not depend on where it landed in the
        tick's permutation. Per open market in ascending order, in this exact
        order:

        1. ``exchange.cancel_all(agent_id="MM", market_id=...,
           reason=MM_REQUOTE)``. The **exchange** emits the ``OrderCancelled``
           events, one per order in ``priority_key`` order, because it is the
           single emitter of that event (CONTRACTS section 4.5), and it is the
           single event carrying the released collateral.
        2. read ``exchange.reference_price(market_id)``. It is read *after* the
           cancel on purpose: the previous quote is two sided, so reading before
           would make the market maker anchor on its own mid and drift away from
           the public price forever.
        3. ``emit(MMQuoted)``.
        4. submit the bid then the ask, each through ``Exchange.submit`` like any
           other participant. A quote that crosses a resting agent order
           executes normally and produces trades; a quote is also subject to the
           section 6.1 collateral check and can be rejected, which emits
           ``OrderRejected(agent_id="MM")`` and leaves the market with one side.
           ``MatchConfig.mm_initial_cash_cents`` defaults to ten times an
           agent's cash (decision 16) precisely so that never happens, and
           ``test_market_maker.py::test_guaranteed_liquidity_with_mute_agents``
           asserts it over a whole match.

        Args:
            tick: Current tick.
            exchange: The CLOB facade. Only ``open_market_ids``,
                ``reference_price``, ``cancel_all`` and ``submit`` are used:
                nothing here reads a position or a private signal.
            inventory: The ``MM`` snapshot the runner took just before the call,
                ``AccountBook.inventory_view(MM_ACCOUNT_ID)``. It is frozen at
                the top of the requote, before any of this tick's quotes exist,
                and it is the only inventory this module ever sees (decision 28).
            journal: The match journal. This module is the single emitter of
                ``MMQuoted``.

        Returns:
            One :class:`Quote` per market quoted, ascending by ``market_id``.
            Empty when the preset is disabled.

        Raises:
            InvalidConfigError: If ``inventory`` does not describe the ``MM``
                account. Quoting off another account's inventory would silently
                invert the FR-5.8.3 skew.
        """
        if inventory.account_id != self.ACCOUNT_ID:
            raise InvalidConfigError(
                "the market maker must be handed the MM inventory view",
                account_id=inventory.account_id,
            )
        if not self._config.enabled:
            return ()

        quotes: list[Quote] = []
        for market_id in exchange.open_market_ids():
            if market_id not in self._market_ids:
                continue
            exchange.cancel_all(
                tick=tick,
                reason=CancelReason.MM_REQUOTE,
                agent_id=self.ACCOUNT_ID,
                market_id=market_id,
            )
            ref_price, _source = exchange.reference_price(market_id)
            quote = self.compute_quote(
                tick=tick,
                market_id=market_id,
                ref_price=ref_price,
                inventory_qty=inventory.inventory_qty(market_id),
            )
            journal.emit(
                MMQuoted,
                tick=tick,
                market_id=quote.market_id,
                ref_price=quote.ref_price,
                anchor_price=quote.anchor_price,
                bid_price=quote.bid_price,
                ask_price=quote.ask_price,
                quote_qty=quote.quote_qty,
                effective_spread=quote.effective_spread,
                inventory_qty=quote.inventory_qty,
                skew_cents=quote.skew_cents,
                widened=quote.widened,
                widen_until_tick=quote.widen_until_tick,
            )
            if quote.bid_price is not None:
                self._submit_side(
                    tick=tick,
                    exchange=exchange,
                    market_id=market_id,
                    side=Side.BUY,
                    price=quote.bid_price,
                    item_index=_BID_ITEM_INDEX,
                )
            if quote.ask_price is not None:
                self._submit_side(
                    tick=tick,
                    exchange=exchange,
                    market_id=market_id,
                    side=Side.SELL,
                    price=quote.ask_price,
                    item_index=_ASK_ITEM_INDEX,
                )
            quotes.append(quote)
        return tuple(quotes)

    def _submit_side(
        self,
        *,
        tick: int,
        exchange: Exchange,
        market_id: str,
        side: Side,
        price: int,
        item_index: int,
    ) -> None:
        """Submit one side of the quote as a plain GTC limit order."""
        exchange.submit(
            tick=tick,
            agent_id=self.ACCOUNT_ID,
            intent=OrderIntent(
                op="place",
                market_id=market_id,
                side=side,
                order_type=OrderType.LIMIT,
                price=price,
                qty=self._config.quote_qty,
            ),
            item_index=item_index,
        )

    def __repr__(self) -> str:
        """Render the preset and the market count, never a memory address."""
        return f"ReferenceMarketMaker(markets={len(self._market_ids)}, spread={self._config.base_spread_cents})"
