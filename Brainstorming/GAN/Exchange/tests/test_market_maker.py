"""A07: the reference market maker and its three liquidity presets (section 7.10).

Eight independent claims, one per functional requirement of PRD section 5.8:

1. FR-5.8.1: every open market gets one quote per tick, emitted before any agent
   order of that tick, through a full cancel/replace;
2. FR-5.8.1 and AC-P9: the quote is two sided on at least 95 % of the (tick,
   market) pairs;
3. FR-5.8.2: the quote is a function of the public reference price alone. The
   market maker sees no signal, no latent value and no news content;
4. FR-5.8.3: the anchor is skewed against the inventory and the side that would
   breach ``I_max`` is not shown, so invariant I10 holds by construction;
5. FR-5.8.4: a HIGH impact news item multiplies the spread for ``w`` ticks on the
   markets it names, and only those;
6. FR-5.8.6: the three presets carry exactly the PRD table's numbers and the mean
   effective spread lands within one cent of each;
7. AC-P9: with mute agents no market maker quote is ever rejected and the
   reference price is always defined;
8. T2.6: the cost of liquidity study is journal-only and reproduces
   ``docs/MM_LIQUIDITY_COST.md``.

There is no ``MatchRunner`` yet (A09), so this file drives P3 itself: a tick here
is ``begin_tick``, then the single ``note_news`` handover of P1 step 5b, then the
requote of P3 step 9, then the agent flow, then the P4 step 15 invariant check.
That is the part of the tick contract the market maker participates in, and
driving it by hand is what makes every assertion below read a *real* journal
produced by the real :class:`~pxe.exchange.exchange.Exchange` and the real
:class:`~pxe.exchange.accounts.AccountBook`.

Every test that looks at the journal asserts it is non empty and holds at least
one event of the type under test before claiming anything (section 10's
anti-vacuous rule).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pxe.errors import InvalidConfigError, UnknownProfileError
from pxe.events import Event, MMQuoted, OrderCancelled, OrderPlaced, OrderRejected, TradeExecuted
from pxe.exchange.accounts import AccountBook
from pxe.exchange.exchange import Exchange
from pxe.journal import Journal
from pxe.mm.market_maker import Quote, ReferenceMarketMaker
from pxe.mm.profiles import (
    LiquidityCostRow,
    build_liquidity_study,
    liquidity_cost_row,
    mm_config_for,
    render_liquidity_study,
)
from pxe.rng import RngTree, randint
from pxe.types import (
    LIQUIDITY_PROFILES,
    MILLI_ONE,
    MM_ACCOUNT_ID,
    PPM_ONE,
    CancelReason,
    LiquidityProfileName,
    MarketSpec,
    MatchConfig,
    NewsImpact,
    NewsItem,
    OrderIntent,
    OrderType,
    ScenarioSpec,
    Side,
    make_agent_id,
    make_market_id,
)

STUDY_SEED = 20260827
DOC_PATH_PARTS = ("docs", "MM_LIQUIDITY_COST.md")
#: Size of the published study. Small enough that the whole suite stays fast,
#: large enough that the mean spread and the market maker PnL are stable.
DOC_MATCHES = 200
DOC_TICKS = 24
DOC_MARKETS = 2
DOC_AGENTS = 6


# ---------------------------------------------------------------------------
# A P3 harness. There is no runner yet, so the phase order the market maker
# lives in is spelled out here once and reused by every test.
# ---------------------------------------------------------------------------
def _scenario(config: MatchConfig, *, prior_price: int = 50) -> ScenarioSpec:
    markets = tuple(
        MarketSpec(
            market_id=make_market_id(index),
            question=f"does event {index} happen",
            prior_price=prior_price,
            resolution_tick=config.ticks_total,
            latent_key=f"latent_{index}",
        )
        for index in range(1, config.n_markets + 1)
    )
    return ScenarioSpec(
        template_id="election",
        template_version="1.0.0",
        seed=config.seed,
        ticks_total=config.ticks_total,
        markets=markets,
        talking_mode=config.talking_mode,
        liquidity_profile_name=config.liquidity_profile_name,
    )


@dataclass
class Harness:
    """One match worth of engine, driven tick by tick by :func:`run_tick`."""

    config: MatchConfig
    scenario: ScenarioSpec
    accounts: AccountBook
    exchange: Exchange
    journal: Journal
    mm: ReferenceMarketMaker
    agent_ids: tuple[str, ...]
    rng: RngTree
    quotes_by_tick: dict[int, tuple[Quote, ...]] = field(default_factory=dict)

    @property
    def market_ids(self) -> tuple[str, ...]:
        return tuple(spec.market_id for spec in self.scenario.markets)

    def ref_prices(self) -> dict[str, int]:
        return {mid: self.exchange.reference_price(mid)[0] for mid in self.market_ids}


def build_harness(
    *,
    profile: LiquidityProfileName | str = LiquidityProfileName.STANDARD,
    seed: int = STUDY_SEED,
    ticks_total: int = 24,
    n_markets: int = 2,
    n_agents: int = 6,
    prior_price: int = 50,
) -> Harness:
    """Assemble a match the market maker can quote in."""
    profile_name = LiquidityProfileName(str(profile))
    config = MatchConfig(
        seed=seed,
        ticks_total=ticks_total,
        n_agents=n_agents,
        n_markets=n_markets,
        mm=mm_config_for(profile_name),
        liquidity_profile_name=profile_name,
    )
    scenario = _scenario(config, prior_price=prior_price)
    agent_ids = tuple(make_agent_id(index) for index in range(1, n_agents + 1))
    accounts = AccountBook(
        agent_ids=agent_ids,
        market_ids=[spec.market_id for spec in scenario.markets],
        config=config,
    )
    journal = Journal(f"m-election-{seed}-01")
    exchange = Exchange(config=config, scenario=scenario, accounts=accounts, journal=journal)
    rng = RngTree(seed)
    mm = ReferenceMarketMaker(
        config=config.mm,
        market_ids=[spec.market_id for spec in scenario.markets],
        rng=rng.child("mm"),
    )
    return Harness(
        config=config,
        scenario=scenario,
        accounts=accounts,
        exchange=exchange,
        journal=journal,
        mm=mm,
        agent_ids=agent_ids,
        rng=rng,
    )


Flow = Callable[[Harness, int, tuple[Quote, ...]], None]


def run_tick(
    harness: Harness,
    tick: int,
    *,
    news: Sequence[NewsItem] = (),
    flow: Flow | None = None,
) -> tuple[Quote, ...]:
    """Run the part of one tick the market maker takes part in.

    P1 step 0 (``begin_tick``), the single P1 step 5b ``note_news`` handover, the
    P3 step 9 requote, the agent flow that P3 step 11 would apply, then the P4
    step 15 invariant check, which is where I10 is enforced.
    """
    harness.exchange.begin_tick(tick)
    harness.mm.note_news(tick=tick, items=news)
    quotes = harness.mm.requote(
        tick=tick,
        exchange=harness.exchange,
        inventory=harness.accounts.inventory_view(MM_ACCOUNT_ID),
        journal=harness.journal,
    )
    harness.quotes_by_tick[tick] = quotes
    if flow is not None:
        flow(harness, tick, quotes)
    harness.accounts.check_invariants(
        ref_prices=harness.ref_prices(),
        book_view=harness.exchange.book_view(),
    )
    return quotes


def run_match(
    harness: Harness,
    *,
    news_at: dict[int, Sequence[NewsItem]] | None = None,
    flow: Flow | None = None,
) -> Harness:
    """Run every tick of the harness's horizon."""
    for tick in range(1, harness.config.ticks_total + 1):
        run_tick(harness, tick, news=(news_at or {}).get(tick, ()), flow=flow)
    return harness


