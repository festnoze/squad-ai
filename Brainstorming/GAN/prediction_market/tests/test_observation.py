"""E1: the run calendar and the observation builder, which is the leak boundary of the whole product.

Two tests here are the ones PRD 6.3 ships with the product, and both are written so that they cannot
pass by accident:

* **the poisoned-future test** injects one of each channel into a bar (a future bar, a future news item,
  a future hive entry, a future memory record, a cash event whose application bar has not completed, a
  ``delisted_at_ms`` and a ``last_bar``), each carrying a string that appears nowhere else, and asserts
  by content match over the rendered observation that none of them surfaces, and that the cash event
  whose application bar **has** completed does;
* **the clock test** is structural rather than an integer scan, exactly as section 8.3 requires: a scan
  cannot pass on legal data, because ``close_at_ms == resolved_at_ms`` is the normal case on both venues
  and ``bars_window = 90`` collides with the bar count of any ninety-bar market. It asserts the recursive
  key set, the bar count on a market of exactly ``bars_window`` bars and again of ``bars_window + 7``,
  and the as-of price on the first bar and on a later one.

The continuous kinds are exercised through test doubles that carry the declared surface of
``pmx.types.ContinuousInstrument``, ``SessionCalendar``, ``CashEvent`` and ``MarketMeta.kind``, none of
which exists in ``pmx.types`` yet (amendment C1b, section 17.9, applied by gate G2). The doubles are
structural, so the moment D1 lands the real types these tests bind to them instead.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import cast

import pytest

from pmx.data.loader import load_dataset, load_manifest
from pmx.data.sessions import in_session
from pmx.engine.calendar import BarSlice, Calendar, meta_kind
from pmx.engine.execution import applies_at as execution_applies_at
from pmx.engine.observation import (
    CASH_EVENTS_VIEW_MAX,
    DESCRIPTION_VIEW_CHARS,
    FORBIDDEN_OBSERVATION_KEYS,
    GATED_MARKET_VIEW_FIELDS,
    GATED_OBSERVATION_FIELDS,
    NEWS_VIEW_TEXT_CHARS,
    SENSOR_NAMES,
    SENSOR_VIEW_FIELDS,
    ResearchLedger,
    assert_no_leak,
    build_grant,
    build_observation,
    cash_event_applies_at,
    completed_bars,
    filter_grant,
    filter_hive_view,
    hours_to_next_bar,
    leak_scan_payload,
    market_view_fields,
    mentions_forbidden_key,
    news_view_of,
    observation_bytes,
    observation_key_set,
    render_observation_json,
    resolve_sensor_set,
    tape_stats_at,
    unsensed_view_fields,
    visible_cash_events,
)
from pmx.errors import (
    InvalidConfigError,
    LeakError,
    ObservationTooLargeError,
    SchemaError,
)
from pmx.journal import canonical_json
from pmx.types import (
    CASH_EVENT_KINDS,
    DATA_CASH_EVENT_KINDS,
    MS_PER_DAY,
    MS_PER_HOUR,
    OBSERVATION_MAX_BYTES,
    Bar,
    CashEventView,
    Dataset,
    DatasetManifest,
    DatasetWindow,
    ForecastView,
    HiveLessonView,
    HiveView,
    LessonView,
    Limits,
    Market,
    MarketMeta,
    MarketQuality,
    MarketView,
    MemoryView,
    NewsItem,
    NewsView,
    NoteView,
    Observation,
    PortfolioView,
    PositionView,
    ResearchGrant,
    ResearchRequest,
    ResolutionView,
    RunConfig,
    Session,
    SessionCalendar,
    Trade,
    bar_of,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_PACK = REPO_ROOT / "data" / "demo_v1"
DAY = MS_PER_DAY
#: A Monday 00:00Z, so that a weekday session calendar in the tests reads as one.
MONDAY = 1_772_409_600_000


# --------------------------------------------------------------------------------------------------
# Builders for the wave-1 types
# --------------------------------------------------------------------------------------------------
def a_bar(
    t_ms: int,
    price_bp: int,
    *,
    volume_milli: int = 4_000,
    n_trades: int = 8,
    bid_bp: int | None = None,
    ask_bp: int | None = None,
) -> Bar:
    return Bar(
        t_ms=t_ms,
        open_bp=price_bp,
        high_bp=price_bp,
        low_bp=price_bp,
        close_bp=price_bp,
        vwap_bp=price_bp,
        volume_milli=volume_milli,
        n_trades=n_trades,
        yes_bid_bp=bid_bp,
        yes_ask_bp=ask_bp,
        open_interest=None,
    )


def a_market(
    market_id: str = "demo-alpha",
    *,
    created_day: int = 0,
    n_bars: int = 10,
    close_day: int | None = None,
    resolved_day: int | None = None,
    prices: Sequence[int] | None = None,
    extra_bars: Sequence[Bar] = (),
    trades: Sequence[Trade] = (),
    quotes: bool = False,
) -> Market:
    """A binary market with dense daily bars from ``created_day`` and a settlement on its last bar.

    ``extra_bars`` is how the poisoned-future test appends a bar that must never be seen: a record the
    builder did not write is exactly what the leak boundary refuses to trust.
    """
    resolved = created_day + n_bars - 1 if resolved_day is None else resolved_day
    closes = list(prices) if prices is not None else [5_000 + 100 * i for i in range(n_bars)]
    bars = [
        a_bar(
            (created_day + index) * DAY,
            closes[index],
            bid_bp=closes[index] - 50 if quotes else None,
            ask_bp=closes[index] + 50 if quotes else None,
        )
        for index in range(n_bars)
    ]
    bars.extend(extra_bars)
    return Market(
        schema_version="market.v2",
        id=market_id,
        provider="demo",
        provider_id=market_id.upper(),
        url="",
        question=f"Will {market_id} resolve YES?",
        description="D" * (DESCRIPTION_VIEW_CHARS + 500),
        category="politics",
        tags=("test",),
        wiki_subjects=(),
        currency="usd",
        source="reconstructed",
        created_at_ms=created_day * DAY,
        close_at_ms=(resolved if close_day is None else close_day) * DAY,
        resolved_at_ms=resolved * DAY,
        resolution=1,
        resolution_source="venue",
        event_key=None,
        interval_min=1_440,
        bars=tuple(bars),
        trades=tuple(trades),
        first_price_bp=4_242,
        final_price_bp=closes[-1],
        hardness_tags=(),
        quality=MarketQuality(
            n_trades=len(trades), unique_bettors=42, life_days=n_bars, volume_milli_total=1, traded_bars=n_bars
        ),
        fee_schedule_id="demo-zero",
        notes="",
    )


def a_news_item(
    news_id: str,
    *,
    published_day: int,
    market_ids: Sequence[str] = (),
    scores: Sequence[int] = (),
    headline: str = "A headline",
    text: str = "T",
    visible_from_ms: int | None = None,
) -> NewsItem:
    published_at_ms = published_day * DAY
    return NewsItem(
        schema_version="news.v1",
        news_id=news_id,
        source="wikipedia_current_events",
        kind="headline",
        published_at_ms=published_at_ms,
        revid=None,
        asof_day=None,
        visible_from_ms=published_at_ms if visible_from_ms is None else visible_from_ms,
        fetched_at_ms=0,
        url="https://example.invalid",
        headline=headline,
        text=text,
        section="politics",
        wiki_links=(),
        source_urls=(),
        match_ids=tuple(market_ids),
        match_scores_permille=tuple(scores),
        lang="en",
        author_key=None,
    )


def demo_manifest() -> DatasetManifest:
    """The committed demo pack's manifest, reused so a synthetic dataset needs no hand-built one."""
    return load_manifest(DEMO_PACK)


def a_dataset(
    markets: Sequence[object],
    *,
    metas: Sequence[MarketMeta] | None = None,
    news: Sequence[NewsItem] = (),
    manifest: DatasetManifest | None = None,
) -> Dataset:
    by_id = {cast(Market, market).id: market for market in markets}
    if metas is None:
        metas = tuple(
            MarketMeta(
                id=market.id,
                provider=market.provider,
                category=market.category,
                tags=market.tags,
                event_key=market.event_key,
                created_at_ms=market.created_at_ms,
                close_at_ms=market.close_at_ms,
                resolved_at_ms=market.resolved_at_ms,
                resolution=market.resolution,
                interval_min=market.interval_min,
                n_bars=len(market.bars),
                hardness_tags=market.hardness_tags,
                fee_schedule_id=market.fee_schedule_id,
                fold="all",
            )
            for market in (cast(Market, item) for item in markets)
        )
    return Dataset(
        manifest=manifest if manifest is not None else demo_manifest(),
        metas=tuple(metas),
        path=DEMO_PACK,
        market_loader=lambda market_id: cast(Market, by_id[market_id]),
        news_loader=lambda: tuple(news),
    )


def a_config(**overrides: object) -> RunConfig:
    """A run config with a fixed seed; every field of section 8.1 keeps its default unless named."""
    base: dict[str, object] = {"seed": 7, "interval_min": 1_440}
    base.update(overrides)
    factory = cast(Callable[..., RunConfig], RunConfig)
    return factory(**base)


def a_limits(**overrides: int) -> Limits:
    """``Limits`` at section 8.1's defaults; a test names only the cap it is about."""
    base: dict[str, int] = {
        "bars_window": 90,
        "news_per_market": 20,
        "news_global": 50,
        "hive_lessons": 20,
        "hive_forecasts": 200,
        "markets_per_obs_max": 200,
        "notes_max_chars": 500,
        "lessons_per_bar_max": 5,
        "lesson_max_chars": 300,
        "research_units_total": 10,
    }
    base.update(overrides)
    factory = cast(Callable[..., Limits], Limits)
    return factory(**base)


def a_portfolio(*, research_units_remaining: int = 10) -> PortfolioView:
    return PortfolioView(
        cash_cents=100_000,
        reserved_cents=0,
        equity_cents=100_000,
        fees_paid_cents=0,
        peak_equity_cents=100_000,
        drawdown_bp=0,
        n_open_positions=0,
        n_open_orders=0,
        research_units_remaining=research_units_remaining,
    )


# --------------------------------------------------------------------------------------------------
# Test doubles for the names amendment C1b declares and gate G2 has not landed
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FakeCashEvent:
    """``pmx.types.CashEvent`` (section 17.3)."""

    cash_event_id: str
    market_id: str
    kind: str
    t_ms: int
    origin: str
    source_url: str
    detail: dict[str, int | str]


@dataclass(frozen=True, slots=True)
class FakeContinuous:
    """``pmx.types.ContinuousInstrument`` (section 17.1), with the two base methods of ruling R173."""

    id: str
    kind: str = "equity"
    provider: str = "xnas"
    vendor: str = "yahoo"
    symbol: str = "AAPL"
    url: str = "https://example.invalid"
    description: str = "Apple Inc. common stock."
    category: str = "finance"
    tags: tuple[str, ...] = ("equity",)
    currency: str = "usd"
    tick_size_micro: int = 10_000
    point_value_micro: int = 1_000_000
    session_calendar_id: str = "xnys"
    fee_schedule_id: str = "xnas-zero-2026-09"
    borrow_schedule_id: str | None = "xnas-borrowgc-2026-09"
    carry_schedule_id: str | None = None
    listed_at_ms: int = MONDAY
    delisted_at_ms: int | None = None
    short_allowed: bool = True
    interval_min: int = 1_440
    first_price_ticks: int = 18_862_000
    underlying_id: str | None = None
    twins: tuple[str, ...] = ()
    bars: tuple[Bar, ...] = ()
    trades: tuple[Trade, ...] = ()
    cash_events: tuple[FakeCashEvent, ...] = ()

    @property
    def instrument(self) -> FakeContinuous:
        """``pmx.types.Instrument.instrument``: the base view of an instrument is the instrument."""
        return self

    def bar_at(self, t_ms: int) -> Bar | None:
        target = bar_of(t_ms, self.interval_min)
        for bar in self.bars:
            if bar.t_ms == target:
                return bar
        return None

    def bars_before(self, now_ms: int, limit: int) -> tuple[Bar, ...]:
        span = self.interval_min * 60_000
        completed = [bar for bar in self.bars if bar.t_ms + span <= now_ms]
        return tuple(completed[-limit:]) if limit > 0 else ()


@dataclass(frozen=True, slots=True)
class FakeMeta:
    """``MarketMeta`` plus ``kind`` (ruling R144) and the continuous values of ruling R186."""

    id: str
    provider: str
    category: str
    tags: tuple[str, ...]
    event_key: str | None
    created_at_ms: int
    close_at_ms: int
    resolved_at_ms: int
    resolution: int
    interval_min: int
    n_bars: int
    hardness_tags: tuple[str, ...]
    fee_schedule_id: str
    fold: str
    kind: str = "binary"


