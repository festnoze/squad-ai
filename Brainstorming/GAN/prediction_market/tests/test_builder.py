"""D6: resampling, the dataset builder and the ``pmx data`` command group.

The tests are in the order the data flows: prints to bars (section 5.2), then the window, the ten quality
filters, the hardness tags and the chronological split (sections 7.4 to 7.7), then the manifest and the
hash (section 7.8), then the command group end to end over staged fixtures.

Every test is offline. ``tests/fixtures/d6/staging/`` holds exactly what an importer and a fetcher of
section 7.12 return, rendered as the canonical documents ``pmx data import`` and ``pmx data news fetch``
write into staging, so the end-to-end build reads real ``market.v2`` and ``news.v1`` documents and the
network paths are exercised against stubs of the two entry points the CLI resolves by name.

Six of the thirteen staged markets are there to be dropped, one per filter that a schema-valid document can
express, so "the filters ran" is a statement about counts rather than about coverage.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from pmx import cli_data
from pmx.data.builder import (
    BACKGROUND_SOURCE,
    ILLIQUID_DECILE_MIN_SLICE,
    KALSHI_COHORT_TARGET,
    KALSHI_MARKET_FLOOR,
    MANIFOLD_COHORT_TARGET,
    MANIFOLD_MARKET_FLOOR,
    SELF_RESOLVED_SOURCE,
    SELF_RESOLVED_TAG,
    WINDOW_DAYS_MAX,
    BuildResult,
    MarketFacts,
    SplitPlan,
    as_plain_dict,
    build_config_from_manifest,
    build_dataset,
    build_dataset_from_payloads,
    build_outcome,
    check_window_days,
    hardness_tags_for,
    illiquid_boundaries,
    link_news_payloads,
    market_facts,
    month_index_of,
    month_quotas,
    plan_folds,
    removal_reason,
    sample_seed_for,
    split_block_of,
    stratified_cap,
    window_bounds,
)
from pmx.data.loader import load_dataset, load_manifest, seal_dataset, verify_dataset_report
from pmx.data.news import linker
from pmx.data.resample import (
    Quote,
    bars_from_trades,
    median_daily_volume_milli,
    traded_bars,
    volume_milli_total,
)
from pmx.data.schema import market_from_payload, validate_against_schema
from pmx.data.universe import read_series_list
from pmx.errors import InvalidConfigError, LeakError, SchemaError
from pmx.journal import canonical_json
from pmx.types import (
    LINK_THRESHOLD_PERMILLE,
    MS_PER_DAY,
    MS_PER_HOUR,
    REMOVED_FILTER_KEYS,
    SAFETY_LAG_MS_DEFAULT,
    TAPE_KIND_BARS_ONLY,
    TAPE_KIND_PRINTS,
    BuildConfig,
    Trade,
    day_key,
    iso_date_from_ms,
    month_edges_for,
    ms_from_iso_date,
    round_half_up,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "d6"
STAGING = FIXTURES / "staging"

FREEZE_DATE = "2026-09-07"
FREEZE_MS = ms_from_iso_date(FREEZE_DATE)
WINDOW_START_MS = FREEZE_MS - 365 * MS_PER_DAY
WINDOW_END_MS = FREEZE_MS - MS_PER_DAY

#: The five staged markets that survive every filter, and the eight that do not.
KEPT_IDS = (
    "kalshi-KXPRESA-26-A",
    "manifold-abc123",
    "kalshi-KXTRIV-26-F",
    "kalshi-KXCPI-26-B",
    "kalshi-KXFED-26-C",
)


# --------------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------------
def config(**overrides: object) -> BuildConfig:
    """The build the fixtures were staged for, with overrides."""
    base: dict[str, object] = {
        "freeze_date": FREEZE_DATE,
        "providers": ("kalshi", "manifold"),
        "news_sources": ("manifold_comment", "wikipedia_current_events"),
    }
    base.update(overrides)
    return BuildConfig(**base)  # type: ignore[arg-type]


def read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line:
            parsed = json.loads(line)
            assert isinstance(parsed, dict)
            rows.append(parsed)
    return rows


def staged_markets(*providers: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for provider in providers or ("kalshi", "manifold"):
        rows.extend(read_jsonl(STAGING / "markets" / f"{provider}.jsonl"))
    return rows


def staged_news(*sources: str) -> list[dict[str, object]]:
    names = sources or ("gdelt", "manifold_comment", "wikipedia_asof", "wikipedia_current_events")
    rows: list[dict[str, object]] = []
    for source in names:
        rows.extend(read_jsonl(STAGING / "news" / f"{source}.jsonl"))
    return rows


def build(tmp_path: Path, **overrides: object) -> BuildResult:
    """The reference build of the staged fixtures into ``tmp_path/y2026``."""
    kwargs: dict[str, object] = {
        "out_dir": tmp_path / "y2026",
        "config": config(),
        "market_payloads": staged_markets(),
        "news_payloads": staged_news(),
        "excluded_series": ("KXMVE",),
    }
    kwargs.update(overrides)
    return build_dataset_from_payloads(**kwargs)  # type: ignore[arg-type]


def facts(**overrides: object) -> MarketFacts:
    """A market that passes every filter, so a test can break exactly one thing.

    Overriding ``closes_bp`` alone re-derives the three other per-bar tuples to the same length, because a
    tape whose arrays disagree is not a tape and ``MarketFacts`` reads them in lockstep.
    """
    created = WINDOW_START_MS + 10 * MS_PER_DAY
    resolved = created + 60 * MS_PER_DAY
    n_bars = 61
    if "closes_bp" in overrides and "bar_times_ms" not in overrides:
        closes = overrides["closes_bp"]
        assert isinstance(closes, tuple)
        n_bars = len(closes)
        first_day = created // MS_PER_DAY * MS_PER_DAY
        overrides.setdefault("bar_times_ms", tuple(first_day + i * MS_PER_DAY for i in range(n_bars)))
        overrides.setdefault("bar_volumes_milli", tuple(2_000 for _ in range(n_bars)))
        overrides.setdefault("bar_n_trades", tuple(3 for _ in range(n_bars)))
        overrides.setdefault("resolved_at_ms", first_day + (n_bars - 1) * MS_PER_DAY + 22 * MS_PER_HOUR)
    base: dict[str, object] = {
        "id": "kalshi-KXOK-26-A",
        "provider": "kalshi",
        "provider_id": "KXOK-26-A",
        "category": "politics",
        "source": "imported",
        "resolution_source": "venue",
        "tags": (),
        "created_at_ms": created,
        "close_at_ms": resolved - MS_PER_DAY,
        "resolved_at_ms": resolved,
        "resolution": 1,
        "interval_min": 1_440,
        "bar_times_ms": tuple(created // MS_PER_DAY * MS_PER_DAY + i * MS_PER_DAY for i in range(n_bars)),
        "closes_bp": tuple(5_500 + 10 * i for i in range(n_bars)),
        "bar_volumes_milli": tuple(2_000 for _ in range(n_bars)),
        "bar_n_trades": tuple(3 for _ in range(n_bars)),
        "n_trades": 200,
        "unique_bettors": 40,
    }
    base.update(overrides)
    return MarketFacts(**base)  # type: ignore[arg-type]


def reason_for(**overrides: object) -> str | None:
    return removal_reason(
        facts(**overrides),
        config(),
        window_start_ms=WINDOW_START_MS,
        window_end_ms=WINDOW_END_MS,
        freeze_ms=FREEZE_MS,
        excluded_series=frozenset({"KXMVE"}),
    )


def trade(t_ms: int, price_bp: int, size_milli: int, side: str = "yes") -> Trade:
    return Trade(t_ms=t_ms, price_bp=price_bp, size_milli=size_milli, side=side)


DAY0 = ms_from_iso_date("2026-01-01")


# --------------------------------------------------------------------------------------------------
# 5.2 Prints to the bar grid
# --------------------------------------------------------------------------------------------------
def test_a_bar_of_prints_carries_ohlc_vwap_volume_and_count() -> None:
    bars = bars_from_trades(
        [
            trade(DAY0 + 1_000, 4_000, 1_000),
            trade(DAY0 + 2_000, 4_600, 3_000),
            trade(DAY0 + 3_000, 3_800, 2_000),
            trade(DAY0 + 4_000, 4_200, 4_000),
        ],
        interval_min=1_440,
        start_ms=DAY0,
        end_ms=DAY0,
        first_price_bp=4_000,
    )
    assert len(bars) == 1
    bar = bars[0]
    assert (bar.open_bp, bar.high_bp, bar.low_bp, bar.close_bp) == (4_000, 4_600, 3_800, 4_200)
    assert bar.volume_milli == 10_000
    assert bar.n_trades == 4
    notional = 4_000 * 1_000 + 4_600 * 3_000 + 3_800 * 2_000 + 4_200 * 4_000
    assert bar.vwap_bp == round_half_up(notional, 10_000) == 4_220


def test_a_bar_with_no_print_repeats_the_previous_close_at_zero_volume() -> None:
    bars = bars_from_trades(
        [trade(DAY0 + 1_000, 6_100, 2_000), trade(DAY0 + 2 * MS_PER_DAY + 5, 6_400, 1_000)],
        interval_min=1_440,
        start_ms=DAY0,
        end_ms=DAY0 + 2 * MS_PER_DAY,
        first_price_bp=6_000,
    )
    silent = bars[1]
    assert (silent.open_bp, silent.high_bp, silent.low_bp, silent.close_bp, silent.vwap_bp) == (6_100,) * 5
    assert silent.volume_milli == 0
    assert silent.n_trades == 0
    assert bars[2].open_bp == 6_400  # the next print opens its own bar


def test_bars_before_the_first_print_carry_first_price_bp() -> None:
    bars = bars_from_trades(
        [trade(DAY0 + 3 * MS_PER_DAY + 10, 7_000, 1_000)],
        interval_min=1_440,
        start_ms=DAY0,
        end_ms=DAY0 + 3 * MS_PER_DAY,
        first_price_bp=6_500,
    )
    assert [bar.close_bp for bar in bars] == [6_500, 6_500, 6_500, 7_000]
    assert [bar.volume_milli for bar in bars] == [0, 0, 0, 1_000]


def test_the_grid_is_dense_and_aligned_from_start_to_end_inclusive() -> None:
    bars = bars_from_trades(
        [],
        interval_min=1_440,
        start_ms=DAY0 + 9 * MS_PER_HOUR,  # a raw instant, re-aligned by the resampler
        end_ms=DAY0 + 4 * MS_PER_DAY + 22 * MS_PER_HOUR,
        first_price_bp=5_000,
    )
    assert len(bars) == 5
    assert [bar.t_ms for bar in bars] == [DAY0 + i * MS_PER_DAY for i in range(5)]
    assert all(bar.t_ms % MS_PER_DAY == 0 for bar in bars)


def test_vwap_stays_inside_the_bar_range_on_a_lopsided_tape() -> None:
    bars = bars_from_trades(
        [trade(DAY0, 9_000, 1), trade(DAY0 + 1, 1_000, 9_999)],
        interval_min=1_440,
        start_ms=DAY0,
        end_ms=DAY0,
        first_price_bp=9_000,
    )
    bar = bars[0]
    assert bar.low_bp <= bar.vwap_bp <= bar.high_bp
    assert bar.vwap_bp == round_half_up(9_000 * 1 + 1_000 * 9_999, 10_000)


def test_prints_out_of_order_resample_to_the_same_bars_as_sorted_prints() -> None:
    ordered = [trade(DAY0 + 1, 4_000, 500), trade(DAY0 + 2, 4_400, 700), trade(DAY0 + 3, 4_100, 100)]
    shuffled = [ordered[2], ordered[0], ordered[1]]
    common = {"interval_min": 1_440, "start_ms": DAY0, "end_ms": DAY0, "first_price_bp": 4_000}
    assert bars_from_trades(shuffled, **common) == bars_from_trades(ordered, **common)  # type: ignore[arg-type]


def test_a_print_outside_the_grid_is_refused_rather_than_dropped() -> None:
    with pytest.raises(SchemaError) as caught:
        bars_from_trades(
            [trade(DAY0 - 1, 4_000, 1_000)],
            interval_min=1_440,
            start_ms=DAY0,
            end_ms=DAY0 + MS_PER_DAY,
            first_price_bp=4_000,
        )
    assert "outside" in str(caught.value)


def test_an_unknown_interval_and_an_inverted_range_are_refused() -> None:
    with pytest.raises(InvalidConfigError):
        bars_from_trades([], interval_min=15, start_ms=DAY0, end_ms=DAY0, first_price_bp=5_000)
    with pytest.raises(InvalidConfigError):
        bars_from_trades([], interval_min=1_440, start_ms=DAY0, end_ms=DAY0 - MS_PER_DAY, first_price_bp=5_000)


def test_a_quote_lands_on_its_own_bar_and_a_crossed_quote_is_refused() -> None:
    bars = bars_from_trades(
        [],
        interval_min=1_440,
        start_ms=DAY0,
        end_ms=DAY0 + MS_PER_DAY,
        first_price_bp=5_000,
        quotes={DAY0 + MS_PER_DAY: Quote(yes_bid_bp=4_900, yes_ask_bp=5_100, open_interest=42)},
    )
    assert (bars[0].yes_bid_bp, bars[0].yes_ask_bp, bars[0].open_interest) == (None, None, None)
    assert (bars[1].yes_bid_bp, bars[1].yes_ask_bp, bars[1].open_interest) == (4_900, 5_100, 42)
    with pytest.raises(SchemaError):
        bars_from_trades(
            [],
            interval_min=1_440,
            start_ms=DAY0,
            end_ms=DAY0,
            first_price_bp=5_000,
            quotes={DAY0: Quote(yes_bid_bp=5_200, yes_ask_bp=5_100)},
        )


def test_the_hourly_grid_splits_one_day_into_twenty_four_bars() -> None:
    bars = bars_from_trades(
        [trade(DAY0 + 5 * MS_PER_HOUR + 7, 5_500, 2_000)],
        interval_min=60,
        start_ms=DAY0,
        end_ms=DAY0 + 23 * MS_PER_HOUR,
        first_price_bp=5_000,
    )
    assert len(bars) == 24
    assert bars[5].close_bp == 5_500 and bars[5].n_trades == 1
    assert bars[6].close_bp == 5_500 and bars[6].volume_milli == 0


def test_traded_bars_volume_total_and_median_daily_volume_read_the_tape() -> None:
    bars = bars_from_trades(
        [
            trade(DAY0, 5_000, 1_000),
            trade(DAY0 + MS_PER_DAY, 5_100, 3_000),
            trade(DAY0 + 3 * MS_PER_DAY, 5_200, 5_000),
        ],
        interval_min=1_440,
        start_ms=DAY0,
        end_ms=DAY0 + 3 * MS_PER_DAY,
        first_price_bp=5_000,
    )
    assert traded_bars(bars) == 3
    assert volume_milli_total(bars) == 9_000
    assert median_daily_volume_milli(bars) == 1_000  # days are 1000, 3000, 0, 5000; lower middle of four


# --------------------------------------------------------------------------------------------------
# 7.4 The window and the ten filters
# --------------------------------------------------------------------------------------------------
def test_window_bounds_is_the_twelve_month_window_on_resolved_at() -> None:
    start_ms, end_ms = window_bounds(config(), [])
    assert (start_ms, end_ms) == (FREEZE_MS - 365 * MS_PER_DAY, FREEZE_MS - MS_PER_DAY)


def test_a_demo_only_build_takes_its_window_from_its_own_markets() -> None:
    old = facts(
        id="demo-brexit-2016",
        provider="demo",
        created_at_ms=ms_from_iso_date("2016-02-01") + 3 * MS_PER_HOUR,
        resolved_at_ms=ms_from_iso_date("2016-06-24") + 7 * MS_PER_HOUR,
    )
    start_ms, end_ms = window_bounds(config(providers=("demo",)), [old])
    assert start_ms == ms_from_iso_date("2016-02-01")
    assert end_ms == old.resolved_at_ms + 1
    assert start_ms % MS_PER_DAY == 0


def test_a_market_that_passes_every_filter_has_no_removal_reason() -> None:
    assert reason_for() is None


@pytest.mark.parametrize(
    ("key", "overrides"),
    [
        ("resolution", {"resolution": 2}),
        ("binary", {"tags": ("multiple_choice",)}),
        ("no_leak", {"resolved_at_ms": FREEZE_MS + MS_PER_DAY}),
        ("window", {"resolved_at_ms": WINDOW_START_MS - MS_PER_DAY}),
        ("opened_early", {"created_at_ms": WINDOW_START_MS - 91 * MS_PER_DAY}),
        ("self_resolved", {"resolution_source": SELF_RESOLVED_SOURCE}),
        ("kalshi_shards", {"provider_id": "KXMVEDOW-26-D"}),
        ("min_trades", {"n_trades": 4, "unique_bettors": 2}),
        ("min_life", {"resolved_at_ms": WINDOW_START_MS + 12 * MS_PER_DAY}),
        # A market with no activity at all: no print in any bar and no size in any bar either.
        ("density", {"bar_n_trades": tuple([0] * 61), "bar_volumes_milli": tuple([0] * 61)}),
    ],
)
def test_each_filter_removes_the_market_built_to_fail_it(key: str, overrides: dict[str, object]) -> None:
    assert reason_for(**overrides) == key


def test_the_kalshi_series_table_removes_a_shard_whose_ticker_looks_innocent() -> None:
    assert reason_for(provider_id="KXQUIET-26-A") is None
    assert (
        removal_reason(
            facts(provider_id="KXQUIET-26-A"),
            config(),
            window_start_ms=WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
            excluded_series=frozenset({"KXQUIET"}),
        )
        == "kalshi_shards"
    )


def test_self_resolved_reads_the_marker_or_the_tag_and_can_be_switched_off() -> None:
    """D3 records creator resolution in ``resolution_source`` because ``Market`` has no resolver field."""
    assert reason_for(resolution_source=SELF_RESOLVED_SOURCE) == "self_resolved"
    assert reason_for(tags=(SELF_RESOLVED_TAG,)) == "self_resolved"
    assert (
        removal_reason(
            facts(resolution_source=SELF_RESOLVED_SOURCE),
            config(exclude_self_resolved=False),
            window_start_ms=WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
        )
        is None
    )


def test_min_trades_passes_on_unique_bettors_alone_and_fails_when_both_are_thin() -> None:
    assert reason_for(n_trades=1, unique_bettors=30) is None
    assert reason_for(n_trades=50, unique_bettors=None) is None
    assert reason_for(n_trades=49, unique_bettors=29) == "min_trades"


def test_the_window_filters_are_skipped_for_a_demo_build() -> None:
    old = facts(
        id="demo-brexit-2016",
        provider="demo",
        created_at_ms=ms_from_iso_date("2016-02-01"),
        resolved_at_ms=ms_from_iso_date("2016-06-24"),
        bar_times_ms=tuple(ms_from_iso_date("2016-02-01") + i * MS_PER_DAY for i in range(145)),
        closes_bp=tuple(5_000 for _ in range(145)),
        bar_volumes_milli=tuple(0 for _ in range(145)),
        bar_n_trades=tuple(1 for _ in range(145)),
    )
    kwargs = {
        "window_start_ms": ms_from_iso_date("2016-02-01"),
        "window_end_ms": ms_from_iso_date("2016-06-25"),
        "freeze_ms": FREEZE_MS,
    }
    assert removal_reason(old, config(providers=("demo",)), window_checks=False, **kwargs) is None  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# 7.5 Hardness tags
# --------------------------------------------------------------------------------------------------
def test_trivial_is_a_market_that_was_never_in_doubt() -> None:
    certain = facts(closes_bp=tuple(9_600 + i for i in range(61)))
    assert "trivial" in hardness_tags_for(certain, illiquid_boundary_milli=-1)
    doubtful = facts(closes_bp=tuple(4_000 + 10 * i for i in range(61)))
    assert "trivial" not in hardness_tags_for(doubtful, illiquid_boundary_milli=-1)


def test_upset_is_the_last_thirty_days_of_price_on_the_wrong_side_of_the_outcome() -> None:
    favoured_but_lost = facts(resolution=0, closes_bp=tuple(6_000 + 10 * i for i in range(61)))
    assert "upset" in hardness_tags_for(favoured_but_lost, illiquid_boundary_milli=-1)
    favoured_and_won = facts(resolution=1, closes_bp=tuple(6_000 + 10 * i for i in range(61)))
    assert "upset" not in hardness_tags_for(favoured_and_won, illiquid_boundary_milli=-1)


def test_upset_reads_the_last_thirty_days_and_not_the_last_thirty_bars() -> None:
    """On an hourly grid the two readings disagree, and section 7.5 says days."""
    created = DAY0
    resolved = created + 99 * MS_PER_HOUR
    hourly = facts(
        interval_min=60,
        created_at_ms=created,
        close_at_ms=resolved - MS_PER_HOUR,
        resolved_at_ms=resolved,
        resolution=1,
        bar_times_ms=tuple(created + i * MS_PER_HOUR for i in range(100)),
        closes_bp=tuple([2_000] * 70 + [9_000] * 30),
        bar_volumes_milli=tuple(1_000 for _ in range(100)),
        bar_n_trades=tuple(1 for _ in range(100)),
    )
    # The whole life is inside thirty days, so the mean is 4100 and the market was an upset; the last
    # thirty *bars* average 9000 and would have hidden it.
    assert "upset" in hardness_tags_for(hourly, illiquid_boundary_milli=-1)


def test_whipsaw_needs_more_than_four_crossings_of_the_midpoint() -> None:
    four = facts(closes_bp=(4_000, 6_000, 4_000, 6_000, 4_000))
    assert "whipsaw" not in hardness_tags_for(four, illiquid_boundary_milli=-1)
    six = facts(closes_bp=(4_000, 6_000, 4_000, 6_000, 4_000, 6_000, 4_000))
    assert "whipsaw" in hardness_tags_for(six, illiquid_boundary_milli=-1)


def test_illiquid_is_the_bottom_decile_of_its_own_provider_slice() -> None:
    slice_of_ten = [
        facts(
            id=f"kalshi-KXVOL-26-{index:02d}",
            bar_volumes_milli=tuple((index + 1) * 1_000 for _ in range(61)),
        )
        for index in range(ILLIQUID_DECILE_MIN_SLICE)
    ]
    boundaries = illiquid_boundaries(slice_of_ten)
    assert boundaries == {"kalshi": 1_000}
    tagged = [
        item.id
        for item in slice_of_ten
        if "illiquid" in hardness_tags_for(item, illiquid_boundary_milli=boundaries["kalshi"])
    ]
    assert tagged == ["kalshi-KXVOL-26-00"]


def test_a_provider_slice_under_ten_markets_has_no_decile_and_tags_nothing() -> None:
    boundaries = illiquid_boundaries([facts(id=f"kalshi-KXVOL-26-{i}") for i in range(9)])
    assert boundaries == {"kalshi": -1}
    assert "illiquid" not in hardness_tags_for(facts(), illiquid_boundary_milli=-1)


# --------------------------------------------------------------------------------------------------
# 7.7 The split
# --------------------------------------------------------------------------------------------------
def test_the_month_edges_are_the_contract_offsets_and_the_two_cuts(tmp_path: Path) -> None:
    """The thirteen edges stay; the two headline cuts are the count quantiles and no longer month edges.

    Ruling R247 replaced the calendar cut of section 7.7 and R290 made the cut key ``fold_key_ms``. The
    month edges are still in the manifest, because they are the rolling folds' edges of 12.7, so this
    test keeps every assertion it made about them and replaces the two it made about the cuts with the
    post-ruling statement: each cut is the fold key of the market at its quantile index, computed here
    by hand from the sorted keys rather than read back off the object that produced it.
    """
    result = build(tmp_path)
    split = result.manifest.split
    edges = split.month_edges_ms
    assert len(edges) == 13
    assert [(edge - edges[0]) // MS_PER_DAY for edge in edges] == [
        0, 30, 60, 91, 121, 152, 182, 212, 243, 273, 304, 334, 365,
    ]
    assert edges == month_edges_for(WINDOW_START_MS)
    plan = result.plan
    assert plan is not None
    keys = sorted(plan.fold_keys[market_id] for market_id in result.kept_ids)
    n = len(keys)
    assert (split.train_end_ms, split.validation_end_ms) == (
        keys[(n * 600) // 1_000],
        keys[(n * 800) // 1_000],
    )
    # The cut is a bar open, so a run can clip t0_ms and t1_ms to it (7.7).
    assert split.train_end_ms % MS_PER_DAY == 0 and split.validation_end_ms % MS_PER_DAY == 0
    # ... and it is NOT the calendar cut this ruling replaced, on this dataset.
    assert split.train_end_ms != edges[8]


def test_the_split_is_chronological_and_no_market_is_in_two_folds(tmp_path: Path) -> None:
    result = build(tmp_path)
    split = result.manifest.split
    by_fold: dict[str, list[int]] = {"train": [], "validation": [], "sealed": []}
    for market_id, fold in result.folds.items():
        payload = json.loads((result.path / "markets" / f"{market_id}.json").read_text(encoding="utf-8"))
        by_fold[fold].append(int(payload["resolved_at_ms"]))
    assert sum(len(rows) for rows in by_fold.values()) == len(result.kept_ids) == 5
    assert len(set(result.folds)) == len(result.folds)  # one fold per market, by construction
    assert max(by_fold["train"]) < split.train_end_ms <= min(by_fold["validation"])
    assert max(by_fold["validation"]) < split.validation_end_ms <= min(by_fold["sealed"])
    assert max(by_fold["sealed"]) < WINDOW_END_MS
    assert (split.n_train, split.n_validation, split.n_sealed) == (3, 1, 1)


# --------------------------------------------------------------------------------------------------
# 7.8 The build, the manifest, the hash
# --------------------------------------------------------------------------------------------------
def test_the_build_keeps_the_five_good_markets_and_counts_every_filter(tmp_path: Path) -> None:
    result = build(tmp_path)
    assert set(result.kept_ids) == set(KEPT_IDS)
    assert set(result.removed) == set(REMOVED_FILTER_KEYS)
    assert result.removed == {
        "window": 1,
        "opened_early": 1,
        "binary": 1,
        "min_trades": 1,
        "min_life": 1,
        "density": 1,
        "self_resolved": 1,
        "kalshi_shards": 1,
        "resolution": 0,
        "no_leak": 1,
    }
    assert sum(result.removed.values()) + len(result.kept_ids) == len(staged_markets())
    counts = result.manifest.counts
    assert counts.markets == 5
    assert dict(counts.per_provider) == {"kalshi": 4, "manifold": 1}
    assert counts.resolution_yes + counts.resolution_no == 5
    assert dict(counts.hardness_tags) == {"trivial": 1, "upset": 1, "whipsaw": 1}


def test_the_manifest_validates_against_its_schema_and_carries_the_build(tmp_path: Path) -> None:
    result = build(tmp_path, notes="fixture build")
    payload = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    validate_against_schema("dataset.v1.json", payload, where="manifest")
    assert payload["schema_version"] == "dataset.v1"
    assert payload["sealed"] is False
    assert payload["freeze_ms"] == FREEZE_MS
    assert payload["window"] == {"start_ms": WINDOW_START_MS, "end_ms": WINDOW_END_MS}
    assert payload["filters"]["config"] == config().to_dict()
    assert payload["filters"]["config"]["limit_per_provider"] == 0  # None renders as 0, never as null
    assert payload["built_by"]["contract_version"] == "2.0"
    assert "fixture build" in payload["notes"]
    assert "illiquid decile boundary" in payload["notes"]


def test_the_dataset_hash_is_the_contract_formula_over_the_files_on_disk(tmp_path: Path) -> None:
    result = build(tmp_path)
    rows: list[tuple[str, str]] = []
    for directory in ("markets", "news", "wiki_asof"):
        for path in sorted((result.path / directory).rglob("*")):
            if path.is_file():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                rows.append((path.relative_to(result.path).as_posix(), digest))
    rows.sort()
    blob = "\n".join(f"{name} {digest}" for name, digest in rows) + "\n"
    assert result.dataset_hash == hashlib.sha256(blob.encode("utf-8")).hexdigest()
    assert [entry.path for entry in result.manifest.files] == [name for name, _ in rows]
    assert all(not entry.path.endswith("manifest.json") for entry in result.manifest.files)


def test_every_written_file_is_utf8_lf_and_canonical(tmp_path: Path) -> None:
    result = build(tmp_path)
    written = sorted(path for path in result.path.rglob("*") if path.is_file())
    assert len(written) == len(result.manifest.files) + 1  # the three directories plus manifest.json
    for path in written:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        assert b"\r" not in raw
        assert text.endswith("\n") and not text.endswith("\n\n")
        for line in text.splitlines():
            assert canonical_json(json.loads(line)) == line
        if path.suffix == ".json":
            assert len(text.splitlines()) == 1


def test_the_quality_block_is_recomputed_from_the_tape(tmp_path: Path) -> None:
    result = build(tmp_path)
    staged = {str(row["id"]): row for row in staged_markets()}
    payload = json.loads((result.path / "markets" / "kalshi-KXPRESA-26-A.json").read_text(encoding="utf-8"))
    written = market_facts(payload)
    assert payload["quality"]["traded_bars"] == written.traded_bars
    assert payload["quality"]["volume_milli_total"] == written.volume_milli_total
    assert payload["quality"]["life_days"] == written.life_days
    # the provider's own counts are kept, the tape's are recomputed
    original = staged["kalshi-KXPRESA-26-A"]
    assert payload["quality"]["n_trades"] == original["quality"]["n_trades"]  # type: ignore[index]
    assert payload["trades"] == original["trades"]
    assert payload["hardness_tags"] == list(result.hardness["kalshi-KXPRESA-26-A"])


def test_news_files_are_keyed_by_the_day_of_publication_and_sorted(tmp_path: Path) -> None:
    result = build(tmp_path)
    days = sorted(path.name for path in (result.path / "news").glob("*.jsonl"))
    assert days == ["20251016.jsonl", "20251121.jsonl", "20251203.jsonl", "20251217.jsonl"]
    for path in (result.path / "news").glob("*.jsonl"):
        items = read_jsonl(path)
        assert [(int(str(i["published_at_ms"])), str(i["news_id"])) for i in items] == sorted(
            (int(str(i["published_at_ms"])), str(i["news_id"])) for i in items
        )
        for item in items:
            published_at_ms = int(str(item["published_at_ms"]))
            assert day_key(published_at_ms // MS_PER_DAY * MS_PER_DAY) == path.stem
            assert int(str(item["visible_from_ms"])) == published_at_ms + SAFETY_LAG_MS_DEFAULT
    assert result.manifest.news.n_items == 6
    assert result.manifest.news.n_linked == 4
    # one gdelt item this build's news_sources do not select, and one headline older than every market
    assert result.n_news_dropped == 2


def test_match_ids_are_pruned_to_the_markets_that_survived(tmp_path: Path) -> None:
    result = build(tmp_path)
    kept = set(result.kept_ids)
    linked_to_a_dropped_market = None
    for path in (result.path / "news").glob("*.jsonl"):
        for item in read_jsonl(path):
            ids = [str(mid) for mid in list(item["match_ids"])]  # type: ignore[call-overload]
            scores = list(item["match_scores_permille"])  # type: ignore[call-overload]
            assert len(ids) == len(scores)
            assert all(mid in kept for mid in ids)
            assert ids == sorted(set(ids))
            if str(item["news_id"]) == "wce-20251120-0004":
                linked_to_a_dropped_market = ids
    assert linked_to_a_dropped_market == []  # it named manifold-tooold, which the window dropped


def test_a_background_snapshot_is_written_under_its_market_and_its_asof_day(tmp_path: Path) -> None:
    result = build(tmp_path)
    path = result.path / "wiki_asof" / "kalshi-KXPRESA-26-A" / "20251008.json"
    assert path.is_file()
    item = json.loads(path.read_text(encoding="utf-8"))
    assert item["source"] == BACKGROUND_SOURCE
    assert item["asof_day"] == "2025-10-08"
    assert item["revid"] == 999_001
    assert item["published_at_ms"] <= ms_from_iso_date("2025-10-08") + MS_PER_DAY


def test_a_news_item_published_after_the_freeze_stops_the_build(tmp_path: Path) -> None:
    poisoned = dict(staged_news("wikipedia_current_events")[0])
    poisoned["news_id"] = "wce-20260908-0009"
    poisoned["published_at_ms"] = FREEZE_MS + MS_PER_DAY
    poisoned["visible_from_ms"] = FREEZE_MS + MS_PER_DAY + SAFETY_LAG_MS_DEFAULT
    with pytest.raises(LeakError) as caught:
        build(tmp_path, news_payloads=[*staged_news(), poisoned])
    assert "after the freeze" in str(caught.value)


def test_a_news_item_visible_before_its_safety_lag_stops_the_build(tmp_path: Path) -> None:
    early = dict(staged_news("wikipedia_current_events")[0])
    early["visible_from_ms"] = int(str(early["published_at_ms"]))
    with pytest.raises(LeakError):
        build(tmp_path, news_payloads=[early])
    late = dict(staged_news("wikipedia_current_events")[0])
    late["visible_from_ms"] = int(str(late["published_at_ms"])) + SAFETY_LAG_MS_DEFAULT + 1
    with pytest.raises(SchemaError):
        build(tmp_path, news_payloads=[late])


def test_two_news_items_may_not_share_a_news_id(tmp_path: Path) -> None:
    items = staged_news("wikipedia_current_events")
    with pytest.raises(SchemaError) as caught:
        build(tmp_path, news_payloads=[items[0], dict(items[0])])
    assert "news_id" in str(caught.value)


def test_two_builds_of_the_same_inputs_agree_byte_for_byte(tmp_path: Path) -> None:
    first = build(tmp_path, out_dir=tmp_path / "one", name="y2026")
    second = build(tmp_path, out_dir=tmp_path / "two", name="y2026")
    assert first.dataset_hash == second.dataset_hash
    assert (first.path / "manifest.json").read_bytes() == (second.path / "manifest.json").read_bytes()


def test_the_cap_is_applied_after_the_filters_and_not_before(tmp_path: Path) -> None:
    """Section 7.4's ``limit_per_provider``, moved behind the filters.

    Applied before them, the cap spent its budget on markets a filter was about to drop: the first real
    build staged 400 Kalshi rows, every one of which the ``min_trades`` filter then removed. The proof
    that it now runs afterwards is that the removed counts of a capped build are **identical** to those
    of an uncapped one, market for market and filter for filter: every staged market still reaches every
    filter, and the cap decides only between the survivors.
    """
    uncapped = build(tmp_path / "all")
    capped = build(tmp_path / "two", config=config(limit_per_provider=2))
    assert capped.removed == uncapped.removed
    assert sum(capped.removed.values()) == len(staged_markets()) - len(uncapped.kept_ids)
    assert dict(capped.manifest.counts.per_provider) == {"kalshi": 2, "manifold": 1}
    assert set(capped.kept_ids) <= set(uncapped.kept_ids)
    assert capped.manifest.filters.config["limit_per_provider"] == 2


def test_the_cap_reports_what_it_sampled_from(tmp_path: Path) -> None:
    """The pre-cap count per provider per month is in the manifest, so the sample is auditable."""
    result = build(tmp_path, config=config(limit_per_provider=2))
    precap = result.manifest.counts.precap_per_provider_month
    assert sorted(precap) == ["kalshi", "manifold"]
    assert all(len(months) == 12 for months in precap.values())
    assert sum(precap["kalshi"]) == 4, "four Kalshi markets passed every filter"
    assert sum(precap["manifold"]) == 1
    assert sum(sum(months) for months in precap.values()) > result.manifest.counts.markets


def test_an_uncapped_build_reports_the_months_it_kept_everything_from(tmp_path: Path) -> None:
    result = build(tmp_path)
    precap = result.manifest.counts.precap_per_provider_month
    assert sum(sum(months) for months in precap.values()) == result.manifest.counts.markets


def test_the_month_quotas_are_equal_with_the_remainder_to_the_fullest_months() -> None:
    """Pure arithmetic, so it is asserted directly rather than through a build."""
    assert month_quotas([5] * 12, 12) == (1,) * 12
    assert sum(month_quotas([5] * 12, 25)) == 25
    # 14 over twelve months: one each, then the two biggest months take the remainder (ties by month).
    quotas = month_quotas([3, 9, 1, 1, 1, 1, 1, 1, 1, 1, 1, 9], 14)
    assert sum(quotas) == 14
    assert quotas[1] == quotas[11] == 2 and quotas[0] == 1
    # A month with nothing in it cannot fill its quota, so the room goes to the months that can.
    thin = month_quotas([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 7], 12)
    assert sum(thin) == 12 and thin[10] == 5 and thin[11] == 7
    # A limit at or above the total keeps everything, and a limit of zero is no limit at all.
    assert month_quotas([2] * 12, 100) == (2,) * 12
    assert month_quotas([2] * 12, 0) == (2,) * 12


def _month_facts(provider: str, per_month: int) -> list[MarketFacts]:
    """``per_month`` markets in each of the twelve months of the window, all of them filter-clean."""
    edges = month_edges_for(WINDOW_START_MS)
    out: list[MarketFacts] = []
    for month in range(12):
        for index in range(per_month):
            resolved = edges[month] + MS_PER_DAY
            out.append(
                facts(
                    id=f"{provider}-m{month:02d}-{index:02d}",
                    provider=provider,
                    provider_id=f"KX{month:02d}-{index:02d}",
                    created_at_ms=resolved - 60 * MS_PER_DAY,
                    resolved_at_ms=resolved,
                )
            )
    return out


def test_the_cap_draws_from_every_month_so_every_fold_is_populated() -> None:
    """The defect this closes: a capped build put every surviving market in the sealed fold.

    Section 12.7 forbids the optimizer to read that fold, so a dataset whose train and validation folds
    are empty has nothing to train on however many markets it holds.
    """
    candidates = _month_facts("kalshi", 20)
    kept, precap = stratified_cap(
        candidates, limit=24, month_edges_ms=month_edges_for(WINDOW_START_MS), name="y2026"
    )
    assert len(kept) == 24
    assert precap["kalshi"] == (20,) * 12
    edges = month_edges_for(WINDOW_START_MS)
    per_month = [0] * 12
    for item in candidates:
        if item.id in kept:
            per_month[month_index_of(item.resolved_at_ms, edges)] += 1
    assert per_month == [2] * 12, "an equal quota per month"
    folds = {
        "train": sum(per_month[:8]),
        "validation": sum(per_month[8:10]),
        "sealed": sum(per_month[10:]),
    }
    assert all(count > 0 for count in folds.values()), folds


def test_the_sample_is_a_function_of_the_dataset_name_and_nothing_else() -> None:
    candidates = _month_facts("kalshi", 20)
    edges = month_edges_for(WINDOW_START_MS)
    first, _ = stratified_cap(candidates, limit=24, month_edges_ms=edges, name="y2026")
    again, _ = stratified_cap(candidates, limit=24, month_edges_ms=edges, name="y2026")
    other, _ = stratified_cap(candidates, limit=24, month_edges_ms=edges, name="y2027")
    assert first == again, "the same name samples the same dataset, twice and on any machine"
    assert other != first, "a different name is a different dataset"
    assert sample_seed_for("y2026") != sample_seed_for("y2027")
    shuffled, _ = stratified_cap(
        list(reversed(candidates)), limit=24, month_edges_ms=edges, name="y2026"
    )
    assert shuffled == first, "the order the markets arrived in is not an input"


def test_a_cap_larger_than_the_window_keeps_every_market() -> None:
    candidates = _month_facts("kalshi", 2)
    kept, _ = stratified_cap(
        candidates, limit=1_000, month_edges_ms=month_edges_for(WINDOW_START_MS), name="y2026"
    )
    assert kept == frozenset(item.id for item in candidates)


def test_the_cap_is_per_provider(tmp_path: Path) -> None:
    kalshi = _month_facts("kalshi", 3)
    manifold = _month_facts("manifold", 3)
    kept, precap = stratified_cap(
        [*kalshi, *manifold],
        limit=12,
        month_edges_ms=month_edges_for(WINDOW_START_MS),
        name="y2026",
    )
    assert len(kept) == 24, "twelve per provider, not twelve in total"
    assert sorted(precap) == ["kalshi", "manifold"]


def test_a_bars_only_market_passes_min_trades_on_its_traded_bars(tmp_path: Path) -> None:
    """The provider with no settled print tape, section 7.4's third branch.

    A settled Kalshi market answers ``n_trades == 0`` because the exchange publishes no print tape for
    it, not because nobody traded; its candlesticks carry the volume and the open interest of every
    period. Read on prints alone the filter removed the whole provider.
    """
    assert reason_for(tape_kind=TAPE_KIND_BARS_ONLY, n_trades=0, unique_bettors=None) is None
    assert (
        reason_for(tape_kind=TAPE_KIND_PRINTS, n_trades=0, unique_bettors=None) == "min_trades"
    ), "the branch is gated on the tape kind, so a print tape with no print still fails"


def test_a_bars_only_market_with_too_few_traded_bars_still_fails_min_trades() -> None:
    quiet = {
        "tape_kind": TAPE_KIND_BARS_ONLY,
        "n_trades": 0,
        "unique_bettors": None,
        "bar_n_trades": tuple([0] * 61),
        "bar_volumes_milli": tuple([1_000] * 19 + [0] * 42),
    }
    assert reason_for(**quiet) == "min_trades", "nineteen traded bars is under the default of twenty"
    busy = dict(quiet)
    busy["bar_volumes_milli"] = tuple([1_000] * 20 + [0] * 41)
    assert reason_for(**busy) is None, "twenty traded bars is the default bar"
    stricter = removal_reason(
        facts(**busy),
        config(min_traded_bars=21),
        window_start_ms=WINDOW_START_MS,
        window_end_ms=WINDOW_END_MS,
        freeze_ms=FREEZE_MS,
    )
    assert stricter == "min_trades", "the bar is a BuildConfig field and moving it moves the answer"
    # The two filters are independent: fourteen traded bars over sixty days of life is under the density
    # bar of 250 permille whatever the bars-only branch of min_trades allows.
    sparse = dict(quiet)
    sparse["bar_volumes_milli"] = tuple([1_000] * 14 + [0] * 47)
    assert (
        removal_reason(
            facts(**sparse),
            config(min_traded_bars=10),
            window_start_ms=WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
        )
        == "density"
    )


def test_a_bar_with_size_and_no_print_is_a_traded_bar() -> None:
    """Both readings are needed: the demo pack has prints with no size, Kalshi has size with no print."""
    prints_only = facts(bar_volumes_milli=tuple([0] * 61), bar_n_trades=tuple([2] * 61))
    size_only = facts(bar_volumes_milli=tuple([1_000] * 61), bar_n_trades=tuple([0] * 61))
    neither = facts(bar_volumes_milli=tuple([0] * 61), bar_n_trades=tuple([0] * 61))
    assert prints_only.traded_bars == 61
    assert size_only.traded_bars == 61
    assert neither.traded_bars == 0


def test_the_manifest_counts_the_bars_only_markets_and_the_category_fallbacks(tmp_path: Path) -> None:
    """Both numbers exist because a zero and a measurement failure read the same without them."""
    staged_by_id = {str(row["id"]): row for row in staged_markets()}
    bars_only = dict(staged_by_id["kalshi-KXFED-26-C"])
    quality = dict(bars_only["quality"])  # type: ignore[call-overload]
    quality["tape_kind"] = TAPE_KIND_BARS_ONLY
    quality["n_trades"] = 0
    quality["unique_bettors"] = None
    bars_only["quality"] = quality
    bars_only["trades"] = []
    # Its series is absent from the map this build is handed, and nothing named a category for it, so it
    # is one of the fallbacks the manifest counts.
    bars_only["category"] = "other"
    payloads = [bars_only if row["id"] == "kalshi-KXFED-26-C" else row for row in staged_markets()]
    result = build(tmp_path, market_payloads=payloads, mapped_series=("KXPRESA", "KXCPI"))
    counts = result.manifest.counts
    assert counts.n_bars_only == 1
    assert "kalshi-KXFED-26-C" in result.kept_ids, "it passed min_trades on its traded bars"
    assert counts.n_category_fallback == 1, "one kept market on the fallback category, series unmapped"
    assert counts.per_category["other"] == 1
    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["n_bars_only"] == 1
    assert manifest["counts"]["n_category_fallback"] == 1
    # A market on the fallback category whose series the map *does* name is not a fallback: the map
    # answered, and ``other`` was the answer.
    mapped = build(
        tmp_path / "mapped", market_payloads=payloads, mapped_series=("KXPRESA", "KXCPI", "KXFED")
    )
    assert mapped.manifest.counts.n_category_fallback == 0


def test_a_build_with_no_bars_only_market_says_nothing_about_it(tmp_path: Path) -> None:
    result = build(tmp_path)
    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    assert "n_bars_only" not in manifest["counts"], "a zero is not news and would move every old hash"
    assert result.manifest.counts.n_bars_only == 0


def test_the_build_links_the_news_archive_to_the_markets_it_kept(tmp_path: Path) -> None:
    """The step that was missing: ``link_items`` existed and nothing in the build path called it.

    The first real dataset carried 7 391 Wikipedia Current events items and not one of them was linked
    to a market; every link it had came from a Manifold comment, which states its own market. Per-market
    news is what the news-reading families and the LLM forecaster read, so an unlinked archive disables
    them however complete it is.
    """
    linked = link_news_payloads(staged_news("wikipedia_current_events"), staged_markets("kalshi"))
    assert len(linked) == len(staged_news("wikipedia_current_events"))
    by_id = {str(item["news_id"]): item for item in linked}
    congress = by_id["wce-20251015-0001"]
    assert "kalshi-KXPRESA-26-A" in congress["match_ids"]  # type: ignore[operator]
    scores = congress["match_scores_permille"]
    assert isinstance(scores, list) and len(scores) == len(congress["match_ids"])  # type: ignore[arg-type]
    assert all(LINK_THRESHOLD_PERMILLE <= int(score) <= 1_000 for score in scores)
    # The input is untouched and the answer is the same twice.
    assert staged_news("wikipedia_current_events") == staged_news("wikipedia_current_events")
    assert link_news_payloads(staged_news("wikipedia_current_events"), staged_markets("kalshi")) == linked


def test_a_link_the_venue_stated_survives_the_build_linker(tmp_path: Path) -> None:
    """Ruling R95 through the build path: a comment's own link is kept at its own score."""
    comments = staged_news("manifold_comment")
    assert comments, "the fixture stages at least one comment"
    linked = {str(item["news_id"]): item for item in link_news_payloads(comments, staged_markets())}
    for item in comments:
        before = dict(zip(item["match_ids"], item["match_scores_permille"], strict=True))  # type: ignore[call-overload]
        after = dict(
            zip(
                linked[str(item["news_id"])]["match_ids"],  # type: ignore[call-overload]
                linked[str(item["news_id"])]["match_scores_permille"],  # type: ignore[call-overload]
                strict=True,
            )
        )
        for market_id, score in before.items():
            assert after.get(market_id, 0) >= score


