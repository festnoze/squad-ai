"""E2: execution, fees and liquidity (CONTRACTS_V2 8.5 to 8.9, 16.1, 17.1 to 17.4).

What these tests are for, in the order the contract asks for them:

* the accounting invariant of 8.9 holds over the journal alone, per instrument kind, over generated
  sequences of orders and cash events, including the ten named cases of 17.3 (a funding sign flip, a
  reverse split on a short, a roll with a negative gap, a roll an agent cannot fund, a dividend on a
  short, a dividend debit that takes cash below zero, a buy at an ex-date open that receives nothing, a
  buy at a split's effective open that is not multiplied, a carry on a long at a negative rate, and a
  forced flat that cash cannot pay);
* ``check_envelope(historical, ...)`` reports no breach on a generated bar and order set, on a binary
  view **and** on a continuous one, and it catches a model that breaks each rule;
* a zero-volume bar fills nothing, no fill lands on the bar its action was decided on, and none lands at
  ``bar_of(close_at_ms)`` or ``bar_of(resolved_at_ms)``;
* every worked number sections 1.2, 1.4, 8.8, 17.1 and 17.4 print is executed rather than described.

The fixture instruments are built here rather than loaded, because E2 owns no dataset: a ``Market`` is
the real ``pmx.types`` record and a continuous instrument is a local record satisfying the structural
``InstrumentLike`` of ``pmx.engine.execution`` (``ContinuousInstrument`` is D1's, landed by gate G2).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pmx import CONTRACT_VERSION, ENGINE_VERSION
from pmx.engine import fees
from pmx.engine.execution import (
    CashEventLike,
    Execution,
    InstrumentLike,
    applies_at,
    instrument_spec,
)
from pmx.engine.fees import (
    CARRY_SCHEDULES,
    FEE_SCHEDULES,
    MILLI,
    NOTIONAL_CENTS_MAX,
    PRICE_TICKS_MAX,
    FeeSchedule,
    cash_in_cents,
    cash_out_cents,
    fee_cents,
    mark_value_cents,
    notional_micro,
    split_position_milli,
)
from pmx.engine.liquidity import (
    CAP_UNLIMITED,
    ENVELOPE_BREACHES,
    Fill,
    HistoricalLiquidity,
    LiquidityMarketView,
    LiquidityOrder,
    ObservedFlow,
    allocate_cap,
    cap_milli,
    check_envelope,
    clamp_price,
    envelope_bounds,
    event_fill,
    finalise_fill,
    half_spread_ticks,
    make_liquidity,
    slippage_ticks,
    truncate_for_cash,
)
from pmx.errors import InvalidConfigError
from pmx.journal import Journal, RunStarted, canonical_sha256
from pmx.rng import RNG_ALGORITHM_VERSION
from pmx.types import (
    BP_ONE,
    MS_PER_DAY,
    Bar,
    CashEvent,
    DatasetWindow,
    Market,
    MarketAction,
    MarketQuality,
    RunConfig,
    Session,
    SessionCalendar,
    Trade,
    bar_of,
    cost_cents,
    proceeds_cents,
    round_half_up,
)

RUN_ID = "r-abcdef01-7-01234567"
DAY = MS_PER_DAY
T0 = 1_600_000_000_000 // DAY * DAY


# --------------------------------------------------------------------------------------------------
# Fixture instruments
# --------------------------------------------------------------------------------------------------
def make_bar(
    t_ms: int,
    *,
    open_bp: int,
    high_bp: int | None = None,
    low_bp: int | None = None,
    close_bp: int | None = None,
    vwap_bp: int | None = None,
    volume_milli: int = 0,
    bid_bp: int | None = None,
    ask_bp: int | None = None,
) -> Bar:
    """One bar, defaulting to a flat bar of the kind a ``reconstructed`` tape carries."""
    close = open_bp if close_bp is None else close_bp
    return Bar(
        t_ms=t_ms,
        open_bp=open_bp,
        high_bp=max(open_bp, close) if high_bp is None else high_bp,
        low_bp=min(open_bp, close) if low_bp is None else low_bp,
        close_bp=close,
        vwap_bp=open_bp if vwap_bp is None else vwap_bp,
        volume_milli=volume_milli,
        n_trades=1 if volume_milli else 0,
        yes_bid_bp=bid_bp,
        yes_ask_bp=ask_bp,
        open_interest=None,
    )


def make_market(
    *,
    market_id: str = "kalshi-demo",
    bars: Sequence[Bar],
    close_at_ms: int,
    resolved_at_ms: int,
    resolution: int = 1,
    source: str = "imported",
    fee_schedule_id: str = "kalshi-general-2026-09",
    interval_min: int = 1_440,
) -> Market:
    """A real ``pmx.types.Market``: the binary instrument, with the tape the test needs."""
    return Market(
        schema_version="market.v2",
        id=market_id,
        provider="kalshi",
        provider_id="DEMO-24",
        url="https://kalshi.com/",
        question="Will the fixture resolve yes?",
        description="",
        category="politics",
        tags=(),
        wiki_subjects=(),
        currency="usd",
        source=source,
        created_at_ms=bars[0].t_ms,
        close_at_ms=close_at_ms,
        resolved_at_ms=resolved_at_ms,
        resolution=resolution,
        resolution_source="venue",
        event_key=None,
        interval_min=interval_min,
        bars=tuple(bars),
        trades=(),
        first_price_bp=bars[0].open_bp,
        final_price_bp=bars[-1].close_bp,
        hardness_tags=(),
        quality=MarketQuality(
            n_trades=0, unique_bettors=None, life_days=len(bars), volume_milli_total=0, traded_bars=0
        ),
        fee_schedule_id=fee_schedule_id,
        notes="",
    )


@dataclass(frozen=True, slots=True)
class Continuous:
    """A continuous instrument, satisfying ``InstrumentLike`` and carrying the base fields of 17.1.

    ``pmx.types.ContinuousInstrument`` is D1's record, landed by gate G2 (17.9); this is the same shape
    read through the same names, which is what lets E2 be built and tested in wave 2.
    """

    id: str
    kind: str
    tick_size_micro: int
    point_value_micro: int
    bars: tuple[Bar, ...]
    provider: str = "binance"
    vendor: str = "binance"
    symbol: str = "BTCUSDT"
    currency: str = "usdt"
    category: str = "crypto"
    source: str = "imported"
    session_calendar_id: str = "continuous"
    fee_schedule_id: str = "binance-perp-2026-09"
    borrow_schedule_id: str | None = None
    carry_schedule_id: str | None = None
    listed_at_ms: int = T0
    delisted_at_ms: int | None = None
    short_allowed: bool = True
    interval_min: int = 1_440
    cash_events: tuple[CashEventLike, ...] = ()
    trades: tuple[Trade, ...] = ()

    def bar_at(self, t_ms: int) -> Bar | None:
        target = bar_of(t_ms, self.interval_min)
        for bar in self.bars:
            if bar.t_ms == target:
                return bar
        return None

    def bars_before(self, now_ms: int, limit: int) -> tuple[Bar, ...]:
        step = self.interval_min * 60_000
        done = [bar for bar in self.bars if bar.t_ms + step <= now_ms]
        return tuple(done[-limit:]) if limit > 0 else ()


def crypto(
    *,
    market_id: str = "binance-btcusdt",
    kind: str = "perp",
    bars: Sequence[Bar] | None = None,
    **extra: object,
) -> Continuous:
    """A perp on a millionth-scale tick: one milli-coin is a fill (ruling R148)."""
    tape = tuple(bars) if bars is not None else tuple(
        make_bar(T0 + index * DAY, open_bp=6_300_000 + index * 1_000, volume_milli=5_000)
        for index in range(4)
    )
    return Continuous(
        id=market_id,
        kind=kind,
        tick_size_micro=10_000,
        point_value_micro=1_000_000,
        bars=tape,
        **extra,  # type: ignore[arg-type]
    )


def data_event(*, market_id: str, kind: str, t_ms: int,
               detail: Mapping[str, int | str]) -> CashEvent:
    """One data cash event of an instrument file (17.3), through D1's own record and its id (R176).

    ``CashEvent.build`` derives the origin from the kind, which is ruling R177's rule, so a data kind
    cannot be built with an engine origin here by accident.
    """
    return CashEvent.build(
        market_id=market_id,
        kind=kind,
        t_ms=t_ms,
        detail=dict(detail),
        source_url="https://example.invalid/corporate-actions",
    )


def continuous_fixture(
    *,
    kind: str = "perp",
    market_id: str = "binance-btcusdt",
    n_bars: int = 4,
    price_ticks: int = 6_300_000,
    prices: Sequence[int] | None = None,
    volume_milli: int = 1_000_000,
    tick_size_micro: int = 10_000,
    point_value_micro: int = 1_000_000,
    fee_schedule_id: str = "binance-perp-2026-09",
    **extra: object,
) -> Continuous:
    """A **flat** continuous tape: ``open == high == low == close`` on every bar.

    Flat is the shape a test wants, and not a convenience: a flat pair estimates a zero half-spread
    (17.4) and the envelope clamps every price into ``[low, high]``, so a fill lands at the price the
    test names and the arithmetic under test is the netting and not the tape.
    """
    tape = tuple(prices) if prices is not None else tuple(price_ticks for _ in range(n_bars))
    bars = tuple(
        make_bar(T0 + index * DAY, open_bp=level, high_bp=level, low_bp=level, close_bp=level,
                 volume_milli=volume_milli)
        for index, level in enumerate(tape)
    )
    return Continuous(
        id=market_id,
        kind=kind,
        tick_size_micro=tick_size_micro,
        point_value_micro=point_value_micro,
        bars=bars,
        fee_schedule_id=fee_schedule_id,
        **extra,  # type: ignore[arg-type]
    )


def sessions_of(calendar_id: str, *days: int) -> SessionCalendar:
    """A sealed session calendar of one whole day per named day offset (17.2, ruling R174).

    The record is ``pmx.types.SessionCalendar``, the type ruling R174 declares ``Execution(calendars=)``
    against, so a test drives execution through the same object a run does and not through a second
    shape of the same data.
    """
    return SessionCalendar(
        calendar_id=calendar_id,
        description=f"A fixture venue open on the days {days} of the window.",
        source_url="https://example.invalid/calendar",
        as_of_date="2026-09-08",
        window=DatasetWindow(start_ms=T0, end_ms=T0 + 64 * DAY),
        sessions=tuple(
            Session(open_ms=T0 + day * DAY, close_ms=T0 + (day + 1) * DAY) for day in days
        ),
    )


def config_of(**extra: object) -> RunConfig:
    """A run config over the fixture window, with the defaults of 8.1 unless a test moves one."""
    values: dict[str, object] = {
        "seed": 7,
        "interval_min": 1_440,
        "t0_ms": T0,
        "t1_ms": T0 + 10 * DAY,
        "bankroll_cents": 100_000,
    }
    values.update(extra)
    return RunConfig(**values)  # type: ignore[arg-type]


def execution_of(*, config: RunConfig | None = None, journal: Journal | None = None,
                 calendars: Mapping[str, SessionCalendar] | None = None,
                 carry_schedules: Mapping[str, fees.CarrySchedule] | None = None,
                 validate: bool = False) -> tuple[Execution, Journal]:
    """An execution over the shipped fee schedules and the ``historical`` model."""
    run_config = config if config is not None else config_of()
    log = journal if journal is not None else Journal(RUN_ID, validate=validate)
    if log.next_seq == 1:
        log.emit(
            RunStarted,
            bar_ms=0,
            seed=run_config.seed,
            engine_version=ENGINE_VERSION,
            contract_version=CONTRACT_VERSION,
            rng_algorithm_version=RNG_ALGORITHM_VERSION,
            dataset_name="fixture",
            dataset_hash="0" * 64,
            interval_min=run_config.interval_min,
            t0_ms=run_config.t0_ms or 0,
            t1_ms=run_config.t1_ms or 0,
            market_ids=(),
            config=run_config.to_dict(),
            config_hash="0" * 64,
            folds={"train_end_ms": 0, "validation_end_ms": 0},
            memory_from_run_id=None,
            memory_hash=None,
            memory_from_run_t1_ms=None,
            contamination_hash=None,
            roster=(),
        )
    execution = Execution(
        journal=log,
        config=run_config,
        schedules=dict(FEE_SCHEDULES),
        liquidity=HistoricalLiquidity(run_config),
        calendars=calendars,
        carry_schedules=carry_schedules,
    )
    return (execution, log)


def binary_view(**extra: object) -> LiquidityMarketView:
    values: dict[str, object] = {
        "market_id": "kalshi-demo",
        "provider": "kalshi",
        "category": "politics",
        "currency": "usd",
        "fee_schedule_id": "kalshi-general-2026-09",
        "source": "imported",
        "interval_min": 1_440,
    }
    values.update(extra)
    return LiquidityMarketView(**values)  # type: ignore[arg-type]


def crypto_view(**extra: object) -> LiquidityMarketView:
    values: dict[str, object] = {
        "market_id": "binance-btcusdt",
        "provider": "binance",
        "category": "crypto",
        "currency": "usdt",
        "fee_schedule_id": "binance-perp-2026-09",
        "source": "imported",
        "interval_min": 1_440,
        "kind": "spot_crypto",
        "tick_size_micro": 10_000,
        "point_value_micro": 1_000_000,
    }
    values.update(extra)
    return LiquidityMarketView(**values)  # type: ignore[arg-type]


def events_of(log: Journal, event_type: str) -> tuple[Any, ...]:
    """Every event of one type, in ``seq`` order.

    The payload is read attribute by attribute, and the bridged classes of ruling R164 carry fields the
    ``JournalEvent`` base does not declare, so the element type is deliberately dynamic: a test that
    named one class would stop compiling the day gate G2 lands ``pmx.journal``'s own.
    """
    return tuple(event for event in log.events if event_type == event.TYPE)


# --------------------------------------------------------------------------------------------------
# 1.2, 1.4, 8.8, 17.1 and 17.4: the price model and the fee schedules
# --------------------------------------------------------------------------------------------------
def test_pq_permille_reproduces_the_kalshi_worked_values() -> None:
    """8.8: 100 contracts at 5 000 bp cost 175 cents; 10 at 9 000 bp cost ceil(6.3) = 7."""
    schedule = FEE_SCHEDULES["kalshi-general-2026-09"]
    assert fee_cents(schedule, size=100, price_bp=5_000, role="taker") == 175
    assert fee_cents(schedule, size=10, price_bp=9_000, role="taker") == 7
    assert fee_cents(schedule, size=10, price_bp=9_000, role="maker") == 0
    assert fee_cents(schedule, size=0, price_bp=9_000, role="taker") == 0


def test_the_other_three_fee_models_are_notional_per_contract_and_zero() -> None:
    """17.4: a taker fee of 5 bp of the notional, 253 cents a contract per side, and nothing."""
    perp = FEE_SCHEDULES["binance-perp-2026-09"]
    fee = fee_cents(perp, size=1, price_bp=6_341_257, role="taker", tick_size_micro=10_000,
                    point_value_micro=1_000_000)
    notional = cash_in_cents(1, 6_341_257, 10_000, 1_000_000)
    assert fee == 4 and notional == 6_341
    assert fee_cents(perp, size=1, price_bp=6_341_257, role="maker", tick_size_micro=10_000,
                     point_value_micro=1_000_000) == 2
    cme = FEE_SCHEDULES["cme-es-2026-09"]
    assert fee_cents(cme, size=2_000, price_bp=21_729, role="taker", tick_size_micro=250_000,
                     point_value_micro=50_000_000) == 506
    assert fee_cents(FEE_SCHEDULES["demo-zero"], size=100, price_bp=5_000, role="taker") == 0
    equity = FEE_SCHEDULES["xnas-zero-2026-09"]
    assert fee_cents(equity, size=1_000, price_bp=19_000, role="taker", tick_size_micro=10_000,
                     point_value_micro=1_000_000) == 0
    assert equity.min_half_spread_ticks == 1


def test_a_sale_fee_is_charged_on_sells_only() -> None:
    """17.4: ``sale_bp`` rides on top of the side's rate, and only when the agent sells."""
    schedule = replace(FEE_SCHEDULES["xnas-zero-2026-09"], sale_bp=1)
    buy = fee_cents(schedule, size=1_000, price_bp=19_000, role="taker", side="buy",
                    tick_size_micro=10_000, point_value_micro=1_000_000)
    sell = fee_cents(schedule, size=1_000, price_bp=19_000, role="taker", side="sell",
                     tick_size_micro=10_000, point_value_micro=1_000_000)
    assert buy == 0
    assert sell == 2  # one basis point of 19 000 cents of notional, rounded up