def meta_for(instrument: FakeContinuous, *, window_end_ms: int) -> FakeMeta:
    """``meta_of`` for a continuous instrument, exactly as ruling R186 defines its values."""
    resolved = instrument.delisted_at_ms if instrument.delisted_at_ms is not None else window_end_ms
    return FakeMeta(
        id=instrument.id,
        provider=instrument.provider,
        category=instrument.category,
        tags=instrument.tags,
        event_key=None,
        created_at_ms=instrument.listed_at_ms,
        close_at_ms=resolved,
        resolved_at_ms=resolved,
        resolution=-1,
        interval_min=instrument.interval_min,
        n_bars=len(instrument.bars),
        hardness_tags=(),
        fee_schedule_id=instrument.fee_schedule_id,
        fold="all",
        kind=instrument.kind,
    )


class FakeMemory:
    """A memory whose ``view`` does **not** filter: the leak boundary must filter it itself (R13)."""

    def __init__(self, view: MemoryView) -> None:
        self._view = view
        self.calls: list[int] = []

    def view(self, *, now_ms: int) -> MemoryView:
        self.calls.append(now_ms)
        return self._view


class FakeHive:
    """A hive whose ``view`` returns more than it should, so the builder's own filters are tested."""

    def __init__(self, view: HiveView) -> None:
        self._view = view
        self.calls: list[tuple[int, str, tuple[str, ...], bool]] = []

    def view(
        self,
        *,
        now_ms: int,
        agent_id: str,
        market_ids: Sequence[str],
        limits: Limits,
        live_coop: bool,
    ) -> HiveView:
        self.calls.append((now_ms, agent_id, tuple(market_ids), live_coop))
        return self._view


# xnys-like sessions: 13:30Z to 20:00Z on every weekday of the nine weeks that start at MONDAY. A sealed
# calendar covers the whole dataset window and not one run's window (17.2), which is what lets a test tell
# the venue's next bar apart from the run's (``hours_to_next_bar`` reads the first, ruling R181).
WEEKDAY_SESSIONS: tuple[Session, ...] = tuple(
    Session(
        open_ms=MONDAY + day * DAY + 13 * MS_PER_HOUR + 30 * 60_000,
        close_ms=MONDAY + day * DAY + 20 * MS_PER_HOUR,
    )
    for day in range(63)
    if day % 7 not in (5, 6)
)
XNYS = SessionCalendar(
    calendar_id="xnys",
    description="A weekday venue, 13:30Z to 20:00Z, for the session half of amendment C1b.",
    source_url="https://example.invalid/xnys",
    as_of_date="2026-02-28",
    window=DatasetWindow(start_ms=MONDAY, end_ms=MONDAY + 63 * DAY),
    sessions=WEEKDAY_SESSIONS,
)


def continuous_setup(
    instrument: FakeContinuous, *, window_end_ms: int, t1_ms: int | None = None
) -> tuple[Dataset, Calendar]:
    meta = meta_for(instrument, window_end_ms=window_end_ms)
    dataset = a_dataset([instrument], metas=cast(Sequence[MarketMeta], [meta]))
    config = a_config(t0_ms=instrument.listed_at_ms, t1_ms=t1_ms if t1_ms is not None else window_end_ms)
    calendar = Calendar(dataset, config, calendars={"xnys": XNYS})
    return dataset, calendar