def test_a_market_with_no_subject_now_gets_the_news_of_its_keywords() -> None:
    """The renormalised score of section 7.6, seen from the builder.

    The market below is the shape of effectively every real market: no ``wiki_subjects`` at all. Under
    the 600/400 split its keyword overlap of 333 permille scored 133, under a threshold of 150, and the
    item was not linked; renormalised over the one kind of evidence the market has, the same overlap
    scores 333 and the link is stored with that score.
    """
    market_payload = dict(
        next(row for row in staged_markets("manifold") if row["id"] == "manifold-abc123")
    )
    market_payload["wiki_subjects"] = []
    item = dict(
        next(
            row
            for row in staged_news("wikipedia_current_events")
            if row["news_id"] == "wce-20251216-0002"
        )
    )
    item["match_ids"] = []
    item["match_scores_permille"] = []
    (linked,) = link_news_payloads([item], [market_payload])
    assert linked["match_ids"] == ["manifold-abc123"]
    (score,) = linked["match_scores_permille"]  # type: ignore[misc]
    assert score == 333, "one of the question's three keywords is in the item"
    assert (400 * score) // 1_000 < LINK_THRESHOLD_PERMILLE, "what the old weighting scored"


def test_a_dataset_is_never_rebuilt_in_place_without_force(tmp_path: Path) -> None:
    build(tmp_path)
    with pytest.raises(InvalidConfigError) as caught:
        build(tmp_path)
    assert "never edited in place" in str(caught.value)
    again = build(tmp_path, overwrite=True)
    assert again.dataset_hash