def test_the_worked_notional_table_of_17_1() -> None:
    """Every row of 17.1's worked table, in the units the contract prints."""
    assert (cash_out_cents(40_000, 6_327, 100, 1_000_000), cash_in_cents(40_000, 6_327, 100, 1_000_000)) == (
        2_531, 2_530,
    )
    assert (cash_out_cents(1, 6_341_257, 10_000, 1_000_000), cash_in_cents(1, 6_341_257, 10_000, 1_000_000)) == (
        6_342, 6_341,
    )
    assert cash_out_cents(2_000, 21_729, 250_000, 50_000_000) == 54_322_500
    assert cash_in_cents(2_000, 21_729, 250_000, 50_000_000) == 54_322_500
    assert cash_out_cents(100_000_000, 108_325, 10, 1_000_000) == 10_832_500
    assert notional_micro(1, 6_341_257, 10_000, 1_000_000) == 63_412_570_000_000_000


@settings(max_examples=400, deadline=None)
@given(size=st.integers(min_value=1, max_value=10**6), price_bp=st.integers(min_value=1, max_value=9_999))
def test_the_binary_identity_holds_over_the_whole_range(size: int, price_bp: int) -> None:
    """Ruling R145: no bp price already written changes value under the generalised conversions."""
    assert cost_cents(size, price_bp) == cash_out_cents(size * MILLI, price_bp, 100, 1_000_000)
    assert proceeds_cents(size, price_bp) == cash_in_cents(size * MILLI, price_bp, 100, 1_000_000)
    assert proceeds_cents(size, price_bp) <= cost_cents(size, price_bp)


def test_the_binary_payout_is_the_settlement_of_8_7() -> None:
    """17.1: ``cash_in_cents(size * MILLI, SETTLE_YES_BP, 100, 1_000_000)`` is ``position * 100``."""
    for size in (1, 7, 40, 1_000):
        assert cash_in_cents(size * MILLI, BP_ONE, 100, 1_000_000) == size * 100


def test_a_mark_floors_a_long_and_ceils_a_short() -> None:
    """8.7 and 17.1: the conservative side in both directions, so equity never flatters a short."""
    assert mark_value_cents(1, 6_341_257, 10_000, 1_000_000) == 6_341
    assert mark_value_cents(-1, 6_341_257, 10_000, 1_000_000) == -6_342
    assert mark_value_cents(0, 6_341_257, 10_000, 1_000_000) == 0


def test_a_split_rounds_half_up_and_keeps_the_sign() -> None:
    """17.3: a 4-for-1 on a long, a 1-for-10 reverse on a short, and no cash in lieu."""
    assert split_position_milli(2_000, 4, 1) == 8_000
    assert split_position_milli(-1_005, 1, 10) == -101
    with pytest.raises(InvalidConfigError):
        split_position_milli(100, 0, 1)


def test_every_shipped_schedule_carries_its_provenance() -> None:
    """8.8 and 17.4: a fee is a venue fact with a page and a date, not a tuned constant."""
    assert set(FEE_SCHEDULES) >= {
        "kalshi-general-2026-09", "kalshi-reduced-2026-09", "polymarket-zero-2026-09",
        "manifold-zero-2026-09", "demo-zero", "binance-spot-2026-09", "binance-perp-2026-09",
        "bybit-perp-2026-09", "kraken-spot-2026-09", "coinbase-spot-2026-09", "xnys-zero-2026-09",
        "xnas-zero-2026-09", "arcx-zero-2026-09", "cme-es-2026-09", "otcfx-spread-2026-09",
    }
    for schedule_id, schedule in FEE_SCHEDULES.items():
        assert schedule.schedule_id == schedule_id
        assert schedule.model in fees.FEE_MODELS
        assert schedule.kind in fees.INSTRUMENT_KINDS
        assert schedule.rounding == "ceil"
        if schedule_id != "demo-zero":
            assert schedule.as_of_date != ""
            assert schedule.source_url.startswith("https://")
    assert set(CARRY_SCHEDULES) == {
        "xnys-borrowgc-2026-09", "xnas-borrowgc-2026-09", "arcx-borrowgc-2026-09"
    }
    for row in CARRY_SCHEDULES.values():
        assert row.role == "borrow"
        assert row.rate_ppm_per_day > 0
        assert row.as_of_date != ""


def test_an_unknown_schedule_id_is_refused_rather_than_priced_at_zero() -> None:
    """A market whose ``fee_schedule_id`` names nothing is a build error, not a free trade."""
    with pytest.raises(InvalidConfigError):
        fees.fee_schedule("kalshi-nosuch-2026-09")
    with pytest.raises(InvalidConfigError):
        fees.carry_schedule("xnys-nosuch-2026-09")


def test_a_schedule_refuses_an_illegal_row() -> None:
    """A model, a kind, a rounding or a rate the contract does not allow fails at construction."""
    with pytest.raises(InvalidConfigError):
        FeeSchedule(schedule_id="kalshi-general-2026-09", provider="kalshi", model="quadratic")
    with pytest.raises(InvalidConfigError):
        FeeSchedule(schedule_id="kalshi-general-2026-09", provider="kalshi", kind="option")
    with pytest.raises(InvalidConfigError):
        FeeSchedule(schedule_id="kalshi-general-2026-09", provider="kalshi", rounding="floor")
    with pytest.raises(InvalidConfigError):
        FeeSchedule(schedule_id="not a schedule id", provider="kalshi")
    with pytest.raises(InvalidConfigError):
        FeeSchedule(schedule_id="kalshi-general-2026-09", provider="kalshi", taker_permille=-1)


# --------------------------------------------------------------------------------------------------
# 16.1 and 17.4: the envelope arithmetic
# --------------------------------------------------------------------------------------------------
def test_the_half_spread_estimator_is_pinned_and_flat_bars_estimate_zero() -> None:
    """17.4: the worked value, the trending pair, the flat pair, and the schedule floor."""
    schedule = FEE_SCHEDULES["binance-perp-2026-09"]
    previous = make_bar(T0, open_bp=6_330_000, high_bp=6_360_000, low_bp=6_300_000, close_bp=6_330_000)
    current = make_bar(T0 + DAY, open_bp=6_330_000, high_bp=6_350_000, low_bp=6_310_000, close_bp=6_330_000)
    assert half_spread_ticks(previous, current, schedule=schedule) == 14_619
    flat = make_bar(T0, open_bp=5_000)
    assert half_spread_ticks(flat, flat, schedule=schedule) == 0
    assert half_spread_ticks(flat, flat, schedule=FEE_SCHEDULES["otcfx-spread-2026-09"]) == 5
    trending = make_bar(T0 + DAY, open_bp=6_250, high_bp=6_400, low_bp=6_200, close_bp=6_350)
    before = make_bar(T0, open_bp=6_150, high_bp=6_300, low_bp=6_100, close_bp=6_250)
    assert half_spread_ticks(before, trending, schedule=FEE_SCHEDULES["kalshi-general-2026-09"]) >= 0


def test_the_cap_is_pro_rata_and_a_reconstructed_market_has_none() -> None:
    """8.6 step 2 and rule 2: 80 and 40 against a cap of 100 fill 66 and 33, whatever the order."""
    config = config_of(volume_cap_permille=100)
    bar = make_bar(T0, open_bp=5_000, volume_milli=1_000_000)
    assert cap_milli(bar, config=config, source="imported") == 100_000
    assert cap_milli(bar, config=config, source="reconstructed") == CAP_UNLIMITED
    assert cap_milli(make_bar(T0, open_bp=5_000), config=config, source="imported") == 0
    big = LiquidityOrder(side="buy", kind="market", size_milli=80)
    small = LiquidityOrder(side="buy", kind="market", size_milli=40)
    forward = allocate_cap([big, small], cap_milli=100)
    backward = allocate_cap([small, big], cap_milli=100)
    assert forward == (67, 33)
    assert sorted(forward) == sorted(backward)
    assert sum(forward) == 100
    assert allocate_cap([big, small], cap_milli=CAP_UNLIMITED) == (80, 40)
    assert allocate_cap([big, small], cap_milli=1_000) == (80, 40)
    assert allocate_cap([], cap_milli=100) == ()


def test_slippage_is_absolute_on_a_binary_and_relative_on_a_continuous_kind() -> None:
    """8.6 step 4, ruling R173: ten basis points of a 6 341 257 tick price is not ten ticks."""
    config = config_of(slippage_bp_per_pct=10)
    assert slippage_ticks(5_000, config=config, taken_pct=3, view=binary_view()) == 30
    relative = slippage_ticks(6_341_257, config=config, taken_pct=3, view=crypto_view())
    assert relative == round_half_up(6_341_257 * 10 * 3, BP_ONE)
    assert relative == 19_024
    assert slippage_ticks(5_000, config=config, taken_pct=0, view=binary_view()) == 0


def test_clamp_price_keeps_a_continuous_price_out_of_the_binary_range() -> None:
    """Ruling R173: a ``clamp_price_bp`` left on a continuous path would print 6 341 257 as 9 999."""
    assert clamp_price(6_341_257, view=binary_view()) == 9_999
    assert clamp_price(6_341_257, view=crypto_view()) == 6_341_257
    assert clamp_price(0, view=crypto_view()) == 1
    bar = make_bar(T0, open_bp=6_300_000, high_bp=6_400_000, low_bp=6_200_000)
    assert envelope_bounds(bar, kind="spot_crypto") == (6_200_000, 6_400_000)
    assert envelope_bounds(make_bar(T0, open_bp=5_000, high_bp=5_100, low_bp=4_900)) == (4_900, 5_100)


def test_truncate_for_cash_recomputes_the_fee_and_keeps_the_first_reason() -> None:
    """Ruling R130: rule 5 is stated over the fill the journal writes, not over an intermediate."""
    schedule = FEE_SCHEDULES["kalshi-general-2026-09"]
    bar = make_bar(T0, open_bp=5_000, volume_milli=1_000_000)
    order = LiquidityOrder(side="buy", kind="market", size_milli=100 * MILLI)
    whole = finalise_fill(quoted_bp=5_000, base_bp=5_000, order=order, bar=bar,
                          filled_milli=100 * MILLI, unfilled_reason="none", price_source="open",
                          schedule=schedule)
    assert whole.fee_cents == 175
    cut = truncate_for_cash(whole, max_filled_milli=40 * MILLI, schedule=schedule, order=order)
    assert cut.filled_milli == 40 * MILLI
    assert cut.fee_cents == fee_cents(schedule, size=40, price_bp=5_000, role="taker")
    assert cut.unfilled_reason == "cash"
    capped = finalise_fill(quoted_bp=5_000, base_bp=5_000, order=order, bar=bar, filled_milli=60 * MILLI,
                           unfilled_reason="volume_cap", price_source="open", schedule=schedule)
    then_cash = truncate_for_cash(capped, max_filled_milli=10 * MILLI, schedule=schedule, order=order)
    assert then_cash.unfilled_reason == "volume_cap"
    assert truncate_for_cash(whole, max_filled_milli=100 * MILLI, schedule=schedule, order=order) is whole


def test_finalise_fill_refuses_an_unfilled_remainder_with_no_reason() -> None:
    """A ``none`` beside a non-zero remainder is the ``bad_reason`` of the envelope, refused at source."""
    schedule = FEE_SCHEDULES["demo-zero"]
    bar = make_bar(T0, open_bp=5_000, volume_milli=1_000)
    order = LiquidityOrder(side="buy", kind="market", size_milli=10 * MILLI)
    with pytest.raises(InvalidConfigError):
        finalise_fill(quoted_bp=5_000, base_bp=5_000, order=order, bar=bar, filled_milli=1_000,
                      unfilled_reason="none", price_source="open", schedule=schedule)
    with pytest.raises(InvalidConfigError):
        finalise_fill(quoted_bp=5_000, base_bp=5_000, order=order, bar=bar, filled_milli=1_000,
                      unfilled_reason="cash", price_source="vwap", schedule=schedule)


def test_an_event_fill_is_the_printed_price_with_the_taker_fee() -> None:
    """17.3, ruling R152: no slippage, no model, ``price_source = "event"``, and the venue's fee."""
    schedule = FEE_SCHEDULES["binance-perp-2026-09"]
    order = LiquidityOrder(side="sell", kind="market", size_milli=2)
    fill = event_fill(order, price_ticks=6_341_257, schedule=schedule, market_view=crypto_view())
    assert (fill.price_bp, fill.base_price_bp, fill.slippage_bp) == (6_341_257, 6_341_257, 0)
    assert (fill.filled_milli, fill.unfilled_milli, fill.unfilled_reason) == (2, 0, "none")
    assert (fill.price_source, fill.role) == ("event", "taker")
    assert fill.fee_cents == fee_cents(schedule, size=2, price_bp=6_341_257, role="taker", side="sell",
                                       tick_size_micro=10_000, point_value_micro=1_000_000)


def test_make_liquidity_builds_historical_and_refuses_what_this_wave_lacks() -> None:
    """16.1 and ruling R139: every caller builds its own model, and only one exists in wave 2."""
    model = make_liquidity(config_of())
    assert (model.model_id, model.params_hash) == ("historical", "")
    with pytest.raises(InvalidConfigError):
        make_liquidity(config_of(), params={"impact_bp": 3})


# --------------------------------------------------------------------------------------------------
# 16.1: the historical model and the envelope check
# --------------------------------------------------------------------------------------------------
def test_historical_prices_a_market_order_at_the_quote_when_the_bar_carries_one() -> None:
    """8.6 step 3 and rule 1: a buy never fills below the ask, a sell never above the bid."""
    config = config_of(volume_cap_permille=1_000, slippage_bp_per_pct=0)
    model = HistoricalLiquidity(config)
    bar = make_bar(T0, open_bp=5_000, high_bp=5_200, low_bp=4_800, volume_milli=100_000,
                   bid_bp=4_950, ask_bp=5_050)
    buy = LiquidityOrder(side="buy", kind="market", size_milli=10 * MILLI)
    sell = LiquidityOrder(side="sell", kind="market", size_milli=10 * MILLI)
    fills = model.quote_bar(binary_view(), bar, (buy, sell), schedule=FEE_SCHEDULES["demo-zero"],
                            now_ms=T0)
    assert fills[0].price_bp == 5_050 and fills[0].price_source == "quote"
    assert fills[1].price_bp == 4_950 and fills[1].price_source == "quote"
    assert fills[0].role == "taker"


def test_historical_falls_back_to_the_open_and_charges_the_half_spread_floor() -> None:
    """8.6 step 3 as amended (ruling R156): a tape without quotes still pays the spread it implies."""
    config = config_of(volume_cap_permille=1_000, slippage_bp_per_pct=0)
    model = HistoricalLiquidity(config)
    schedule = FEE_SCHEDULES["otcfx-spread-2026-09"]
    view = crypto_view(kind="fx", fee_schedule_id=schedule.schedule_id)
    first = make_bar(T0, open_bp=108_325, high_bp=108_400, low_bp=108_200, volume_milli=100_000)
    second = make_bar(T0 + DAY, open_bp=108_325, high_bp=108_500, low_bp=108_100, volume_milli=100_000)
    buy = LiquidityOrder(side="buy", kind="market", size_milli=1_000)
    early = model.quote_bar(view, first, (buy,), schedule=schedule, now_ms=T0)
    assert early[0].price_source == "open"
    assert early[0].price_bp == 108_325 + schedule.min_half_spread_ticks
    later = model.quote_bar(view, second, (buy,), schedule=schedule, now_ms=T0 + DAY)
    assert later[0].price_bp >= 108_325 + schedule.min_half_spread_ticks