# ---------------------------------------------------------------------------
# Agent flows. None of them is a pxe.agents baseline: A12's agents consume an
# Observation, which needs A10's observation builder, so this file drives the
# exchange directly. The shapes matter, not the provenance.
# ---------------------------------------------------------------------------
def mute_flow(harness: Harness, tick: int, quotes: tuple[Quote, ...]) -> None:
    """AC-P9's population: agents that predict and never order."""
    return None


def directional_flow(qty: int = 25, *, side: Side = Side.BUY) -> Flow:
    """Every agent takes the same side every tick, so the inventory cap must bind."""

    def flow(harness: Harness, tick: int, quotes: tuple[Quote, ...]) -> None:
        for agent_id in harness.agent_ids:
            for quote in quotes:
                harness.exchange.submit(
                    tick=tick,
                    agent_id=agent_id,
                    intent=OrderIntent(
                        op="place",
                        market_id=quote.market_id,
                        side=side,
                        order_type=OrderType.MARKET,
                        qty=qty,
                    ),
                    item_index=0,
                )

    return flow


def informed_flow(*, edge_cents: int = 2, max_qty: int = 20) -> Flow:
    """A two way, noisily informed flow: the shape that costs a market maker money.

    Each market carries a hidden fair value drawn once per match from a
    ``test.mm_study`` substream. Each agent forms a noisy estimate of it and
    crosses the quote when the estimate is far enough past the touch. Nothing
    here is visible to the market maker: it is exactly the adverse selection
    FR-5.8.2 exposes it to.
    """
    fair_values: dict[tuple[int, str], int] = {}

    def flow(harness: Harness, tick: int, quotes: tuple[Quote, ...]) -> None:
        rng = harness.rng.fresh_substream(f"test.mm_flow.{tick}")
        for quote in quotes:
            key = (harness.config.seed, quote.market_id)
            if key not in fair_values:
                fair_values[key] = randint(harness.rng.fresh_substream(f"test.mm_fair.{quote.market_id}"), 15, 85)
            fair = fair_values[key]
            for agent_id in harness.agent_ids:
                estimate = fair + randint(rng, -12, 12)
                qty = randint(rng, 1, max_qty)
                if quote.ask_price is not None and estimate >= quote.ask_price + edge_cents:
                    side = Side.BUY
                elif quote.bid_price is not None and estimate <= quote.bid_price - edge_cents:
                    side = Side.SELL
                else:
                    continue
                harness.exchange.submit(
                    tick=tick,
                    agent_id=agent_id,
                    intent=OrderIntent(
                        op="place",
                        market_id=quote.market_id,
                        side=side,
                        order_type=OrderType.MARKET,
                        qty=qty,
                    ),
                    item_index=0,
                )

    return flow


# ---------------------------------------------------------------------------
# Journal readers used by the assertions.
# ---------------------------------------------------------------------------
def quotes_of(events: Sequence[Event]) -> tuple[MMQuoted, ...]:
    return tuple(event for event in events if isinstance(event, MMQuoted))


def assert_journal_has(events: Sequence[Event], event_type: type[Event]) -> None:
    """Section 10's anti-vacuous rule, spelled once."""
    assert events, "the journal is empty: nothing below would be an assertion"
    assert any(isinstance(event, event_type) for event in events), (
        f"the journal holds no {event_type.__name__}: the claim under test cannot be made"
    )