def test_a_market_on_another_grid_than_the_dataset_is_refused(tmp_path: Path) -> None:
    hourly = dict(staged_markets("kalshi")[0])
    hourly["interval_min"] = 60
    with pytest.raises(InvalidConfigError) as caught:
        build(tmp_path, market_payloads=[hourly])
    assert "one grid per dataset" in str(caught.value)


def test_a_market_from_a_provider_the_build_did_not_ask_for_is_refused(tmp_path: Path) -> None:
    with pytest.raises(InvalidConfigError):
        build(tmp_path, config=config(providers=("kalshi",)), market_payloads=staged_markets("manifold"))


def test_two_markets_may_not_share_an_id(tmp_path: Path) -> None:
    rows = staged_markets("kalshi")
    with pytest.raises(InvalidConfigError):
        build(tmp_path, market_payloads=[rows[0], dict(rows[0])])


def test_the_object_path_and_the_payload_path_build_the_same_dataset(tmp_path: Path) -> None:
    payloads = staged_markets()
    markets = [market_from_payload(payload, where="fixture") for payload in payloads]
    from_objects = build_dataset(
        out_dir=tmp_path / "objects",
        config=config(),
        markets=markets,
        news=(),
        excluded_series=("KXMVE",),
        name="y2026",
    )
    from_payloads = build_dataset_from_payloads(
        out_dir=tmp_path / "payloads",
        config=config(),
        market_payloads=payloads,
        excluded_series=("KXMVE",),
        name="y2026",
    )
    assert from_objects.dataset_hash == from_payloads.dataset_hash