def test_a_flat_reconstructed_bar_prices_at_the_open_exactly_as_before_the_floor() -> None:
    """17.4: every bar of the demo pack is flat, so the estimator is zero and the base is the open."""
    config = config_of(volume_cap_permille=100, slippage_bp_per_pct=10)
    model = HistoricalLiquidity(config)
    view = binary_view(source="reconstructed", fee_schedule_id="demo-zero")
    first = make_bar(T0, open_bp=3_000)
    second = make_bar(T0 + DAY, open_bp=3_000)
    order = LiquidityOrder(side="buy", kind="market", size_milli=100 * MILLI)
    model.quote_bar(view, first, (order,), schedule=FEE_SCHEDULES["demo-zero"], now_ms=T0)
    fills = model.quote_bar(view, second, (order,), schedule=FEE_SCHEDULES["demo-zero"], now_ms=T0 + DAY)
    assert fills[0].price_bp == 3_000
    assert fills[0].slippage_bp == 0
    assert fills[0].filled_milli == 100 * MILLI


def test_a_zero_volume_bar_fills_nothing() -> None:
    """8.6 step 1: no volume, no fill, and the reason says which truncation fired first."""
    config = config_of()
    model = HistoricalLiquidity(config)
    bar = make_bar(T0, open_bp=5_000, high_bp=5_100, low_bp=4_900)
    market_order = LiquidityOrder(side="buy", kind="market", size_milli=10 * MILLI)
    resting = LiquidityOrder(side="buy", kind="limit", size_milli=10 * MILLI, limit_price_bp=4_950,
                             resting_since_ms=T0)
    fills = model.quote_bar(binary_view(), bar, (market_order, resting),
                            schedule=FEE_SCHEDULES["demo-zero"], now_ms=T0)
    assert [fill.filled_milli for fill in fills] == [0, 0]
    assert [fill.unfilled_reason for fill in fills] == ["zero_volume", "zero_volume"]
    assert all(fill.fee_cents == 0 for fill in fills)


def test_a_resting_limit_order_crosses_only_when_the_range_reaches_it() -> None:
    """8.6: a buy at ``L`` fills at ``min(L, open)`` iff ``low <= L``, else ``no_cross``."""
    config = config_of(volume_cap_permille=1_000)
    model = HistoricalLiquidity(config)
    bar = make_bar(T0, open_bp=5_000, high_bp=5_100, low_bp=4_900, volume_milli=100_000)
    crossing = LiquidityOrder(side="buy", kind="limit", size_milli=5 * MILLI, limit_price_bp=4_950,
                              resting_since_ms=T0)
    far = LiquidityOrder(side="buy", kind="limit", size_milli=5 * MILLI, limit_price_bp=4_800,
                         resting_since_ms=T0)
    above = LiquidityOrder(side="sell", kind="limit", size_milli=5 * MILLI, limit_price_bp=5_050,
                           resting_since_ms=T0)
    fills = model.quote_bar(binary_view(), bar, (crossing, far, above),
                            schedule=FEE_SCHEDULES["kalshi-general-2026-09"], now_ms=T0)
    assert fills[0].price_bp == 4_950 and fills[0].price_source == "limit" and fills[0].role == "maker"
    assert fills[0].slippage_bp == 0
    assert fills[1].filled_milli == 0 and fills[1].unfilled_reason == "no_cross"
    assert fills[2].price_bp == 5_050 and fills[2].filled_milli == 5 * MILLI


def test_the_shared_cap_is_split_across_market_and_limit_orders_of_one_bar() -> None:
    """8.6 step 2: the cap is per (market, bar) and market and resting orders share it."""
    config = config_of(volume_cap_permille=100, slippage_bp_per_pct=0)
    model = HistoricalLiquidity(config)
    bar = make_bar(T0, open_bp=5_000, high_bp=5_100, low_bp=4_900, volume_milli=100_000)
    first = LiquidityOrder(side="buy", kind="market", size_milli=8 * MILLI)
    second = LiquidityOrder(side="buy", kind="limit", size_milli=4 * MILLI, limit_price_bp=5_050,
                            resting_since_ms=T0)
    fills = model.quote_bar(binary_view(), bar, (first, second), schedule=FEE_SCHEDULES["demo-zero"],
                            now_ms=T0)
    assert sum(fill.filled_milli for fill in fills) <= cap_milli(bar, config=config, source="imported")
    assert fills[0].filled_milli == 6 * MILLI
    assert fills[0].unfilled_reason == "volume_cap"
    assert fills[1].filled_milli == 3 * MILLI


_BARS = st.builds(
    lambda low, span, offset, volume, spread: _bar_from(low, span, offset, volume, spread),
    low=st.integers(min_value=100, max_value=8_000),
    span=st.integers(min_value=0, max_value=1_500),
    offset=st.integers(min_value=0, max_value=100),
    volume=st.integers(min_value=0, max_value=500_000),
    spread=st.one_of(st.none(), st.integers(min_value=0, max_value=200)),
)