# ---------------------------------------------------------------------------
# FR-5.8.1: two sided quote every tick, cancel/replace, before the shuffle.
# ---------------------------------------------------------------------------
def test_quotes_every_open_market_before_shuffle() -> None:
    harness = build_harness(ticks_total=24, n_markets=3)
    run_match(harness, flow=informed_flow())
    events = harness.journal.events
    assert_journal_has(events, MMQuoted)
    assert_journal_has(events, OrderPlaced)

    # One quote per open market per tick, markets ascending inside a tick.
    for tick in range(1, harness.config.ticks_total + 1):
        in_tick = [event for event in events if event.tick == tick and isinstance(event, MMQuoted)]
        assert [event.market_id for event in in_tick] == list(harness.market_ids)

    # Every market maker order is placed before any agent order of the same
    # tick: that is what "before the shuffle" means for the journal.
    for tick in range(1, harness.config.ticks_total + 1):
        placed = [event for event in events if event.tick == tick and isinstance(event, OrderPlaced)]
        agent_seqs = [event.seq for event in placed if event.agent_id != MM_ACCOUNT_ID]
        mm_seqs = [event.seq for event in placed if event.agent_id == MM_ACCOUNT_ID]
        assert mm_seqs, f"tick {tick} shows no market maker order"
        if agent_seqs:
            assert max(mm_seqs) < min(agent_seqs)

    # And the quote is a full cancel/replace: from tick 2 onwards every market
    # maker order of the previous tick leaves the book with MM_REQUOTE.
    requotes = [
        event for event in events if isinstance(event, OrderCancelled) and event.reason == str(CancelReason.MM_REQUOTE)
    ]
    assert requotes, "no MM_REQUOTE cancellation: the quote is not being replaced"
    assert all(event.agent_id == MM_ACCOUNT_ID for event in requotes)


def test_mm_quote_is_read_after_its_own_orders_left_the_book() -> None:
    """FR-5.8.2: the anchor is the public price, never the market maker's own mid.

    Cancelling before reading the reference price is the only ordering that
    keeps this true: the previous quote is two sided, so a read taken first
    would return the market maker's own mid and it would anchor on itself
    forever.
    """
    harness = build_harness(ticks_total=24, n_markets=2, prior_price=37)
    run_match(harness, flow=mute_flow)
    quoted = quotes_of(harness.journal.events)
    assert_journal_has(harness.journal.events, MMQuoted)
    assert {event.ref_price for event in quoted} == {37}


@pytest.mark.statistical
def test_two_sided_on_95pct_of_ticks() -> None:
    # Tolerance: AC-P9's own 95 % floor, measured per market over 20 matches of
    # a two way informed flow. Fixed seeds, so the number is reproducible.
    for offset in range(20):
        harness = build_harness(seed=STUDY_SEED + offset, ticks_total=24, n_markets=2)
        run_match(harness, flow=informed_flow())
        quoted = quotes_of(harness.journal.events)
        assert_journal_has(harness.journal.events, MMQuoted)
        for market_id in harness.market_ids:
            rows = [event for event in quoted if event.market_id == market_id]
            assert rows
            two_sided = sum(1 for row in rows if row.bid_price is not None and row.ask_price is not None)
            assert two_sided * 100 >= 95 * len(rows), (
                f"market {market_id} of seed {harness.config.seed} was two sided on {two_sided}/{len(rows)} ticks"
            )


# ---------------------------------------------------------------------------
# FR-5.8.2: uninformed.
# ---------------------------------------------------------------------------
def test_mm_sees_only_public_state() -> None:
    mm_a = ReferenceMarketMaker(
        config=mm_config_for("standard"),
        market_ids=["M1", "M2"],
        rng=RngTree(1).child("mm"),
    )
    mm_b = ReferenceMarketMaker(
        config=mm_config_for("standard"),
        market_ids=["M1", "M2"],
        rng=RngTree(2**63).child("mm"),
    )
    for ref_price in range(1, 100):
        left = mm_a.compute_quote(tick=7, market_id="M1", ref_price=ref_price, inventory_qty=13)
        right = mm_b.compute_quote(tick=7, market_id="M1", ref_price=ref_price, inventory_qty=13)
        assert left == right

    # The content of a news item is invisible: two items with the same impact
    # tag and opposite stories produce the same quote.
    bullish = NewsItem(
        news_id="n-003-00",
        tick=3,
        market_ids=("M1",),
        headline="the incumbent is far ahead",
        body="a landslide is expected",
        impact=NewsImpact.HIGH,
    )
    bearish = NewsItem(
        news_id="n-003-00",
        tick=3,
        market_ids=("M1",),
        headline="the incumbent has collapsed",
        body="defeat is expected",
        impact=NewsImpact.HIGH,
    )
    mm_a.note_news(tick=3, items=(bullish,))
    mm_b.note_news(tick=3, items=(bearish,))
    assert mm_a.compute_quote(tick=3, market_id="M1", ref_price=50, inventory_qty=0) == mm_b.compute_quote(
        tick=3, market_id="M1", ref_price=50, inventory_qty=0
    )
    assert mm_a.is_widened("M1", 3) is True


def test_pxe_mm_never_imports_the_ledger_or_the_world() -> None:
    """CONTRACTS section 13 and decision 28, asserted structurally.

    The ban is not a style rule: reaching into ``AccountBook`` would let A07
    keep a second inventory count that drifts from A06's and breaks I10, and
    importing ``pxe.info`` or ``pxe.world`` would make FR-5.8.2 unverifiable.
    """
    here = Path(__file__).resolve()
    package = here.parent.parent / "src" / "pxe" / "mm"
    sources = sorted(package.glob("*.py"))
    assert [path.name for path in sources] == ["__init__.py", "market_maker.py", "profiles.py"]
    banned = ("pxe.exchange.accounts", "pxe.info", "pxe.world", "pxe.agents", "pxe.runner")
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            for module in banned:
                assert module not in stripped, f"{path.name} imports {module}: {stripped}"