def daily_bars(first_day_ms: int, n: int, *, price: int = 18_862_000, skip_weekend: bool = True) -> tuple[Bar, ...]:
    """``n`` calendar days of daily bars from ``first_day_ms``, weekends dropped when asked.

    A session instrument's file carries no bar outside a session (ruling R149), which is what the loader
    enforces and what these doubles reproduce.
    """
    bars: list[Bar] = []
    for index in range(n):
        t_ms = first_day_ms + index * DAY
        weekday = ((t_ms - MONDAY) // DAY) % 7
        if skip_weekend and weekday in (5, 6):
            continue
        bars.append(a_bar(t_ms, price + index * 1_000, volume_milli=48_000_000, n_trades=0))
    return tuple(bars)


# --------------------------------------------------------------------------------------------------
# The calendar: the run window and the union timeline
# --------------------------------------------------------------------------------------------------
def test_default_window_is_the_first_creation_and_the_last_settlement() -> None:
    dataset = a_dataset(
        [a_market("demo-alpha", created_day=2, n_bars=5), a_market("demo-beta", created_day=4, n_bars=6)]
    )
    calendar = Calendar(dataset, a_config())
    assert calendar.t0_ms == 2 * DAY
    assert calendar.t1_ms == 10 * DAY  # the last settling bar is day 9, and t1 is exclusive


def test_config_window_overrides_the_default_and_is_grid_aligned() -> None:
    dataset = a_dataset([a_market("demo-alpha", created_day=0, n_bars=10)])
    calendar = Calendar(dataset, a_config(t0_ms=3 * DAY, t1_ms=6 * DAY))
    assert (calendar.t0_ms, calendar.t1_ms) == (3 * DAY, 6 * DAY)
    assert [slice_.t_ms for slice_ in calendar.bars()] == [3 * DAY, 4 * DAY, 5 * DAY]


def test_every_grid_point_is_a_bar_on_a_binary_run() -> None:
    dataset = a_dataset(
        [a_market("demo-alpha", created_day=0, n_bars=4), a_market("demo-beta", created_day=1, n_bars=4)]
    )
    calendar = Calendar(dataset, a_config())
    stamps = [slice_.t_ms for slice_ in calendar.bars()]
    assert stamps == [index * DAY for index in range(5)]
    assert all(slice_.open_ids for slice_ in calendar.bars())


def test_a_grid_point_with_no_open_instrument_is_not_a_bar_of_the_run() -> None:
    early = a_market("demo-alpha", created_day=0, n_bars=2)
    late = a_market("demo-beta", created_day=5, n_bars=2)
    calendar = Calendar(a_dataset([early, late]), a_config())
    stamps = [slice_.t_ms for slice_ in calendar.bars()]
    assert stamps == [0, DAY, 5 * DAY, 6 * DAY]
    assert 2 * DAY not in stamps


def test_bar_slices_are_in_market_id_order() -> None:
    dataset = a_dataset([a_market("demo-zulu", n_bars=3), a_market("demo-alpha", n_bars=3)])
    calendar = Calendar(dataset, a_config())
    first = next(iter(calendar.bars()))
    assert first.open_ids == ("demo-alpha", "demo-zulu")
    assert first.listed_ids == ("demo-alpha", "demo-zulu")


def test_a_market_is_listed_once_at_its_first_bar() -> None:
    calendar = Calendar(a_dataset([a_market("demo-alpha", created_day=1, n_bars=3)]), a_config())
    listed = [slice_.t_ms for slice_ in calendar.bars() if slice_.listed_ids]
    assert listed == [DAY]


def test_open_covers_the_settling_bar_and_stops_there() -> None:
    market = a_market("demo-alpha", created_day=0, n_bars=4)  # settles on day 3
    calendar = Calendar(a_dataset([market]), a_config(t1_ms=6 * DAY))
    assert calendar.is_open("demo-alpha", 3 * DAY)
    assert not calendar.is_open("demo-alpha", 4 * DAY)
    assert calendar.settles("demo-alpha", 3 * DAY)
    assert not calendar.settles("demo-alpha", 2 * DAY)


def test_tradable_refuses_the_closing_bar_and_the_settling_bar() -> None:
    """Ruling R9: only a bar entirely inside the trading window can fill."""
    market = a_market("demo-alpha", created_day=0, n_bars=5, close_day=3, resolved_day=4)
    calendar = Calendar(a_dataset([market]), a_config())
    assert calendar.is_tradable("demo-alpha", DAY)
    assert calendar.is_tradable("demo-alpha", 2 * DAY)  # the bar [2d, 3d) ends exactly at close_at_ms
    assert not calendar.is_tradable("demo-alpha", 3 * DAY)  # the bar that contains close_at_ms
    assert not calendar.is_tradable("demo-alpha", 4 * DAY)  # the settling bar
    assert calendar.is_open("demo-alpha", 4 * DAY)


def test_actionable_is_one_bar_before_tradable() -> None:
    """Section 16.2: an action decided at ``t`` fills at the open of ``t + interval_ms``."""
    market = a_market("demo-alpha", created_day=0, n_bars=5, close_day=3, resolved_day=4)
    calendar = Calendar(a_dataset([market]), a_config())
    assert calendar.is_actionable("demo-alpha", DAY)
    assert not calendar.is_actionable("demo-alpha", 2 * DAY)  # its fill bar carries the close
    assert calendar.is_tradable("demo-alpha", 2 * DAY)
    assert not calendar.is_actionable("demo-alpha", 3 * DAY)


def test_nothing_is_actionable_on_the_runs_last_bar() -> None:
    market = a_market("demo-alpha", created_day=0, n_bars=10, close_day=9, resolved_day=9)
    calendar = Calendar(a_dataset([market]), a_config(t1_ms=5 * DAY))
    last = 4 * DAY
    assert calendar.is_tradable("demo-alpha", last)
    assert calendar.next_bar("demo-alpha", last) is None
    assert not calendar.is_actionable("demo-alpha", last)


def test_next_prev_and_last_bar_on_a_binary() -> None:
    market = a_market("demo-alpha", created_day=1, n_bars=4)  # bars on days 1..4, settles day 4
    calendar = Calendar(a_dataset([market]), a_config(t1_ms=8 * DAY))
    assert calendar.last_bar("demo-alpha") == 4 * DAY
    assert calendar.next_bar("demo-alpha", 2 * DAY) == 3 * DAY
    assert calendar.next_bar("demo-alpha", 4 * DAY) is None
    assert calendar.prev_bar("demo-alpha", 3 * DAY) == 2 * DAY
    assert calendar.prev_bar("demo-alpha", DAY) is None
    assert calendar.next_bar("demo-alpha", 0) == DAY


def test_last_bar_is_clamped_by_the_run_window() -> None:
    market = a_market("demo-alpha", created_day=0, n_bars=10)
    calendar = Calendar(a_dataset([market]), a_config(t1_ms=4 * DAY))
    assert calendar.last_bar("demo-alpha") == 3 * DAY


def test_an_unknown_market_is_refused() -> None:
    calendar = Calendar(a_dataset([a_market()]), a_config())
    with pytest.raises(SchemaError):
        calendar.last_bar("demo-nope")


def test_one_grid_per_run() -> None:
    """Ruling R10: there is no run-time resampling, so a second interval is a second dataset."""
    dataset = a_dataset([a_market()])
    with pytest.raises(InvalidConfigError):
        Calendar(dataset, a_config(interval_min=60))
    hourly = replace(a_market(), interval_min=60)
    mixed = a_dataset([hourly])
    with pytest.raises(InvalidConfigError):
        Calendar(mixed, a_config())


def test_a_run_with_no_instrument_is_refused() -> None:
    market = a_market()
    metas = [replace(meta, fold="train") for meta in a_dataset([market]).metas]
    with pytest.raises(InvalidConfigError):
        Calendar(a_dataset([market], metas=metas), a_config(fold="validation"))


def test_the_fold_selects_the_run() -> None:
    train = a_market("demo-alpha", created_day=0, n_bars=3)
    sealed = a_market("demo-beta", created_day=0, n_bars=3)
    metas = [
        replace(meta, fold="train" if meta.id == "demo-alpha" else "sealed")
        for meta in a_dataset([train, sealed]).metas
    ]
    dataset = a_dataset([train, sealed], metas=metas)
    assert Calendar(dataset, a_config(fold="train")).market_ids() == ("demo-alpha",)
    assert Calendar(dataset, a_config(fold="sealed")).market_ids() == ("demo-beta",)
    assert Calendar(dataset, a_config()).market_ids() == ("demo-alpha", "demo-beta")


def test_bar_slice_serialises() -> None:
    slice_ = BarSlice(t_ms=DAY, open_ids=("demo-alpha",), tradable_ids=(), settling_ids=(), listed_ids=())
    assert slice_.to_dict() == {
        "t_ms": DAY,
        "open_ids": ["demo-alpha"],
        "tradable_ids": [],
        "settling_ids": [],
        "listed_ids": [],
        "closing_ids": [],
    }


def test_the_demo_pack_builds_a_calendar_over_its_real_markets() -> None:
    """The one committed dataset: the calendar is the union of twelve real, sparse market lives."""
    dataset = load_dataset(DEMO_PACK)
    calendar = Calendar(dataset, a_config())
    stamps = [slice_.t_ms for slice_ in calendar.bars()]
    assert stamps == sorted(stamps)
    assert len(stamps) == len(set(stamps))
    grid_points = (calendar.t1_ms - calendar.t0_ms) // DAY
    assert 0 < len(stamps) < grid_points  # the twelve markets do not cover 2016 to 2024 densely
    expected = {
        bar.t_ms
        for meta in dataset.metas
        for bar in dataset.market(meta.id).bars
        if calendar.t0_ms <= bar.t_ms < calendar.t1_ms
    }
    assert set(stamps) == expected
    for slice_ in calendar.bars():
        assert slice_.open_ids
        for market_id in slice_.settling_ids:
            assert bar_of(dataset.meta(market_id).resolved_at_ms, 1_440) == slice_.t_ms


# --------------------------------------------------------------------------------------------------
# The calendar: session instruments (amendment C1b)
# --------------------------------------------------------------------------------------------------
def test_session_membership_is_the_intersection_and_not_the_containment() -> None:
    sessions = (Session(open_ms=MONDAY + 13 * MS_PER_HOUR, close_ms=MONDAY + 20 * MS_PER_HOUR),)
    assert in_session(sessions, MONDAY, interval_min=1_440)  # the daily bar holds the session
    assert not in_session(sessions, MONDAY + DAY, interval_min=1_440)
    assert in_session(sessions, MONDAY + 12 * MS_PER_HOUR, interval_min=60) is False
    assert in_session(sessions, MONDAY + 13 * MS_PER_HOUR, interval_min=60) is True


def test_a_weekend_is_not_a_bar_of_a_session_run() -> None:
    instrument = FakeContinuous(id="xnas-AAPL", bars=daily_bars(MONDAY, 12))
    window_end = MONDAY + 12 * DAY
    _, calendar = continuous_setup(instrument, window_end_ms=window_end)
    stamps = [slice_.t_ms for slice_ in calendar.bars()]
    weekend = {MONDAY + 5 * DAY, MONDAY + 6 * DAY}
    assert weekend.isdisjoint(stamps)
    assert len(stamps) == 10
    assert all(slice_.open_ids == ("xnas-AAPL",) for slice_ in calendar.bars())


def test_the_next_bar_after_friday_is_monday() -> None:
    instrument = FakeContinuous(id="xnas-AAPL", bars=daily_bars(MONDAY, 12))
    _, calendar = continuous_setup(instrument, window_end_ms=MONDAY + 12 * DAY)
    friday = MONDAY + 4 * DAY
    assert calendar.next_bar("xnas-AAPL", friday) == MONDAY + 7 * DAY
    assert calendar.prev_bar("xnas-AAPL", MONDAY + 7 * DAY) == friday
    assert calendar.next_bar("xnas-AAPL", MONDAY + 5 * DAY) == MONDAY + 7 * DAY


def test_a_session_instrument_closes_at_its_last_bar_and_never_settles() -> None:
    instrument = FakeContinuous(id="xnas-AAPL", bars=daily_bars(MONDAY, 12))
    _, calendar = continuous_setup(instrument, window_end_ms=MONDAY + 12 * DAY)
    last = calendar.last_bar("xnas-AAPL")
    assert last == MONDAY + 11 * DAY
    assert calendar.closes("xnas-AAPL", last)
    assert not calendar.settles("xnas-AAPL", last)
    assert calendar.is_open("xnas-AAPL", last)
    assert not calendar.is_tradable("xnas-AAPL", last)  # its only fill is the engine's forced flat
    assert calendar.is_tradable("xnas-AAPL", MONDAY + 10 * DAY)
    closing = [slice_.t_ms for slice_ in calendar.bars() if slice_.closing_ids]
    assert closing == [last]


def test_a_delisting_bar_carries_no_bar() -> None:
    delisted = MONDAY + 3 * DAY
    instrument = FakeContinuous(id="xnas-AAPL", bars=daily_bars(MONDAY, 3), delisted_at_ms=delisted)
    _, calendar = continuous_setup(instrument, window_end_ms=MONDAY + 12 * DAY)
    assert calendar.last_bar("xnas-AAPL") == MONDAY + 2 * DAY
    assert not calendar.is_open("xnas-AAPL", delisted)


def test_a_delisting_inside_a_bar_takes_that_whole_bar_out() -> None:
    """Section 17.2: ``listed(i, t)`` is ``t < bar_of(delisted_at_ms)``, aligned or not (ruling R150).

    The instant a venue publishes is rarely a bar open. The bar that **contains** it is priced partly
    after the instrument stopped existing, so it is not a bar of the instrument and ``last_bar(i)`` is
    the bar before it, exactly as it is for a delisting stamped on a bar open.
    """
    delisted = MONDAY + 3 * DAY + 17 * MS_PER_HOUR
    instrument = FakeContinuous(id="xnas-AAPL", bars=daily_bars(MONDAY, 3), delisted_at_ms=delisted)
    _, calendar = continuous_setup(instrument, window_end_ms=MONDAY + 12 * DAY)
    assert calendar.last_bar("xnas-AAPL") == MONDAY + 2 * DAY
    assert calendar.closes("xnas-AAPL", MONDAY + 2 * DAY)
    assert not calendar.is_open("xnas-AAPL", MONDAY + 3 * DAY)
    assert [slice_.t_ms for slice_ in calendar.bars()] == [MONDAY, MONDAY + DAY, MONDAY + 2 * DAY]


def test_an_instrument_that_is_never_delisted_runs_to_the_end_of_the_run() -> None:
    """With no ``delisted_at_ms`` the instrument is listed from its first bar on: the run window ends it.

    ``MarketMeta`` cannot tell a delisting from the dataset's window end (ruling R186 collapses both into
    ``resolved_at_ms``), which is why the calendar reads ``delisted_at_ms`` off the instrument record: a
    run whose ``t1_ms`` reaches past the window end must not lose its last bar to that collapse.
    """
    instrument = FakeContinuous(
        id="binance-BTCUSDT",
        kind="spot_crypto",
        session_calendar_id="continuous",
        bars=daily_bars(MONDAY, 9, skip_weekend=False),
    )
    meta = meta_for(instrument, window_end_ms=MONDAY + 6 * DAY)
    dataset = a_dataset([instrument], metas=cast(Sequence[MarketMeta], [meta]))
    calendar = Calendar(dataset, a_config(t0_ms=MONDAY, t1_ms=MONDAY + 9 * DAY))
    assert calendar.last_bar("binance-BTCUSDT") == MONDAY + 8 * DAY
    assert calendar.is_open("binance-BTCUSDT", MONDAY + 8 * DAY)
    assert len([slice_.t_ms for slice_ in calendar.bars()]) == 9


def test_a_continuous_instrument_with_no_calendar_source_is_refused() -> None:
    instrument = FakeContinuous(id="xnas-AAPL", bars=daily_bars(MONDAY, 3))
    meta = meta_for(instrument, window_end_ms=MONDAY + 3 * DAY)
    dataset = a_dataset([instrument], metas=cast(Sequence[MarketMeta], [meta]))
    with pytest.raises(SchemaError):
        Calendar(dataset, a_config(t0_ms=MONDAY, t1_ms=MONDAY + 3 * DAY))


def test_a_crypto_instrument_names_the_synthesised_continuous_calendar() -> None:
    instrument = FakeContinuous(
        id="binance-BTCUSDT",
        kind="spot_crypto",
        session_calendar_id="continuous",
        bars=daily_bars(MONDAY, 9, skip_weekend=False),
    )
    meta = meta_for(instrument, window_end_ms=MONDAY + 9 * DAY)
    dataset = a_dataset([instrument], metas=cast(Sequence[MarketMeta], [meta]))
    calendar = Calendar(dataset, a_config(t0_ms=MONDAY, t1_ms=MONDAY + 9 * DAY))
    assert len([slice_.t_ms for slice_ in calendar.bars()]) == 9  # a weekend trades on a crypto venue
    assert calendar.kind_of("binance-BTCUSDT") == "spot_crypto"


def test_meta_kind_defaults_to_binary_and_refuses_an_unknown_kind() -> None:
    meta = a_dataset([a_market()]).metas[0]
    assert meta_kind(meta) == "binary"
    with pytest.raises(SchemaError):
        meta_kind(cast(MarketMeta, replace(meta_for(FakeContinuous(id="x-y"), window_end_ms=1), kind="bond")))


# --------------------------------------------------------------------------------------------------
# The observation: the as-of price and the bar window
# --------------------------------------------------------------------------------------------------
def one_observation(
    markets: Sequence[object],
    *,
    now_ms: int,
    config: RunConfig | None = None,
    news: Sequence[NewsItem] = (),
    grants: Sequence[ResearchGrant] = (),
    positions: dict[str, PositionView] | None = None,
    memory: FakeMemory | None = None,
    hive: FakeHive | None = None,
    calendar: Calendar | None = None,
    agent_id: str = "follower",
    sensors: Sequence[str] | None = None,
) -> Observation:
    return build_observation(
        agent_id=agent_id,
        now_ms=now_ms,
        config=config if config is not None else a_config(),
        markets=cast(Sequence[Market], markets),
        positions=positions if positions is not None else {},
        portfolio=a_portfolio(),
        memory=memory,
        hive=hive,
        news=news,
        grants=grants,
        calendar=calendar,
        sensors=sensors,
    )


def test_on_the_first_bar_no_bar_is_completed() -> None:
    """Ruling R11: the as-of price is ``first_price_bp``, there are no bars and no quotes."""
    market = a_market("demo-alpha", created_day=0, n_bars=6, quotes=True)
    view = one_observation([market], now_ms=0).markets[0]
    assert view.bars == ()
    assert view.last_price_bp == market.first_price_bp == 4_242
    assert view.best_bid_bp is None and view.best_ask_bp is None
    assert view.volume_milli_to_date == 0 and view.n_trades_to_date == 0


def test_the_as_of_price_is_the_close_of_the_last_completed_bar() -> None:
    market = a_market("demo-alpha", created_day=0, n_bars=6, prices=[10, 20, 30, 40, 50, 60], quotes=True)
    view = one_observation([market], now_ms=3 * DAY).markets[0]
    assert [bar.t_ms for bar in view.bars] == [0, DAY, 2 * DAY]
    assert view.last_price_bp == 30
    assert (view.best_bid_bp, view.best_ask_bp) == (30 - 50, 30 + 50)
    assert view.volume_milli_to_date == 3 * 4_000
    assert view.n_trades_to_date == 3 * 8


def test_the_bar_window_caps_without_leaking_the_end() -> None:
    """Point 2 of the clock test: the length is ``min(bars_window, completed)`` for both bar counts."""
    config = a_config(bars_window=5)
    for total in (5, 12):
        market = a_market("demo-alpha", created_day=0, n_bars=total)
        for now_day in (1, 3, total - 1):
            view = one_observation([market], now_ms=now_day * DAY, config=config).markets[0]
            assert len(view.bars) == min(config.bars_window, now_day)


def test_the_seven_day_volume_reads_completed_bars_only() -> None:
    market = a_market("demo-alpha", created_day=0, n_bars=12)
    volume_7d, to_date, n_trades = tape_stats_at(market, now_ms=10 * DAY)
    assert to_date == 10 * 4_000
    assert n_trades == 10 * 8
    assert volume_7d == 7 * 4_000


def test_completed_bars_drops_a_bar_the_record_wrongly_returned() -> None:
    """The builder filters what a record hands back; it does not trust it (section 5.4)."""

    @dataclass(frozen=True, slots=True)
    class LyingTape(FakeContinuous):
        def bars_before(self, now_ms: int, limit: int) -> tuple[Bar, ...]:
            return self.bars

    tape = LyingTape(id="binance-BTCUSDT", kind="spot_crypto", bars=daily_bars(MONDAY, 4, skip_weekend=False))
    kept = completed_bars(tape, now_ms=MONDAY + 2 * DAY, limit=90)
    assert [bar.t_ms for bar in kept] == [MONDAY, MONDAY + DAY]


def test_now_ms_must_be_a_bar_open() -> None:
    with pytest.raises(InvalidConfigError):
        one_observation([a_market()], now_ms=DAY + 1)


def test_two_instruments_may_not_share_an_id() -> None:
    with pytest.raises(InvalidConfigError):
        one_observation([a_market("demo-alpha"), a_market("demo-alpha")], now_ms=DAY)


def test_a_market_with_no_position_is_flat() -> None:
    view = one_observation([a_market()], now_ms=DAY).markets[0]
    assert view.position == PositionView(position=0, avg_cost_bp=0, unrealised_cents=0, open_orders=())


def test_the_position_is_carried_through() -> None:
    held = PositionView(position=-40, avg_cost_bp=3_700, unrealised_cents=-120, open_orders=())
    view = one_observation([a_market()], now_ms=DAY, positions={"demo-alpha": held}).markets[0]
    assert view.position == held


def test_the_description_is_truncated_and_the_question_is_whole() -> None:
    market = a_market("demo-alpha")
    view = one_observation([market], now_ms=DAY).markets[0]
    assert len(view.description) == DESCRIPTION_VIEW_CHARS
    assert view.question == market.question


# --------------------------------------------------------------------------------------------------
# The observation: tradability, the market cap and the ordering
# --------------------------------------------------------------------------------------------------
def test_tradable_in_a_view_matches_the_calendar() -> None:
    market = a_market("demo-alpha", created_day=0, n_bars=5, close_day=3, resolved_day=4)
    calendar = Calendar(a_dataset([market]), a_config())
    for day in (1, 2, 3, 4):
        with_calendar = one_observation([market], now_ms=day * DAY, calendar=calendar).markets[0]
        without = one_observation([market], now_ms=day * DAY).markets[0]
        assert with_calendar.tradable == without.tradable == calendar.is_tradable("demo-alpha", day * DAY)


def test_markets_are_sorted_by_id_and_the_cap_prefers_the_tradable_ones() -> None:
    """Section 8.3: the first ``markets_per_obs_max`` by id among the tradable, then among the rest."""
    tradable = a_market("demo-zulu", created_day=0, n_bars=6)
    settling = a_market("demo-alpha", created_day=0, n_bars=3, close_day=2, resolved_day=2)
    config = a_config(markets_per_obs_max=1)
    view = one_observation([settling, tradable], now_ms=2 * DAY, config=config)
    assert [market.market_id for market in view.markets] == ["demo-zulu"]
    both = one_observation([settling, tradable], now_ms=2 * DAY)
    assert [market.market_id for market in both.markets] == ["demo-alpha", "demo-zulu"]
    assert (both.markets[0].tradable, both.markets[1].tradable) == (False, True)


def test_the_limits_are_stated_to_the_agent() -> None:
    config = a_config(bars_window=17, news_global=3, research_budget_by_agent=(("follower", 4),))
    obs = one_observation([a_market()], now_ms=DAY, config=config)
    assert obs.limits.bars_window == 17
    assert obs.limits.news_global == 3
    assert obs.limits.research_units_total == 4
    assert obs.obs_version == "obs.v2"
    assert obs.interval_min == 1_440
    assert obs.now_ms == DAY


# --------------------------------------------------------------------------------------------------
# The observation: news, memory, hive, research
# --------------------------------------------------------------------------------------------------
def test_the_digest_is_ranked_by_score_then_age_and_capped() -> None:
    items = [
        a_news_item("wce-20160101-0001", published_day=0, market_ids=("demo-alpha",), scores=(200,)),
        a_news_item("wce-20160101-0002", published_day=1, market_ids=("demo-alpha",), scores=(900,)),
        a_news_item("wce-20160101-0003", published_day=1, market_ids=("demo-alpha",), scores=(500,)),
    ]
    obs = one_observation([a_market()], now_ms=3 * DAY, news=items, config=a_config(news_global=2))
    assert [item.news_id for item in obs.news] == ["wce-20160101-0002", "wce-20160101-0003"]
    assert [item.news_id for item in obs.markets[0].news] == [
        "wce-20160101-0002",
        "wce-20160101-0003",
        "wce-20160101-0001",
    ]
    assert obs.markets[0].news[0].match_score_permille == 900


def test_an_item_is_invisible_until_its_visible_from() -> None:
    item = a_news_item(
        "wce-20160101-0001",
        published_day=1,
        market_ids=("demo-alpha",),
        scores=(900,),
        visible_from_ms=2 * DAY + 6 * MS_PER_HOUR,
    )
    assert one_observation([a_market()], now_ms=2 * DAY, news=[item]).news == ()
    later = one_observation([a_market()], now_ms=3 * DAY, news=[item])
    assert [view.news_id for view in later.news] == ["wce-20160101-0001"]


def test_the_view_text_is_six_hundred_characters() -> None:
    item = a_news_item(
        "wce-20160101-0001", published_day=0, market_ids=("demo-alpha",), scores=(900,), text="x" * 4_000
    )
    obs = one_observation([a_market()], now_ms=DAY, news=[item])
    assert len(obs.news[0].text) == NEWS_VIEW_TEXT_CHARS


def test_the_per_market_digest_is_capped() -> None:
    items = [
        a_news_item(f"wce-20160101-{index:04d}", published_day=0, market_ids=("demo-alpha",), scores=(500,))
        for index in range(1, 8)
    ]
    obs = one_observation([a_market()], now_ms=DAY, news=items, config=a_config(news_per_market=3))
    assert len(obs.markets[0].news) == 3


def test_memory_is_filtered_on_written_at_and_the_notes_are_capped() -> None:
    now = 5 * DAY
    view = MemoryView(
        lessons=(
            LessonView(written_at_ms=now - DAY, text="past lesson", market_ids=()),
            LessonView(written_at_ms=now + DAY, text="FUTURE-LESSON", market_ids=()),
        ),
        notes=tuple(NoteView(written_at_ms=now - DAY, market_id=None, text=f"n{i}") for i in range(30))
        + (NoteView(written_at_ms=now + DAY, market_id=None, text="FUTURE-NOTE"),),
    )
    memory = FakeMemory(view)
    obs = one_observation([a_market()], now_ms=now, memory=memory)
    assert memory.calls == [now]
    assert [lesson.text for lesson in obs.memory.lessons] == ["past lesson"]
    assert len(obs.memory.notes) == 20
    assert all(note.text != "FUTURE-NOTE" for note in obs.memory.notes)


def test_no_memory_means_an_empty_memory_view() -> None:
    assert one_observation([a_market()], now_ms=DAY).memory == MemoryView()


def test_the_hive_is_empty_when_it_is_switched_off() -> None:
    hive = FakeHive(HiveView(lessons=(HiveLessonView("h-1", "a", 10, "t", (), 0),)))
    obs = one_observation([a_market()], now_ms=DAY, hive=hive, config=a_config(no_hive=True))
    assert obs.hive == HiveView()
    assert hive.calls == []


def test_a_hive_entry_stamped_after_now_is_dropped_and_lessons_rank_by_reputation() -> None:
    now = 4 * DAY
    hive = FakeHive(
        HiveView(
            lessons=(
                HiveLessonView("h-00000002", "liar", -5_000, "false lesson", (), now - DAY),
                HiveLessonView("h-00000001", "good", 9_000, "true lesson", (), now - DAY),
                HiveLessonView("h-00000003", "later", 9_999, "FUTURE-LESSON", (), now + DAY),
            ),
        )
    )
    obs = one_observation([a_market()], now_ms=now, hive=hive)
    assert [lesson.text for lesson in obs.hive.lessons] == ["true lesson", "false lesson"]
    assert hive.calls == [(now, "follower", ("demo-alpha",), False)]


def test_a_forecast_on_a_market_that_is_still_open_never_surfaces() -> None:
    now = 3 * DAY
    hive = FakeHive(
        HiveView(
            forecasts=(
                ForecastView(agent_id="other", market_id="demo-alpha", bar_ms=now - DAY, prob_ppm=999_999),
                ForecastView(agent_id="other", market_id="demo-settled", bar_ms=now - DAY, prob_ppm=123_456),
            ),
            prev_bar_forecasts=(
                ForecastView(agent_id="other", market_id="demo-alpha", bar_ms=now - DAY, prob_ppm=777_777),
            ),
        )
    )
    obs = one_observation([a_market()], now_ms=now, hive=hive)
    assert [item.market_id for item in obs.hive.forecasts] == ["demo-settled"]
    assert obs.hive.prev_bar_forecasts == ()
    coop = one_observation([a_market()], now_ms=now, hive=hive, config=a_config(live_coop=True))
    assert [item.prob_ppm for item in coop.hive.prev_bar_forecasts] == [777_777]


def test_an_open_market_beyond_the_cap_still_hides_its_forecasts() -> None:
    """The forecast filter reads every **open** instrument, not the ones the observation had room for.

    Section 8.3 truncates ``markets`` at ``markets_per_obs_max``; the markets that did not fit are still
    open, still forecast-carried and still unsettled. Filtering the hive against the truncated list would
    surface exactly what section 7.9 forbids: another agent's forecast on a market that has not settled.
    """
    first = a_market("demo-alpha", created_day=0, n_bars=6)
    second = a_market("demo-zulu", created_day=0, n_bars=6)
    hive = FakeHive(
        HiveView(
            forecasts=(
                ForecastView(agent_id="other", market_id="demo-zulu", bar_ms=2 * DAY, prob_ppm=987_654),
            )
        )
    )
    obs = one_observation(
        [first, second], now_ms=3 * DAY, hive=hive, config=a_config(markets_per_obs_max=1)
    )
    assert [view.market_id for view in obs.markets] == ["demo-alpha"]
    assert obs.hive.forecasts == ()
    assert "987654" not in render_observation_json(obs)


def test_the_hive_caps_select_the_most_recent_whatever_order_the_hive_returned() -> None:
    """A cap is a selection, not a slice of the hive's own list (section 10.4's ranking columns).

    A hive that sorted differently, or returned more than the cap, cannot change what the agent reads:
    the filter picks the most recent entries itself and renders them oldest first, so the view is a pure
    function of the set of entries.
    """
    now = 40 * DAY
    resolutions = tuple(
        ResolutionView(
            market_id=f"demo-{day:03d}", outcome=1, life_mean_price_bp=6_000, resolved_at_ms=day * DAY
        )
        for day in range(1, 30)
    )
    forecasts = tuple(
        ForecastView(agent_id="other", market_id=f"demo-{day:03d}", bar_ms=day * DAY, prob_ppm=500_000)
        for day in range(1, 30)
    )
    def filtered(view: HiveView, *, hive_forecasts: int = 5) -> HiveView:
        return filter_hive_view(
            view,
            now_ms=now,
            interval_min=1_440,
            open_market_ids=(),
            limits=a_limits(hive_forecasts=hive_forecasts),
            live_coop=False,
        )

    ascending = filtered(HiveView(resolutions=resolutions, forecasts=forecasts))
    scrambled = filtered(HiveView(resolutions=resolutions[::-1], forecasts=forecasts[::-1]))
    assert ascending == scrambled
    assert [item.market_id for item in ascending.forecasts] == [f"demo-{day:03d}" for day in range(25, 30)]
    assert [item.resolved_at_ms for item in ascending.resolutions] == [day * DAY for day in range(1, 30)]
    assert filtered(HiveView(forecasts=forecasts), hive_forecasts=0).forecasts == ()


def test_a_resolution_is_visible_one_bar_after_the_settling_bar() -> None:
    """Ruling R12: the stamp is ``bar_of(resolved_at_ms) + interval_ms``, never ``resolved_at_ms``."""
    resolved = 3 * DAY + 12 * MS_PER_HOUR
    view = HiveView(
        resolutions=(
            ResolutionView(market_id="demo-past", outcome=1, life_mean_price_bp=6_000, resolved_at_ms=resolved),
        )
    )
    limits = a_limits()
    at_settling = filter_hive_view(
        view, now_ms=3 * DAY, interval_min=1_440, open_market_ids=(), limits=limits, live_coop=False
    )
    assert at_settling.resolutions == ()
    after = filter_hive_view(
        view, now_ms=4 * DAY, interval_min=1_440, open_market_ids=(), limits=limits, live_coop=False
    )
    assert [item.market_id for item in after.resolutions] == ["demo-past"]


def test_trades_are_hidden_until_history_is_granted() -> None:
    trades = tuple(Trade(t_ms=index * DAY + 3, price_bp=5_000, size_milli=1_000, side="yes") for index in range(5))
    market = a_market("demo-alpha", created_day=0, n_bars=6, trades=trades)
    plain = one_observation([market], now_ms=3 * DAY).markets[0]
    assert plain.trades == ()
    grant = build_grant(
        request=ResearchRequest(kind="history", market_id="demo-alpha"),
        granted_at_ms=2 * DAY,
        config=a_config(),
        trades=trades,
    )
    granted = one_observation([market], now_ms=3 * DAY, grants=[grant]).markets[0]
    assert [trade.t_ms for trade in granted.trades] == [3, DAY + 3]
    assert all(trade.t_ms < 3 * DAY for trade in granted.trades)
    # Section 7.9: a trade at exactly ``now_ms`` is future information, because the bar it prints in has
    # not completed. A grant built at this bar with the same tape carries the older prints and not it.
    at_now = build_grant(
        request=ResearchRequest(kind="history", market_id="demo-alpha"),
        granted_at_ms=3 * DAY,
        config=a_config(),
        trades=(*trades, Trade(t_ms=3 * DAY, price_bp=5_000, size_milli=1_000, side="yes")),
    )
    kept = one_observation([market], now_ms=3 * DAY, grants=[at_now]).markets[0]
    assert [trade.t_ms for trade in kept.trades] == [3, DAY + 3, 2 * DAY + 3]
    assert filter_grant(at_now, now_ms=3 * DAY).trades == kept.trades


def test_a_granted_news_request_is_a_deeper_digest() -> None:
    items = [
        a_news_item(f"wce-20160101-{index:04d}", published_day=0, market_ids=("demo-alpha",), scores=(500,))
        for index in range(1, 30)
    ]
    grant = build_grant(
        request=ResearchRequest(kind="news", market_id="demo-alpha"),
        granted_at_ms=DAY,
        config=a_config(news_per_market=5),
        news=items,
    )
    assert len(grant.news) == 15  # three times the per-market cap (section 8.4)
    obs = one_observation([a_market()], now_ms=2 * DAY, grants=[grant])
    assert obs.research.granted[0].kind == "news"
    assert len(obs.research.granted[0].news) == 15


def test_a_per_market_news_grant_carries_that_markets_items_only() -> None:
    """Section 8.4: a granted ``news`` request is a deeper digest **of the market's** items."""
    mine = a_news_item("wce-20160101-0001", published_day=0, market_ids=("demo-alpha",), scores=(400,))
    other = a_news_item("wce-20160101-0002", published_day=0, market_ids=("demo-zulu",), scores=(900,))
    grant = build_grant(
        request=ResearchRequest(kind="news", market_id="demo-alpha"),
        granted_at_ms=DAY,
        config=a_config(),
        news=[mine, other],
    )
    assert [item.news_id for item in grant.news] == ["wce-20160101-0001"]
    global_grant = build_grant(
        request=ResearchRequest(kind="news", market_id=None),
        granted_at_ms=DAY,
        config=a_config(),
        news=[mine, other],
    )
    assert {item.news_id for item in global_grant.news} == {"wce-20160101-0001", "wce-20160101-0002"}


def test_a_wiki_asof_grant_is_as_of_and_bounded() -> None:
    """The background snapshots visible at the granting bar, the most recent ``news_per_market`` of them.

    Section 8.4 states no cap on the payload, and an uncapped one would carry every revision of a
    subject: over the size cap the whole observation raises rather than truncating (8.1), so the digest
    cap is applied here (reported as a contract issue).
    """
    snapshots = [
        a_news_item(
            f"wce-2016010{index % 9 + 1}-{index:04d}",
            published_day=index,
            market_ids=("demo-alpha",),
            scores=(500,),
            headline=f"revision-{index}",
        )
        for index in range(1, 12)
    ]
    grant = build_grant(
        request=ResearchRequest(kind="wiki_asof", market_id="demo-alpha"),
        granted_at_ms=8 * DAY,
        config=a_config(news_per_market=3),
        background=snapshots,
    )
    assert [item.headline for item in grant.news] == ["revision-6", "revision-7", "revision-8"]
    assert all(item.published_at_ms <= 8 * DAY for item in grant.news)
    assert grant.kind == "wiki_asof"
    assert grant.granted_at_ms == 8 * DAY
    # A snapshot whose safety lag has not elapsed is not visible, whatever its capture time (5.5).
    lagged = a_news_item(
        "wce-20160109-0099",
        published_day=8,
        market_ids=("demo-alpha",),
        scores=(500,),
        headline="revision-lagged",
        visible_from_ms=8 * DAY + 6 * MS_PER_HOUR,
    )
    later = build_grant(
        request=ResearchRequest(kind="wiki_asof", market_id="demo-alpha"),
        granted_at_ms=8 * DAY,
        config=a_config(news_per_market=3),
        background=[*snapshots, lagged],
    )
    assert all(item.headline != "revision-lagged" for item in later.news)


def test_a_grant_never_carries_an_item_published_after_now() -> None:
    """A grant crossed a bar boundary, so it is filtered again at the bar it is read at (5.4)."""
    poisoned = a_news_item(
        "wce-20160110-0009",
        published_day=9,
        market_ids=("demo-alpha",),
        scores=(999,),
        headline="POISON-GRANT",
    )
    dirty = ResearchGrant(
        kind="news",
        market_id="demo-alpha",
        granted_at_ms=DAY,
        news=(news_view_of(poisoned, market_id="demo-alpha"),),
    )
    assert filter_grant(dirty, now_ms=2 * DAY).news == ()
    assert filter_grant(dirty, now_ms=10 * DAY).news[0].headline == "POISON-GRANT"
    obs = one_observation([a_market()], now_ms=2 * DAY, grants=[dirty])
    assert obs.research.granted[0].news == ()
    assert "POISON-GRANT" not in render_observation_json(obs)


def test_the_research_ledger_spends_and_refuses() -> None:
    config = a_config(research_budget_units=4)
    ledger = ResearchLedger(config, ["follower", "trend"])
    assert ledger.total("follower") == 4
    first = ledger.request(agent_id="follower", request=ResearchRequest(kind="history", market_id="demo-alpha"))
    assert (first.granted, first.units, first.remaining) == (True, 2, 2)
    second = ledger.request(agent_id="follower", request=ResearchRequest(kind="wiki_asof", market_id="demo-alpha"))
    assert (second.granted, second.units, second.remaining, second.reason) == (False, 3, 2, "budget_exceeded")
    assert ledger.remaining("follower") == 2  # a refused request costs nothing
    third = ledger.request(agent_id="follower", request=ResearchRequest(kind="news"))
    assert (third.granted, third.units, third.remaining) == (True, 1, 1)
    assert ledger.remaining("trend") == 4
    bad_kind = ledger.request(agent_id="follower", request=ResearchRequest(kind="oracle"))
    assert (bad_kind.granted, bad_kind.units, bad_kind.reason) == (False, 0, "bad_research")
    no_market = ledger.request(agent_id="follower", request=ResearchRequest(kind="history"))
    assert (no_market.granted, no_market.reason) == (False, "bad_research")
    assert ledger.remaining("follower") == 1
    with pytest.raises(InvalidConfigError):
        ledger.request(agent_id="stranger", request=ResearchRequest(kind="news"))


def test_the_research_view_states_what_is_left() -> None:
    obs = build_observation(
        agent_id="follower",
        now_ms=DAY,
        config=a_config(),
        markets=[a_market()],
        positions={},
        portfolio=a_portfolio(research_units_remaining=3),
        memory=None,
        hive=None,
        news=(),
        grants=(),
    )
    assert obs.research.units_remaining == 3
    assert obs.portfolio.research_units_remaining == 3


# --------------------------------------------------------------------------------------------------
# The observation: continuous instruments (amendment C1b)
# --------------------------------------------------------------------------------------------------
def test_a_continuous_view_hides_the_close_and_shows_open_as_tradable() -> None:
    """Ruling R181: ``close_at_ms = 0`` and ``tradable = open(i, t)``, or the last bar is announced."""
    instrument = FakeContinuous(id="xnas-AAPL", bars=daily_bars(MONDAY, 12))
    _, calendar = continuous_setup(instrument, window_end_ms=MONDAY + 12 * DAY)
    last = calendar.last_bar("xnas-AAPL")
    view = one_observation([instrument], now_ms=last, calendar=calendar).markets[0]
    assert view.close_at_ms == 0
    assert view.tradable is True  # open, although the engine refuses every agent fill at last_bar
    assert calendar.is_tradable("xnas-AAPL", last) is False
    assert view.created_at_ms == instrument.listed_at_ms
    assert view.first_price_bp == instrument.first_price_ticks
    assert view.question == "AAPL"


def test_the_eight_continuous_view_fields_are_filled() -> None:
    """Ruling R188's eight defaulted fields of ``MarketView``, computed by E1 (section 8.3)."""
    instrument = FakeContinuous(
        id="binance-BTCUSDT.PERP",
        kind="perp",
        session_calendar_id="continuous",
        underlying_id="binance-BTCUSDT",
        twins=("bybit-BTCUSDT.PERP",),
        bars=daily_bars(MONDAY, 4, skip_weekend=False),
    )
    meta = meta_for(instrument, window_end_ms=MONDAY + 4 * DAY)
    dataset = a_dataset([instrument], metas=cast(Sequence[MarketMeta], [meta]))
    calendar = Calendar(dataset, a_config(t0_ms=MONDAY, t1_ms=MONDAY + 4 * DAY))
    view_fields = market_view_fields(
        instrument,
        now_ms=MONDAY + 2 * DAY,
        config=a_config(),
        tradable=True,
        position=PositionView(position=0, avg_cost_bp=0, unrealised_cents=0),
        calendar=calendar,
    )
    assert view_fields["kind"] == "perp"
    assert view_fields["tick_size_micro"] == 10_000
    assert view_fields["point_value_micro"] == 1_000_000
    assert view_fields["session_calendar_id"] == "continuous"
    assert view_fields["hours_to_next_bar"] == 24
    assert view_fields["underlying_id"] == "binance-BTCUSDT"
    assert view_fields["twins"] == ("bybit-BTCUSDT.PERP",)
    assert view_fields["cash_events"] == ()
    binary_fields = market_view_fields(
        cast(FakeContinuous, a_market()),
        now_ms=DAY,
        config=a_config(),
        tradable=True,
        position=PositionView(position=0, avg_cost_bp=0, unrealised_cents=0),
    )
    assert binary_fields["kind"] == "binary"
    assert binary_fields["tick_size_micro"] == 100
    assert binary_fields["point_value_micro"] == 1_000_000
    assert binary_fields["session_calendar_id"] == "continuous"
    assert binary_fields["hours_to_next_bar"] == 0


def test_hours_to_the_next_bar_is_the_weekend_on_a_session_instrument() -> None:
    instrument = FakeContinuous(id="xnas-AAPL", bars=daily_bars(MONDAY, 12))
    _, calendar = continuous_setup(instrument, window_end_ms=MONDAY + 12 * DAY)
    friday = MONDAY + 4 * DAY
    assert hours_to_next_bar(instrument, now_ms=friday, calendar=calendar) == 72
    assert hours_to_next_bar(instrument, now_ms=MONDAY, calendar=calendar) == 24
    assert hours_to_next_bar(cast(FakeContinuous, a_market()), now_ms=DAY, calendar=None) == 0


def test_hours_to_the_next_bar_is_the_venues_and_never_the_runs() -> None:
    """Ruling R181: the field is read from the sealed calendar, so it cannot announce ``last_bar(i)``.

    On the instrument's last bar of the run the run has no next bar for it, and a field computed from the
    run's timeline would publish ``0`` where the venue's schedule says the market opens again on Monday.
    That zero is ``t1_ms`` and ``last_bar(i)`` in disguise, both of which section 7.9 forbids.
    """
    instrument = FakeContinuous(id="xnas-AAPL", bars=daily_bars(MONDAY, 12))
    _, calendar = continuous_setup(instrument, window_end_ms=MONDAY + 12 * DAY)
    last = calendar.last_bar("xnas-AAPL")
    assert last == MONDAY + 11 * DAY  # a Friday: the run ends here, the venue reopens on Monday
    assert calendar.next_bar("xnas-AAPL", last) is None
    assert calendar.session_next_bar("xnas-AAPL", last) == MONDAY + 14 * DAY
    assert hours_to_next_bar(instrument, now_ms=last, calendar=calendar) == 72
    fields = market_view_fields(
        instrument,
        now_ms=last,
        config=a_config(),
        tradable=True,
        position=PositionView(position=0, avg_cost_bp=0, unrealised_cents=0),
        calendar=calendar,
    )
    assert fields["hours_to_next_bar"] == 72
    # A 24/7 instrument answers the grid, and a delisting the venue has not published stays hidden.
    crypto = FakeContinuous(
        id="binance-BTCUSDT",
        kind="spot_crypto",
        session_calendar_id="continuous",
        delisted_at_ms=MONDAY + 4 * DAY,
        bars=daily_bars(MONDAY, 3, skip_weekend=False),
    )
    meta = meta_for(crypto, window_end_ms=MONDAY + 9 * DAY)
    dataset = a_dataset([crypto], metas=cast(Sequence[MarketMeta], [meta]))
    crypto_calendar = Calendar(dataset, a_config(t0_ms=MONDAY, t1_ms=MONDAY + 9 * DAY))
    crypto_last = crypto_calendar.last_bar("binance-BTCUSDT")
    assert crypto_last == MONDAY + 3 * DAY
    assert hours_to_next_bar(crypto, now_ms=crypto_last, calendar=crypto_calendar) == 24


def a_dividend(t_day: int, *, micro: int, market_id: str = "xnas-AAPL") -> FakeCashEvent:
    return FakeCashEvent(
        cash_event_id=f"ce-{micro:016x}",
        market_id=market_id,
        kind="dividend",
        t_ms=MONDAY + t_day * DAY,
        origin="data",
        source_url="https://example.invalid",
        detail={"dividend_micro": micro},
    )


def test_a_cash_event_is_visible_once_its_application_bar_has_completed() -> None:
    """Ruling R183: applied is the venue's published past; unapplied is future information."""
    instrument = FakeContinuous(
        id="xnas-AAPL",
        bars=daily_bars(MONDAY, 12),
        cash_events=(a_dividend(2, micro=260_000), a_dividend(9, micro=314_159)),
    )
    _, calendar = continuous_setup(instrument, window_end_ms=MONDAY + 12 * DAY)
    # The ex-date is day 2; the event applies at the cum-date close, day 1 (ruling R175).
    assert visible_cash_events(instrument, now_ms=MONDAY + DAY, calendar=calendar) == ()
    applied = visible_cash_events(instrument, now_ms=MONDAY + 2 * DAY, calendar=calendar)
    assert applied == (
        CashEventView(
            kind="dividend", t_ms=MONDAY + 2 * DAY, applied_at_ms=MONDAY + DAY, detail={"dividend_micro": 260_000}
        ),
    )
    assert applied[0].to_dict()["applied_at_ms"] == MONDAY + DAY
    # The second dividend's ex-date is day 9 (a Wednesday), so it applies at day 8 and is invisible
    # anywhere before day 9, however long ago the venue announced it.
    at_day_eight = visible_cash_events(instrument, now_ms=MONDAY + 8 * DAY, calendar=calendar)
    assert [event.detail for event in at_day_eight] == [{"dividend_micro": 260_000}]
    both = visible_cash_events(instrument, now_ms=MONDAY + 9 * DAY, calendar=calendar)
    assert [event.detail["dividend_micro"] for event in both] == [260_000, 314_159]


def test_an_engine_cash_event_never_reaches_a_market_view() -> None:
    borrow = FakeCashEvent(
        cash_event_id="ce-borrow",
        market_id="xnas-AAPL",
        kind="borrow_fee",
        t_ms=MONDAY + DAY + DAY - 1,
        origin="engine",
        source_url="",
        detail={"rate_ppm_per_day": 8, "days": 1, "mark_ticks": 19_001_000},
    )
    instrument = FakeContinuous(id="xnas-AAPL", bars=daily_bars(MONDAY, 12), cash_events=(borrow,))
    _, calendar = continuous_setup(instrument, window_end_ms=MONDAY + 12 * DAY)
    assert visible_cash_events(instrument, now_ms=MONDAY + 11 * DAY, calendar=calendar) == ()


def test_the_cash_event_view_is_capped_at_thirty() -> None:
    """``CASH_EVENTS_VIEW_MAX = 30`` applied events, the most recent ones, oldest first (ruling R183)."""
    days = [day for day in range(1, 60) if (day % 7) not in (5, 6)]
    assert len(days) > CASH_EVENTS_VIEW_MAX  # otherwise this test would assert nothing about the cap
    events = tuple(a_dividend(day, micro=1_000 + day) for day in days)
    instrument = FakeContinuous(
        id="xnas-AAPL", bars=daily_bars(MONDAY, 60), cash_events=events, delisted_at_ms=MONDAY + 60 * DAY
    )
    _, calendar = continuous_setup(instrument, window_end_ms=MONDAY + 60 * DAY, t1_ms=MONDAY + 60 * DAY)
    visible = visible_cash_events(instrument, now_ms=MONDAY + 59 * DAY, calendar=calendar)
    assert len(visible) == CASH_EVENTS_VIEW_MAX
    assert [event.applied_at_ms for event in visible] == sorted(event.applied_at_ms for event in visible)
    # The most recent thirty, so the oldest applied event is gone and the newest applied one is there.
    applied_days = [(event.t_ms - MONDAY) // DAY for event in visible]
    assert applied_days[0] > days[0]
    assert applied_days[-1] == max(days)


# --------------------------------------------------------------------------------------------------
# The two tests PRD 6.3 ships with the product
# --------------------------------------------------------------------------------------------------
def test_the_clock_test() -> None:
    """Section 8.3, literally: the key set, the two bar counts, and the as-of price."""
    config = a_config(bars_window=8)
    market = a_market("demo-alpha", created_day=0, n_bars=config.bars_window, prices=list(range(100, 900, 100)))
    longer = a_market("demo-beta", created_day=0, n_bars=config.bars_window + 7)
    obs = one_observation([market, longer], now_ms=6 * DAY, config=config)
    keys = observation_key_set(obs.to_dict())
    assert keys & frozenset(FORBIDDEN_OBSERVATION_KEYS) == frozenset()
    for view in obs.markets:
        assert len(view.bars) == min(config.bars_window, 6)
    at_the_end = one_observation([market, longer], now_ms=14 * DAY, config=config)
    assert len(at_the_end.markets[1].bars) == config.bars_window
    assert at_the_end.markets[0].last_price_bp == market.bars[-1].close_bp
    assert obs.markets[0].last_price_bp == market.bars[5].close_bp
    first = one_observation([market], now_ms=0, config=config)
    assert first.markets[0].last_price_bp == market.first_price_bp
    assert "final_price_bp" not in render_observation_json(obs)


def test_the_poisoned_future_test() -> None:
    """PRD 6.3 and section 7.9: one poisoned datum per channel, none of which may surface."""
    now = 4 * DAY
    poisoned_bar = a_bar(now, 7_777, volume_milli=987_654_321, n_trades=424_242)
    later_bar = a_bar(now + DAY, 7_778, volume_milli=987_654_322)
    market = a_market("demo-alpha", created_day=0, n_bars=4, extra_bars=(poisoned_bar, later_bar))
    poisoned_news = a_news_item(
        "wce-20160105-0001",
        published_day=5,
        market_ids=("demo-alpha",),
        scores=(999,),
        headline="POISON-NEWS-HEADLINE",
        text="POISON-NEWS-BODY",
        visible_from_ms=(5 * DAY) + 6 * MS_PER_HOUR,
    )
    visible_news = a_news_item(
        "wce-20160101-0002", published_day=1, market_ids=("demo-alpha",), scores=(500,), headline="A-VISIBLE-HEADLINE"
    )
    memory = FakeMemory(
        MemoryView(
            lessons=(LessonView(written_at_ms=now + DAY, text="POISON-MEMORY-LESSON", market_ids=()),),
            notes=(NoteView(written_at_ms=now + DAY, market_id="demo-alpha", text="POISON-MEMORY-NOTE"),),
        )
    )
    hive = FakeHive(
        HiveView(
            lessons=(HiveLessonView("h-00000009", "future", 9_999, "POISON-HIVE-LESSON", (), now + DAY),),
            forecasts=(ForecastView(agent_id="other", market_id="demo-alpha", bar_ms=now - DAY, prob_ppm=987_654),),
            resolutions=(
                ResolutionView(market_id="demo-alpha", outcome=1, life_mean_price_bp=6_543, resolved_at_ms=now),
            ),
        )
    )
    obs = one_observation(
        [market],
        now_ms=now,
        news=[visible_news, poisoned_news],
        memory=memory,
        hive=hive,
    )
    rendered = render_observation_json(obs)
    for poison in (
        "7777",
        "987654321",
        "424242",
        "POISON-NEWS-HEADLINE",
        "POISON-NEWS-BODY",
        "POISON-MEMORY-LESSON",
        "POISON-MEMORY-NOTE",
        "POISON-HIVE-LESSON",
        "987654",  # another agent's forecast on a market that has not settled
        "6543",  # the resolution of a market that settles at this very bar
    ):
        assert poison not in rendered, poison
    assert "A-VISIBLE-HEADLINE" in rendered
    assert [bar.t_ms for bar in obs.markets[0].bars] == [0, DAY, 2 * DAY, 3 * DAY]
    assert obs.markets[0].last_price_bp == market.bars[3].close_bp


def test_the_poisoned_future_test_on_a_continuous_instrument() -> None:
    """The C1b half of the same test: a cash event, a ``delisted_at_ms`` and a ``last_bar``."""
    delisted = MONDAY + 30 * DAY
    instrument = FakeContinuous(
        id="xnas-AAPL",
        bars=daily_bars(MONDAY, 12),
        delisted_at_ms=delisted,
        cash_events=(a_dividend(2, micro=260_000), a_dividend(9, micro=314_159)),
    )
    meta = meta_for(instrument, window_end_ms=MONDAY + 12 * DAY)
    dataset = a_dataset([instrument], metas=cast(Sequence[MarketMeta], [meta]))
    config = a_config(t0_ms=MONDAY, t1_ms=MONDAY + 12 * DAY)
    calendar = Calendar(dataset, config, calendars={"xnys": XNYS})
    now = MONDAY + 3 * DAY
    obs = one_observation([instrument], now_ms=now, config=config, calendar=calendar)
    rendered = render_observation_json(obs)
    assert str(delisted) not in rendered
    assert str(calendar.last_bar("xnas-AAPL")) not in rendered
    assert "314159" not in rendered
    scanned = leak_scan_payload(obs.to_dict())
    assert observation_key_set(scanned) & frozenset(FORBIDDEN_OBSERVATION_KEYS) == frozenset()
    assert_no_leak(obs.to_dict(), agent_id="a", now_ms=now)  # the guard the builder itself runs
    applied = visible_cash_events(instrument, now_ms=now, calendar=calendar)
    assert [event.detail["dividend_micro"] for event in applied] == [260_000]
    view_fields = market_view_fields(
        instrument,
        now_ms=now,
        config=config,
        tradable=True,
        position=PositionView(position=0, avg_cost_bp=0, unrealised_cents=0),
        calendar=calendar,
    )
    assert view_fields["cash_events"] == applied
    assert view_fields["close_at_ms"] == 0


def test_the_demo_pack_builds_a_real_observation_under_the_size_cap() -> None:
    """The done-when, on the one committed dataset: real bars, real predicates, real bytes."""
    dataset = load_dataset(DEMO_PACK)
    config = a_config()
    calendar = Calendar(dataset, config)
    brexit = dataset.market("demo-brexit-2016")
    now = brexit.bars[40].t_ms
    open_ids = calendar.bar_slice(now).open_ids
    assert "demo-brexit-2016" in open_ids
    obs = build_observation(
        agent_id="follower",
        now_ms=now,
        config=config,
        markets=[dataset.market(market_id) for market_id in open_ids],
        positions={},
        portfolio=a_portfolio(),
        memory=None,
        hive=None,
        news=dataset.news_global(now),
        grants=(),
        calendar=calendar,
    )
    assert [view.market_id for view in obs.markets] == list(open_ids)
    view = next(item for item in obs.markets if item.market_id == "demo-brexit-2016")
    assert view.last_price_bp == brexit.bars[39].close_bp
    assert [bar.t_ms for bar in view.bars] == [bar.t_ms for bar in brexit.bars[:40]][-config.bars_window :]
    assert view.tradable is calendar.is_tradable("demo-brexit-2016", now)
    assert 0 < observation_bytes(obs) < OBSERVATION_MAX_BYTES
    assert observation_key_set(obs.to_dict()) & frozenset(FORBIDDEN_OBSERVATION_KEYS) == frozenset()
    # This market is why section 8.3 forbids an integer scan: its close_at_ms equals its resolved_at_ms,
    # and close_at_ms is public on every venue, so the value is legally in the view and only the key set
    # can be asserted.
    assert brexit.close_at_ms == brexit.resolved_at_ms
    assert view.close_at_ms == brexit.close_at_ms
    assert "final_price_bp" not in render_observation_json(obs)


def test_the_leak_guard_refuses_a_forbidden_key() -> None:
    with pytest.raises(LeakError):
        assert_no_leak({"markets": [{"market_id": "demo-alpha", "resolved_at_ms": 1}]}, agent_id="a", now_ms=0)
    with pytest.raises(LeakError):
        assert_no_leak({"markets": [{"market_id": "demo-alpha", "dividend_micro": 1}]}, agent_id="a", now_ms=0)
    assert_no_leak({"markets": [{"market_id": "demo-alpha", "close_at_ms": 1}]}, agent_id="a", now_ms=0)


def test_every_forbidden_key_is_caught_wherever_it_sits() -> None:
    """The guard runs on the whole tree, so no depth and no container hides a forbidden name.

    Section 8.3's clock test is a key-set test, which is only as good as the set: this asserts the set is
    enforced at every depth for every name in it, and that the clean payload it starts from passes, so
    the test cannot go green against a guard that raises on everything or on nothing.
    """
    obs = one_observation([a_market()], now_ms=3 * DAY)
    clean = json.loads(render_observation_json(obs))
    assert_no_leak(clean, agent_id="follower", now_ms=3 * DAY)
    for key in FORBIDDEN_OBSERVATION_KEYS:
        in_a_view = json.loads(render_observation_json(obs))
        cast(list[dict[str, object]], in_a_view["markets"])[0][key] = "POISON"
        with pytest.raises(LeakError):
            assert_no_leak(in_a_view, agent_id="follower", now_ms=3 * DAY)
        deeper = json.loads(render_observation_json(obs))
        cast(dict[str, object], deeper["memory"])["extras"] = [{"nested": [{key: 1}]}]
        with pytest.raises(LeakError):
            assert_no_leak(deeper, agent_id="follower", now_ms=3 * DAY)


def test_one_of_each_cluster_and_detector_record_is_refused() -> None:
    """Section 7.9 as amendment C1 extends it (ruling R116) and amendment C1b again (R181, R183).

    E1's row in section 13 asks for one of each: a ``MatchReason``, an ``EventCluster``, a
    ``Constraint``, an ``OpportunityEvent``, a ``CashEvent`` whose application bar has not completed, a
    ``delisted_at_ms``, a ``last_bar`` and an unresolved ``price_realised_ticks``. Each is injected as
    the record it really is, because that is how it would arrive: a later package hands a view a
    structure, not a bare key.
    """
    poisoned_records: dict[str, object] = {
        "match_reason": {"kind": "wiki_subject", "asof": True, "detail": "Brexit", "score_permille": 900},
        "cluster": {
            "cluster_id": "ec-0123456789abcdef",
            "market_ids": ["demo-alpha", "demo-zulu"],
            "asof": True,
            "score_permille": 900,
            "resolution_span_ms": -1,
            "source": "matcher",
        },
        "constraint": {
            "constraint_id": "cn-implies-0123456789ab",
            "kind": "implies",
            "market_ids": ["demo-alpha", "demo-zulu"],
            "direction": "none",
            "cluster_id": None,
        },
        "opportunity": {
            "opportunity_id": "op-divergence-0123456789abcdef",
            "detector_id": "divergence",
            "window": [0, DAY],
            "duration_bars": 2,
            "size_ppm": 40_000,
            "size_net_bp": 120,
            "payoff_cents": 900,
            "tradable_for_money": True,
            "evidence": [{"kind": "price", "ref": "demo-alpha", "t_ms": 0, "value": 1, "unit": "ppm"}],
        },
        "unapplied_cash_event": {
            "cash_event_id": "ce-0123456789abcdef",
            "kind": "dividend",
            "t_ms": 9 * DAY,
            "detail": {"dividend_micro": 314_159},
        },
        "delisting": {"delisted_at_ms": 30 * DAY},
        "last_bar": {"last_bar": 29 * DAY, "last_price_ticks": 19_000_000},
        "unresolved_horizon": {"horizon_bars": 5, "price_realised_ticks": 19_100_000, "realised_sign": 1},
    }
    obs = one_observation([a_market()], now_ms=3 * DAY)
    for name, record in poisoned_records.items():
        payload = json.loads(render_observation_json(obs))
        cast(list[dict[str, object]], payload["markets"])[0][name] = record
        with pytest.raises(LeakError, match="forbidden key"):
            assert_no_leak(payload, agent_id="follower", now_ms=3 * DAY)


def test_the_cheap_leak_prefilter_is_wrong_in_one_direction_only() -> None:
    """``False`` from the prefilter is a proof, so the exact scan may be skipped; ``True`` is a suspicion.

    The guard runs on every observation of every agent of every bar, so it has a fast path. This asserts
    the fast path can only ever skip a payload the exact scan would have passed: a clean observation says
    ``False``, a legal hive resolution and a headline that merely quotes a forbidden name both say
    ``True`` and are then passed by :func:`assert_no_leak`, and a real leak says ``True`` and raises.
    """
    clean = one_observation([a_market()], now_ms=3 * DAY)
    assert mentions_forbidden_key(render_observation_json(clean)) is False
    hive = FakeHive(
        HiveView(
            resolutions=(
                ResolutionView(
                    market_id="demo-past", outcome=1, life_mean_price_bp=6_000, resolved_at_ms=3 * DAY
                ),
            )
        )
    )
    legal = one_observation([a_market()], now_ms=5 * DAY, hive=hive)
    assert mentions_forbidden_key(render_observation_json(legal)) is True
    assert_no_leak(legal.to_dict(), agent_id="follower", now_ms=5 * DAY)
    # A headline that quotes a forbidden name does not even reach the exact scan: JSON escapes the
    # quotation marks of a string, so ``"quality":`` inside a text is ``\"quality\":`` in the render and
    # is not the shape an object key has. The prefilter is therefore tighter than a plain word search,
    # and it is still one-sided, which is the only property the fast path relies on.
    quoting = a_news_item(
        "wce-20160101-0001",
        published_day=0,
        market_ids=("demo-alpha",),
        scores=(900,),
        headline='the word "quality": in a headline',
    )
    quoted = one_observation([a_market()], now_ms=3 * DAY, news=[quoting])
    assert '\\"quality\\":' in render_observation_json(quoted)
    assert mentions_forbidden_key(render_observation_json(quoted)) is False
    assert_no_leak(quoted.to_dict(), agent_id="follower", now_ms=3 * DAY)
    leaked = json.loads(render_observation_json(clean))
    cast(list[dict[str, object]], leaked["markets"])[0]["resolved_at_ms"] = 4 * DAY
    assert mentions_forbidden_key(json.dumps(leaked, separators=(",", ":"))) is True
    with pytest.raises(LeakError):
        assert_no_leak(leaked, agent_id="follower", now_ms=3 * DAY)


def test_the_two_published_past_subtrees_are_the_only_exemptions() -> None:
    """A settled market's announcement and an applied cash event's detail are legal where they sit."""
    assert_no_leak(
        {
            "hive": {"resolutions": [{"market_id": "demo-past", "outcome": 1, "resolved_at_ms": 3 * DAY}]},
            "markets": [{"market_id": "demo-alpha", "cash_events": [{"detail": {"dividend_micro": 260_000}}]}],
        },
        agent_id="a",
        now_ms=4 * DAY,
    )
    with pytest.raises(LeakError):
        assert_no_leak(
            {"hive": {"forecasts": [{"market_id": "demo-alpha", "resolved_at_ms": 3 * DAY}]}},
            agent_id="a",
            now_ms=4 * DAY,
        )
    scanned = leak_scan_payload(
        {"hive": {"resolutions": [{"resolved_at_ms": 1}], "lessons": [{"entry_id": "h-1"}]}}
    )
    assert scanned == {"hive": {"resolutions": [], "lessons": [{"entry_id": "h-1"}]}}


def test_a_settled_markets_resolution_reaches_the_agent_through_the_hive() -> None:
    """The whole point of the hive: an outcome an agent may read, one bar after settlement (R12)."""
    now = 5 * DAY
    hive = FakeHive(
        HiveView(
            resolutions=(
                ResolutionView(
                    market_id="demo-past", outcome=1, life_mean_price_bp=6_000, resolved_at_ms=3 * DAY
                ),
            )
        )
    )
    obs = one_observation([a_market()], now_ms=now, hive=hive)
    assert [item.market_id for item in obs.hive.resolutions] == ["demo-past"]
    assert "demo-past" in render_observation_json(obs)


# --------------------------------------------------------------------------------------------------
# Serialisation, size and determinism
# --------------------------------------------------------------------------------------------------
def test_an_observation_serialises_canonically_and_carries_no_float() -> None:
    obs = one_observation([a_market()], now_ms=3 * DAY)
    rendered = render_observation_json(obs)
    assert "\n" not in rendered
    payload = json.loads(rendered)
    assert payload["obs_version"] == "obs.v2"
    assert observation_bytes(obs) == len(rendered.encode("utf-8"))

    def no_float(node: object) -> None:
        if isinstance(node, float):
            raise AssertionError("an observation may not carry a float")
        if isinstance(node, dict):
            for value in cast(dict[str, object], node).values():
                no_float(value)
        elif isinstance(node, list):
            for value in cast(list[object], node):
                no_float(value)

    no_float(payload)


def test_two_builds_of_the_same_bar_are_identical() -> None:
    market = a_market("demo-alpha", created_day=0, n_bars=9)
    news = [a_news_item("wce-20160101-0001", published_day=0, market_ids=("demo-alpha",), scores=(700,))]
    first = one_observation([market], now_ms=4 * DAY, news=news)
    second = one_observation([market], now_ms=4 * DAY, news=news)
    assert render_observation_json(first) == render_observation_json(second)


def test_an_observation_over_the_cap_is_refused_rather_than_truncated() -> None:
    """Section 8.1: a silent truncation is a leak of a different kind, so the builder raises instead."""
    market = a_market("demo-alpha", created_day=0, n_bars=200)
    fat_news = [
        a_news_item(
            f"wce-20160101-{index:04d}",
            published_day=0,
            market_ids=("demo-alpha",),
            scores=(500,),
            text="x" * 4_000,
            headline="h" * 300,
        )
        for index in range(1, 51)
    ]
    config = a_config(bars_window=200, news_per_market=50, news_global=200)
    obs = one_observation([market], now_ms=150 * DAY, config=config, news=fat_news)
    assert 0 < observation_bytes(obs) < OBSERVATION_MAX_BYTES
    # A research payload the builder did not size: one grant whose body alone exceeds the cap.
    huge = ResearchGrant(
        kind="news",
        market_id="demo-alpha",
        granted_at_ms=DAY,
        news=(
            NewsView(
                news_id="wce-20160101-0099",
                source="wikipedia_current_events",
                kind="headline",
                published_at_ms=0,
                headline="h",
                text="x" * (OBSERVATION_MAX_BYTES + 1_024),
                section=None,
                url="",
                match_score_permille=0,
            ),
        ),
    )
    with pytest.raises(ObservationTooLargeError):
        one_observation([market], now_ms=150 * DAY, config=config, news=fat_news, grants=[huge])


def test_the_two_spellings_of_ruling_r175_agree_on_every_kind() -> None:
    """Ruling R175 is computed twice in the engine, so the two answers are pinned against each other.

    ``pmx.engine.execution.applies_at`` is the declared home (R175) and
    ``pmx.engine.observation.cash_event_applies_at`` is the leak boundary's own spelling, because the
    observation may not import the module that moves money. A divergence between them would show an
    agent a dividend at a bar the engine paid it at another, which is exactly the asymmetry R183 exists
    to close, so this test is the guard until the gate says which file owns the rule.
    """
    instrument = FakeContinuous(id="xnas-AAPL", bars=daily_bars(MONDAY, 12))
    _, calendar = continuous_setup(instrument, window_end_ms=MONDAY + 12 * DAY)
    for kind in CASH_EVENT_KINDS:
        for day in (0, 1, 5, 9):
            event = FakeCashEvent(
                cash_event_id="ce-0123456789abcdef",
                market_id=instrument.id,
                kind=kind,
                t_ms=MONDAY + day * DAY,
                origin="data" if kind in DATA_CASH_EVENT_KINDS else "engine",
                source_url="",
                detail={},
            )
            mine = cash_event_applies_at(event, interval_min=instrument.interval_min, calendar=calendar)
            theirs = execution_applies_at(event, instrument, calendar)
            assert mine == theirs, (kind, day)
    # Without a calendar the corporate kinds have no application bar and stay hidden, which is the one
    # deliberate difference: execution always holds a calendar and the runner always passes one.
    dividend = FakeCashEvent(
        cash_event_id="ce-0123456789abcdef",
        market_id=instrument.id,
        kind="dividend",
        t_ms=MONDAY + 5 * DAY,
        origin="data",
        source_url="",
        detail={},
    )
    assert cash_event_applies_at(dividend, interval_min=1_440, calendar=None) is None
    assert visible_cash_events(instrument, now_ms=MONDAY + 6 * DAY, calendar=None) == ()


# --------------------------------------------------------------------------------------------------
# The sensor gene's hook (PRD v5 section 1): an observation assembled from a per-agent sensor set
#
# The hook gates view fields by subtraction, so the tests below are about two things and nothing else:
# that the default set is the builder that predates it, byte for byte, and that a narrowed set removes
# exactly what it says and can never add anything, the poisoned future included.
# --------------------------------------------------------------------------------------------------
SENSOR_NOW = 4 * DAY


def a_sensor_world() -> dict[str, object]:
    """A world in which **every** field this hook gates carries something an agent could act on.

    That matters more than it looks: on a market with no quotes, no prints and no linked news, half the
    gated fields are already empty, and every "the key is gone" assertion below would pass for the wrong
    reason. Here the quotes are quoted, the prints are granted, the digest is linked and the memory has a
    note, so a dropped field is a dropped value. The two cross-asset fields are the exception and cannot
    be furnished by a binary market (it has no underlying and no twin), so the ``cross_asset`` row is
    checked by key and never by value.
    """
    trades = tuple(
        Trade(t_ms=index * DAY + 3, price_bp=5_000 + index, size_milli=1_000, side="yes") for index in range(4)
    )
    market = a_market("demo-alpha", created_day=0, n_bars=9, quotes=True, trades=trades)
    news = [
        a_news_item(
            "wce-20160101-0001",
            published_day=1,
            market_ids=("demo-alpha",),
            scores=(700,),
            headline="A-VISIBLE-HEADLINE",
        )
    ]
    memory = FakeMemory(
        MemoryView(notes=(NoteView(written_at_ms=DAY, market_id="demo-alpha", text="A-VISIBLE-NOTE"),))
    )
    grant = build_grant(
        request=ResearchRequest(kind="history", market_id="demo-alpha"),
        granted_at_ms=SENSOR_NOW - DAY,
        config=a_config(),
        trades=trades,
    )
    return {"markets": [market], "news": news, "memory": memory, "grants": [grant]}


def an_observation_with(sensors: Sequence[str] | None) -> Observation:
    """The same world at the same bar, seen through one sensor set."""
    world = a_sensor_world()
    return one_observation(
        cast(Sequence[object], world["markets"]),
        now_ms=SENSOR_NOW,
        news=cast(Sequence[NewsItem], world["news"]),
        grants=cast(Sequence[ResearchGrant], world["grants"]),
        memory=cast(FakeMemory, world["memory"]),
        sensors=sensors,
    )


def test_the_default_sensor_set_is_todays_behaviour_byte_for_byte() -> None:
    """Point 1 of the hook: ``None`` means every sensor, and the full diet spelled out is the same bytes.

    Both build a **plain** ``MarketView`` and a plain ``Observation`` and not a narrowed one, which is
    what makes the whole existing suite the proof that the default changed nothing.
    """
    default = an_observation_with(None)
    explicit = an_observation_with(list(SENSOR_NAMES))
    assert render_observation_json(default) == render_observation_json(explicit)
    assert observation_bytes(default) == observation_bytes(explicit)
    assert type(default) is Observation
    assert type(explicit) is Observation
    assert {type(view) for view in default.markets} == {MarketView}
    assert {type(view) for view in explicit.markets} == {MarketView}
    assert resolve_sensor_set(SENSOR_NAMES) is None
    # The world really is furnished, so the assertions of the next tests bite.
    view = default.markets[0]
    assert view.bars and view.trades and view.news
    assert (view.underlying_id, view.twins) == (None, ())  # a binary has neither
    assert view.best_bid_bp is not None and view.best_ask_bp is not None
    assert view.volume_milli_to_date > 0 and view.n_trades_to_date > 0
    assert default.news and default.memory.notes


@pytest.mark.parametrize("dropped", SENSOR_NAMES)
def test_dropping_one_sensor_omits_exactly_that_sensors_fields(dropped: str) -> None:
    """Point 2: a narrowed set omits exactly the gated fields and nothing else, at both levels."""
    full = an_observation_with(None).to_dict()
    narrowed = an_observation_with([name for name in SENSOR_NAMES if name != dropped]).to_dict()
    gated = SENSOR_VIEW_FIELDS[dropped]
    assert set(full) - set(narrowed) == set(gated.observation)
    for key in set(narrowed) - {"markets"}:
        assert narrowed[key] == full[key], key
    before_views = cast(list[dict[str, object]], full["markets"])
    after_views = cast(list[dict[str, object]], narrowed["markets"])
    for before, after in zip(before_views, after_views, strict=True):
        assert set(before) - set(after) == set(gated.market)
        for key in after:
            assert after[key] == before[key], key


def test_an_unknown_sensor_is_refused_and_never_silently_ignored() -> None:
    """Point 5: a genome that names a sensor this build does not have dies at the boundary.

    Every name PRD v5 lists whose data no built dataset carries yet is refused too, one by one, so a
    caller cannot buy a promise: those rows are C1c's and S1's to add.
    """
    with pytest.raises(InvalidConfigError) as caught:
        an_observation_with(["tape", "hn"])
    assert caught.value.context["sensors"] == ["hn"]
    assert caught.value.context["known"] == list(SENSOR_NAMES)
    for future in (
        "hn",
        "gdelt_recent",
        "filings",
        "macro_releases",
        "comments",
        "wiki_asof",
        "hive_insights",
        "hive_reputation",
        "",
        "TAPE",
    ):
        with pytest.raises(InvalidConfigError):
            resolve_sensor_set([future])


def test_absence_cannot_be_mistaken_for_zero_or_for_empty() -> None:
    """Point 2 again, the part that matters: an unsensed field is absent and not a value.

    The contrast is the test. On a market's very first bar the volume fields are legitimately ``0`` and
    the quotes legitimately ``None``, and those values are **present**. With the sensor dropped the keys
    are gone, reading the attribute raises, and even ``hasattr`` raises, so nothing can turn the absence
    into a default and no agent can tell itself the market was quiet.
    """
    first_bar = one_observation(
        [a_market("demo-alpha", created_day=0, n_bars=6, quotes=True)], now_ms=0
    ).markets[0].to_dict()
    assert first_bar["volume_milli_to_date"] == 0
    assert first_bar["n_trades_to_date"] == 0
    assert first_bar["best_bid_bp"] is None
    assert first_bar["trades"] == []

    blind = [name for name in SENSOR_NAMES if name not in ("volume_profile", "microstructure")]
    view = an_observation_with(blind).markets[0]
    payload = view.to_dict()
    assert isinstance(view, MarketView)
    for gone in (
        "volume_milli_7d",
        "volume_milli_to_date",
        "n_trades_to_date",
        "best_bid_bp",
        "best_ask_bp",
        "trades",
    ):
        assert gone not in payload, gone
        with pytest.raises(SchemaError) as caught:
            getattr(view, gone)
        assert caught.value.context["field"] == gone
        with pytest.raises(SchemaError):
            hasattr(view, gone)
    expected = SENSOR_VIEW_FIELDS["volume_profile"].market | SENSOR_VIEW_FIELDS["microstructure"].market
    assert view.unsensed_fields == expected
    # The ungated fields still read, and the sensed ones still carry their values.
    assert view.market_id == "demo-alpha"
    assert view.tradable is True
    assert view.last_price_bp == 5_000 + 300
    assert repr(view).startswith("SensedMarketView(")
    # And the absence survives the round trip through the dataclasses and the canonical JSON alike.
    assert json.loads(render_observation_json(an_observation_with(blind)))["markets"][0] == payload


def test_an_observation_level_sensor_is_absent_at_the_top_level() -> None:
    """``wiki_daily`` and ``memory`` gate a field of the ``Observation`` itself, not of a market view."""
    obs = an_observation_with(["tape"])
    payload = json.loads(render_observation_json(obs))
    assert isinstance(obs, Observation)
    assert obs.unsensed_fields == frozenset({"memory", "news"})
    for gone in ("memory", "news"):
        assert gone not in payload
        with pytest.raises(SchemaError) as caught:
            getattr(obs, gone)
        assert caught.value.context["field"] == gone
    assert "news" not in payload["markets"][0]
    assert "A-VISIBLE-NOTE" not in render_observation_json(obs)
    assert "A-VISIBLE-HEADLINE" not in render_observation_json(obs)
    # What is left is the tape and the ungated fields, at their full value.
    assert obs.agent_id == "follower"
    assert obs.portfolio.cash_cents == 100_000
    assert [bar.t_ms for bar in obs.markets[0].bars] == [index * DAY for index in range(4)]
    assert repr(obs).startswith("SensedObservation(")


def test_the_as_of_law_holds_for_every_sensor_set() -> None:
    """Point 4: a sensor set narrows and never widens, over all 128 of them.

    The poisoned-future world of PRD 6.3 is rebuilt here and every subset of the catalogue is asked for
    it. Three properties are asserted for each: no poisoned datum surfaces, no forbidden key appears, and
    every byte the set kept is the byte the default set carried (so no set can alter a field either).
    Exhaustive rather than random on purpose: 128 builds are cheaper than one flaky seed.
    """
    now = SENSOR_NOW
    poisoned_bar = a_bar(now, 7_777, volume_milli=987_654_321, n_trades=424_242)
    market = a_market("demo-alpha", created_day=0, n_bars=4, quotes=True, extra_bars=(poisoned_bar,))
    poisoned_news = a_news_item(
        "wce-20160105-0001",
        published_day=5,
        market_ids=("demo-alpha",),
        scores=(999,),
        headline="POISON-NEWS-HEADLINE",
        text="POISON-NEWS-BODY",
        visible_from_ms=(5 * DAY) + 6 * MS_PER_HOUR,
    )
    visible_news = a_news_item(
        "wce-20160101-0002", published_day=1, market_ids=("demo-alpha",), scores=(500,), headline="A-HEADLINE"
    )
    memory = FakeMemory(
        MemoryView(
            lessons=(LessonView(written_at_ms=now + DAY, text="POISON-MEMORY-LESSON", market_ids=()),),
            notes=(NoteView(written_at_ms=now + DAY, market_id="demo-alpha", text="POISON-MEMORY-NOTE"),),
        )
    )
    hive = FakeHive(
        HiveView(
            lessons=(HiveLessonView("h-00000009", "future", 9_999, "POISON-HIVE-LESSON", (), now + DAY),),
            forecasts=(ForecastView(agent_id="other", market_id="demo-alpha", bar_ms=now - DAY, prob_ppm=987_654),),
            resolutions=(
                ResolutionView(market_id="demo-alpha", outcome=1, life_mean_price_bp=6_543, resolved_at_ms=now),
            ),
        )
    )
    grant = build_grant(
        request=ResearchRequest(kind="history", market_id="demo-alpha"),
        granted_at_ms=now - DAY,
        config=a_config(),
        trades=(Trade(t_ms=now + 1, price_bp=8_888, size_milli=1_000, side="yes"),),
    )

    def build(sensors: Sequence[str] | None) -> dict[str, object]:
        return one_observation(
            [market],
            now_ms=now,
            news=[visible_news, poisoned_news],
            memory=memory,
            hive=hive,
            grants=[grant],
            sensors=sensors,
        ).to_dict()

    poisons = (
        "7777",
        "987654321",
        "424242",
        "8888",
        "POISON-NEWS-HEADLINE",
        "POISON-NEWS-BODY",
        "POISON-MEMORY-LESSON",
        "POISON-MEMORY-NOTE",
        "POISON-HIVE-LESSON",
        "987654",
        "6543",
    )
    default = build(None)
    all_sets = [
        combination
        for size in range(len(SENSOR_NAMES) + 1)
        for combination in itertools.combinations(SENSOR_NAMES, size)
    ]
    assert len(all_sets) == 2 ** len(SENSOR_NAMES)
    for sensors in all_sets:
        payload = build(list(sensors))
        rendered = canonical_json(payload)
        for poison in poisons:
            assert poison not in rendered, (poison, sensors)
        assert observation_key_set(leak_scan_payload(payload)) & frozenset(FORBIDDEN_OBSERVATION_KEYS) == frozenset()
        assert_no_leak(payload, agent_id="follower", now_ms=now)
        assert set(payload) <= set(default)
        for key in set(payload) - {"markets"}:
            assert payload[key] == default[key], (key, sensors)
        views = cast(list[dict[str, object]], payload["markets"])
        default_views = cast(list[dict[str, object]], default["markets"])
        for view, before in zip(views, default_views, strict=True):
            assert set(view) <= set(before)
            for key in view:
                assert view[key] == before[key], (key, sensors)
            for bar in cast(list[dict[str, object]], view.get("bars", [])):
                assert cast(int, bar["t_ms"]) + DAY <= now
            for trade in cast(list[dict[str, object]], view.get("trades", [])):
                assert cast(int, trade["t_ms"]) < now
            for item in cast(list[dict[str, object]], view.get("news", [])):
                assert cast(int, item["published_at_ms"]) <= now
        for item in cast(list[dict[str, object]], payload.get("news", [])):
            assert cast(int, item["published_at_ms"]) <= now


def test_every_gated_name_is_a_field_of_the_view_it_gates() -> None:
    """The extension point C1c writes into: a row naming a field no view has would gate nothing at all.

    It would also fail silently, because dropping a name that is not in the payload removes nothing, so
    this is the test that makes a mistyped row in ``SENSOR_VIEW_FIELDS`` a red test rather than a sensor
    an agent pays for and still sees.
    """
    market_fields = {field.name for field in dataclass_fields(MarketView)}
    observation_fields = {field.name for field in dataclass_fields(Observation)}
    assert market_fields >= GATED_MARKET_VIEW_FIELDS
    assert observation_fields >= GATED_OBSERVATION_FIELDS
    for name, gated in SENSOR_VIEW_FIELDS.items():
        assert gated.market or gated.observation, name
        assert gated.market <= market_fields, name
        assert gated.observation <= observation_fields, name
    # The identity fields, the agent's own book and the caps it is judged under are ungated on purpose.
    assert GATED_MARKET_VIEW_FIELDS & {"market_id", "question", "tradable", "position", "kind"} == set()
    assert GATED_OBSERVATION_FIELDS & {"markets", "portfolio", "hive", "research", "limits"} == set()


def test_a_sensor_set_is_a_set_difference_and_a_duplicate_changes_nothing() -> None:
    """A field is present as soon as any sensor that gates it was bought, and a set is a set."""
    assert unsensed_view_fields(None) == (frozenset(), frozenset())
    market, observation = unsensed_view_fields(frozenset({"tape"}))
    assert market == GATED_MARKET_VIEW_FIELDS - SENSOR_VIEW_FIELDS["tape"].market
    assert observation == GATED_OBSERVATION_FIELDS
    assert resolve_sensor_set(["tape", "tape"]) == frozenset({"tape"})
    twice = render_observation_json(an_observation_with(["tape", "tape"]))
    assert twice == render_observation_json(an_observation_with(["tape"]))
    # ``wiki_daily`` is the one sensor that gates a field of both views, and it gates both or neither.
    both = an_observation_with(["wiki_daily"]).to_dict()
    assert "news" in both
    assert "news" in cast(list[dict[str, object]], both["markets"])[0]
    without = an_observation_with([name for name in SENSOR_NAMES if name != "wiki_daily"]).to_dict()
    assert "news" not in without
    assert "news" not in cast(list[dict[str, object]], without["markets"])[0]


def test_a_narrowed_observation_is_still_guarded_deterministic_and_smaller() -> None:
    """A narrowed observation is journalable in exactly the way a full one is: the guards run on it."""
    obs = an_observation_with(["calendar"])
    payload = obs.to_dict()
    assert_no_leak(payload, agent_id="follower", now_ms=SENSOR_NOW)
    assert json.loads(render_observation_json(obs)) == payload
    assert observation_bytes(obs) < observation_bytes(an_observation_with(None))
    again = an_observation_with(["calendar"])
    assert render_observation_json(again) == render_observation_json(obs)
    assert again == obs
    assert hash(again) == hash(obs)
    assert again.markets[0] == obs.markets[0]
    assert obs != an_observation_with(None)
    assert obs.markets[0] != an_observation_with(None).markets[0]