def _bar_from(low: int, span: int, offset: int, volume: int, spread: int | None) -> Bar:
    """A generated binary bar: a legal range, a possibly zero volume, and quotes half the time."""
    high = min(9_999, low + span)
    open_bp = min(high, low + (span * offset) // 100)
    close = min(high, max(low, open_bp))
    bid = None if spread is None else max(1, open_bp - spread)
    ask = None if spread is None else min(9_999, open_bp + spread)
    return make_bar(T0, open_bp=open_bp, high_bp=high, low_bp=low, close_bp=close, vwap_bp=open_bp,
                    volume_milli=volume, bid_bp=bid, ask_bp=ask)


_CRYPTO_BARS = st.builds(
    lambda low, span, offset, volume: _crypto_bar_from(low, span, offset, volume),
    low=st.integers(min_value=6_000_000, max_value=6_500_000),
    span=st.integers(min_value=0, max_value=50_000),
    offset=st.integers(min_value=0, max_value=100),
    volume=st.integers(min_value=0, max_value=20_000),
)


def _crypto_bar_from(low: int, span: int, offset: int, volume: int) -> Bar:
    """A generated continuous bar, in ticks of a hundredth of a quote unit, with no quote at all."""
    high = low + span
    open_bp = low + (span * offset) // 100
    return make_bar(T0, open_bp=open_bp, high_bp=high, low_bp=low, close_bp=open_bp, vwap_bp=open_bp,
                    volume_milli=volume)


_ORDERS = st.lists(
    st.builds(
        lambda side, kind, size, limit: LiquidityOrder(
            side=side,
            kind=kind,
            size_milli=size,
            limit_price_bp=limit if kind == "limit" else None,
            resting_since_ms=T0 if kind == "limit" else None,
        ),
        side=st.sampled_from(["buy", "sell"]),
        kind=st.sampled_from(["market", "limit"]),
        size=st.integers(min_value=1, max_value=40).map(lambda size: size * MILLI),
        limit=st.integers(min_value=1, max_value=9_999),
    ),
    min_size=1,
    max_size=4,
)

_CRYPTO_ORDERS = st.lists(
    st.builds(
        lambda side, kind, size, limit: LiquidityOrder(
            side=side,
            kind=kind,
            size_milli=size,
            limit_price_bp=limit if kind == "limit" else None,
            resting_since_ms=T0 if kind == "limit" else None,
        ),
        side=st.sampled_from(["buy", "sell"]),
        kind=st.sampled_from(["market", "limit"]),
        size=st.integers(min_value=1, max_value=3_000),
        limit=st.integers(min_value=6_000_000, max_value=6_500_000),
    ),
    min_size=1,
    max_size=4,
)


@settings(max_examples=250, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(bar=_BARS, orders=_ORDERS, permille=st.integers(min_value=0, max_value=1_000))
def test_check_envelope_reports_no_breach_for_historical_on_a_binary(
    bar: Bar, orders: list[LiquidityOrder], permille: int
) -> None:
    """16.1: the function every implementation must pass, driven on the binary view."""
    config = config_of(volume_cap_permille=permille)
    schedule = FEE_SCHEDULES["kalshi-general-2026-09"]
    breaches = check_envelope(HistoricalLiquidity(config), market_view=binary_view(), bar=bar,
                              orders=orders, config=config, schedule=schedule)
    assert breaches == ()


@settings(max_examples=250, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(bar=_CRYPTO_BARS, orders=_CRYPTO_ORDERS, permille=st.integers(min_value=0, max_value=1_000))
def test_check_envelope_reports_no_breach_for_historical_on_a_continuous_kind(
    bar: Bar, orders: list[LiquidityOrder], permille: int
) -> None:
    """Ruling R173: a ``clamp_price_bp``, a ``// MILLI`` or an absolute slippage would fail here."""
    config = config_of(volume_cap_permille=permille, slippage_bp_per_pct=10)
    schedule = FEE_SCHEDULES["binance-perp-2026-09"]
    breaches = check_envelope(HistoricalLiquidity(config), market_view=crypto_view(), bar=bar,
                              orders=orders, config=config, schedule=schedule)
    assert breaches == ()


class _ArrivalModel:
    """A model that consumes the shared cap first come first served: envelope rule 4's counter-example."""

    model_id = "historical"
    params_hash = ""

    def __init__(self, config: RunConfig) -> None:
        self._config = config

    def quote_bar(self, market_view: LiquidityMarketView, bar: Bar, orders: Sequence[LiquidityOrder], *,
                  schedule: FeeSchedule, now_ms: int) -> tuple[Fill, ...]:
        del now_ms
        left = cap_milli(bar, config=self._config, source=market_view.source)
        fills: list[Fill] = []
        for order in orders:
            take = min(order.size_milli, max(0, left))
            left -= take
            fills.append(
                finalise_fill(quoted_bp=bar.high_bp, base_bp=bar.high_bp, order=order, bar=bar,
                              filled_milli=take, unfilled_reason="volume_cap", price_source="open",
                              schedule=schedule, market_view=market_view)
            )
        return tuple(fills)

    def on_bar_end(self, observed_flow: ObservedFlow) -> None:
        del observed_flow


class _FreeLunchModel:
    """A model that discounts the fee and prints above the bar: envelope rules 3 and 5's counter-example."""

    model_id = "historical"
    params_hash = ""

    def quote_bar(self, market_view: LiquidityMarketView, bar: Bar, orders: Sequence[LiquidityOrder], *,
                  schedule: FeeSchedule, now_ms: int) -> tuple[Fill, ...]:
        del schedule, now_ms, market_view
        return tuple(
            Fill(
                price_bp=bar.high_bp + 1,
                base_price_bp=bar.high_bp + 1,
                slippage_bp=0,
                filled_milli=order.size_milli,
                unfilled_milli=0,
                unfilled_reason="none",
                price_source="open",
                role="taker",
                fee_cents=0,
            )
            for order in orders
        )

    def on_bar_end(self, observed_flow: ObservedFlow) -> None:
        del observed_flow


def test_check_envelope_catches_arrival_rationing_and_a_free_lunch() -> None:
    """16.1: the check is executable, so a model that breaks a rule is named, not trusted."""
    config = config_of(volume_cap_permille=100)
    schedule = FEE_SCHEDULES["kalshi-general-2026-09"]
    bar = make_bar(T0, open_bp=5_000, high_bp=5_100, low_bp=4_900, volume_milli=100_000)
    orders = [
        LiquidityOrder(side="buy", kind="market", size_milli=8 * MILLI),
        LiquidityOrder(side="buy", kind="market", size_milli=4 * MILLI),
    ]
    arrival = check_envelope(_ArrivalModel(config), market_view=binary_view(), bar=bar, orders=orders,
                             config=config, schedule=schedule)
    assert "order_dependent" in arrival
    lunch = check_envelope(_FreeLunchModel(), market_view=binary_view(), bar=bar, orders=orders,
                           config=config, schedule=schedule)
    assert "outside_range" in lunch
    assert "bad_fee" in lunch
    assert "over_cap" in lunch
    assert set(lunch) <= set(ENVELOPE_BREACHES)


# --------------------------------------------------------------------------------------------------
# 8.9: the accounting invariant, rebuilt from the journal alone
# --------------------------------------------------------------------------------------------------
def assert_accounting(
    execution: Execution,
    log: Journal,
    *,
    bankroll: int,
    settlements: Mapping[str, int] | None = None,
    settled: Sequence[str] = (),
) -> None:
    """Every line of 8.9 and 17.3, recomputed over the journal and compared to execution's own state.

    ``settlements`` carries the ``settlement_applied.cash_delta_cents`` the **runner** would have
    journaled from what :meth:`Execution.settle` returned, because execution never writes that event.
    """
    paid: dict[str, int] = {}
    reserved: dict[str, int] = {}
    position: dict[tuple[str, str], int] = {}
    records: tuple[Any, ...] = log.events
    for event in records:
        kind = event.TYPE
        if kind == "order_placed":
            reserved[event.agent_id] = reserved.get(event.agent_id, 0) + event.reserved_cents
        elif kind == "order_expired":
            reserved[event.agent_id] = reserved.get(event.agent_id, 0) - event.released_cents
        elif kind == "filled":
            paid[event.agent_id] = paid.get(event.agent_id, 0) + event.cash_delta_cents
            reserved[event.agent_id] = reserved.get(event.agent_id, 0) - event.released_cents
            signed = event.filled_size if event.side == "buy" else -event.filled_size
            key = (event.agent_id, event.market_id)
            assert event.position_after - event.position_before == signed
            assert position.get(key, 0) == event.position_before
            position[key] = event.position_after
            assert event.filled_size + event.unfilled_size == event.requested_size
            assert event.filled_size >= 0 and event.unfilled_size >= 0
            assert (event.unfilled_reason == "none") == (event.unfilled_size == 0)
        elif kind == "fee_charged":
            paid[event.agent_id] = paid.get(event.agent_id, 0) - event.fee_cents
            assert event.fee_cents >= 0
        elif kind == "cash_event_applied":
            paid[event.agent_id] = paid.get(event.agent_id, 0) + event.cash_delta_cents
            key = (event.agent_id, event.market_id)
            if event.kind in ("funding", "dividend", "borrow_fee", "carry"):
                assert event.position_after == event.position_before
            if event.kind in ("split", "roll", "forced_flat"):
                assert event.cash_delta_cents == 0
            position[key] = event.position_after
    for agent_id, delta in (settlements or {}).items():
        paid[agent_id] = paid.get(agent_id, 0) + delta
    for agent_id in execution.agent_ids():
        portfolio = execution.portfolio(agent_id)
        assert portfolio.cash_cents == bankroll + paid.get(agent_id, 0)
        assert portfolio.reserved_cents == reserved.get(agent_id, 0)
        assert portfolio.reserved_cents >= 0
        assert portfolio.reserved_cents <= max(0, portfolio.cash_cents)
        if portfolio.cash_cents < 0:
            assert portfolio.reserved_cents == 0
    for (agent_id, market_id), expected in position.items():
        wanted = 0 if market_id in settled else expected
        assert execution.position(agent_id, market_id).position == wanted


# --------------------------------------------------------------------------------------------------
# 8.5 to 8.7 on a binary: latency, netting, limits, settlement, ruin
# --------------------------------------------------------------------------------------------------
def binary_fixture(
    *,
    volume_milli: int = 100_000,
    price_bp: int = 5_000,
    n_bars: int = 5,
    source: str = "imported",
    fee_schedule_id: str = "kalshi-general-2026-09",
    resolution: int = 1,
) -> Market:
    """A five-bar binary whose close and resolution share the last bar (the Kalshi normal case)."""
    bars = [
        make_bar(T0 + index * DAY, open_bp=price_bp, high_bp=price_bp, low_bp=price_bp,
                 close_bp=price_bp, volume_milli=volume_milli)
        for index in range(n_bars)
    ]
    return make_market(
        bars=bars,
        close_at_ms=T0 + (n_bars - 1) * DAY,
        resolved_at_ms=T0 + (n_bars - 1) * DAY,
        resolution=resolution,
        source=source,
        fee_schedule_id=fee_schedule_id,
    )


def test_place_queues_and_reserves_nothing() -> None:
    """Ruling R110: the decide phase moves no cent, emits no event and earmarks no cash."""
    market = binary_fixture()
    execution, log = execution_of()
    execution.place(agent_id="alpha", market=market, action=MarketAction(
        market_id=market.id, prob_ppm=600_000, kind="target", target_position=10), item_index=0, t_ms=T0)
    assert [event.TYPE for event in log.events] == ["run_started"]
    assert execution.portfolio("alpha").cash_cents == 100_000
    assert execution.portfolio("alpha").reserved_cents == 0
    assert execution.pending_market_ids(t_ms=T0) == ()
    assert execution.pending_market_ids(t_ms=T0 + DAY) == (market.id,)


def test_a_market_order_fills_at_the_next_bars_open_and_never_on_the_decided_bar() -> None:
    """16.2: an action decided at ``t`` executes at the open of ``t + interval``, carrying ``t``."""
    market = binary_fixture()
    execution, log = execution_of(validate=True)
    action = MarketAction(market_id=market.id, prob_ppm=600_000, kind="target", target_position=10)
    execution.place(agent_id="alpha", market=market, action=action, item_index=3, t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    placed = events_of(log, "order_placed")
    filled = events_of(log, "filled")
    charged = events_of(log, "fee_charged")
    assert len(placed) == len(filled) == len(charged) == 1
    assert placed[0].bar_ms == T0 + DAY
    assert placed[0].decided_at_ms == T0
    assert placed[0].order_id == "o-00000001"
    assert placed[0].reserved_cents == 0
    assert filled[0].bar_ms == T0 + DAY
    assert filled[0].fill_price_bp == 5_000
    assert filled[0].base_price_bp == 5_000
    assert filled[0].slippage_bp == 0
    assert filled[0].price_source == "open"
    assert filled[0].filled_size == 10
    assert filled[0].close_size == 0 and filled[0].open_size == 10
    assert filled[0].cash_delta_cents == -cost_cents(10, 5_000)
    assert filled[0].position_after == 10
    assert filled[0].avg_cost_bp_after == 5_000
    assert charged[0].fee_cents == fee_cents(FEE_SCHEDULES["kalshi-general-2026-09"], size=10,
                                             price_bp=5_000, role="taker")
    assert all(event.bar_ms != T0 for event in log.events)
    assert execution.portfolio("alpha").cash_cents == 100_000 - 500 - 18
    assert_accounting(execution, log, bankroll=100_000)


def test_no_fill_exists_at_the_close_or_the_settling_bar() -> None:
    """Ruling R9 and 16.2: the action decided on the last tradable bar has nowhere to fill."""
    market = binary_fixture()
    settling = bar_of(market.resolved_at_ms, market.interval_min)
    execution, log = execution_of()
    action = MarketAction(market_id=market.id, prob_ppm=600_000, kind="target", target_position=5)
    execution.place(agent_id="alpha", market=market, action=action, item_index=0, t_ms=settling - DAY)
    assert execution.pending_market_ids(t_ms=settling) == (market.id,)
    execution.execute_bar(t_ms=settling, market=market)
    rejected = events_of(log, "order_rejected")
    assert len(rejected) == 1
    assert rejected[0].reason == "not_tradable"
    assert rejected[0].decided_at_ms == settling - DAY
    assert rejected[0].bar_ms == settling
    assert events_of(log, "order_placed") == ()
    assert events_of(log, "filled") == ()
    assert execution.position("alpha", market.id).position == 0


def test_a_target_that_equals_the_position_produces_no_order_at_all() -> None:
    """8.4: never a size-zero order, and a repeated target is a no-op once the fill has landed."""
    market = binary_fixture()
    execution, log = execution_of()
    action = MarketAction(market_id=market.id, prob_ppm=600_000, kind="target", target_position=10)
    execution.place(agent_id="alpha", market=market, action=action, item_index=0, t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    execution.place(agent_id="alpha", market=market, action=action, item_index=0, t_ms=T0 + DAY)
    execution.execute_bar(t_ms=T0 + 2 * DAY, market=market)
    assert len(events_of(log, "order_placed")) == 1
    assert len(events_of(log, "filled")) == 1
    hold = MarketAction(market_id=market.id, prob_ppm=600_000, kind="hold")
    execution.place(agent_id="alpha", market=market, action=hold, item_index=1, t_ms=T0 + 2 * DAY)
    assert execution.pending_market_ids(t_ms=T0 + 3 * DAY) == ()


def test_abstain_closes_the_position_and_a_flat_abstain_produces_nothing() -> None:
    """8.4: abstention is a strategy, and closing is a market order queued like any other."""
    market = binary_fixture()
    execution, log = execution_of()
    execution.place(agent_id="alpha", market=market, action=MarketAction(
        market_id=market.id, prob_ppm=600_000, kind="target", target_position=10), item_index=0, t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    abstain = MarketAction(market_id=market.id, prob_ppm=500_000, kind="abstain")
    execution.place(agent_id="alpha", market=market, action=abstain, item_index=0, t_ms=T0 + DAY)
    execution.execute_bar(t_ms=T0 + 2 * DAY, market=market)
    closing = events_of(log, "filled")[1]
    assert closing.side == "sell"
    assert closing.close_size == 10 and closing.open_size == 0
    assert closing.fill_price_bp == 5_000
    assert closing.cash_delta_cents == proceeds_cents(10, 5_000)
    assert closing.position_after == 0
    assert closing.avg_cost_bp_after == 0
    assert events_of(log, "order_placed")[1].origin == "abstain"
    execution.place(agent_id="alpha", market=market, action=abstain, item_index=0, t_ms=T0 + 2 * DAY)
    execution.execute_bar(t_ms=T0 + 3 * DAY, market=market)
    assert len(events_of(log, "filled")) == 2
    assert_accounting(execution, log, bankroll=100_000)


def test_a_no_leg_pays_up_front_and_settles_at_the_mirror() -> None:
    """8.5 and 1.4: holding 40 NO is ``position = -40``, opened at ``cost_cents(40, 10_000 - p)``."""
    market = binary_fixture(price_bp=6_327, resolution=0, fee_schedule_id="demo-zero")
    execution, log = execution_of(config=config_of(volume_cap_permille=1_000))
    execution.place(agent_id="alpha", market=market, action=MarketAction(
        market_id=market.id, prob_ppm=300_000, kind="target", target_position=-40), item_index=0, t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    opened = events_of(log, "filled")[0]
    assert opened.cash_delta_cents == -cost_cents(40, BP_ONE - 6_327)
    assert opened.cash_delta_cents == -1_470
    assert opened.position_after == -40
    assert opened.avg_cost_bp_after == 6_327
    deltas = execution.settle(market=market)
    assert deltas == {"alpha": 40 * 100}
    assert execution.position("alpha", market.id).position == 0
    assert_accounting(execution, log, bankroll=100_000, settlements=deltas, settled=[market.id])


def test_a_fill_never_takes_cash_below_zero() -> None:
    """8.5: the opening part is truncated against free cash and the reason is ``cash``."""
    market = binary_fixture(volume_milli=100_000_000, fee_schedule_id="demo-zero")
    execution, log = execution_of(config=config_of(volume_cap_permille=1_000, slippage_bp_per_pct=0,
                                                   bankroll_cents=5_000))
    execution.place(agent_id="alpha", market=market, action=MarketAction(
        market_id=market.id, prob_ppm=900_000, kind="target", target_position=1_000), item_index=0,
        t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    fill = events_of(log, "filled")[0]
    assert fill.filled_size == 100
    assert fill.unfilled_size == 900
    assert fill.unfilled_reason == "cash"
    assert execution.portfolio("alpha").cash_cents == 0
    assert_accounting(execution, log, bankroll=5_000)


def test_a_limit_order_reserves_its_worst_case_and_releases_on_the_fill() -> None:
    """8.5 and 8.6: the reservation is the opening cost of the full size at the limit price."""
    bars = [make_bar(T0 + index * DAY, open_bp=5_000, high_bp=5_100, low_bp=4_900, close_bp=5_000,
                     volume_milli=100_000) for index in range(5)]
    market = make_market(bars=bars, close_at_ms=T0 + 4 * DAY, resolved_at_ms=T0 + 4 * DAY,
                         fee_schedule_id="demo-zero")
    execution, log = execution_of(config=config_of(volume_cap_permille=1_000, slippage_bp_per_pct=0))
    action = MarketAction(market_id=market.id, prob_ppm=600_000, kind="limit", side="buy",
                          price_bp=4_950, size=20, ttl_bars=2)
    execution.place(agent_id="alpha", market=market, action=action, item_index=0, t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    placed = events_of(log, "order_placed")[0]
    filled = events_of(log, "filled")[0]
    assert placed.kind == "limit"
    assert placed.reserved_cents == cost_cents(20, 4_950)
    assert placed.expires_at_ms == T0 + DAY + 2 * DAY
    assert filled.price_source == "limit"
    assert filled.fill_price_bp == 4_950
    assert filled.slippage_bp == 0
    assert filled.base_price_bp == 4_950
    assert filled.released_cents == cost_cents(20, 4_950)
    assert filled.filled_size == 20
    assert execution.portfolio("alpha").reserved_cents == 0
    assert events_of(log, "fee_charged")[0].role == "maker"
    assert_accounting(execution, log, bankroll=100_000)


def test_a_resting_remainder_stays_on_the_book_and_expires_on_its_ttl() -> None:
    """8.6: an unfilled remainder rests until ``ttl_bars`` have passed, counted from the drain bar."""
    bars = [
        make_bar(T0 + index * DAY, open_bp=5_000, high_bp=5_000, low_bp=5_000, volume_milli=10_000)
        for index in range(4)
    ]
    market = make_market(bars=bars, close_at_ms=T0 + 3 * DAY, resolved_at_ms=T0 + 3 * DAY,
                         fee_schedule_id="demo-zero")
    execution, log = execution_of(config=config_of(volume_cap_permille=100, slippage_bp_per_pct=0))
    action = MarketAction(market_id=market.id, prob_ppm=600_000, kind="limit", side="buy",
                          price_bp=4_900, size=5, ttl_bars=1)
    execution.place(agent_id="alpha", market=market, action=action, item_index=0, t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    resting = execution.position("alpha", market.id).open_orders
    assert len(resting) == 1
    assert resting[0].remaining_size == 5
    assert events_of(log, "filled")[0].unfilled_reason == "no_cross"
    assert execution.portfolio("alpha").reserved_cents == cost_cents(5, 4_900)
    execution.expire_orders(t_ms=T0 + 2 * DAY, markets=[market])
    expired = events_of(log, "order_expired")
    assert len(expired) == 1
    assert expired[0].reason == "ttl"
    assert expired[0].released_cents == cost_cents(5, 4_900)
    assert expired[0].phase == "open"
    assert execution.portfolio("alpha").reserved_cents == 0
    assert_accounting(execution, log, bankroll=100_000)


def test_a_limit_order_that_cannot_fund_its_reservation_is_refused() -> None:
    """The invariant keeps ``reserved <= max(0, cash)``, so an unfundable reservation never happens."""
    market = binary_fixture(fee_schedule_id="demo-zero")
    execution, log = execution_of(config=config_of(bankroll_cents=100))
    action = MarketAction(market_id=market.id, prob_ppm=600_000, kind="limit", side="buy",
                          price_bp=5_000, size=100, ttl_bars=3)
    execution.place(agent_id="alpha", market=market, action=action, item_index=0, t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    rejected = events_of(log, "order_rejected")
    assert len(rejected) == 1
    assert rejected[0].reason == "insufficient_cash"
    assert events_of(log, "order_placed") == ()


def test_a_limit_action_missing_a_field_is_rejected_at_the_execution_bar() -> None:
    """8.6 step 0: the rejection carries ``decided_at_ms``, so it traces to the intent that caused it."""
    market = binary_fixture()
    execution, log = execution_of()
    actions = (
        MarketAction(market_id=market.id, prob_ppm=1, kind="limit", side=None, price_bp=5_000, size=1,
                     ttl_bars=1),
        MarketAction(market_id=market.id, prob_ppm=1, kind="limit", side="buy", price_bp=None, size=1,
                     ttl_bars=1),
        MarketAction(market_id=market.id, prob_ppm=1, kind="limit", side="buy", price_bp=5_000, size=0,
                     ttl_bars=1),
        MarketAction(market_id=market.id, prob_ppm=1, kind="limit", side="buy", price_bp=5_000, size=1,
                     ttl_bars=None),
        MarketAction(market_id=market.id, prob_ppm=1, kind="target", target_position=None),
    )
    for index, action in enumerate(actions):
        execution.place(agent_id="alpha", market=market, action=action, item_index=index, t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    reasons = [event.reason for event in events_of(log, "order_rejected")]
    assert reasons == ["missing_field", "bad_price", "bad_size", "bad_ttl", "missing_field"]
    assert events_of(log, "order_placed") == ()


def test_an_order_over_the_notional_cap_is_rejected_as_bad_size() -> None:
    """Ruling R196: the notional cap is checked once, at the execute phase, where the price is known."""
    market = binary_fixture()
    execution, log = execution_of()
    action = MarketAction(market_id=market.id, prob_ppm=600_000, kind="target", target_position=10**14)
    execution.place(agent_id="alpha", market=market, action=action, item_index=0, t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    assert [event.reason for event in events_of(log, "order_rejected")] == ["bad_size"]


def test_a_ruined_agents_queued_intent_is_rejected_at_its_execution_bar() -> None:
    """16.2: the ruin itself is the close phase of the deciding bar; the rejection is the next bar."""
    market = binary_fixture(fee_schedule_id="demo-zero")
    execution, log = execution_of(config=config_of(bankroll_cents=1_500, ruin_floor_cents=2_000))
    execution.register_agent("alpha")
    action = MarketAction(market_id=market.id, prob_ppm=600_000, kind="target", target_position=1)
    execution.place(agent_id="alpha", market=market, action=action, item_index=0, t_ms=T0)
    execution.mark(t_ms=T0, markets=[market])
    assert execution.is_ruined("alpha")
    assert execution.ruined_agent_ids() == ("alpha",)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    assert [event.reason for event in events_of(log, "order_rejected")] == ["ruined"]


def test_settlement_pays_both_legs_and_expires_every_resting_order() -> None:
    """8.7: a YES leg is paid ``position * 100``, a NO leg the mirror, and the book is cleared."""
    market = binary_fixture(price_bp=4_000, fee_schedule_id="demo-zero")
    settling = bar_of(market.resolved_at_ms, market.interval_min)
    execution, log = execution_of(config=config_of(volume_cap_permille=1_000, slippage_bp_per_pct=0))
    for agent_id, target in (("alpha", 20), ("beta", -20)):
        execution.place(agent_id=agent_id, market=market, action=MarketAction(
            market_id=market.id, prob_ppm=400_000, kind="target", target_position=target),
            item_index=0, t_ms=T0)
    execution.place(agent_id="alpha", market=market, action=MarketAction(
        market_id=market.id, prob_ppm=400_000, kind="limit", side="buy", price_bp=1_000, size=1,
        ttl_bars=10), item_index=1, t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    deltas = execution.settle(market=market)
    assert deltas == {"alpha": 2_000, "beta": 0}
    expired = events_of(log, "order_expired")
    assert [event.reason for event in expired] == ["settled"]
    assert expired[0].bar_ms == settling
    assert expired[0].phase == "settle"
    assert execution.portfolio("alpha").reserved_cents == 0
    assert_accounting(execution, log, bankroll=100_000, settlements=deltas, settled=[market.id])


def test_marking_uses_the_bar_close_and_ruin_freezes_the_agent() -> None:
    """8.7: the mark is the close of bar ``t`` itself, and equity at or under the floor freezes."""
    bars = [
        make_bar(T0, open_bp=5_000, close_bp=5_000, volume_milli=1_000_000),
        make_bar(T0 + DAY, open_bp=5_000, close_bp=200, low_bp=200, high_bp=5_000,
                 volume_milli=1_000_000),
        make_bar(T0 + 2 * DAY, open_bp=200, close_bp=100, low_bp=100, high_bp=200,
                 volume_milli=1_000_000),
    ]
    market = make_market(bars=bars, close_at_ms=T0 + 2 * DAY, resolved_at_ms=T0 + 2 * DAY,
                         fee_schedule_id="demo-zero")
    execution, log = execution_of(config=config_of(volume_cap_permille=1_000, slippage_bp_per_pct=0,
                                                   bankroll_cents=10_000, ruin_floor_cents=1_000))
    execution.place(agent_id="alpha", market=market, action=MarketAction(
        market_id=market.id, prob_ppm=900_000, kind="target", target_position=190), item_index=0, t_ms=T0)
    execution.place(agent_id="alpha", market=market, action=MarketAction(
        market_id=market.id, prob_ppm=900_000, kind="limit", side="buy", price_bp=100, size=1,
        ttl_bars=9), item_index=1, t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    assert execution.position("alpha", market.id).position == 190
    views = execution.mark(t_ms=T0 + DAY, markets=[market])
    view = views["alpha"]
    assert view.cash_cents == 10_000 - cost_cents(190, 5_000)
    assert view.equity_cents - view.cash_cents == 190 * 200 // 100
    assert view.equity_cents == 880
    assert view.peak_equity_cents == 10_000
    assert view.drawdown_bp < 0
    assert execution.is_ruined("alpha")
    ruined = execution.drain_ruined()
    assert len(ruined) == 1
    assert ruined[0][0] == "alpha"
    assert ruined[0][2] == ("o-00000002",)
    assert execution.drain_ruined() == ()
    assert [event.reason for event in events_of(log, "order_expired")] == ["ruined"]
    assert events_of(log, "order_expired")[0].phase == "close"
    assert_accounting(execution, log, bankroll=10_000)


def test_pending_market_ids_holds_a_market_that_settled_and_one_with_a_resting_order() -> None:
    """Ruling R131: the queue's own market set is the only correct enumeration for the drain."""
    market = binary_fixture()
    settling = bar_of(market.resolved_at_ms, market.interval_min)
    execution, _log = execution_of(config=config_of(volume_cap_permille=1_000))
    execution.place(agent_id="alpha", market=market, action=MarketAction(
        market_id=market.id, prob_ppm=600_000, kind="target", target_position=1), item_index=0,
        t_ms=settling - DAY)
    assert execution.pending_market_ids(t_ms=settling) == (market.id,)
    execution.place(agent_id="alpha", market=market, action=MarketAction(
        market_id=market.id, prob_ppm=600_000, kind="limit", side="buy", price_bp=100, size=1,
        ttl_bars=5), item_index=1, t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    assert execution.pending_market_ids(t_ms=T0 + 2 * DAY) == (market.id,)


# --------------------------------------------------------------------------------------------------
# 17.1 to 17.3 on a continuous instrument: shorts, marking, the forced flat
# --------------------------------------------------------------------------------------------------
def continuous_config(*, n_bars: int = 4, **extra: object) -> RunConfig:
    """A config whose ``t1_ms`` makes the tape's last bar ``last_bar(i)``, which is where 17.3 flattens."""
    values: dict[str, object] = {
        "t1_ms": T0 + n_bars * DAY,
        "volume_cap_permille": 1_000,
        "slippage_bp_per_pct": 0,
        "bankroll_cents": 100_000_000,
    }
    values.update(extra)
    return config_of(**values)


def drive_continuous(
    execution: Execution,
    instrument: Continuous,
    *,
    plan: Mapping[int, Sequence[tuple[str, MarketAction]]] | None = None,
    flat_at: int | None = None,
    stop_after: int | None = None,
) -> None:
    """Run the phase order of 8.2 over a continuous instrument's whole tape.

    Per bar: ``open`` expires, ``decide`` queues through :meth:`Execution.place`, ``execute`` drains the
    previous bar's queue, ``settle`` applies the cash events whose application bar is this one (and the
    forced flat at ``last_bar(i)``), and ``close`` marks. ``flat_at`` defaults to the tape's last bar,
    which is what ``t1_ms`` of :func:`continuous_config` makes ``last_bar(i)``.
    """
    grid = [bar.t_ms for bar in instrument.bars]
    last = grid[-1] if flat_at is None else flat_at
    for t_ms in grid:
        if stop_after is not None and t_ms > stop_after:
            return
        execution.expire_orders(t_ms=t_ms, markets=[instrument])
        for index, (agent_id, action) in enumerate((plan or {}).get(t_ms, ())):
            execution.place(agent_id=agent_id, market=instrument, action=action, item_index=index,
                            t_ms=t_ms)
        if instrument.id in execution.pending_market_ids(t_ms=t_ms):
            execution.execute_bar(t_ms=t_ms, market=instrument)
        execution.apply_cash_events(t_ms=t_ms, market=instrument)
        if t_ms == last:
            execution.force_flat(t_ms=t_ms, market=instrument)
        execution.mark(t_ms=t_ms, markets=[instrument])


def target(market_id: str, position: int, *, prob_ppm: int = 500_000) -> MarketAction:
    """A ``target`` action, whose ``target_position`` is milli-units on a continuous instrument."""
    return MarketAction(market_id=market_id, prob_ppm=prob_ppm, kind="target", target_position=position)


def test_a_continuous_long_pays_the_notional_and_the_notional_bp_fee() -> None:
    """17.1 and 17.4: ``cash_out_cents`` at the fill price, and 5 bp of the notional as the taker fee."""
    instrument = continuous_fixture()
    execution, log = execution_of(config=continuous_config())
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, 1_000))]},
                     stop_after=T0 + DAY)
    fill = events_of(log, "filled")[0]
    assert fill.filled_size == 1_000
    assert fill.fill_price_bp == 6_300_000
    assert fill.price_source == "open"
    assert fill.open_size == 1_000 and fill.close_size == 0
    assert fill.cash_delta_cents == -cash_out_cents(1_000, 6_300_000, 10_000, 1_000_000)
    assert fill.cash_delta_cents == -6_300_000
    assert fill.avg_cost_bp_after == 6_300_000
    fee = events_of(log, "fee_charged")[0]
    assert fee.fee_cents == 3_150
    assert fee.role == "taker"
    view = execution.portfolio("alpha")
    assert view.cash_cents == 100_000_000 - 6_300_000 - 3_150
    assert view.equity_cents == view.cash_cents + mark_value_cents(1_000, 6_300_000, 10_000, 1_000_000)
    assert_accounting(execution, log, bankroll=100_000_000)


def test_a_sell_beyond_the_long_opens_a_short_that_receives_cash() -> None:
    """Ruling R154: the NO leg is replaced by the liability model, and a short **receives** at the fill."""
    instrument = continuous_fixture(n_bars=5)
    execution, log = execution_of(config=continuous_config(n_bars=5))
    drive_continuous(
        execution,
        instrument,
        plan={T0: [("alpha", target(instrument.id, 1_000))],
              T0 + DAY: [("alpha", target(instrument.id, -500))]},
        stop_after=T0 + 2 * DAY,
    )
    closing = events_of(log, "filled")[1]
    assert closing.side == "sell"
    assert closing.requested_size == 1_500
    assert closing.close_size == 1_000 and closing.open_size == 500
    assert closing.position_before == 1_000 and closing.position_after == -500
    received = cash_in_cents(1_000, 6_300_000, 10_000, 1_000_000)
    received += cash_in_cents(500, 6_300_000, 10_000, 1_000_000)
    assert closing.cash_delta_cents == received
    assert closing.avg_cost_bp_after == 6_300_000
    assert execution.position("alpha", instrument.id).position == -500
    assert_accounting(execution, log, bankroll=100_000_000)


def test_the_opening_notional_of_a_short_may_not_exceed_free_cash() -> None:
    """Ruling R154: ``short_notional <= free_cash``, so a cover up to a doubling of the price is payable."""
    instrument = continuous_fixture()
    execution, log = execution_of(config=continuous_config(bankroll_cents=6_300_000))
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, -2_000))]},
                     stop_after=T0 + DAY)
    fill = events_of(log, "filled")[0]
    assert fill.filled_size == 1_000
    assert fill.unfilled_size == 1_000
    assert fill.unfilled_reason == "cash"
    assert cash_out_cents(1_000, 6_300_000, 10_000, 1_000_000) == 6_300_000
    assert execution.portfolio("alpha").cash_cents == 6_300_000 + 6_300_000 - 3_150
    assert_accounting(execution, log, bankroll=6_300_000)


def test_spot_crypto_forbids_a_short_and_a_sell_only_closes() -> None:
    """17.1: ``spot_crypto`` carries ``short_allowed = false``; its short is the ``perp`` twin."""
    instrument = continuous_fixture(kind="spot_crypto", short_allowed=False,
                                    fee_schedule_id="binance-spot-2026-09")
    execution, log = execution_of(config=continuous_config())
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, -500))]},
                     stop_after=T0 + DAY)
    assert [event.reason for event in events_of(log, "order_rejected")] == ["short_not_allowed"]
    assert events_of(log, "filled") == ()

    other = continuous_fixture(kind="spot_crypto", n_bars=5, short_allowed=False,
                               fee_schedule_id="binance-spot-2026-09")
    execution, log = execution_of(config=continuous_config(n_bars=5))
    drive_continuous(
        execution,
        other,
        plan={T0: [("alpha", target(other.id, 1_000))],
              T0 + DAY: [("alpha", target(other.id, -500))]},
        stop_after=T0 + 2 * DAY,
    )
    closing = events_of(log, "filled")[1]
    assert closing.requested_size == 1_000
    assert closing.close_size == 1_000 and closing.open_size == 0
    assert closing.position_after == 0
    assert_accounting(execution, log, bankroll=100_000_000)


def test_a_runaway_short_takes_equity_below_zero_and_ruin_stays_the_rule_on_equity() -> None:
    """Rulings R154 and R180: ``positions_value_cents`` is signed and equity may fall below zero."""
    instrument = continuous_fixture(n_bars=4, prices=[6_300_000, 6_300_000, 20_000_000, 20_000_000])
    execution, log = execution_of(config=continuous_config(bankroll_cents=6_300_000,
                                                           ruin_floor_cents=0))
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, -1_000))]},
                     stop_after=T0 + 2 * DAY)
    view = execution.portfolio("alpha")
    assert view.cash_cents == 6_300_000 + 6_300_000 - 3_150
    assert mark_value_cents(-1_000, 20_000_000, 10_000, 1_000_000) == -20_000_000
    assert view.equity_cents == view.cash_cents - 20_000_000
    assert view.equity_cents < 0
    assert execution.is_ruined("alpha")
    assert view.drawdown_bp < 0
    assert_accounting(execution, log, bankroll=6_300_000)