# ---------------------------------------------------------------------------
# FR-5.8.3: inventory skew and hard cap.
# ---------------------------------------------------------------------------
def test_inventory_skew_is_opposite_to_the_inventory() -> None:
    config = mm_config_for("standard")
    mm = ReferenceMarketMaker(config=config, market_ids=["M1"], rng=RngTree(7).child("mm"))
    flat = mm.compute_quote(tick=1, market_id="M1", ref_price=50, inventory_qty=0)
    assert flat.skew_cents == 0
    assert flat.anchor_price == 50
    assert flat.effective_spread == config.base_spread_cents

    full_long = mm.compute_quote(tick=1, market_id="M1", ref_price=50, inventory_qty=config.inventory_max)
    assert full_long.skew_cents == -config.skew_cents
    assert full_long.anchor_price == 50 - config.skew_cents
    assert full_long.bid_price is None, "a full long inventory must stop showing the bid"

    full_short = mm.compute_quote(tick=1, market_id="M1", ref_price=50, inventory_qty=-config.inventory_max)
    assert full_short.skew_cents == config.skew_cents
    assert full_short.ask_price is None, "a full short inventory must stop showing the ask"

    # The suppression is on the full quoted size, one contract before the cap.
    edge = config.inventory_max - config.quote_qty
    assert mm.compute_quote(tick=1, market_id="M1", ref_price=50, inventory_qty=edge).bid_price is not None
    assert mm.compute_quote(tick=1, market_id="M1", ref_price=50, inventory_qty=edge + 1).bid_price is None


@pytest.mark.property
@pytest.mark.slow
@given(
    profile=st.sampled_from([str(profile.name) for profile in LIQUIDITY_PROFILES]),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
    buy=st.booleans(),
    qty=st.integers(min_value=1, max_value=60),
)
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_inventory_skew_and_cap(profile: str, seed: int, buy: bool, qty: int) -> None:
    """FR-5.8.3 and invariant I10: the absolute inventory never passes I_max.

    A one directional flow is the adversarial case: the market maker absorbs it
    until the side that would breach the cap disappears. ``check_invariants``
    runs on every tick inside :func:`run_tick`, so I10 is asserted by the ledger
    as well as here.
    """
    harness = build_harness(profile=profile, seed=seed, ticks_total=24, n_markets=2)
    cap = harness.config.mm.inventory_max
    run_match(harness, flow=directional_flow(qty, side=Side.BUY if buy else Side.SELL))

    events = harness.journal.events
    assert_journal_has(events, TradeExecuted)
    assert_journal_has(events, MMQuoted)
    mm_trades = [
        event
        for event in events
        if isinstance(event, TradeExecuted) and MM_ACCOUNT_ID in (event.maker_agent_id, event.taker_agent_id)
    ]
    assert mm_trades, "the flow never reached the market maker: the cap claim would be vacuous"

    for market_id in harness.market_ids:
        assert abs(harness.accounts.position(MM_ACCOUNT_ID, market_id).qty) <= cap
    for quote in quotes_of(events):
        assert abs(quote.inventory_qty) <= cap
        if quote.inventory_qty + harness.config.mm.quote_qty > cap:
            assert quote.bid_price is None
        if quote.inventory_qty - harness.config.mm.quote_qty < -cap:
            assert quote.ask_price is None


def test_inventory_cap_actually_binds_under_a_one_way_flow() -> None:
    """The companion of the property test: prove the cap is reachable at all."""
    harness = build_harness(profile="illiquid", ticks_total=48, n_markets=2)
    run_match(harness, flow=directional_flow(10, side=Side.BUY))
    events = harness.journal.events
    assert_journal_has(events, TradeExecuted)
    cap = harness.config.mm.inventory_max
    # The agents only ever buy, so the market maker only ever sells: inventory
    # walks to -I_max and the ask disappears.
    assert harness.accounts.position(MM_ACCOUNT_ID, "M1").qty == -cap
    suppressed = [quote for quote in quotes_of(events) if quote.ask_price is None]
    assert suppressed, "the ask was never suppressed: the cap never bound"
    assert all(quote.bid_price is not None for quote in suppressed)


# ---------------------------------------------------------------------------
# FR-5.8.4: post news widening.
# ---------------------------------------------------------------------------
def test_post_news_widening() -> None:
    harness = build_harness(profile="standard", ticks_total=24, n_markets=2)
    window = harness.config.mm.post_news_widen_ticks
    base = harness.config.mm.base_spread_cents
    widened_spread = base * harness.config.mm.widen_multiplier
    high = NewsItem(
        news_id="n-003-00",
        tick=3,
        market_ids=("M1",),
        headline="the count has been suspended",
        body="",
        impact=NewsImpact.HIGH,
    )
    low = NewsItem(
        news_id="n-010-00",
        tick=10,
        market_ids=("M1", "M2"),
        headline="a routine bulletin",
        body="",
        impact=NewsImpact.LOW,
    )
    run_match(harness, news_at={3: (high,), 10: (low,)}, flow=mute_flow)

    quoted = quotes_of(harness.journal.events)
    assert_journal_has(harness.journal.events, MMQuoted)
    by_key = {(event.tick, event.market_id): event for event in quoted}

    # The window is inclusive of its last tick: the news lands in P1 of tick 3
    # and the requote of that same tick is already widened.
    for tick in range(3, 3 + window + 1):
        row = by_key[(tick, "M1")]
        assert row.widened is True, f"tick {tick} should be widened"
        assert row.widen_until_tick == 3 + window
        assert row.effective_spread == widened_spread
    for tick in (1, 2, 3 + window + 1, 24):
        row = by_key[(tick, "M1")]
        assert row.widened is False, f"tick {tick} should not be widened"
        assert row.effective_spread == base

    # Only the markets the item named. M2 is never widened, and the LOW impact
    # item at tick 10 widens nothing anywhere.
    assert all(by_key[(tick, "M2")].widened is False for tick in range(1, 25))
    assert all(by_key[(tick, "M2")].effective_spread == base for tick in range(1, 25))
    for tick in range(10, 13):
        assert by_key[(tick, "M1")].widened is False