def test_as_plain_dict_renders_a_model_and_passes_a_payload_through() -> None:
    payload = staged_markets("kalshi")[0]
    market = market_from_payload(payload, where="fixture")
    assert as_plain_dict(market) == as_plain_dict(payload) == payload
    with pytest.raises(SchemaError):
        as_plain_dict(object())


def test_build_config_from_manifest_round_trips_and_slides_the_freeze(tmp_path: Path) -> None:
    result = build(tmp_path, config=config(min_trades=11, limit_per_provider=3, window_days=200))
    manifest = load_manifest(result.path)
    same = build_config_from_manifest(manifest)
    assert same == config(min_trades=11, limit_per_provider=3, window_days=200)
    slid = build_config_from_manifest(manifest, freeze_date="2026-10-01")
    assert slid.freeze_date == "2026-10-01"
    assert slid.freeze_ms == ms_from_iso_date("2026-10-01")
    assert slid.providers == same.providers and slid.min_trades == same.min_trades


# --------------------------------------------------------------------------------------------------
# The dataset D1 has to be able to read, seal and verify
# --------------------------------------------------------------------------------------------------
def test_the_built_dataset_loads_seals_verifies_and_fails_on_a_changed_byte(tmp_path: Path) -> None:
    result = build(tmp_path)
    dataset = load_dataset(result.path, verify=True)
    assert [meta.id for meta in dataset.metas] == list(result.kept_ids)
    assert {meta.id: meta.fold for meta in dataset.metas} == result.folds
    assert {meta.id: tuple(meta.hardness_tags) for meta in dataset.metas} == result.hardness

    sealed = seal_dataset(result.path)
    assert sealed.sealed is True
    assert sealed.dataset_hash == result.dataset_hash  # nothing but the flag moved
    assert verify_dataset_report(result.path).ok

    victim = result.path / "markets" / f"{result.kept_ids[0]}.json"
    victim.write_bytes(victim.read_bytes().replace(b'"notes":""', b'"notes":" "'))
    report = verify_dataset_report(result.path)
    assert report.ok is False
    assert report.mismatched_files == (f"markets/{result.kept_ids[0]}.json",)