def test_the_forced_flat_closes_at_the_last_bars_close_as_a_fill_in_the_settle_phase() -> None:
    """Rulings R150 and R152: an event fill, never a mark, and the only settle-phase ``filled``."""
    instrument = continuous_fixture(n_bars=4, prices=[6_300_000, 6_300_000, 6_400_000, 6_500_000])
    execution, log = execution_of(config=continuous_config())
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, 1_000))]})
    placed = events_of(log, "order_placed")[-1]
    assert placed.origin == "forced_flat"
    assert placed.phase == "settle"
    closing = events_of(log, "filled")[-1]
    assert closing.phase == "settle"
    assert closing.price_source == "event"
    assert closing.slippage_bp == 0
    assert closing.fill_price_bp == 6_500_000
    assert closing.side == "sell"
    assert closing.filled_size == 1_000
    assert closing.position_after == 0
    assert closing.cash_delta_cents == cash_in_cents(1_000, 6_500_000, 10_000, 1_000_000)
    assert events_of(log, "fee_charged")[-1].role == "taker"
    applied = events_of(log, "cash_event_applied")[-1]
    assert applied.kind == "forced_flat"
    assert applied.origin == "engine"
    assert applied.cash_delta_cents == 0
    assert applied.position_before == 1_000 and applied.position_after == 0
    assert applied.order_ids == (closing.order_id,)
    assert applied.detail["reason"] == "window_end"
    assert applied.detail["price_ticks"] == 6_500_000
    assert execution.position("alpha", instrument.id).position == 0
    assert execution.portfolio("alpha").reserved_cents == 0
    assert_accounting(execution, log, bankroll=100_000_000)


def test_a_forced_flat_that_cash_cannot_pay_is_truncated_and_the_residual_is_journaled() -> None:
    """Rulings R154 and R198: the cover is truncated like any buy and the liability stays in equity."""
    instrument = continuous_fixture(n_bars=4, prices=[6_300_000, 6_300_000, 20_000_000, 20_000_000])
    execution, log = execution_of(config=continuous_config(bankroll_cents=6_300_000,
                                                           ruin_floor_cents=0))
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, -1_000))]})
    assert execution.is_ruined("alpha")
    closing = events_of(log, "filled")[-1]
    assert closing.side == "buy"
    assert closing.unfilled_reason == "cash"
    assert closing.filled_size == 629
    assert closing.unfilled_size == 371
    assert closing.position_before == -1_000 and closing.position_after == -371
    applied = events_of(log, "cash_event_applied")[-1]
    assert applied.kind == "forced_flat"
    assert applied.position_after == -371
    assert execution.position("alpha", instrument.id).position == -371
    view = execution.portfolio("alpha")
    assert view.equity_cents == view.cash_cents + mark_value_cents(-371, 20_000_000, 10_000, 1_000_000)
    assert view.cash_cents >= 0
    assert_accounting(execution, log, bankroll=6_300_000)


def test_settle_is_binary_only_and_the_forced_flat_is_continuous_only() -> None:
    """17.3: a binary settles and is never forced flat; a continuous instrument has nothing to ride to."""
    instrument = continuous_fixture()
    execution, _log = execution_of(config=continuous_config())
    with pytest.raises(InvalidConfigError):
        execution.settle(market=instrument)
    market = binary_fixture()
    with pytest.raises(InvalidConfigError):
        execution.force_flat(t_ms=T0, market=market)


def test_instrument_spec_reads_the_binary_row_of_the_17_1_table() -> None:
    """17.1: a ``Market`` satisfies the ``Instrument`` base through the mapping that section declares."""
    market = binary_fixture()
    spec = instrument_spec(market)
    assert spec.kind == "binary"
    assert spec.tick_size_micro == 100
    assert spec.point_value_micro == 1_000_000
    assert spec.session_calendar_id == "continuous"
    assert spec.borrow_schedule_id is None and spec.carry_schedule_id is None
    assert spec.listed_at_ms == market.created_at_ms
    assert spec.delisted_at_ms == market.resolved_at_ms
    assert spec.short_allowed is True
    assert spec.is_binary and spec.interval_ms == DAY
    assert instrument_spec(continuous_fixture()).kind == "perp"
    with pytest.raises(InvalidConfigError):
        instrument_spec(continuous_fixture(kind="commodity"))


# --------------------------------------------------------------------------------------------------
# 17.3: the seven cash event kinds, their entitlement rule and their ordering
# --------------------------------------------------------------------------------------------------
def _kind_fixture(defaults: Mapping[str, object], extra: Mapping[str, object]) -> Continuous:
    """One kind's fixture row, with the test's own overrides applied over the venue's defaults."""
    values = dict(defaults)
    values.update(extra)
    return continuous_fixture(**values)  # type: ignore[arg-type]


def equity_fixture(**extra: object) -> Continuous:
    """An equity at a cent tick: 1 000 milli-units is one share and 10 000 ticks is one hundred dollars."""
    return _kind_fixture(
        {
            "kind": "equity", "market_id": "xnas-aapl", "n_bars": 5, "price_ticks": 10_000,
            "tick_size_micro": 10_000, "point_value_micro": 1_000_000,
            "fee_schedule_id": "xnas-zero-2026-09", "provider": "xnas", "vendor": "yahoo",
            "symbol": "AAPL", "currency": "usd", "category": "finance",
        },
        extra,
    )