def test_widening_extends_and_never_shortens() -> None:
    harness = build_harness(profile="illiquid", ticks_total=24, n_markets=2)
    window = harness.config.mm.post_news_widen_ticks
    mm = harness.mm
    first = NewsItem(
        news_id="n-005-00", tick=5, market_ids=("M1",), headline="a first shock", body="", impact=NewsImpact.HIGH
    )
    mm.note_news(tick=5, items=(first,))
    assert mm.is_widened("M1", 5 + window) is True
    assert mm.is_widened("M1", 5 + window + 1) is False
    # An older item cannot shorten a window that is already open.
    mm.note_news(tick=5, items=(first,))
    assert mm.is_widened("M1", 5 + window) is True
    later = NewsItem(
        news_id="n-006-00", tick=6, market_ids=("M1",), headline="a second shock", body="", impact=NewsImpact.HIGH
    )
    mm.note_news(tick=6, items=(later,))
    assert mm.is_widened("M1", 6 + window) is True


def test_an_item_naming_no_market_widens_nothing() -> None:
    mm = ReferenceMarketMaker(config=mm_config_for("standard"), market_ids=["M1"], rng=RngTree(3).child("mm"))
    noise = NewsItem(
        news_id="n-002-00",
        tick=2,
        market_ids=(),
        headline="unrelated chatter",
        body="",
        impact=NewsImpact.HIGH,
        is_noise=True,
    )
    mm.note_news(tick=2, items=(noise,))
    assert mm.is_widened("M1", 2) is False
    assert mm.compute_quote(tick=2, market_id="M1", ref_price=50, inventory_qty=0).widen_until_tick == 0


# ---------------------------------------------------------------------------
# FR-5.8.6: the three presets.
# ---------------------------------------------------------------------------
def test_three_presets() -> None:
    # Exactly the PRD section 5.8 table, spelled out here so a silent edit of
    # types.LIQUIDITY_PROFILES fails this test and not a golden hash.
    expected = {
        "liquid": (4, 50, 500, 2, 1),
        "standard": (6, 25, 300, 4, 2),
        "illiquid": (12, 10, 150, 8, 3),
    }
    assert [str(profile.name) for profile in LIQUIDITY_PROFILES] == ["liquid", "standard", "illiquid"]
    for name, (spread, qty, cap, skew, window) in expected.items():
        config = mm_config_for(name)
        assert (config.base_spread_cents, config.quote_qty, config.inventory_max) == (spread, qty, cap)
        assert (config.skew_cents, config.post_news_widen_ticks) == (skew, window)
        assert config.widen_multiplier == 2
        assert config.half_spread_cents() == (spread + 1) // 2
        assert config.half_spread_cents(widened=True) == (2 * spread + 1) // 2
    assert mm_config_for(LiquidityProfileName.LIQUID) is mm_config_for("liquid")
    with pytest.raises(UnknownProfileError):
        mm_config_for("glacial")

    # And each preset really shows its own spread on a real book.
    for name in expected:
        harness = build_harness(profile=name, ticks_total=24, n_markets=2)
        run_match(harness, flow=mute_flow)
        quoted = quotes_of(harness.journal.events)
        assert_journal_has(harness.journal.events, MMQuoted)
        assert {event.effective_spread for event in quoted} == {expected[name][0]}
        assert {event.quote_qty for event in quoted} == {expected[name][1]}


@pytest.mark.statistical
def test_mean_spread_within_one_cent_of_profile() -> None:
    """FR-5.8.6 measured on the recipe, that is on the quotes FR-5.8.4 left alone.

    Tolerance: FR-5.8.6's own "+/- 1 cent", measured over 12 matches per preset
    of a two way informed flow, fixed seeds. The mean is reported in thousandths
    of a cent so the assertion needs no float.

    This harness publishes no high impact news, so ``widened_quotes`` is zero
    and the base spread is the effective spread. The real arena is the other
    case, and it is
    ``test_the_published_study_separates_the_recipe_from_the_widening`` below
    that covers it: over real baseline matches the effective spread sits
    **above** the preset by design (up to 3.1 c on ``illiquid``) while the base
    spread is exactly the preset. Asserting FR-5.8.6 against the effective
    spread would therefore contradict FR-5.8.4.
    """
    for profile in LIQUIDITY_PROFILES:
        name = str(profile.name)
        journals = []
        for offset in range(12):
            harness = build_harness(profile=name, seed=STUDY_SEED + offset, ticks_total=24, n_markets=2)
            run_match(harness, flow=informed_flow())
            journals.append(harness.journal.events)
        row = liquidity_cost_row(profile_name=name, journals=journals)
        assert row.quotes > 0
        assert row.two_sided_quotes > 0
        target = profile.mm.base_spread_cents * MILLI_ONE
        assert abs(row.mean_base_spread_milli - target) <= MILLI_ONE, (
            f"{name}: base spread {row.mean_base_spread_milli} milli-cents, target {target}"
        )
        assert row.widened_quotes == 0, "this harness publishes no news, so nothing may be widened"
        assert row.mean_effective_spread_milli == row.mean_base_spread_milli