# --------------------------------------------------------------------------------------------------
# The command group
# --------------------------------------------------------------------------------------------------
def test_the_group_runs_as_a_module() -> None:
    """U4 wires the group into ``pmx`` in wave 5; until then it has to run on its own."""
    done = subprocess.run(
        [sys.executable, "-m", "pmx.cli_data", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0
    for command in ("import", "news", "build", "refresh", "seal", "verify", "status", "migrate-v1"):
        assert command in done.stdout


def test_no_subcommand_prints_the_help_and_returns_two(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_data.main([]) == 2
    assert "build" in capsys.readouterr().out


def test_build_seal_verify_and_status_through_the_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_dir = tmp_path / "y2026"
    argv = [
        "build",
        "--provider", "kalshi,manifold",
        "--freeze", FREEZE_DATE,
        "--offline",
        "--no-seal",
        "--news-source", "manifold_comment,wikipedia_current_events",
        "--staging", str(STAGING),
        "--out", str(out_dir),
    ]
    assert cli_data.main(argv) == 0
    printed = capsys.readouterr().out
    assert "markets    5" in printed
    assert "kalshi_shards=1" in printed
    assert "train 3" in printed

    assert cli_data.main(["seal", "--dataset", str(out_dir)]) == 0
    assert "sealed y2026" in capsys.readouterr().out
    assert load_manifest(out_dir).sealed is True

    assert cli_data.main(["verify", "--dataset", str(out_dir)]) == 0
    assert "verified" in capsys.readouterr().out

    assert cli_data.main(["status", "--dataset", str(out_dir)]) == 0
    status = capsys.readouterr().out
    assert "sealed     true" in status
    assert "removed    binary=1" in status

    assert cli_data.main(["status", "--dataset", str(out_dir), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["name"] == "y2026"
    validate_against_schema("dataset.v1.json", payload, where="manifest")


def test_verify_returns_one_and_names_the_file_after_a_changed_byte(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = build(tmp_path)
    capsys.readouterr()
    victim = result.path / "markets" / f"{result.kept_ids[0]}.json"
    victim.write_bytes(victim.read_bytes().replace(b'"notes":""', b'"notes":"x"'))
    assert cli_data.main(["verify", "--dataset", str(result.path)]) == 1
    captured = capsys.readouterr()
    assert "MISMATCH" in captured.err
    assert f"markets/{result.kept_ids[0]}.json" in captured.err


def test_a_pmx_error_becomes_exit_code_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = cli_data.main(
        [
            "build",
            "--provider", "kalshi",
            "--freeze", FREEZE_DATE,
            "--offline",
            "--staging", str(tmp_path / "nothing-staged"),
            "--out", str(tmp_path / "y2026"),
        ]
    )
    assert code == 1
    assert "no staged import" in capsys.readouterr().err


def test_import_stages_exactly_what_the_importer_returned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The network path with the two entry points the CLI resolves by name replaced by stubs."""
    seen: dict[str, object] = {}

    def fake_importer(
        *,
        client: object,
        window_start_ms: int,
        window_end_ms: int,
        freeze_ms: int,
        limit: int | None = None,
        interval_min: int = 1_440,
    ) -> Sequence[object]:
        seen.update(
            client=client,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            freeze_ms=freeze_ms,
            limit=limit,
            interval_min=interval_min,
        )
        return tuple(reversed(staged_markets("kalshi")))  # returned out of canonical order on purpose

    monkeypatch.setattr(cli_data, "_load_importer", lambda provider: fake_importer)
    monkeypatch.setattr(cli_data, "_make_client", lambda **kwargs: kwargs)
    staging = tmp_path / "staging"
    code = cli_data.main(
        ["import", "kalshi", "--freeze", FREEZE_DATE, "--staging", str(staging), "--limit", "9"]
    )
    assert code == 0
    assert seen["window_start_ms"] == WINDOW_START_MS
    assert seen["window_end_ms"] == WINDOW_END_MS
    assert seen["freeze_ms"] == FREEZE_MS
    assert seen["limit"] == 9
    assert seen["interval_min"] == 1_440
    assert isinstance(seen["client"], dict) and "kalshi" in str(seen["client"]["base_url"])

    staged = read_jsonl(staging / "markets" / "kalshi.jsonl")
    assert [str(row["id"]) for row in staged] == [
        str(row["id"]) for row in sorted(staged_markets("kalshi"), key=lambda r: (r["resolved_at_ms"], r["id"]))
    ]
    assert "staged 6 kalshi markets" in capsys.readouterr().out


def test_news_fetch_stages_each_day_with_the_lag_the_build_will_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    days: list[int] = []
    item = dict(staged_news("wikipedia_current_events")[0])
    item["visible_from_ms"] = int(str(item["published_at_ms"]))  # a fetcher that stamped the wrong lag

    def fake_fetcher(*, client: object, day_start_ms: int, safety_lag_ms: int = 0) -> Sequence[object]:
        days.append(day_start_ms)
        return (dict(item, news_id=f"wce-20251015-{len(days):04d}"),) if len(days) < 3 else ()

    monkeypatch.setattr(cli_data, "_load_day_fetcher", lambda source: fake_fetcher)
    monkeypatch.setattr(cli_data, "_make_client", lambda **kwargs: kwargs)
    staging = tmp_path / "staging"
    code = cli_data.main(
        [
            "news", "fetch",
            "--freeze", FREEZE_DATE,
            "--source", "wikipedia_current_events",
            "--staging", str(staging),
            "--days", "5",
            "--safety-lag-ms", "3600000",
        ]
    )
    assert code == 0
    assert len(days) == 5
    assert days == sorted(days)
    assert days[-1] == (FREEZE_MS - MS_PER_DAY)
    assert all(day % MS_PER_DAY == 0 for day in days)
    staged = read_jsonl(staging / "news" / "wikipedia_current_events.jsonl")
    assert len(staged) == 2
    for row in staged:
        assert int(str(row["visible_from_ms"])) == int(str(row["published_at_ms"])) + 3_600_000


def test_refresh_reuses_the_filters_and_refuses_to_edit_the_old_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = build(tmp_path, config=config(min_trades=11))
    monkeypatch.setattr(cli_data, "_staged_markets", lambda staging, providers: staged_markets(*providers))
    monkeypatch.setattr(cli_data, "_staged_news", lambda staging: staged_news())
    assert (
        cli_data.main(
            [
                "refresh",
                "--dataset", str(first.path),
                "--freeze", "2026-09-08",
                "--out", str(tmp_path / "y2026b"),
                "--offline",
                "--no-seal",
            ]
        )
        == 0
    )
    capsys.readouterr()
    refreshed = load_manifest(tmp_path / "y2026b")
    assert refreshed.freeze_date == "2026-09-08"
    assert refreshed.filters.config["min_trades"] == 11
    assert refreshed.window.start_ms == ms_from_iso_date("2026-09-08") - 365 * MS_PER_DAY
    assert load_manifest(first.path).freeze_date == FREEZE_DATE  # the old dataset is untouched

    code = cli_data.main(
        ["refresh", "--dataset", str(first.path), "--freeze", "2026-09-09", "--out", str(first.path)]
    )
    assert code == 1
    assert "never edited in place" in capsys.readouterr().err


def test_supported_passes_only_the_keywords_a_callable_declares() -> None:
    def narrow(*, client: object, day_start_ms: int) -> None: ...

    def wide(*, client: object, day_start_ms: int, safety_lag_ms: int = 0) -> None: ...

    candidates: Mapping[str, object] = {"safety_lag_ms": 7, "index_offset_by_day": {}}
    assert cli_data._supported(narrow, candidates) == {}
    assert cli_data._supported(wide, candidates) == {"safety_lag_ms": 7}


def test_the_news_floor_drops_an_item_older_than_every_market(tmp_path: Path) -> None:
    """An unbounded archive would sit in ``news_global`` for the whole run and crowd out the real news."""
    from pmx.data.builder import news_floor_ms

    floor_ms = news_floor_ms(window_start_ms=WINDOW_START_MS, opened_early_days=90)
    assert floor_ms == WINDOW_START_MS - 90 * MS_PER_DAY
    result = build(tmp_path)
    written = {
        str(item["news_id"])
        for path in (result.path / "news").glob("*.jsonl")
        for item in read_jsonl(path)
    }
    assert "wce-20230101-0005" not in written
    assert "wce-20251016-0001" not in written  # the id names the page day, not the file day
    assert "wce-20251015-0001" in written
    assert all(int(str(item["published_at_ms"])) >= floor_ms for path in (result.path / "news").glob("*.jsonl")
               for item in read_jsonl(path))


def test_migrate_v1_writes_the_demo_pack_and_seal_refuses_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_dir = tmp_path / "demo_v1"
    assert cli_data.main(["migrate-v1", "--out", str(out_dir)]) == 0
    printed = capsys.readouterr().out
    assert "migrated 12 v1 markets" in printed
    assert "provider   demo=12" in printed
    manifest = load_manifest(out_dir)
    assert manifest.sealed is False and manifest.providers == ("demo",)
    assert manifest.is_demo_pack
    assert verify_dataset_report(out_dir).ok

    # a reconstructed tape is not evidence, so it can never be sealed and therefore never claimed
    assert cli_data.main(["seal", "--dataset", str(out_dir)]) == 1
    assert "reconstructed" in capsys.readouterr().err


def test_the_comment_fetcher_is_told_the_next_free_index_of_each_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``mfc`` id is positional inside its day, so two markets commented on one day must not collide."""
    offsets_seen: list[dict[str, int]] = []
    template = staged_news("manifold_comment")[0]

    def fake_fetch_comments(
        *,
        client: object,
        market: object,
        safety_lag_ms: int = 0,
        index_offset_by_day: Mapping[str, int] | None = None,
    ) -> Sequence[object]:
        offsets_seen.append(dict(index_offset_by_day or {}))
        market_id = getattr(market, "id", "")
        return (dict(template, news_id=f"mfc-20251203-{len(offsets_seen):04d}", match_ids=[market_id]),)

    monkeypatch.setattr(cli_data, "_resolve", _only_for("fetch_comments", fake_fetch_comments))
    monkeypatch.setattr(cli_data, "_make_client", lambda **kwargs: kwargs)
    items = cli_data._fetch_comments(
        staged_markets("manifold")[:3],
        cache_dir=tmp_path / "cache",
        safety_lag_ms=SAFETY_LAG_MS_DEFAULT,
    )
    assert len(items) == 3
    assert offsets_seen == [{}, {"20251203": 1}, {"20251203": 2}]
    assert [str(item["news_id"]) for item in items] == [
        "mfc-20251203-0001",
        "mfc-20251203-0002",
        "mfc-20251203-0003",
    ]


def _only_for(name: str, replacement: object) -> object:
    """A ``_resolve`` that answers ``replacement`` for one entry point and the real thing for the rest."""
    real = cli_data._resolve

    def resolve(module_name: str, attribute: str) -> object:
        return replacement if attribute == name else real(module_name, attribute)

    return resolve


def test_background_snapshots_are_asked_for_every_seventh_day_and_never_at_settlement() -> None:
    created = ms_from_iso_date("2026-01-01") + 9 * MS_PER_HOUR
    resolved = ms_from_iso_date("2026-01-22") + 22 * MS_PER_HOUR
    days = cli_data._asof_days(created, resolved)
    assert days == ["2026-01-01", "2026-01-08", "2026-01-15"]
    assert "2026-01-22" not in days  # never at or after the settling day (section 7.1)
    assert cli_data._asof_days(created, created + 3 * MS_PER_HOUR) == []


def test_a_build_seals_by_default_and_the_sealed_dataset_verifies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-1 asks ``pmx data build`` for a sealed dataset, so sealing is the default and ``--no-seal`` opts
    out. A dataset holding a reconstructed tape then fails loudly instead of being quietly left unsealed.

    ``--audits-root`` is passed for a reason the default makes easy to miss: sealing draws the linker
    audit of 7.6, and :data:`pmx.cli_data.AUDITS_ROOT` is the working directory, which for a test run is
    the repository itself. Without the flag this test writes ``audits/<hash>/linker.json`` into the
    tracked tree of ruling R296, where a reviewer's real verdicts live, on every run of the suite. The
    two assertions below pin both halves: the audit lands under ``tmp_path``, and the repository's own
    ``audits/`` tree is left exactly as the run found it.
    """
    out_dir = tmp_path / "y2026"
    repository_audits = Path(cli_data.AUDITS_ROOT) / linker.AUDITS_DIR
    before = sorted(repository_audits.rglob("*")) if repository_audits.is_dir() else []
    code = cli_data.main(
        [
            "build",
            "--provider", "kalshi,manifold",
            "--freeze", FREEZE_DATE,
            "--offline",
            "--news-source", "manifold_comment,wikipedia_current_events",
            "--staging", str(STAGING),
            "--out", str(out_dir),
            "--audits-root", str(tmp_path),
        ]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "sealed     true" in printed
    manifest = load_manifest(out_dir)
    assert manifest.sealed is True
    assert verify_dataset_report(out_dir).ok
    assert cli_data.main(["verify", "--dataset", str(out_dir)]) == 0
    assert linker.linker_audit_path(tmp_path, manifest.dataset_hash).is_file()
    after = sorted(repository_audits.rglob("*")) if repository_audits.is_dir() else []
    assert after == before


# --------------------------------------------------------------------------------------------------
# 7.7 The count-quantile, cluster-aware cut (decisions D-R1 and D-R2, rulings R247, R248, R290)
#
# The fixtures below are synthetic on purpose: every one of them is a distribution whose folds can be
# worked out by hand, which is the only way a test of a quantile says anything. The staged fixtures of
# tests/fixtures/d6 exercise the same code on real documents, above.
# --------------------------------------------------------------------------------------------------
def dated(market_id: str, day: int, *, event_key: str | None = None, provider: str = "kalshi") -> MarketFacts:
    """A market resolving ``day`` days into the window, optionally inside an event group."""
    resolved = WINDOW_START_MS + day * MS_PER_DAY + 12 * MS_PER_HOUR
    return facts(
        id=market_id,
        provider=provider,
        provider_id=market_id.split("-", 1)[1],
        created_at_ms=WINDOW_START_MS,
        close_at_ms=resolved - MS_PER_DAY,
        resolved_at_ms=resolved,
        event_key=event_key,
    )


def plan_of(rows: Sequence[MarketFacts], **overrides: object) -> SplitPlan:
    kwargs: dict[str, object] = {"interval_min": 1_440, "window_start_ms": WINDOW_START_MS}
    kwargs.update(overrides)
    return plan_folds(rows, **kwargs)  # type: ignore[arg-type]


def test_the_cut_is_a_count_quantile_and_the_realised_counts_are_the_hand_computation() -> None:
    """Ten markets, one per group, resolving on ten different days: 6 / 2 / 2 exactly.

    ``k_train = (10 * 600) // 1000 = 6`` and ``k_validation = 8``, so the cuts are the sixth and the
    eighth fold key in order and the three folds hold six, two and two.
    """
    rows = [dated(f"kalshi-KX{index}", 30 * index) for index in range(10)]
    plan = plan_of(rows)
    assert plan.counts == {"train": 6, "validation": 2, "sealed": 2}
    assert plan.realised_permille == (600, 200, 200)
    keys = sorted(plan.fold_keys.values())
    assert (plan.train_end_ms, plan.validation_end_ms) == (keys[6], keys[8])
    assert plan.cluster_moves == ()
    assert plan.empty_folds == ()


def test_the_split_stays_chronological_market_by_market() -> None:
    rows = [dated(f"kalshi-KX{index}", 7 * index) for index in range(20)]
    plan = plan_of(rows)
    by_fold: dict[str, list[int]] = {"train": [], "validation": [], "sealed": []}
    for item in rows:
        by_fold[plan.folds[item.id]].append(item.resolved_at_ms)
    assert max(by_fold["train"]) < min(by_fold["validation"])
    assert max(by_fold["validation"]) < min(by_fold["sealed"])


def test_a_group_straddling_a_boundary_lands_whole_in_the_later_fold() -> None:
    """Ruling R248: every market of a group takes the fold of its latest-resolving member.

    The pair below resolves on day 30 and on day 300, which the cut puts on opposite sides of
    ``train_end_ms``. The early leg follows the late one, and the manifest reports it as a
    ``cluster_moves`` row: a train price path on the early leg would otherwise encode the sealed
    outcome of the late one, which is exactly what the cross-asset sensor would carry.
    """
    rows = [dated(f"kalshi-KX{index}", 30 * index) for index in range(10)]
    rows.append(dated("kalshi-KXPAIRA-1", 30, event_key="KXPAIR-EV"))
    rows.append(dated("kalshi-KXPAIRB-1", 300, event_key="KXPAIR-EV"))
    plan = plan_of(rows)
    assert plan.folds["kalshi-KXPAIRA-1"] == plan.folds["kalshi-KXPAIRB-1"] == "sealed"
    assert plan.fold_keys["kalshi-KXPAIRA-1"] == plan.fold_keys["kalshi-KXPAIRB-1"]
    moved = {move.market_id: move for move in plan.cluster_moves}
    assert set(moved) == {"kalshi-KXPAIRA-1"}
    assert (moved["kalshi-KXPAIRA-1"].from_fold, moved["kalshi-KXPAIRA-1"].to_fold) == ("train", "sealed")
    assert moved["kalshi-KXPAIRA-1"].group_id == "kalshi:KXPAIR-EV"


def test_a_cluster_beats_the_event_key_and_can_join_two_venues() -> None:
    rows = [dated(f"kalshi-KX{index}", 30 * index) for index in range(10)]
    rows.append(dated("kalshi-KXEARLY-1", 30, event_key="KXEARLY-EV"))
    rows.append(dated("manifold-late", 300, provider="manifold"))
    cluster = "ec-0123456789abcdef"
    plan = plan_of(rows, clusters={"kalshi-KXEARLY-1": cluster, "manifold-late": cluster})
    assert plan.folds["kalshi-KXEARLY-1"] == plan.folds["manifold-late"]
    assert plan.group_ids["kalshi-KXEARLY-1"] == cluster  # the cluster, not the event key
    assert [move.group_id for move in plan.cluster_moves] == [cluster]


def test_the_cluster_rule_is_inside_the_cut_and_does_not_thin_the_train_fold() -> None:
    """Ruling R290, as the measurement that refused the two-step rule.

    Twelve markets in six dense two-leg groups whose legs straddle the calendar. Cutting on each
    market's own resolution and moving each group afterwards moves markets one way only, always later,
    so the train fold can only lose: that reintroduces the inverted pyramid D-R1 was written to fix.
    Cutting on ``fold_key_ms`` holds the shares up to the ties of one bar.
    """
    rows: list[MarketFacts] = []
    for index in range(6):
        rows.append(dated(f"kalshi-KXGA{index}-1", 10 * index, event_key=f"KXG{index}-EV"))
        rows.append(dated(f"kalshi-KXGB{index}-1", 10 * index + 200, event_key=f"KXG{index}-EV"))
    plan = plan_of(rows)
    assert sum(plan.counts.values()) == 12
    assert plan.counts["train"] == 6 and plan.counts["validation"] == 2 and plan.counts["sealed"] == 4
    # What the refused two-step rule does on this same fixture: cut on each market's own bar, then move
    # every group to its latest member's fold. Every early leg leaves the train fold and none arrives.
    own_keys = sorted(item.resolved_at_ms for item in rows)
    train_end_own = own_keys[(12 * 600) // 1_000]
    latest = {
        key: max(item.resolved_at_ms for item in rows if item.event_key == key)
        for key in {item.event_key for item in rows}
    }
    two_step_train = sum(
        1
        for item in rows
        if item.resolved_at_ms < train_end_own and latest[item.event_key] < train_end_own
    )
    assert two_step_train < plan.counts["train"]  # the drift the ruling names, measured


def test_a_dataset_of_one_market_puts_it_in_the_sealed_fold_and_reports_two_empty_folds() -> None:
    """``k_train = k_validation = 0``, so both cuts are the one market's key and it lands sealed.

    The builder reports the empty folds and does not refuse them: a dataset of one market is still a
    dataset. The refusal is ``make_folds``'s (7.7, ``FoldIntegrityError``), because that is the consumer
    for which every paired bound depends on all three folds being populated.
    """
    plan = plan_of([dated("kalshi-KXONE-1", 100)])
    assert plan.counts == {"train": 0, "validation": 0, "sealed": 1}
    assert plan.empty_folds == ("train", "validation")
    assert plan.realised_permille == (0, 0, 1_000)


def test_an_empty_dataset_cuts_at_the_window_open_and_counts_three_zeros() -> None:
    plan = plan_of([])
    assert plan.counts == {"train": 0, "validation": 0, "sealed": 0}
    assert (plan.train_end_ms, plan.validation_end_ms) == (WINDOW_START_MS, WINDOW_START_MS)
    assert plan.realised_permille == (0, 0, 0)
    assert plan.empty_folds == ("train", "validation", "sealed")


def test_every_cut_is_a_bar_open_on_the_hourly_grid_too() -> None:
    rows = [
        facts(
            id=f"kalshi-KXH{index}-1",
            provider_id=f"KXH{index}-1",
            interval_min=60,
            created_at_ms=WINDOW_START_MS,
            close_at_ms=WINDOW_START_MS + (index + 1) * MS_PER_DAY,
            resolved_at_ms=WINDOW_START_MS + (index + 1) * MS_PER_DAY + 90 * 60_000,
        )
        for index in range(10)
    ]
    plan = plan_of(rows, interval_min=60)
    assert plan.train_end_ms % MS_PER_HOUR == 0
    assert plan.validation_end_ms % MS_PER_HOUR == 0
    assert plan.counts == {"train": 6, "validation": 2, "sealed": 2}


def test_the_quantiles_are_validated_rather_than_trusted() -> None:
    """Every malformed pair is an ``InvalidConfigError`` named at the boundary, never an ``IndexError``.

    The last two cases are the ones the first version of the guard let through. 7.7 reads the cut bar off
    the ordered list, ``k = (n * 1_000) // 1_000`` is ``n``, and ``ordered[n]`` is one past the end, so a
    permille of a thousand at either cut escaped from inside :func:`plan_folds` as an ``IndexError``,
    which section 13.1's taxonomy does not admit.
    """
    one = [dated("kalshi-KXA-1", 10)]
    with pytest.raises(InvalidConfigError):
        plan_of(one, quantiles_permille=(800, 600))
    with pytest.raises(InvalidConfigError):
        plan_of(one, quantiles_permille=(600, 1_400))
    with pytest.raises(InvalidConfigError):
        plan_of(one, quantiles_permille=(600,))
    with pytest.raises(InvalidConfigError):
        plan_of(one, quantiles_permille=(600, 1_000))
    with pytest.raises(InvalidConfigError):
        plan_of(one, quantiles_permille=(1_000, 1_000))
    # 999 is legal and is the degenerate cut next to the refusal: the sealed fold keeps the last market.
    ten = [dated(f"kalshi-KX{index}-1", 10 * index) for index in range(10)]
    assert plan_of(ten, quantiles_permille=(998, 999)).counts == {
        "train": 9, "validation": 0, "sealed": 1
    }


def test_the_split_block_is_the_shape_section_7_8_states_after_the_amendment(tmp_path: Path) -> None:
    result = build(tmp_path)
    plan = result.plan
    assert plan is not None
    block = split_block_of(result.manifest.split, plan)
    assert block["method"] == "count_quantile"
    assert block["quantiles_permille"] == [600, 800]
    assert block["n_moved"] == len(plan.cluster_moves)
    assert block["realised_permille"] == list(plan.realised_permille)
    assert block["train_end_date"] == iso_date_from_ms(result.manifest.split.train_end_ms)
    assert block["validation_end_date"] == iso_date_from_ms(result.manifest.split.validation_end_ms)
    assert set(block) >= {
        "month_edges_ms", "train_end_ms", "validation_end_ms", "n_train", "n_validation", "n_sealed",
        "method", "quantiles_permille", "train_end_date", "validation_end_date", "cluster_moves",
        "n_moved", "realised_permille",
    }


def test_the_manifest_blocks_the_build_cannot_yet_write_validate_against_dataset_v1(tmp_path: Path) -> None:
    """Every block of 7.8 amendment C1c added is assembled and is legal against the shipped schema.

    ``dataset.v1.json`` already admits ``purpose``, ``window_days``, ``resolution_span``, the ``split``
    cuts and moves, ``universe`` and ``build`` (C1c landed the schema); what refuses them today is the
    strict pydantic model of ``pmx.data.schema`` and the dataclass of ``pmx.types``, both D1's. This
    test is the proof that the day those two carry the fields the builder's document is already right.
    """
    result = build(tmp_path)
    document = result.manifest_blocks
    # CONTRACT ISSUE, reported by DS1 and owned by amendment C1c: 7.8 and ruling R290 require
    # ``split.realised_permille``, and ``dataset.v1.json``'s ``split`` object (additionalProperties
    # false) does not declare it, so the block the contract asks for is refused by the shipped schema.
    # The two assertions below pin both halves, so the day C1c adds the property this test says so.
    split = document["split"]
    assert isinstance(split, dict)
    assert "realised_permille" in split
    with pytest.raises(SchemaError, match="realised_permille"):
        validate_against_schema("dataset.v1.json", document, where="dataset manifest")
    without = {**document, "split": {k: v for k, v in split.items() if k != "realised_permille"}}
    validate_against_schema("dataset.v1.json", without, where="dataset manifest")
    assert document["purpose"] == "research"
    assert document["window_days"] == 365
    assert isinstance(document["universe"], dict)
    assert isinstance(document["build"], dict)
    span = document["resolution_span"]
    assert isinstance(span, dict) and span["min_ms"] < span["max_ms"]


# --------------------------------------------------------------------------------------------------
# 5.6 window_days and purpose (decisions D-S3 and D-S4, rulings R262, R263)
# --------------------------------------------------------------------------------------------------
def test_a_window_wider_than_the_ceiling_is_refused_with_its_reason(tmp_path: Path) -> None:
    assert WINDOW_DAYS_MAX == 730
    check_window_days(730)  # exactly at the ceiling is legal
    with pytest.raises(InvalidConfigError) as raised:
        check_window_days(731)
    assert raised.value.context["window_days_max"] == 730
    assert "recall" in str(raised.value) and "regime" in str(raised.value)
    with pytest.raises(InvalidConfigError):
        build(tmp_path, config=config(window_days=1_095))


def test_the_ceiling_is_refused_at_the_flag_before_a_socket_is_opened(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``pmx data build --window-days 900`` exits 1 with the reason, and writes no dataset."""
    out = tmp_path / "wide"
    code = cli_data.main(
        [
            "build", "--provider", "kalshi", "--freeze", FREEZE_DATE, "--window-days", "900",
            "--offline", "--out", str(out), "--staging", str(STAGING),
        ]
    )
    assert code == 1
    assert "window_days_max=730" in capsys.readouterr().err
    assert not (out / "manifest.json").exists()


def test_a_purpose_outside_the_two_is_refused(tmp_path: Path) -> None:
    with pytest.raises(InvalidConfigError):
        build(tmp_path, purpose="demo")


def test_a_showcase_build_is_exempt_from_the_window_rule_and_from_nothing_else(tmp_path: Path) -> None:
    """Decision D-S4: the landmark events are kept in a quarantined partition, not thrown away.

    The staged fixture ``manifold-tooold`` resolved outside the window and a research build counts it
    under the ``window`` filter. A showcase build keeps it, takes its window from its own markets, and
    still applies every other filter: the multi-outcome leg and the short-lived market are still gone.
    """
    research = build(tmp_path / "research")
    assert research.removed["window"] == 1 and research.purpose == "research"
    showcase = build(tmp_path / "showcase", purpose="showcase")
    assert showcase.purpose == "showcase"
    assert showcase.removed["window"] == 0 and showcase.removed["opened_early"] == 0
    assert "manifold-tooold" in showcase.kept_ids
    assert showcase.removed["no_leak"] == 1  # the freeze rule is never lifted, for any purpose
    assert "manifold-afterfreeze" not in showcase.kept_ids
    assert showcase.removed["binary"] == 1 and showcase.removed["min_life"] == 1
    created = [
        int(
            json.loads(
                (showcase.path / "markets" / f"{market_id}.json").read_text(encoding="utf-8")
            )["created_at_ms"]
        )
        for market_id in showcase.kept_ids
    ]
    assert showcase.window[0] <= min(created)


def test_the_purpose_reaches_the_document_the_manifest_will_carry(tmp_path: Path) -> None:
    showcase = build(tmp_path, purpose="showcase")
    assert showcase.manifest_blocks["purpose"] == "showcase"


# --------------------------------------------------------------------------------------------------
# 7.4 build.status per venue (rulings R270 and R290)
# --------------------------------------------------------------------------------------------------
def test_a_kalshi_shortfall_fails_the_build_and_a_manifold_only_shortfall_does_not() -> None:
    """Ruling R290 in the form R270 states, and the blanket sentence it deleted from 7.4."""
    both_short = build_outcome(per_provider={"kalshi": 10, "manifold": 10})
    assert both_short["status"] == "failed"
    manifold_only = build_outcome(per_provider={"kalshi": KALSHI_MARKET_FLOOR, "manifold": 10})
    assert manifold_only["status"] == "ok"
    assert manifold_only["shortfall"] == {"manifold": {"markets": MANIFOLD_MARKET_FLOOR - 10}}
    neither = build_outcome(
        per_provider={"kalshi": KALSHI_MARKET_FLOOR, "manifold": MANIFOLD_MARKET_FLOOR}
    )
    assert neither["status"] == "ok" and neither["shortfall"] == {}


def test_the_cohort_target_decides_the_status_once_a_cohort_count_exists() -> None:
    outcome = build_outcome(
        per_provider={"kalshi": KALSHI_MARKET_FLOOR, "manifold": MANIFOLD_MARKET_FLOOR},
        cohorts_per_provider={"kalshi": 12, "manifold": 8},
    )
    assert outcome["status"] == "failed"
    assert outcome["shortfall"] == {"kalshi": {"cohorts": KALSHI_COHORT_TARGET - 12}}
    assert outcome["targets"] == {
        "kalshi_cohorts": KALSHI_COHORT_TARGET,
        "kalshi_markets": KALSHI_MARKET_FLOOR,
        "manifold_cohorts": MANIFOLD_COHORT_TARGET,
        "manifold_markets": MANIFOLD_MARKET_FLOOR,
    }


def test_the_fallback_steps_are_recorded_in_the_order_they_were_taken() -> None:
    outcome = build_outcome(
        per_provider={"kalshi": 100},
        fallbacks=[
            {"step": "window_days", "from": 365, "to": 540, "reason": "cohort target unreachable at 365"},
            {"step": "min_trades", "from": 50, "to": 20, "reason": "still short by 900 markets"},
        ],
    )
    steps = outcome["fallbacks"]
    assert isinstance(steps, list)
    assert [step["step"] for step in steps] == ["window_days", "min_trades"]


# --------------------------------------------------------------------------------------------------
# 5.2 The hourly grid is a first-class path (decision D-R5)
# --------------------------------------------------------------------------------------------------
def hourly_market(market_id: str, *, day: int, hours: int = 240) -> dict[str, object]:
    """A schema-valid hourly market: dense bars on the 60-minute grid, enough size to pass 7.4."""
    created = WINDOW_START_MS + day * MS_PER_DAY
    resolved = created + hours * MS_PER_HOUR
    ticker = market_id.split("-", 1)[1]
    bars = [
        {
            "t_ms": created + index * MS_PER_HOUR,
            "open_bp": 5_000, "high_bp": 5_100, "low_bp": 4_900, "close_bp": 5_000, "vwap_bp": 5_000,
            "volume_milli": 2_000, "n_trades": 0, "yes_bid_bp": 4_950, "yes_ask_bp": 5_050,
            "open_interest": 100,
        }
        for index in range(hours + 1)
    ]
    return {
        "schema_version": "market.v2",
        "id": market_id,
        "provider": "kalshi",
        "provider_id": ticker,
        "url": "https://kalshi.com/x",
        "question": f"Will {ticker} settle yes?",
        "description": "",
        "category": "economics",
        "tags": [],
        "wiki_subjects": [],
        "currency": "usd",
        "source": "imported",
        "created_at_ms": created,
        "close_at_ms": resolved - MS_PER_HOUR,
        "resolved_at_ms": resolved,
        "resolution": 1,
        "resolution_source": "venue",
        "event_key": f"{ticker}-EV",
        "interval_min": 60,
        "bars": bars,
        "trades": [],
        "first_price_bp": 5_000,
        "final_price_bp": 5_000,
        "hardness_tags": [],
        "quality": {
            "n_trades": 0,
            "unique_bettors": None,
            "life_days": hours // 24,
            "volume_milli_total": 2_000 * (hours + 1),
            "traded_bars": hours + 1,
            "tape_kind": TAPE_KIND_BARS_ONLY,
        },
        "fee_schedule_id": "kalshi-general-2026-09",
        "notes": "",
    }


def test_an_hourly_build_is_a_first_class_path_through_the_builder_and_the_loader(tmp_path: Path) -> None:
    """Decision D-R5: ``y2026h`` at ``interval_min = 60`` is the headline Kalshi dataset.

    Built, sealed, verified and loaded back, with the cuts on the hourly grid and every market of the
    dataset on that one grid (5.3: one grid per dataset, and an hourly claim is a second dataset).
    """
    payloads = [hourly_market(f"kalshi-KXH{index}-1", day=10 * index) for index in range(10)]
    result = build_dataset_from_payloads(
        out_dir=tmp_path / "y2026h",
        config=config(interval_min=60, providers=("kalshi",), min_traded_bars=200),
        market_payloads=payloads,
        news_payloads=[],
    )
    assert result.manifest.interval_min == 60
    assert len(result.kept_ids) == 10
    assert (result.manifest.split.n_train, result.manifest.split.n_validation) == (6, 2)
    assert result.manifest.split.train_end_ms % MS_PER_HOUR == 0
    seal_dataset(result.path)
    assert verify_dataset_report(result.path).ok
    dataset = load_dataset(result.path)
    assert {meta.interval_min for meta in dataset.metas} == {60}
    assert sorted({meta.fold for meta in dataset.metas}) == ["sealed", "train", "validation"]


def test_a_whole_hourly_market_is_still_refused_by_a_daily_build(tmp_path: Path) -> None:
    """5.3: one grid per dataset, and the refusal reads the market's own ``interval_min``.

    The sibling above flips the field on a daily fixture; this one offers a genuinely hourly market,
    dense on the 60-minute grid, so the refusal is not an artefact of a market whose bars contradict
    its declared grid.
    """
    with pytest.raises(InvalidConfigError, match="another grid"):
        build_dataset_from_payloads(
            out_dir=tmp_path / "mixed",
            config=config(providers=("kalshi",)),
            market_payloads=[hourly_market("kalshi-KXH0-1", day=10)],
            news_payloads=[],
        )


# --------------------------------------------------------------------------------------------------
# The CLI half of amendment C1c: the audit file, the series list and the new reports
# --------------------------------------------------------------------------------------------------
def sealed_cli_build(tmp_path: Path, *extra: str) -> Path:
    """A sealed dataset built through ``pmx data build``, with the audits tree inside ``tmp_path``."""
    out_dir = tmp_path / "y2026"
    argv = [
        "build",
        "--provider", "kalshi,manifold",
        "--freeze", FREEZE_DATE,
        "--offline",
        "--news-source", "manifold_comment,wikipedia_current_events",
        "--staging", str(STAGING),
        "--out", str(out_dir),
        "--audits-root", str(tmp_path),
        *extra,
    ]
    assert cli_data.main(argv) == 0
    return out_dir


def test_the_build_writes_the_linker_audit_into_the_tracked_audits_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Decision D-R4 and ruling R296: fifty links per build, in ``audits/``, keyed by the sealed hash."""
    out_dir = sealed_cli_build(tmp_path)
    printed = capsys.readouterr().out
    manifest = load_manifest(out_dir)
    path = tmp_path / "audits" / manifest.dataset_hash[:16] / "linker.json"
    assert path.is_file()
    assert "links drawn for review" in printed
    audit = json.loads(path.read_text(encoding="utf-8"))
    assert audit["dataset_hash"] == manifest.dataset_hash
    assert audit["precision_permille"] == 0  # nobody has reviewed it yet
    assert all(link["verdict"] is None for link in audit["links"])
    assert audit["n"] == len(audit["links"]) <= 50
    # the audit is outside the dataset directory and therefore outside its hash
    assert not str(path).startswith(str(out_dir))
    assert verify_dataset_report(out_dir).ok


def test_audit_links_keeps_the_verdicts_a_reviewer_has_already_filled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_dir = sealed_cli_build(tmp_path)
    capsys.readouterr()
    manifest = load_manifest(out_dir)
    path = tmp_path / "audits" / manifest.dataset_hash[:16] / "linker.json"
    audit = json.loads(path.read_text(encoding="utf-8"))
    assert audit["links"], "the fixture dataset carries at least one link to review"
    for index, link in enumerate(audit["links"]):
        link["verdict"] = "correct" if index % 4 else "wrong"
        link["reviewer"] = "g3"
    path.write_text(json.dumps(audit), encoding="utf-8", newline="\n")

    assert cli_data.main(["audit-links", "--dataset", str(out_dir), "--audits-root", str(tmp_path)]) == 0
    printed = capsys.readouterr().out
    again = json.loads(path.read_text(encoding="utf-8"))
    assert [link["verdict"] for link in again["links"]] == [link["verdict"] for link in audit["links"]]
    n_correct = sum(1 for link in again["links"] if link["verdict"] == "correct")
    n_wrong = sum(1 for link in again["links"] if link["verdict"] == "wrong")
    assert again["precision_permille"] == round_half_up(1_000 * n_correct, n_correct + n_wrong)
    assert "precision" in printed


def test_the_build_writes_the_series_list_as_an_output_one_ticker_per_line(tmp_path: Path) -> None:
    """Ruling R258: the series list is an output, and one comma-separated line is what broke a reader."""
    out_dir = sealed_cli_build(tmp_path, "--universe-min-settled", "1", "--universe-min-volume-cents", "0")
    listed = (out_dir / "kalshi_series.txt").read_text(encoding="utf-8")
    assert listed.endswith("\n")
    tickers = listed.split("\n")[:-1]
    assert tickers == sorted(set(tickers))
    assert "KXCPI" in tickers
    assert read_series_list(listed) == tuple(tickers)
    assert verify_dataset_report(out_dir).ok  # the list is outside the hashed walk of 4.3


def test_the_build_prints_the_blocks_the_manifest_cannot_yet_carry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sealed_cli_build(tmp_path)
    printed = capsys.readouterr().out
    assert "purpose    research" in printed
    assert "method count_quantile [600, 800]" in printed
    assert "realised   [600, 200, 200] permille" in printed
    assert "universe   " in printed
    assert "build      status failed" in printed  # five markets is far below the Kalshi market floor


def test_a_showcase_build_through_the_cli_keeps_the_landmark_market(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--purpose showcase`` keeps the out-of-window landmark, and cannot yet be sealed.

    The build half of decision D-S4 is here and works: the landmark market that a research build counts
    under the ``window`` filter is kept, the window is taken from the dataset's own markets, and the
    purpose is reported. The **read** half is blocked on an agreement DS1 reports: ``purpose`` is
    ``DatasetManifest.purpose`` in 5.6 and neither ``pmx.types`` nor the strict ``DatasetManifestModel``
    of ``pmx.data.schema`` carries it, so no manifest on disk can say it and the loader applies the
    window rule of 5.6 to a dataset it cannot tell apart from a research one. The second half of this
    test pins that, so the day the field lands it says so.
    """
    out_dir = tmp_path / "y2026"
    assert (
        cli_data.main(
            [
                "build", "--provider", "kalshi,manifold", "--freeze", FREEZE_DATE, "--offline",
                "--no-seal", "--purpose", "showcase", "--staging", str(STAGING),
                "--out", str(out_dir), "--audits-root", str(tmp_path),
            ]
        )
        == 0
    )
    printed = capsys.readouterr().out
    assert "purpose    showcase" in printed
    # Seven: the five a research build keeps, plus the out-of-window landmark and the one that opened
    # before the window, which are the two filters 5.6's window rule covers and the only two lifted.
    assert "markets    7" in printed
    assert (out_dir / "markets" / "manifold-tooold.json").is_file()
    # BLOCKED, reported as an agreement needed: without DatasetManifest.purpose the loader reads this
    # dataset as research and applies the window rule of 5.6 to it.
    with pytest.raises(SchemaError, match="before the window opens"):
        load_dataset(out_dir)


def test_the_audit_links_command_is_in_the_group_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_data.main([]) == 2
    assert "audit-links" in capsys.readouterr().out


def test_a_comma_separated_flag_also_splits_on_the_newline_a_build_writes() -> None:
    """``--kalshi-series "$(cat kalshi_series.txt)"`` must mean the tickers and not one long ticker."""
    newline = chr(10)
    assert cli_data._csv(f"KXCPI{newline}KXFED{newline}") == ("KXCPI", "KXFED")
    assert cli_data._csv("KXCPI,KXFED") == ("KXCPI", "KXFED")
    assert cli_data._csv(f"KXCPI, KXFED{newline}KXBTC") == ("KXCPI", "KXFED", "KXBTC")
    assert cli_data._csv("") == () and cli_data._csv(None) == ()