def future_fixture(**extra: object) -> Continuous:
    """An ES future: a quarter-point tick and a fifty dollar point value (17.1's table)."""
    return _kind_fixture(
        {
            "kind": "future", "market_id": "xcme-es", "n_bars": 5, "price_ticks": 21_729,
            "tick_size_micro": 250_000, "point_value_micro": 50_000_000,
            "fee_schedule_id": "cme-es-2026-09", "provider": "xcme", "vendor": "yahoo",
            "symbol": "ESZ6", "currency": "usd", "category": "finance",
        },
        extra,
    )


def fx_fixture(**extra: object) -> Continuous:
    """An fx pair at a tenth-of-a-pip tick, whose only carry is the ``carry`` event of 17.3."""
    return _kind_fixture(
        {
            "kind": "fx", "market_id": "otcfx-eurusd", "n_bars": 5, "price_ticks": 11_000,
            "tick_size_micro": 10_000, "point_value_micro": 1_000_000,
            "fee_schedule_id": "otcfx-spread-2026-09", "provider": "otcfx", "vendor": "ecb",
            "symbol": "EURUSD", "currency": "usd", "category": "finance",
        },
        extra,
    )


class DenseGrid:
    """A ``BarCalendar`` over a dense daily grid, which is all :func:`applies_at` reads (ruling R187).

    E1's ``Calendar`` is the run's implementation; this is the same three questions answered over one
    instrument, so the entitlement rule can be tested without a runner.
    """

    def __init__(self, *, first: int, last: int, step: int = DAY) -> None:
        self._first = first
        self._last = last
        self._step = step

    def last_bar(self, market_id: str) -> int:
        del market_id
        return self._last

    def next_bar(self, market_id: str, t_ms: int) -> int | None:
        del market_id
        return t_ms + self._step if t_ms + self._step <= self._last else None

    def prev_bar(self, market_id: str, t_ms: int) -> int | None:
        del market_id
        return t_ms - self._step if t_ms - self._step >= self._first else None


def test_applies_at_shifts_the_three_corporate_kinds_and_leaves_the_other_four() -> None:
    """Ruling R175: the old regime's last close for a corporate event, ``bar_of(t_ms)`` for a charge."""
    instrument = equity_fixture()
    grid = DenseGrid(first=T0, last=T0 + 4 * DAY)
    for kind in ("dividend", "split", "roll"):
        event = data_event(market_id=instrument.id, kind=kind, t_ms=T0 + 3 * DAY, detail={})
        assert applies_at(event, instrument, grid) == T0 + 2 * DAY
    for kind in ("funding", "borrow_fee", "carry", "forced_flat"):
        event = data_event(market_id=instrument.id, kind=kind, t_ms=T0 + 4 * DAY - 1, detail={})
        assert applies_at(event, instrument, grid) == T0 + 3 * DAY
    on_the_first_bar = data_event(market_id=instrument.id, kind="roll", t_ms=T0, detail={})
    assert applies_at(on_the_first_bar, instrument, grid) is None


def test_funding_debits_the_long_at_a_positive_rate_and_credits_it_at_a_negative_one() -> None:
    """17.3: a long pays a positive ``rate_ppm`` and a short receives it, and the sign flips both."""
    for position, rate_ppm, expected in ((1_000, 10_000, -63_000), (1_000, -10_000, 63_000),
                                         (-1_000, 10_000, 63_000), (-1_000, -10_000, -63_000)):
        event = data_event(market_id="binance-btcusdt", kind="funding", t_ms=T0 + 2 * DAY,
                           detail={"rate_ppm": rate_ppm, "mark_ticks": 6_300_000})
        instrument = continuous_fixture(cash_events=(event,))
        execution, log = execution_of(config=continuous_config())
        drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, position))]},
                         stop_after=T0 + 2 * DAY)
        applied = events_of(log, "cash_event_applied")
        assert len(applied) == 1
        assert applied[0].kind == "funding" and applied[0].origin == "data"
        assert applied[0].bar_ms == T0 + 2 * DAY and applied[0].phase == "settle"
        assert applied[0].cash_delta_cents == expected
        assert applied[0].position_before == position == applied[0].position_after
        assert applied[0].order_ids == ()
        assert applied[0].detail["rate_ppm"] == rate_ppm
        assert_accounting(execution, log, bankroll=100_000_000)


def test_a_dividend_pays_a_long_the_floor_and_charges_a_short_the_ceiling() -> None:
    """17.3: ``q * dividend_micro // 10 ** 7`` for a long, the ceiling of the same magnitude for a short."""
    for position, expected in ((1_000_000, 25_000), (-1_000_000, -25_000)):
        event = data_event(market_id="xnas-aapl", kind="dividend", t_ms=T0 + 3 * DAY,
                           detail={"dividend_micro": 250_000})
        instrument = equity_fixture(cash_events=(event,))
        execution, log = execution_of(config=continuous_config(n_bars=5))
        drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, position))]},
                         stop_after=T0 + 2 * DAY)
        applied = events_of(log, "cash_event_applied")
        assert len(applied) == 1
        assert applied[0].kind == "dividend"
        assert applied[0].cash_delta_cents == expected
        assert applied[0].position_after == position == applied[0].position_before
        assert_accounting(execution, log, bankroll=100_000_000)


def test_a_buy_at_the_ex_date_open_receives_no_dividend() -> None:
    """Ruling R175: the tape took the dividend out of the ex-date open, so the buyer is owed nothing."""
    event = data_event(market_id="xnas-aapl", kind="dividend", t_ms=T0 + 3 * DAY,
                       detail={"dividend_micro": 250_000})
    instrument = equity_fixture(cash_events=(event,))
    execution, log = execution_of(config=continuous_config(n_bars=5))
    drive_continuous(
        execution,
        instrument,
        plan={T0 + DAY: [("alpha", target(instrument.id, 1_000_000))],
              T0 + 2 * DAY: [("beta", target(instrument.id, 1_000_000))]},
        stop_after=T0 + 3 * DAY,
    )
    applied = events_of(log, "cash_event_applied")
    assert [event.agent_id for event in applied] == ["alpha"]
    assert applied[0].cash_delta_cents == 25_000
    assert execution.position("beta", instrument.id).position == 1_000_000
    assert_accounting(execution, log, bankroll=100_000_000)


def test_a_reverse_split_scales_a_short_and_expires_the_book_in_the_old_scale() -> None:
    """17.3 and ruling R153: the position is scaled, the cash does not move, and every price is stale."""
    event = data_event(market_id="xnas-aapl", kind="split", t_ms=T0 + 3 * DAY,
                       detail={"numerator": 1, "denominator": 10})
    instrument = equity_fixture(cash_events=(event,))
    execution, log = execution_of(config=continuous_config(n_bars=5))
    resting = MarketAction(market_id=instrument.id, prob_ppm=500_000, kind="limit", side="buy",
                           price_bp=5_000, size=1_000, ttl_bars=4)
    drive_continuous(
        execution,
        instrument,
        plan={T0: [("alpha", target(instrument.id, -1_000)), ("alpha", resting)]},
        stop_after=T0 + 2 * DAY,
    )
    applied = events_of(log, "cash_event_applied")
    assert len(applied) == 1
    assert applied[0].kind == "split"
    assert applied[0].cash_delta_cents == 0
    assert applied[0].position_before == -1_000
    assert applied[0].position_after == split_position_milli(-1_000, 1, 10)
    assert applied[0].position_after == -100
    assert applied[0].avg_cost_ticks_before == 10_000
    assert applied[0].avg_cost_ticks_after == 100_000
    expired = events_of(log, "order_expired")
    assert [event.reason for event in expired] == ["corporate_action"]
    assert expired[0].phase == "settle"
    assert execution.portfolio("alpha").reserved_cents == 0
    assert_accounting(execution, log, bankroll=100_000_000)


def test_a_buy_at_a_splits_effective_open_is_not_multiplied() -> None:
    """Ruling R175: the effective-date open is already in the new scale, so the buyer holds new shares."""
    event = data_event(market_id="xnas-aapl", kind="split", t_ms=T0 + 3 * DAY,
                       detail={"numerator": 4, "denominator": 1})
    instrument = equity_fixture(cash_events=(event,))
    execution, log = execution_of(config=continuous_config(n_bars=5))
    drive_continuous(
        execution,
        instrument,
        plan={T0 + DAY: [("alpha", target(instrument.id, 1_000))],
              T0 + 2 * DAY: [("beta", target(instrument.id, 1_000))]},
        stop_after=T0 + 3 * DAY,
    )
    applied = events_of(log, "cash_event_applied")
    assert [event.agent_id for event in applied] == ["alpha"]
    assert applied[0].position_before == 1_000 and applied[0].position_after == 4_000
    assert execution.position("alpha", instrument.id).position == 4_000
    assert execution.position("beta", instrument.id).position == 1_000
    assert_accounting(execution, log, bankroll=100_000_000)


def test_a_roll_pays_two_fills_and_never_trades_the_gap() -> None:
    """17.3 and ruling R152: two event fills at the record's two prices, each with its taker fee."""
    event = data_event(market_id="xcme-es", kind="roll", t_ms=T0 + 3 * DAY,
                       detail={"from_symbol": "ESU6", "to_symbol": "ESZ6",
                               "from_price_ticks": 21_729, "to_price_ticks": 21_700,
                               "gap_ticks": -29})
    instrument = future_fixture(cash_events=(event,))
    execution, log = execution_of(config=continuous_config(n_bars=5))
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, 2_000))]},
                     stop_after=T0 + 2 * DAY)
    fills = events_of(log, "filled")
    assert len(fills) == 3
    closing, reopening = fills[1], fills[2]
    assert closing.phase == "settle" and closing.price_source == "event"
    assert closing.side == "sell" and closing.fill_price_bp == 21_729
    assert closing.cash_delta_cents == cash_in_cents(2_000, 21_729, 250_000, 50_000_000)
    assert reopening.side == "buy" and reopening.fill_price_bp == 21_700
    assert reopening.cash_delta_cents == -cash_out_cents(2_000, 21_700, 250_000, 50_000_000)
    assert reopening.position_after == 2_000
    placed = [event.origin for event in events_of(log, "order_placed")]
    assert placed == ["target", "roll", "roll"]
    charged = events_of(log, "fee_charged")
    assert [event.fee_cents for event in charged[1:]] == [506, 506]
    applied = events_of(log, "cash_event_applied")
    assert len(applied) == 1
    assert applied[0].kind == "roll"
    assert applied[0].cash_delta_cents == 0
    assert applied[0].position_before == 2_000 and applied[0].position_after == 2_000
    assert applied[0].avg_cost_ticks_after == 21_700
    assert applied[0].order_ids == (closing.order_id, reopening.order_id)
    assert applied[0].detail["gap_ticks"] == -29
    gap = cash_in_cents(2_000, 21_729, 250_000, 50_000_000)
    gap -= cash_out_cents(2_000, 21_700, 250_000, 50_000_000)
    assert closing.cash_delta_cents + reopening.cash_delta_cents == gap
    assert_accounting(execution, log, bankroll=100_000_000)


def test_a_roll_with_a_positive_gap_shrinks_a_position_the_agent_cannot_fund() -> None:
    """Ruling R198: the reopening leg is truncated like any buy and the residual is in ``position_after``."""
    event = data_event(market_id="xcme-es", kind="roll", t_ms=T0 + 3 * DAY,
                       detail={"from_symbol": "ESU6", "to_symbol": "ESZ6",
                               "from_price_ticks": 21_700, "to_price_ticks": 30_000,
                               "gap_ticks": 8_300})
    instrument = future_fixture(price_ticks=21_700, cash_events=(event,))
    execution, log = execution_of(config=continuous_config(n_bars=5, bankroll_cents=60_000_000))
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, 2_000))]},
                     stop_after=T0 + 2 * DAY)
    reopening = events_of(log, "filled")[2]
    assert reopening.side == "buy"
    assert reopening.filled_size == 1_599
    assert reopening.unfilled_size == 401
    assert reopening.unfilled_reason == "cash"
    assert reopening.position_after == 1_599
    applied = events_of(log, "cash_event_applied")[0]
    assert applied.position_before == 2_000
    assert applied.position_after == 1_599
    assert execution.portfolio("alpha").cash_cents >= 0
    assert_accounting(execution, log, bankroll=60_000_000)


def test_borrow_fee_is_charged_at_every_session_close_and_a_weekend_is_charged_on_monday() -> None:
    """17.3 and ruling R176: one engine event per (instrument, session), ``days`` since the previous close."""
    calendars = {"xnas": sessions_of("xnas", 0, 1, 4, 5)}
    bars = tuple(
        make_bar(T0 + day * DAY, open_bp=10_000, high_bp=10_000, low_bp=10_000, close_bp=10_000,
                 volume_milli=1_000_000)
        for day in (0, 1, 4, 5)
    )
    instrument = Continuous(
        id="xnas-aapl", kind="equity", tick_size_micro=10_000, point_value_micro=1_000_000, bars=bars,
        provider="xnas", vendor="yahoo", symbol="AAPL", currency="usd", category="finance",
        session_calendar_id="xnas", fee_schedule_id="xnas-zero-2026-09",
        borrow_schedule_id="xnas-borrowgc-2026-09",
    )
    config = continuous_config(n_bars=6, bankroll_cents=10_000_000)
    execution, log = execution_of(config=config, calendars=calendars)
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, -100_000))]})
    charges = [event for event in events_of(log, "cash_event_applied") if event.kind == "borrow_fee"]
    assert [event.bar_ms for event in charges] == [T0 + DAY, T0 + 4 * DAY, T0 + 5 * DAY]
    assert [event.detail["days"] for event in charges] == [1, 3, 1]
    assert [event.cash_delta_cents for event in charges] == [-8, -24, -8]
    assert all(event.origin == "engine" for event in charges)
    assert all(event.detail["rate_ppm_per_day"] == 8 for event in charges)
    assert CARRY_SCHEDULES["xnas-borrowgc-2026-09"].rate_ppm_per_day == 8
    assert_accounting(execution, log, bankroll=10_000_000)


def test_a_long_owes_no_borrow_fee() -> None:
    """17.3: ``borrow_fee`` exists only for agents who are short."""
    calendars = {"xnas": sessions_of("xnas", 0, 1, 2, 3, 4)}
    instrument = equity_fixture(borrow_schedule_id="xnas-borrowgc-2026-09",
                                session_calendar_id="xnas")
    execution, log = execution_of(config=continuous_config(n_bars=5, bankroll_cents=100_000_000),
                                  calendars=calendars)
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, 100_000))]})
    assert [event.kind for event in events_of(log, "cash_event_applied")] == ["forced_flat"]
    assert_accounting(execution, log, bankroll=100_000_000)


def test_carry_credits_a_long_at_a_positive_rate_and_debits_it_at_a_negative_one() -> None:
    """Ruling R177: the fx carry is a seventh, engine-origin kind, signed and computed per session."""
    schedules = {
        "otcfx-carrygc-2026-09": fees.CarrySchedule(
            schedule_id="otcfx-carrygc-2026-09", provider="otcfx", kind="fx", role="carry",
            rate_ppm_per_day=20, source_url="https://www.bis.org/statistics/rpfx22.htm",
            as_of_date="2026-09-08",
        ),
        "otcfx-carrydebit-2026-09": fees.CarrySchedule(
            schedule_id="otcfx-carrydebit-2026-09", provider="otcfx", kind="fx", role="carry",
            rate_ppm_per_day=-20, source_url="https://www.bis.org/statistics/rpfx22.htm",
            as_of_date="2026-09-08",
        ),
    }
    calendars = {"otcfx": sessions_of("otcfx", 0, 1, 2, 3, 4)}
    for schedule_id, expected in (("otcfx-carrygc-2026-09", 22), ("otcfx-carrydebit-2026-09", -22)):
        instrument = fx_fixture(carry_schedule_id=schedule_id, session_calendar_id="otcfx")
        execution, log = execution_of(config=continuous_config(n_bars=5, bankroll_cents=10_000_000),
                                      calendars=calendars, carry_schedules=schedules)
        drive_continuous(execution, instrument,
                         plan={T0: [("alpha", target(instrument.id, 100_000))]},
                         stop_after=T0 + DAY)
        charges = [event for event in events_of(log, "cash_event_applied") if event.kind == "carry"]
        assert len(charges) == 1
        assert charges[0].origin == "engine"
        assert charges[0].cash_delta_cents == expected
        assert charges[0].position_before == 100_000 == charges[0].position_after
        assert charges[0].detail["days"] == 1
        assert_accounting(execution, log, bankroll=10_000_000)