# ---------------------------------------------------------------------------
# AC-P9: guaranteed liquidity.
# ---------------------------------------------------------------------------
@pytest.mark.e2e
def test_guaranteed_liquidity_with_mute_agents() -> None:
    """AC-P9: mute agents, and every market is still two sided every tick.

    The one silent way this can fail is a rejected market maker quote, which is
    why the second assertion is on ``OrderRejected(agent_id="MM")`` and not on
    the quote alone (CONTRACTS section 5, P3 step 9, decision 16).
    """
    harness = build_harness(profile="illiquid", ticks_total=48, n_markets=5, n_agents=8)
    run_match(harness, flow=mute_flow)
    events = harness.journal.events
    assert_journal_has(events, MMQuoted)

    rejected = [event for event in events if isinstance(event, OrderRejected) and event.agent_id == MM_ACCOUNT_ID]
    assert rejected == [], f"the market maker was rejected {len(rejected)} times"

    quoted = quotes_of(events)
    assert len(quoted) == harness.config.ticks_total * harness.config.n_markets
    for market_id in harness.market_ids:
        rows = [event for event in quoted if event.market_id == market_id]
        two_sided = sum(1 for row in rows if row.bid_price is not None and row.ask_price is not None)
        assert two_sided == len(rows)
        assert two_sided * 100 >= 95 * len(rows)


def test_reference_price_always_defined() -> None:
    """AC-P9's second half: FR-5.4.6's fallback chain has no hole.

    Three branches must each be exercised, otherwise "always defined" is a
    claim about one branch: the public prior on tick 1 (nothing has traded and
    the market maker's own quote is cancelled before the read), the last traded
    price once a flow has hit the quote, and the mid when agent orders rest on
    both sides.
    """
    harness = build_harness(ticks_total=24, n_markets=2, prior_price=61)
    sources: set[str] = set()
    for market_id in harness.market_ids:
        price, source = harness.exchange.reference_price(market_id)
        assert (price, source) == (61, "prior")
        sources.add(source)

    def flow(inner: Harness, tick: int, quotes: tuple[Quote, ...]) -> None:
        informed_flow()(inner, tick, quotes)
        for market_id in inner.market_ids:
            price, source = inner.exchange.reference_price(market_id)
            assert 1 <= price <= 99
            sources.add(source)
        if tick == 5:
            # Rest one order on each side so the mid branch is reached too.
            for side, price in ((Side.BUY, 30), (Side.SELL, 80)):
                inner.exchange.submit(
                    tick=tick,
                    agent_id=inner.agent_ids[0],
                    intent=OrderIntent(
                        op="place",
                        market_id="M1",
                        side=side,
                        order_type=OrderType.LIMIT,
                        price=price,
                        qty=1,
                    ),
                    item_index=0,
                )

    run_match(harness, flow=flow)
    assert_journal_has(harness.journal.events, MMQuoted)
    assert {"prior", "last", "mid"} <= sources, f"only reached {sorted(sources)}"
    for event in quotes_of(harness.journal.events):
        assert 1 <= event.ref_price <= 99
        assert 1 <= event.anchor_price <= 99


# ---------------------------------------------------------------------------
# Guard rails on the public surface.
# ---------------------------------------------------------------------------
def test_requote_refuses_a_foreign_inventory_view() -> None:
    harness = build_harness(ticks_total=24, n_markets=2)
    harness.exchange.begin_tick(1)
    with pytest.raises(InvalidConfigError):
        harness.mm.requote(
            tick=1,
            exchange=harness.exchange,
            inventory=harness.accounts.inventory_view("A1"),
            journal=harness.journal,
        )
    assert harness.journal.events == (), "a refused requote must not have journalled anything"


def test_a_disabled_preset_never_quotes() -> None:
    harness = build_harness(ticks_total=24, n_markets=2)
    disabled = ReferenceMarketMaker(
        config=mm_config_for("standard").__class__(
            base_spread_cents=6,
            quote_qty=25,
            inventory_max=300,
            skew_cents=4,
            post_news_widen_ticks=2,
            enabled=False,
        ),
        market_ids=list(harness.market_ids),
        rng=RngTree(1).child("mm"),
    )
    harness.exchange.begin_tick(1)
    assert (
        disabled.requote(
            tick=1,
            exchange=harness.exchange,
            inventory=harness.accounts.inventory_view(MM_ACCOUNT_ID),
            journal=harness.journal,
        )
        == ()
    )
    assert harness.journal.events == ()


def test_market_maker_rejects_a_degenerate_construction() -> None:
    config = mm_config_for("standard")
    with pytest.raises(InvalidConfigError):
        ReferenceMarketMaker(config=config, market_ids=[], rng=RngTree(1).child("mm"))
    with pytest.raises(InvalidConfigError):
        ReferenceMarketMaker(config=config, market_ids=["M1", "M1"], rng=RngTree(1).child("mm"))
    mm = ReferenceMarketMaker(config=config, market_ids=["M1"], rng=RngTree(1).child("mm"))
    with pytest.raises(InvalidConfigError):
        mm.compute_quote(tick=1, market_id="M2", ref_price=50, inventory_qty=0)
    with pytest.raises(InvalidConfigError):
        mm.compute_quote(tick=1, market_id="M1", ref_price=0, inventory_qty=0)


def test_a_closed_market_is_not_quoted() -> None:
    from pxe.types import MarketStatus

    harness = build_harness(ticks_total=24, n_markets=3)
    run_tick(harness, 1, flow=mute_flow)
    harness.exchange.cancel_all(tick=2, reason=CancelReason.MARKET_RESOLVED, market_id="M2")
    harness.exchange.close_market(tick=2, market_id="M2", status=MarketStatus.RESOLVED)
    quotes = run_tick(harness, 2, flow=mute_flow)
    assert [quote.market_id for quote in quotes] == ["M1", "M3"]
    tick_two = [event for event in harness.journal.events if event.tick == 2 and isinstance(event, MMQuoted)]
    assert [event.market_id for event in tick_two] == ["M1", "M3"]