def test_the_events_of_one_bar_apply_in_kind_order_whatever_their_stamps() -> None:
    """Ruling R193: kind first, so the ex-date dividend is paid per pre-split share."""
    split = data_event(market_id="xnas-aapl", kind="split", t_ms=T0 + 3 * DAY,
                       detail={"numerator": 4, "denominator": 1})
    dividend = data_event(market_id="xnas-aapl", kind="dividend", t_ms=T0 + 3 * DAY + 13 * 3_600_000,
                          detail={"dividend_micro": 1_000_000})
    instrument = equity_fixture(cash_events=(split, dividend))
    execution, log = execution_of(config=continuous_config(n_bars=5))
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, 1_000))]},
                     stop_after=T0 + 2 * DAY)
    applied = events_of(log, "cash_event_applied")
    assert [event.kind for event in applied] == ["dividend", "split"]
    assert applied[0].cash_delta_cents == 1_000 * 1_000_000 // 10_000_000
    assert applied[0].cash_delta_cents == 100
    assert applied[1].position_after == 4_000
    assert_accounting(execution, log, bankroll=100_000_000)


def test_an_event_whose_application_bar_lies_outside_the_run_is_not_applied() -> None:
    """17.3: no position can exist before the run's first bar of the instrument, so nothing is owed."""
    event = data_event(market_id="xnas-aapl", kind="dividend", t_ms=T0,
                       detail={"dividend_micro": 250_000})
    instrument = equity_fixture(cash_events=(event,))
    execution, log = execution_of(config=continuous_config(n_bars=5))
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, 1_000_000))]},
                     stop_after=T0 + 3 * DAY)
    assert events_of(log, "cash_event_applied") == ()
    assert_accounting(execution, log, bankroll=100_000_000)


def test_a_cash_event_writes_nothing_for_an_agent_with_no_position() -> None:
    """17.3: nothing for an agent whose position is zero before and after."""
    event = data_event(market_id="binance-btcusdt", kind="funding", t_ms=T0 + 2 * DAY,
                       detail={"rate_ppm": 10_000, "mark_ticks": 6_300_000})
    instrument = continuous_fixture(cash_events=(event,))
    execution, log = execution_of(config=continuous_config())
    execution.register_agent("alpha")
    drive_continuous(execution, instrument, stop_after=T0 + 2 * DAY)
    assert events_of(log, "cash_event_applied") == ()
    assert execution.portfolio("alpha").cash_cents == 100_000_000


def test_calendars_none_reads_as_the_continuous_calendar_and_owes_no_session_charge() -> None:
    """Ruling R174: ``None`` is the synthesised ``continuous`` calendar, which never closes a session."""
    instrument = equity_fixture(borrow_schedule_id="xnas-borrowgc-2026-09")
    execution, log = execution_of(config=continuous_config(n_bars=5))
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, -100_000))]},
                     stop_after=T0 + 3 * DAY)
    assert events_of(log, "cash_event_applied") == ()
    assert execution.position("alpha", instrument.id).position == -100_000
    assert_accounting(execution, log, bankroll=100_000_000)


def test_a_dividend_debit_takes_cash_below_zero_and_a_debit_balance_funds_nothing() -> None:
    """Ruling R179: the proceeds of a short spent elsewhere, then an ex-date, then nothing funds."""
    dividend = data_event(market_id="xnas-aapl", kind="dividend", t_ms=T0 + 4 * DAY,
                          detail={"dividend_micro": 2_000_000})
    short_leg = equity_fixture(market_id="xnas-aapl", n_bars=7, cash_events=(dividend,))
    long_leg = equity_fixture(market_id="xnys-msft", n_bars=7, provider="xnys", symbol="MSFT",
                              fee_schedule_id="xnys-zero-2026-09")
    execution, log = execution_of(config=config_of(t1_ms=T0 + 7 * DAY, volume_cap_permille=1_000,
                                                   slippage_bp_per_pct=0, bankroll_cents=1_000_000))
    execution.place(agent_id="alpha", market=short_leg, action=target(short_leg.id, -100_000),
                    item_index=0, t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=short_leg)
    assert execution.portfolio("alpha").cash_cents == 2_000_000

    execution.place(agent_id="alpha", market=long_leg, action=target(long_leg.id, 199_000),
                    item_index=0, t_ms=T0 + DAY)
    execution.execute_bar(t_ms=T0 + 2 * DAY, market=long_leg)
    assert execution.portfolio("alpha").cash_cents == 10_000

    resting = MarketAction(market_id=long_leg.id, prob_ppm=500_000, kind="limit", side="buy",
                           price_bp=5_000, size=100, ttl_bars=4)
    execution.place(agent_id="alpha", market=long_leg, action=resting, item_index=0, t_ms=T0 + 2 * DAY)
    execution.execute_bar(t_ms=T0 + 3 * DAY, market=long_leg)
    assert execution.portfolio("alpha").reserved_cents == 500

    execution.place(agent_id="alpha", market=long_leg, action=target(long_leg.id, 299_000),
                    item_index=0, t_ms=T0 + 3 * DAY)
    execution.apply_cash_events(t_ms=T0 + 3 * DAY, market=short_leg)
    applied = events_of(log, "cash_event_applied")
    assert len(applied) == 1
    assert applied[0].kind == "dividend"
    assert applied[0].cash_delta_cents == -20_000
    view = execution.portfolio("alpha")
    assert view.cash_cents == -10_000
    assert view.reserved_cents == 0
    debit = [event for event in events_of(log, "order_expired") if event.reason == "debit"]
    assert len(debit) == 1
    assert debit[0].released_cents == 500

    execution.execute_bar(t_ms=T0 + 4 * DAY, market=long_leg)
    starved = events_of(log, "filled")[-1]
    assert starved.filled_size == 0
    assert starved.unfilled_reason == "cash"
    assert execution.portfolio("alpha").cash_cents == -10_000
    assert_accounting(execution, log, bankroll=1_000_000)


# --------------------------------------------------------------------------------------------------
# 8.9 and 17.3: the accounting invariant per kind, over generated sequences
# --------------------------------------------------------------------------------------------------
AGENTS: tuple[str, ...] = ("alpha", "beta")

#: The one carry schedule the tests declare. 17.4 ships none on purpose (ruling R177: an fx
#: instrument's ``carry_schedule_id`` is ``null`` unless a dataset declares the rate differential), so
#: without a run-supplied row the ``carry`` kind of 17.3 is unreachable and untestable.
TEST_CARRY_SCHEDULES: Mapping[str, fees.CarrySchedule] = {
    "otcfx-carrygc-2026-09": fees.CarrySchedule(
        schedule_id="otcfx-carrygc-2026-09", provider="otcfx", kind="fx", role="carry",
        rate_ppm_per_day=20, source_url="https://www.bis.org/statistics/rpfx22.htm",
        as_of_date="2026-09-08", note="the rate differential of PRD v4 1.1, off by default",
    ),
}


@dataclass(frozen=True, slots=True)
class Op:
    """One generated intent: a ``target`` at an absolute position, or a resting ``limit``."""

    agent_id: str
    kind: str
    position: int = 0
    side: str = "buy"
    price_ticks: int = 0
    size: int = 1
    ttl_bars: int = 1

    def action(self, market_id: str) -> MarketAction:
        """The ``MarketAction`` of 8.4 this intent is, whose sizes are the instrument's own units."""
        if self.kind == "target":
            return MarketAction(market_id=market_id, prob_ppm=500_000, kind="target",
                                target_position=self.position)
        return MarketAction(market_id=market_id, prob_ppm=500_000, kind="limit", side=self.side,
                            price_bp=self.price_ticks, size=self.size, ttl_bars=self.ttl_bars)


@dataclass(frozen=True, slots=True)
class KindProfile:
    """One instrument kind as the invariant test needs it: its scales, its schedule and its band."""

    kind: str
    market_id: str
    tick_size_micro: int
    point_value_micro: int
    fee_schedule_id: str
    price_low: int
    price_high: int
    size_max: int
    seed_position: int
    bankroll_cents: int
    quoted: bool = False
    short_allowed: bool = True
    session_calendar_id: str = "continuous"
    borrow_schedule_id: str | None = None
    carry_schedule_id: str | None = None


PROFILES: Mapping[str, KindProfile] = {
    "binary": KindProfile(
        kind="binary", market_id="kalshi-demo", tick_size_micro=100, point_value_micro=1_000_000,
        fee_schedule_id="kalshi-general-2026-09", price_low=500, price_high=9_000, size_max=60,
        seed_position=20, bankroll_cents=1_000_000, quoted=True,
    ),
    "spot_crypto": KindProfile(
        kind="spot_crypto", market_id="binance-btcusdt", tick_size_micro=10_000,
        point_value_micro=1_000_000, fee_schedule_id="binance-spot-2026-09",
        price_low=6_200_000, price_high=6_400_000, size_max=3_000, seed_position=1_000,
        bankroll_cents=100_000_000, short_allowed=False,
    ),
    "perp": KindProfile(
        kind="perp", market_id="binance-btcusdt", tick_size_micro=10_000,
        point_value_micro=1_000_000, fee_schedule_id="binance-perp-2026-09",
        price_low=6_200_000, price_high=6_400_000, size_max=3_000, seed_position=1_000,
        bankroll_cents=100_000_000,
    ),
    "fx": KindProfile(
        kind="fx", market_id="otcfx-eurusd", tick_size_micro=10_000, point_value_micro=1_000_000,
        fee_schedule_id="otcfx-spread-2026-09", price_low=10_500, price_high=11_500,
        size_max=100_000, seed_position=50_000, bankroll_cents=10_000_000,
        session_calendar_id="otcfx", carry_schedule_id="otcfx-carrygc-2026-09",
    ),
    "equity": KindProfile(
        kind="equity", market_id="xnas-aapl", tick_size_micro=10_000, point_value_micro=1_000_000,
        fee_schedule_id="xnas-zero-2026-09", price_low=9_500, price_high=10_500, size_max=100_000,
        seed_position=50_000, bankroll_cents=10_000_000, quoted=True, session_calendar_id="xnas",
        borrow_schedule_id="xnas-borrowgc-2026-09",
    ),
    "future": KindProfile(
        kind="future", market_id="xcme-es", tick_size_micro=250_000, point_value_micro=50_000_000,
        fee_schedule_id="cme-es-2026-09", price_low=21_500, price_high=21_900, size_max=2_000,
        seed_position=1_000, bankroll_cents=200_000_000,
    ),
}


def generated_bar(t_ms: int, *, level: int, span: int, volume: int, spread: int, binary: bool,
                  quoted: bool) -> Bar:
    """One generated bar: a legal range, a possibly zero volume, and a quote when the venue has one."""
    ceiling = 9_999 if binary else PRICE_TICKS_MAX
    low = max(1, min(level, ceiling))
    high = min(ceiling, low + span)
    open_bp = low + (high - low) // 3
    close = low + 2 * (high - low) // 3
    bid = max(1, open_bp - spread) if quoted else None
    ask = min(ceiling, open_bp + spread) if quoted else None
    return make_bar(t_ms, open_bp=open_bp, high_bp=high, low_bp=low, close_bp=close, vwap_bp=open_bp,
                    volume_milli=volume, bid_bp=bid, ask_bp=ask)


def cash_events_of(profile: KindProfile, *, bars: Sequence[Bar], detail: Mapping[str, int],
                   ) -> tuple[CashEvent, ...]:
    """The data events the kind's row of 17.3 allows, stamped so that they apply at bar index two.

    A ``funding`` time is an instant of its own bar; a ``dividend``, a ``split`` and a ``roll`` are
    stamped with the open of the first bar priced in the **new** regime and apply one bar earlier
    (ruling R175), so all of them land on the same bar and their kind order is exercised (ruling R193).
    """
    market_id = profile.market_id
    if profile.kind == "perp":
        return (data_event(market_id=market_id, kind="funding", t_ms=bars[2].t_ms,
                           detail={"rate_ppm": detail["rate_ppm"], "mark_ticks": bars[2].close_bp}),)
    if profile.kind == "equity":
        return (
            data_event(market_id=market_id, kind="dividend", t_ms=bars[3].t_ms,
                       detail={"dividend_micro": detail["dividend_micro"]}),
            data_event(market_id=market_id, kind="split", t_ms=bars[3].t_ms,
                       detail={"numerator": detail["numerator"],
                               "denominator": detail["denominator"]}),
        )
    if profile.kind == "future":
        from_price = bars[2].close_bp
        to_price = max(1, from_price + detail["gap"])
        return (data_event(market_id=market_id, kind="roll", t_ms=bars[3].t_ms,
                           detail={"from_symbol": "ESU6", "to_symbol": "ESZ6",
                                   "from_price_ticks": from_price, "to_price_ticks": to_price,
                                   "gap_ticks": to_price - from_price}),)
    return ()


def drive_sequence(
    profile: KindProfile,
    *,
    levels: Sequence[int],
    spans: Sequence[int],
    volumes: Sequence[int],
    spreads: Sequence[int],
    ops: Sequence[Sequence[Op]],
    detail: Mapping[str, int],
) -> tuple[Execution, Journal]:
    """Drive one generated sequence of one kind through 8.2's phase order and assert every 8.9 line.

    The whole point of running the real phase order rather than calling :meth:`Execution._apply_fill`
    by hand is that the invariant is a statement about the **journal**: it holds only if every event the
    engine writes agrees with every cent it moved, on the same bars, in the same order.
    """
    n_bars = len(levels)
    binary = profile.kind == "binary"
    bars = tuple(
        generated_bar(T0 + index * DAY, level=levels[index], span=spans[index],
                      volume=volumes[index], spread=spreads[index], binary=binary,
                      quoted=profile.quoted)
        for index in range(n_bars)
    )
    calendars: Mapping[str, SessionCalendar] | None = None
    if profile.session_calendar_id != "continuous":
        calendars = {
            profile.session_calendar_id: sessions_of(profile.session_calendar_id, *range(n_bars))
        }
    config = config_of(t1_ms=T0 + n_bars * DAY, bankroll_cents=profile.bankroll_cents,
                       volume_cap_permille=1_000, slippage_bp_per_pct=20)
    execution, log = execution_of(config=config, calendars=calendars,
                                  carry_schedules=TEST_CARRY_SCHEDULES)
    for agent_id in AGENTS:
        execution.register_agent(agent_id)
    instrument: InstrumentLike
    if binary:
        instrument = make_market(market_id=profile.market_id, bars=bars,
                                 close_at_ms=T0 + (n_bars - 1) * DAY,
                                 resolved_at_ms=T0 + (n_bars - 1) * DAY,
                                 resolution=detail["resolution"],
                                 fee_schedule_id=profile.fee_schedule_id)
    else:
        instrument = Continuous(
            id=profile.market_id, kind=profile.kind, tick_size_micro=profile.tick_size_micro,
            point_value_micro=profile.point_value_micro, bars=bars,
            fee_schedule_id=profile.fee_schedule_id, session_calendar_id=profile.session_calendar_id,
            borrow_schedule_id=profile.borrow_schedule_id,
            carry_schedule_id=profile.carry_schedule_id, short_allowed=profile.short_allowed,
            cash_events=cash_events_of(profile, bars=bars, detail=detail),
        )
    settlements: Mapping[str, int] = {}
    settled: tuple[str, ...] = ()
    seeded = [Op(agent_id="alpha", kind="target", position=profile.seed_position), *ops[0]]
    schedule = [seeded, *ops[1:]]
    for index, bar in enumerate(bars):
        t_ms = bar.t_ms
        execution.expire_orders(t_ms=t_ms, markets=[instrument])
        for item_index, op in enumerate(schedule[index]):
            execution.place(agent_id=op.agent_id, market=instrument,
                            action=op.action(profile.market_id), item_index=item_index, t_ms=t_ms)
        if profile.market_id in execution.pending_market_ids(t_ms=t_ms):
            execution.execute_bar(t_ms=t_ms, market=instrument)
        if binary:
            if t_ms == T0 + (n_bars - 1) * DAY:
                settlements = execution.settle(market=instrument)
                settled = (profile.market_id,)
        else:
            execution.apply_cash_events(t_ms=t_ms, market=instrument)
            if index == n_bars - 1:
                execution.force_flat(t_ms=t_ms, market=instrument)
        execution.mark(t_ms=t_ms, markets=[instrument])
        assert_accounting(execution, log, bankroll=profile.bankroll_cents,
                          settlements=settlements, settled=settled)
    assert events_of(log, "filled") != ()
    for agent_id in AGENTS:
        assert execution.portfolio(agent_id).reserved_cents == 0
    assert_accounting(execution, log, bankroll=profile.bankroll_cents, settlements=settlements,
                      settled=settled)
    return (execution, log)