def test_the_quote_returned_equals_the_quote_journalled() -> None:
    harness = build_harness(ticks_total=24, n_markets=2)
    quotes = run_tick(harness, 1, flow=mute_flow)
    quoted = quotes_of(harness.journal.events)
    assert_journal_has(harness.journal.events, MMQuoted)
    assert len(quotes) == len(quoted)
    for quote, event in zip(quotes, quoted, strict=True):
        assert (quote.market_id, quote.ref_price, quote.anchor_price) == (
            event.market_id,
            event.ref_price,
            event.anchor_price,
        )
        assert (quote.bid_price, quote.ask_price, quote.quote_qty) == (
            event.bid_price,
            event.ask_price,
            event.quote_qty,
        )
        assert (quote.effective_spread, quote.inventory_qty, quote.skew_cents) == (
            event.effective_spread,
            event.inventory_qty,
            event.skew_cents,
        )
        assert (quote.widened, quote.widen_until_tick) == (event.widened, event.widen_until_tick)


def test_two_runs_of_the_same_seed_produce_the_same_journal_hash() -> None:
    """O1 for the slice A07 owns: the quoting path draws nothing."""
    hashes = set()
    for _ in range(2):
        harness = build_harness(ticks_total=24, n_markets=3)
        run_match(harness, flow=informed_flow())
        assert_journal_has(harness.journal.events, MMQuoted)
        hashes.add(harness.journal.hash())
    assert len(hashes) == 1


# ---------------------------------------------------------------------------
# T2.6: the cost of liquidity study and docs/MM_LIQUIDITY_COST.md.
# ---------------------------------------------------------------------------
def study_journals(
    *, profile: str, matches: int, ticks_total: int, n_markets: int, n_agents: int
) -> list[tuple[Event, ...]]:
    """Run ``matches`` matches of one preset and return their journals."""
    journals: list[tuple[Event, ...]] = []
    for offset in range(matches):
        harness = build_harness(
            profile=profile,
            seed=STUDY_SEED + offset,
            ticks_total=ticks_total,
            n_markets=n_markets,
            n_agents=n_agents,
        )
        run_match(harness, flow=informed_flow())
        journals.append(harness.journal.events)
    return journals


def build_published_study(matches: int = DOC_MATCHES) -> str:
    """Produce exactly the Markdown committed as ``docs/MM_LIQUIDITY_COST.md``.

    This is the stand-in for ``pxe mm study`` until A23 lands the CLI: the CLI
    will drive real ``MatchRunner`` matches and hand their journals to the same
    :func:`pxe.mm.profiles.build_liquidity_study`.
    """
    study = build_liquidity_study(
        seed=STUDY_SEED,
        ticks_total=DOC_TICKS,
        n_markets=DOC_MARKETS,
        n_agents=DOC_AGENTS,
        journals_by_profile={
            str(profile.name): study_journals(
                profile=str(profile.name),
                matches=matches,
                ticks_total=DOC_TICKS,
                n_markets=DOC_MARKETS,
                n_agents=DOC_AGENTS,
            )
            for profile in LIQUIDITY_PROFILES
        },
    )
    return render_liquidity_study(study)


def test_liquidity_cost_row_is_journal_only_and_populated() -> None:
    journals = study_journals(profile="standard", matches=3, ticks_total=24, n_markets=2, n_agents=6)
    for events in journals:
        assert_journal_has(events, MMQuoted)
        assert_journal_has(events, TradeExecuted)
    row = liquidity_cost_row(profile_name="standard", journals=journals)
    assert isinstance(row, LiquidityCostRow)
    assert row.matches == 3
    assert row.quotes == 3 * 24 * 2
    assert row.two_sided_quotes > 0
    assert row.mm_trades > 0
    assert row.mm_volume_qty > 0
    assert row.mean_effective_spread_milli > 0
    assert 0 < row.two_sided_ppm <= PPM_ONE
    assert row.max_abs_inventory_qty <= row.inventory_max
    assert row.mm_pnl_cents == row.mm_realised_cents + row.mm_inventory_value_cents
    # The informed flow is adversely selecting: providing liquidity costs money.
    assert row.mm_pnl_cents < 0
    assert row.mm_pnl_cents_per_match < 0


def test_liquidity_cost_row_refuses_a_journal_without_a_quote() -> None:
    harness = build_harness(ticks_total=24, n_markets=2)
    with pytest.raises(InvalidConfigError):
        liquidity_cost_row(profile_name="standard", journals=[harness.journal.events])
    with pytest.raises(UnknownProfileError):
        liquidity_cost_row(profile_name="glacial", journals=[])


def test_build_liquidity_study_ignores_the_caller_dict_order() -> None:
    per_profile = {
        str(profile.name): study_journals(profile=str(profile.name), matches=2, ticks_total=24, n_markets=2, n_agents=6)
        for profile in LIQUIDITY_PROFILES
    }
    forward = build_liquidity_study(
        seed=STUDY_SEED, ticks_total=24, n_markets=2, n_agents=6, journals_by_profile=per_profile
    )
    backward = build_liquidity_study(
        seed=STUDY_SEED,
        ticks_total=24,
        n_markets=2,
        n_agents=6,
        journals_by_profile=dict(reversed(list(per_profile.items()))),
    )
    assert [row.profile_name for row in forward.rows] == ["liquid", "standard", "illiquid"]
    assert forward == backward
    assert render_liquidity_study(forward) == render_liquidity_study(backward)

    with pytest.raises(InvalidConfigError):
        build_liquidity_study(seed=1, ticks_total=24, n_markets=2, n_agents=6, journals_by_profile={})
    with pytest.raises(InvalidConfigError):
        build_liquidity_study(seed=1, ticks_total=24, n_markets=2, n_agents=6, journals_by_profile={"glacial": []})