def sequence_strategy(profile: KindProfile, *, n_bars: int = 5) -> st.SearchStrategy[dict[str, object]]:
    """The generator of one kind's sequences: bars, quotes, volumes, intents and one event payload."""
    op = st.builds(
        Op,
        agent_id=st.sampled_from(AGENTS),
        kind=st.sampled_from(["target", "limit"]),
        position=st.integers(min_value=-profile.size_max, max_value=profile.size_max),
        side=st.sampled_from(["buy", "sell"]),
        price_ticks=st.integers(min_value=profile.price_low, max_value=profile.price_high),
        size=st.integers(min_value=1, max_value=profile.size_max),
        ttl_bars=st.integers(min_value=1, max_value=3),
    )
    span_high = max(1, (profile.price_high - profile.price_low) // 2)
    return st.fixed_dictionaries({
        "levels": st.lists(st.integers(min_value=profile.price_low, max_value=profile.price_high),
                           min_size=n_bars, max_size=n_bars),
        "spans": st.lists(st.integers(min_value=0, max_value=span_high),
                          min_size=n_bars, max_size=n_bars),
        "volumes": st.lists(st.integers(min_value=0, max_value=200 * profile.size_max),
                            min_size=n_bars, max_size=n_bars),
        "spreads": st.lists(st.integers(min_value=0, max_value=max(1, span_high // 4)),
                            min_size=n_bars, max_size=n_bars),
        "ops": st.lists(st.lists(op, min_size=0, max_size=2), min_size=n_bars, max_size=n_bars),
        "detail": st.fixed_dictionaries({
            "rate_ppm": st.integers(min_value=-50_000, max_value=50_000),
            "dividend_micro": st.integers(min_value=0, max_value=500_000),
            "numerator": st.sampled_from([1, 2, 3, 4]),
            "denominator": st.sampled_from([1, 2, 3, 10]),
            "gap": st.integers(min_value=-2_000, max_value=8_000),
            "resolution": st.sampled_from([0, 1]),
        }),
    })


def check_sequence(kind: str, case: Mapping[str, object]) -> None:
    """Unpack one generated case and drive it, so the six per-kind tests are one body."""
    profile = PROFILES[kind]
    _execution, _log = drive_sequence(
        profile,
        levels=case["levels"],  # type: ignore[arg-type]
        spans=case["spans"],  # type: ignore[arg-type]
        volumes=case["volumes"],  # type: ignore[arg-type]
        spreads=case["spreads"],  # type: ignore[arg-type]
        ops=case["ops"],  # type: ignore[arg-type]
        detail=case["detail"],  # type: ignore[arg-type]
    )


@settings(max_examples=1_000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(case=sequence_strategy(PROFILES["binary"]))
def test_the_invariant_holds_on_generated_binary_sequences(case: Mapping[str, object]) -> None:
    """8.9 on the binary kind: fills, fees, reservations and the settlement, over the journal alone."""
    check_sequence("binary", case)


@settings(max_examples=1_000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(case=sequence_strategy(PROFILES["spot_crypto"]))
def test_the_invariant_holds_on_generated_spot_crypto_sequences(case: Mapping[str, object]) -> None:
    """17.3's ``spot_crypto`` row: fills, fees and the forced flat, and no short at any price."""
    check_sequence("spot_crypto", case)


@settings(max_examples=1_000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(case=sequence_strategy(PROFILES["perp"]))
def test_the_invariant_holds_on_generated_perp_sequences(case: Mapping[str, object]) -> None:
    """17.3's ``perp`` row: a funding of either sign on a long or a short, plus the forced flat."""
    check_sequence("perp", case)


@settings(max_examples=1_000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(case=sequence_strategy(PROFILES["fx"]))
def test_the_invariant_holds_on_generated_fx_sequences(case: Mapping[str, object]) -> None:
    """17.3's ``fx`` row: a signed carry at every session close (ruling R177), plus the forced flat."""
    check_sequence("fx", case)


@settings(max_examples=1_000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(case=sequence_strategy(PROFILES["equity"]))
def test_the_invariant_holds_on_generated_equity_sequences(case: Mapping[str, object]) -> None:
    """17.3's ``equity`` row: a dividend, a split of either direction and a borrow fee on shorts."""
    check_sequence("equity", case)


@settings(max_examples=1_000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(case=sequence_strategy(PROFILES["future"]))
def test_the_invariant_holds_on_generated_future_sequences(case: Mapping[str, object]) -> None:
    """17.3's ``future`` row: a roll of either gap sign, two fills and two fees, plus the forced flat."""
    check_sequence("future", case)


def fixed_case(profile: KindProfile, *, n_bars: int = 5) -> dict[str, object]:
    """One hand-written sequence per kind: a short, a resting limit, a reversal and a close.

    It exists so that the generated sequences above cannot go vacuous without a test failing: the guard
    below drives this case and asserts that every cash event kind the instrument's row of 17.3 names
    actually reached the journal.
    """
    middle = profile.price_low + (profile.price_high - profile.price_low) // 2
    span = max(1, (profile.price_high - profile.price_low) // 4)
    ops: list[list[Op]] = [
        [Op(agent_id="beta", kind="target", position=-profile.seed_position)],
        [Op(agent_id="alpha", kind="limit", side="buy", price_ticks=profile.price_low,
            size=max(1, profile.size_max // 2), ttl_bars=2)],
        [Op(agent_id="beta", kind="target", position=profile.seed_position)],
        [Op(agent_id="alpha", kind="target", position=0)],
        [],
    ]
    return {
        "levels": [middle] * n_bars,
        "spans": [span] * n_bars,
        "volumes": [200 * profile.size_max] * n_bars,
        "spreads": [1] * n_bars,
        "ops": ops[:n_bars],
        "detail": {"rate_ppm": 30_000, "dividend_micro": 300_000, "numerator": 1, "denominator": 10,
                   "gap": 500, "resolution": 1},
    }


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("binary", frozenset()),
        ("spot_crypto", frozenset({"forced_flat"})),
        ("perp", frozenset({"funding", "forced_flat"})),
        ("fx", frozenset({"carry", "forced_flat"})),
        ("equity", frozenset({"dividend", "split", "borrow_fee", "forced_flat"})),
        ("future", frozenset({"roll", "forced_flat"})),
    ],
)
def test_every_kind_exercises_the_cash_events_its_row_of_17_3_names(
    kind: str, expected: frozenset[str]
) -> None:
    """17.3's kind table: the lines each kind can move, asserted to be reached and not merely declared."""
    profile = PROFILES[kind]
    execution, log = drive_sequence(profile, **fixed_case(profile))  # type: ignore[arg-type]
    written = {event.kind for event in events_of(log, "cash_event_applied")}
    assert written == set(expected)
    assert len(events_of(log, "filled")) >= 4
    assert any(event.filled_size > 0 for event in events_of(log, "filled"))
    assert events_of(log, "order_placed") != ()
    for agent_id in AGENTS:
        assert execution.portfolio(agent_id).reserved_cents == 0


# --------------------------------------------------------------------------------------------------
# The remaining edges of 8.6, 16.2 and 17.3
# --------------------------------------------------------------------------------------------------
def test_a_zero_volume_bar_moves_no_cent_through_execution() -> None:
    """8.6 step 1 at the engine's level: the reason reaches the journal and no position opens."""
    bars = [
        make_bar(T0, open_bp=5_000, volume_milli=100_000),
        make_bar(T0 + DAY, open_bp=5_000, high_bp=5_100, low_bp=4_900, volume_milli=0),
        make_bar(T0 + 2 * DAY, open_bp=5_000, volume_milli=100_000),
    ]
    market = make_market(bars=bars, close_at_ms=T0 + 2 * DAY, resolved_at_ms=T0 + 2 * DAY,
                         fee_schedule_id="kalshi-general-2026-09")
    execution, log = execution_of(config=config_of(volume_cap_permille=1_000))
    execution.place(agent_id="alpha", market=market, action=MarketAction(
        market_id=market.id, prob_ppm=600_000, kind="target", target_position=10), item_index=0, t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    fill = events_of(log, "filled")[0]
    assert fill.filled_size == 0
    assert fill.unfilled_size == 10
    assert fill.unfilled_reason == "zero_volume"
    assert fill.cash_delta_cents == 0
    assert events_of(log, "fee_charged")[0].fee_cents == 0
    assert execution.position("alpha", market.id).position == 0
    assert execution.portfolio("alpha").cash_cents == 100_000
    assert_accounting(execution, log, bankroll=100_000)


def test_a_truncated_sell_keeps_the_sale_fee_of_its_own_side() -> None:
    """Ruling R130 and 17.4: the fee of the fill the journal writes reads the order's side, not a default."""
    schedule = replace(FEE_SCHEDULES["xnas-zero-2026-09"], taker_bp=2, sale_bp=3)
    view = crypto_view(kind="equity", fee_schedule_id=schedule.schedule_id)
    bar = make_bar(T0, open_bp=19_000, high_bp=19_000, low_bp=19_000, volume_milli=1_000_000)
    order = LiquidityOrder(side="sell", kind="market", size_milli=100_000)
    whole = finalise_fill(quoted_bp=19_000, base_bp=19_000, order=order, bar=bar,
                          filled_milli=100_000, unfilled_reason="none", price_source="open",
                          schedule=schedule, market_view=view)
    assert whole.fee_cents == fee_cents(schedule, size=100_000, price_bp=19_000, role="taker",
                                        side="sell", tick_size_micro=10_000,
                                        point_value_micro=1_000_000)
    cut = truncate_for_cash(whole, max_filled_milli=40_000, schedule=schedule, market_view=view,
                            order=order)
    assert cut.filled_milli == 40_000
    assert cut.fee_cents == fee_cents(schedule, size=40_000, price_bp=19_000, role="taker", side="sell",
                                      tick_size_micro=10_000, point_value_micro=1_000_000)
    assert cut.fee_cents > fee_cents(schedule, size=40_000, price_bp=19_000, role="taker", side="buy",
                                     tick_size_micro=10_000, point_value_micro=1_000_000)


def test_the_notional_cap_is_checked_on_a_continuous_order_too() -> None:
    """Rulings R147 and R196: the cap is checked once, at the execute phase, in the instrument's units."""
    instrument = continuous_fixture()
    execution, log = execution_of(config=continuous_config())
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, 10**12))]},
                     stop_after=T0 + DAY)
    assert [event.reason for event in events_of(log, "order_rejected")] == ["bad_size"]
    assert events_of(log, "order_placed") == ()
    assert notional_micro(10**12, 6_300_000, 10_000, 1_000_000) > NOTIONAL_CENTS_MAX * 10**13


def test_the_forced_flat_of_a_delisted_instrument_names_delisting_as_its_reason() -> None:
    """17.3: ``reason`` is ``delisted`` when the instrument's own window ends inside the run."""
    instrument = continuous_fixture(n_bars=4, delisted_at_ms=T0 + 4 * DAY)
    execution, log = execution_of(config=continuous_config(n_bars=6))
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, 1_000))]})
    applied = events_of(log, "cash_event_applied")[-1]
    assert applied.kind == "forced_flat"
    assert applied.detail["reason"] == "delisted"
    assert execution.position("alpha", instrument.id).position == 0
    assert_accounting(execution, log, bankroll=100_000_000)


def test_an_action_decided_on_the_runs_last_bar_is_dropped_and_never_drains() -> None:
    """16.2: there is no execute phase after the run's last actionable bar, so the intent is dropped."""
    market = binary_fixture(n_bars=5)
    execution, log = execution_of(config=config_of(t1_ms=T0 + 4 * DAY, volume_cap_permille=1_000))
    execution.place(agent_id="alpha", market=market, action=MarketAction(
        market_id=market.id, prob_ppm=600_000, kind="target", target_position=5), item_index=0,
        t_ms=T0 + 3 * DAY)
    assert execution.pending_market_ids(t_ms=T0 + 4 * DAY) == ()
    assert [event.TYPE for event in log.events] == ["run_started"]


def test_expire_orders_takes_a_resting_order_off_a_market_that_stopped_being_tradable() -> None:
    """8.2 phase 1: the open phase expires what the ttl or the trading window has ended."""
    market = binary_fixture(n_bars=5, price_bp=5_000, fee_schedule_id="demo-zero")
    settling = bar_of(market.resolved_at_ms, market.interval_min)
    execution, log = execution_of(config=config_of(volume_cap_permille=1_000))
    action = MarketAction(market_id=market.id, prob_ppm=600_000, kind="limit", side="buy",
                          price_bp=1_000, size=5, ttl_bars=20)
    execution.place(agent_id="alpha", market=market, action=action, item_index=0, t_ms=T0)
    execution.execute_bar(t_ms=T0 + DAY, market=market)
    assert execution.portfolio("alpha").reserved_cents == cost_cents(5, 1_000)
    execution.expire_orders(t_ms=settling, markets=[market])
    expired = events_of(log, "order_expired")
    assert [event.reason for event in expired] == ["not_tradable"]
    assert expired[0].phase == "open"
    assert execution.portfolio("alpha").reserved_cents == 0
    assert_accounting(execution, log, bankroll=100_000)


def test_an_engine_events_id_hashes_the_last_instant_of_the_bar_it_applies_at() -> None:
    """Ruling R176: ``t_ms = bar + interval_ms - 1``, so ``bar_of(t_ms)`` is the bar it applies at."""
    instrument = continuous_fixture(n_bars=4)
    execution, log = execution_of(config=continuous_config())
    drive_continuous(execution, instrument, plan={T0: [("alpha", target(instrument.id, 1_000))]})
    applied = events_of(log, "cash_event_applied")[-1]
    last_bar = T0 + 3 * DAY
    expected = CashEvent.build(
        market_id=instrument.id, kind="forced_flat", t_ms=last_bar + DAY - 1,
        detail={"reason": "window_end", "price_ticks": 6_300_000},
    )
    assert expected.origin == "engine" and expected.source_url == ""
    assert bar_of(expected.t_ms, 1_440) == last_bar
    assert expected.cash_event_id == "ce-" + canonical_sha256(
        [instrument.id, "forced_flat", last_bar + DAY - 1,
         {"reason": "window_end", "price_ticks": 6_300_000}]
    )[:16]
    assert applied.cash_event_id == expected.cash_event_id
    assert re.fullmatch(r"ce-[0-9a-f]{16}", applied.cash_event_id) is not None
    assert_accounting(execution, log, bankroll=100_000_000)