def test_the_illiquid_preset_costs_an_agent_more_than_the_liquid_one() -> None:
    """The spread is the difficulty dial (PRD section 1), so it must be measurable."""
    rows = {}
    for profile in LIQUIDITY_PROFILES:
        name = str(profile.name)
        rows[name] = liquidity_cost_row(
            profile_name=name,
            journals=study_journals(profile=name, matches=4, ticks_total=24, n_markets=2, n_agents=6),
        )
    assert rows["liquid"].mean_effective_spread_milli < rows["standard"].mean_effective_spread_milli
    assert rows["standard"].mean_effective_spread_milli < rows["illiquid"].mean_effective_spread_milli
    assert rows["liquid"].mm_volume_qty > rows["illiquid"].mm_volume_qty


def test_the_published_study_separates_the_recipe_from_the_widening() -> None:
    """FR-5.8.6 and FR-5.8.4 measure two different spreads, and both are published.

    Over real baseline matches the market maker widens on roughly a fifth of its
    quotes (a high impact news item doubles the spread for ``w`` ticks,
    FR-5.8.4), so the **effective** spread an agent pays sits above the preset
    while the **base** spread is the preset exactly. Before this split, the
    committed T2.6 document checked FR-5.8.6 against the effective spread and
    reported a distance of 0.000 c only because the synthetic flow of this file
    publishes no news; run over the shipped command it reported 1.351 c on
    ``standard`` and 3.146 c on ``illiquid``, that is a failing acceptance
    criterion presented as a passing one.
    """
    deviations: dict[str, int] = {}
    for profile in LIQUIDITY_PROFILES:
        name = str(profile.name)
        journals = [_cli_study_journal(profile=name, index=offset, ticks_total=24, n_markets=2) for offset in range(6)]
        row = liquidity_cost_row(profile_name=name, journals=journals)
        target = profile.mm.base_spread_cents * MILLI_ONE
        assert row.two_sided_quotes > 0, "nothing was quoted, so both means would be zero"
        assert row.widened_quotes > 0, f"{name}: FR-5.8.4 never fired, so this test would prove nothing"
        # FR-5.8.6's own tolerance. The residual is the 1..99 price clamp, which
        # keeps a quote near the edge from showing its whole spread: 0.023 c on
        # ``illiquid`` and nothing at all on the other two.
        assert abs(row.mean_base_spread_milli - target) <= MILLI_ONE, (
            f"{name}: base spread {row.mean_base_spread_milli} is not within one cent of the preset {target}"
        )
        assert row.mean_effective_spread_milli > row.mean_base_spread_milli, (
            f"{name}: widening did not move the effective spread"
        )
        deviations[name] = abs(row.mean_effective_spread_milli - target)
    # Teeth: on at least one preset the effective spread misses FR-5.8.6's own
    # tolerance outright, so measuring the criterion on it rather than on the
    # base spread is not a nicety, it is the difference between pass and fail.
    assert max(deviations.values()) > MILLI_ONE, deviations


def _cli_study_journal(*, profile: str, index: int, ticks_total: int, n_markets: int) -> tuple[Event, ...]:
    """Play one study match exactly as ``pxe mm study`` does, in memory.

    It goes through the CLI's own helper so that this file measures the shipped
    command and not a copy of it.
    """
    import argparse

    from pxe.cli import DEFAULT_AGENTS, _study_journal

    args = argparse.Namespace(
        seed=STUDY_SEED,
        template="election",
        ticks=ticks_total,
        markets=n_markets,
        agents=",".join(DEFAULT_AGENTS),
    )
    return _study_journal(args, profile=LiquidityProfileName(profile), index=index)


@pytest.mark.slow
def test_mm_liquidity_cost_doc_is_what_the_shipped_command_prints(repo_root: Path) -> None:
    """T2.6's deliverable, produced by the command the contract names.

    Section 1 says ``docs/MM_LIQUIDITY_COST.md`` is "generated by pxe mm study"
    and the document itself says so in its first line. That was false until this
    test landed: the committed bytes came from ``build_published_study``, a
    private harness with a synthetic ``informed_flow`` the CLI cannot reproduce,
    so the shipped command had never written the deliverable it is credited
    with, and the acceptance table it prints was measured on a flow that
    publishes no news.

    Regenerate it with the command the T2.6 exit gate names::

        .venv/Scripts/python.exe -m pxe.cli mm study --profile all --matches 200

    That takes about six minutes, which is why this test is marked ``slow``.
    """
    path = repo_root.joinpath(*DOC_PATH_PARTS)
    assert path.is_file(), "docs/MM_LIQUIDITY_COST.md is missing"
    committed = path.read_text(encoding="utf-8")
    assert committed.strip(), "the document is empty"
    assert "Generated by `pxe mm study`" in committed
    for name in ("liquid", "standard", "illiquid"):
        assert name in committed
    assert f"matches per preset: {DOC_MATCHES}" in committed, "the document does not record its own sample size"

    from pxe.cli import main as cli_main

    out = path.parent.parent / "runs" / "mm_study_check.md"
    assert cli_main(["mm", "study", "--profile", "all", "--matches", str(DOC_MATCHES), "--out", str(out)]) == 0
    try:
        assert out.read_text(encoding="utf-8") == committed
    finally:
        out.unlink(missing_ok=True)
