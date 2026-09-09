"""E3: the forecast scores and the calibration curve (CONTRACTS_V2 12.1, 12.2, 17.5).

Every test here asserts an identity the contract states rather than a number the code happens to
produce. Four of them are the identities the plan's done-when names:

* on a regular grid the time-weighted Brier **equals** the plain mean, exactly (12.1);
* on the migrated v1 paths it **differs** from v1's control-point average, by the amount pinned below
  (ruling R3, PRD 4.5: the migration removes the control-point bias);
* ``skill(market_follower) == 0`` and ``skill(random_walk) == 0`` hold **by construction**, on the first
  bar of a market too (rulings R11 and R158);
* the calibration module imports nothing from execution and reads no fill (12.2).

The strongest test in the file is the fixture one: ``tests/fixtures/contract/journal.backtest.jsonl`` is
a complete two-agent journal C0 wrote before this module existed, and its ``settled`` and
``settlement_applied`` events carry the Brier values the engine must produce. Reproducing them from the
journal's ``market_priced`` and ``forecast_recorded`` events is what proves this module and the contract
agree about which bars are scored and which price the market's own statement is.
"""

from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pmx.journal import canonical_json
from pmx.metrics import calibration as calib
from pmx.scoring import (
    BASELINE_5000_PPM,
    LOGIT_EVEN_INDEX,
    LOGIT_MAX_INDEX,
    LOGIT_MIN_INDEX,
    LOGIT_ROUND_TRIP_PPM_MAX,
    LOGIT_TABLE,
    LOGIT_TABLE_SIZE,
    LOGIT_TABLE_STEPS,
    PMV_HORIZONS_DAYS,
    PPM_PER_LOGIT_STEP,
    QUANTILE_LEVELS_PPM,
    RANDOM_WALK_BRIER_MICRO,
    RANDOM_WALK_UP_PPM,
    ForecastBar,
    HorizonBucket,
    bar_weights_ms,
    baseline_pinball_micro,
    baseline_quantiles_ticks,
    brier_tw_micro,
    directional_brier_micro,
    directional_skill_micro,
    horizon_bucket_name,
    horizon_bucket_of,
    horizon_buckets,
    log_micronats,
    logit_index_of,
    logit_milli,
    market_brier_tw_micro,
    pinball_micro,
    pinball_skill_micro,
    plain_mean_micro,
    pmv_bp,
    random_walk_resolution,
    realised_sign_of,
    resolve_horizon,
    score_binary_market,
    score_continuous_horizon,
    score_continuous_market,
    signed_mean,
    skill_micro,
    skill_vs_5000_micro,
    unlogit_ppm,
    weighted_mean_micro,
)
from pmx.types import (
    CALIBRATION_BINS,
    MS_PER_DAY,
    PPM_ONE,
    CalibrationBinView,
    brier_micro,
    interval_ms,
    neg_ln_micronats,
    ppm_from_bp,
    round_half_up,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "contract"
DEMO_MARKETS = REPO_ROOT / "data" / "demo_v1" / "markets"

DAY_MS = MS_PER_DAY
DAILY_MS = interval_ms(1_440)


def daily_bars(rows: list[tuple[int, int]], *, t0_ms: int = 0) -> list[ForecastBar]:
    """A dense daily record from ``(prob_ppm, market_price_bp)`` pairs."""
    return [
        ForecastBar(t_ms=t0_ms + index * DAY_MS, prob_ppm=prob, market_price_bp=price)
        for index, (prob, price) in enumerate(rows)
    ]


# --------------------------------------------------------------------------------------------------
# 12.1 The worked examples and the two means
# --------------------------------------------------------------------------------------------------
def test_worked_example_of_section_1_4() -> None:
    """A 700_000 ppm statement against a market at 6_300 bp on a market that resolves YES."""
    bars = [ForecastBar(t_ms=0, prob_ppm=700_000, market_price_bp=6_300)]
    assert brier_micro(700_000, 1) == 90_000
    assert brier_micro(ppm_from_bp(6_300), 1) == 136_900
    assert brier_tw_micro(bars, outcome=1, interval_ms=DAILY_MS) == 90_000
    assert market_brier_tw_micro(bars, outcome=1, interval_ms=DAILY_MS) == 136_900
    assert skill_micro(bars, outcome=1, interval_ms=DAILY_MS) == 46_900


def test_bar_weights_are_the_gaps_with_the_interval_last() -> None:
    bars = daily_bars([(500_000, 5_000)] * 3)
    assert bar_weights_ms(bars, interval_ms=DAILY_MS) == (DAY_MS, DAY_MS, DAILY_MS)
    ragged = [
        ForecastBar(t_ms=0, prob_ppm=1, market_price_bp=1),
        ForecastBar(t_ms=10 * DAY_MS, prob_ppm=1, market_price_bp=1),
    ]
    assert bar_weights_ms(ragged, interval_ms=DAILY_MS) == (10 * DAY_MS, DAILY_MS)
    assert bar_weights_ms([], interval_ms=DAILY_MS) == ()


@settings(max_examples=200, deadline=None)
@given(
    probs=st.lists(st.integers(min_value=0, max_value=PPM_ONE), min_size=1, max_size=40),
    outcome=st.integers(min_value=0, max_value=1),
)
def test_time_weighted_brier_equals_the_plain_mean_on_a_regular_grid(probs: list[int], outcome: int) -> None:
    """The identity of section 12.1: every weight is ``interval_ms``, so the weighting cancels exactly."""
    bars = daily_bars([(prob, 5_000) for prob in probs])
    plain = plain_mean_micro([brier_micro(prob, outcome) for prob in probs])
    assert brier_tw_micro(bars, outcome=outcome, interval_ms=DAILY_MS) == plain
    assert log_micronats(bars, outcome=outcome, interval_ms=DAILY_MS) == plain_mean_micro(
        [
            neg_ln_micronats(max(10_000, min(990_000, prob if outcome == 1 else PPM_ONE - prob)))
            for prob in probs
        ]
    )


def test_time_weighted_brier_differs_from_the_plain_mean_on_an_irregular_grid() -> None:
    """The weighting is not decoration: a nine-day gap weighs nine days, not one bar."""
    bars = [
        ForecastBar(t_ms=0, prob_ppm=0, market_price_bp=5_000),
        ForecastBar(t_ms=DAY_MS, prob_ppm=1_000_000, market_price_bp=5_000),
        ForecastBar(t_ms=10 * DAY_MS, prob_ppm=1_000_000, market_price_bp=5_000),
    ]
    weighted = brier_tw_micro(bars, outcome=1, interval_ms=DAILY_MS)
    plain = plain_mean_micro([1_000_000, 0, 0])
    assert plain == 333_333
    assert weighted == round_half_up(1_000_000 * DAY_MS, DAY_MS + 9 * DAY_MS + DAILY_MS)
    assert weighted == 90_909
    assert weighted != plain


def test_signed_mean_rounds_half_away_from_zero_and_is_symmetric() -> None:
    assert signed_mean([]) == 0
    assert signed_mean([1, 2]) == 2  # 1.5 away from zero
    assert signed_mean([-1, -2]) == -2
    assert signed_mean([-1_850, 0]) == -925
    assert signed_mean([1_850, 0]) == 925


# --------------------------------------------------------------------------------------------------
# 12.1 The market baseline and the zero-skill identity (rulings R11 and R66)
# --------------------------------------------------------------------------------------------------
@settings(max_examples=200, deadline=None)
@given(
    prices=st.lists(st.integers(min_value=1, max_value=9_999), min_size=1, max_size=40),
    outcome=st.integers(min_value=0, max_value=1),
)
def test_market_follower_skill_is_zero_by_construction(prices: list[int], outcome: int) -> None:
    """An agent that states the market's own price on every bar, including the first, has zero skill."""
    bars = daily_bars([(ppm_from_bp(price), price) for price in prices])
    assert skill_micro(bars, outcome=outcome, interval_ms=DAILY_MS) == 0
    assert brier_tw_micro(bars, outcome=outcome, interval_ms=DAILY_MS) == market_brier_tw_micro(
        bars, outcome=outcome, interval_ms=DAILY_MS
    )
    for bucket in horizon_buckets(bars, outcome=outcome, close_at_ms=40 * DAY_MS, interval_ms=DAILY_MS):
        assert bucket.skill_micro == 0


def test_skill_vs_5000_is_measured_against_the_constant_forecast() -> None:
    bars = daily_bars([(700_000, 6_300), (800_000, 6_400)])
    assert brier_micro(BASELINE_5000_PPM, 1) == 250_000
    agent = brier_tw_micro(bars, outcome=1, interval_ms=DAILY_MS)
    assert skill_vs_5000_micro(bars, outcome=1, interval_ms=DAILY_MS) == 250_000 - agent


def test_a_market_that_priced_the_outcome_perfectly_leaves_no_skill_to_take() -> None:
    """The baseline is the market's own bars, so a right market makes skill negative for a wrong agent."""
    bars = daily_bars([(200_000, 9_999), (200_000, 9_999)])
    assert skill_micro(bars, outcome=1, interval_ms=DAILY_MS) < 0


# --------------------------------------------------------------------------------------------------
# The contract fixture: a complete journal C0 wrote before this module existed (ruling R83)
# --------------------------------------------------------------------------------------------------
def read_fixture_journal() -> list[dict[str, Any]]:
    lines = (CONTRACT_FIXTURES / "journal.backtest.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_fixture_journal_reproduces_both_briers_of_the_settle_phase() -> None:
    """``settled.market_brier_tw_micro`` and ``settlement_applied.agent_brier_tw_micro``, from the journal."""
    events = read_fixture_journal()
    prices: dict[int, int] = {}
    forecasts: dict[str, list[tuple[int, int]]] = {}
    settled: dict[str, Any] = {}
    applied: dict[str, dict[str, Any]] = {}
    for event in events:
        kind = event["type"]
        if kind == "market_priced":
            prices[int(event["bar_ms"])] = int(event["last_close_bp"])
        elif kind == "forecast_recorded":
            forecasts.setdefault(str(event["agent_id"]), []).append((int(event["bar_ms"]), int(event["prob_ppm"])))
        elif kind == "settled":
            settled = event
        elif kind == "settlement_applied":
            applied[str(event["agent_id"])] = event

    outcome = int(settled["outcome"])
    close_at_ms = int(settled["resolved_at_ms"])
    bar_ms_sorted = sorted(prices)
    assert len(bar_ms_sorted) == int(settled["n_bars"]) == 2

    baseline = [
        ForecastBar(t_ms=bar_ms, prob_ppm=ppm_from_bp(prices[bar_ms]), market_price_bp=prices[bar_ms])
        for bar_ms in bar_ms_sorted
    ]
    assert market_brier_tw_micro(baseline, outcome=outcome, interval_ms=DAILY_MS) == int(
        settled["market_brier_tw_micro"]
    )

    assert sorted(forecasts) == ["contrarian", "market_follower"]
    for agent_id, stated in forecasts.items():
        bars = [
            ForecastBar(t_ms=bar_ms, prob_ppm=prob_ppm, market_price_bp=prices[bar_ms])
            for bar_ms, prob_ppm in sorted(stated)
        ]
        score = score_binary_market(
            bars,
            outcome=outcome,
            close_at_ms=int(applied[agent_id].get("close_at_ms", close_at_ms)),
            settle_bar_ms=bar_ms_sorted[-1],
            interval_ms=DAILY_MS,
        )
        assert score.n_forecast_bars == int(applied[agent_id]["n_forecast_bars"])
        assert score.agent_brier_tw_micro == int(applied[agent_id]["agent_brier_tw_micro"])
        assert score.market_brier_tw_micro == int(settled["market_brier_tw_micro"])
    assert forecasts["market_follower"] == [(bar_ms, ppm_from_bp(prices[bar_ms])) for bar_ms in bar_ms_sorted]
    follower = [
        ForecastBar(t_ms=bar_ms, prob_ppm=ppm_from_bp(prices[bar_ms]), market_price_bp=prices[bar_ms])
        for bar_ms in bar_ms_sorted
    ]
    assert skill_micro(follower, outcome=outcome, interval_ms=DAILY_MS) == 0


# --------------------------------------------------------------------------------------------------
# 12.1 The log score
# --------------------------------------------------------------------------------------------------
def test_log_score_pinned_values_and_the_two_clamps() -> None:
    even = [ForecastBar(t_ms=0, prob_ppm=500_000, market_price_bp=5_000)]
    assert log_micronats(even, outcome=1, interval_ms=DAILY_MS) == 693_147
    assert log_micronats(even, outcome=0, interval_ms=DAILY_MS) == 693_147
    certain_wrong = [ForecastBar(t_ms=0, prob_ppm=0, market_price_bp=5_000)]
    assert log_micronats(certain_wrong, outcome=1, interval_ms=DAILY_MS) == 4_605_170
    certain_right = [ForecastBar(t_ms=0, prob_ppm=PPM_ONE, market_price_bp=5_000)]
    assert log_micronats(certain_right, outcome=1, interval_ms=DAILY_MS) == 10_050
    assert log_micronats(certain_right, outcome=0, interval_ms=DAILY_MS) == 4_605_170


def test_log_score_punishes_confident_wrongness_harder_than_brier_does() -> None:
    """PRD 4.5's reason for keeping the log score beside the Brier."""
    mild = [ForecastBar(t_ms=0, prob_ppm=400_000, market_price_bp=5_000)]
    bold = [ForecastBar(t_ms=0, prob_ppm=20_000, market_price_bp=5_000)]
    brier_ratio = brier_tw_micro(bold, outcome=1, interval_ms=DAILY_MS) // brier_tw_micro(
        mild, outcome=1, interval_ms=DAILY_MS
    )
    log_ratio = log_micronats(bold, outcome=1, interval_ms=DAILY_MS) // log_micronats(
        mild, outcome=1, interval_ms=DAILY_MS
    )
    assert brier_ratio == 2
    assert log_ratio == 4


# --------------------------------------------------------------------------------------------------
# 12.1 The horizon buckets
# --------------------------------------------------------------------------------------------------
def test_horizon_bucket_edges_and_the_settlement_lag() -> None:
    close = 100 * DAY_MS
    assert horizon_bucket_of(close - 30 * DAY_MS, close_at_ms=close) == "30d"
    assert horizon_bucket_of(close - 30 * DAY_MS + 1, close_at_ms=close) == "7d"
    assert horizon_bucket_of(close - 7 * DAY_MS, close_at_ms=close) == "7d"
    assert horizon_bucket_of(close - 7 * DAY_MS + 1, close_at_ms=close) == "2d"
    assert horizon_bucket_of(close - 2 * DAY_MS, close_at_ms=close) == "2d"
    assert horizon_bucket_of(close - 2 * DAY_MS + 1, close_at_ms=close) == "0d"
    assert horizon_bucket_of(close, close_at_ms=close) == "0d"
    # Ruling R56: a market stays open after its close, where days_to_close is negative.
    assert horizon_bucket_of(close + 3 * DAY_MS, close_at_ms=close) == "0d"


def test_horizon_buckets_are_always_four_and_partition_the_record() -> None:
    bars = daily_bars([(600_000, 5_000)] * 45)
    close_at_ms = 44 * DAY_MS
    buckets = horizon_buckets(bars, outcome=1, close_at_ms=close_at_ms, interval_ms=DAILY_MS)
    assert tuple(bucket.bucket for bucket in buckets) == ("30d", "7d", "2d", "0d")
    assert sum(bucket.n_bars for bucket in buckets) == len(bars)
    populated = [bucket for bucket in buckets if bucket.n_bars > 0]
    assert len(populated) == 4
    for bucket in populated:
        assert bucket.brier_tw_micro == brier_micro(600_000, 1)


def test_an_empty_horizon_bucket_reports_zeros_rather_than_raising() -> None:
    """Ruling R2: a bucket no bar fell into is the common case on a short-lived market."""
    bars = daily_bars([(600_000, 5_000)] * 2)
    buckets = horizon_buckets(bars, outcome=1, close_at_ms=DAY_MS, interval_ms=DAILY_MS)
    by_name = {bucket.bucket: bucket for bucket in buckets}
    assert by_name["30d"].n_bars == 0
    assert by_name["30d"].brier_tw_micro == 0
    assert by_name["30d"].market_brier_tw_micro == 0
    assert by_name["30d"].skill_micro == 0
    assert by_name["0d"].n_bars == 2


def test_horizon_bucket_refuses_a_string_outside_the_declared_shape() -> None:
    with pytest.raises(ValueError, match="RE_HORIZON_BUCKET"):
        HorizonBucket(bucket="14d", n_bars=1, brier_tw_micro=0, market_brier_tw_micro=0, skill_micro=0)
    assert HorizonBucket(
        bucket=horizon_bucket_name(24), n_bars=1, brier_tw_micro=0, market_brier_tw_micro=0, skill_micro=0
    ).bucket == "h24"


# --------------------------------------------------------------------------------------------------
# 12.1 PMV
# --------------------------------------------------------------------------------------------------
def test_pmv_reads_the_move_in_the_direction_the_agent_leaned() -> None:
    """Five daily bars, an agent above the price throughout, and a market that rises 100 bp a day."""
    bars = daily_bars([(900_000, 5_000), (900_000, 5_100), (900_000, 5_200), (900_000, 5_300), (900_000, 5_400)])
    settle = 4 * DAY_MS
    # Bars 0, 1 and 2 have a future bar strictly before the settling bar; bars 3 and 4 do not.
    assert pmv_bp(bars, horizon_days=1, settle_bar_ms=settle) == 100
    bearish = daily_bars([(100_000, 5_000), (100_000, 5_100), (100_000, 5_200), (100_000, 5_300), (100_000, 5_400)])
    assert pmv_bp(bearish, horizon_days=1, settle_bar_ms=settle) == -100


def test_pmv_takes_the_first_bar_at_or_after_the_horizon() -> None:
    bars = daily_bars([(900_000, 5_000)] + [(900_000, 5_000 + 10 * index) for index in range(1, 9)])
    settle = 8 * DAY_MS
    assert pmv_bp(bars, horizon_days=7, settle_bar_ms=settle) == 70
    assert PMV_HORIZONS_DAYS == (1, 7)


def test_pmv_skips_a_bar_with_no_future_bar_and_reports_zero_when_all_are_skipped() -> None:
    bars = daily_bars([(900_000, 5_000), (900_000, 9_900)])
    # The only candidate future bar is the settling bar itself, which section 12.1 refuses.
    assert pmv_bp(bars, horizon_days=1, settle_bar_ms=DAY_MS) == 0
    assert pmv_bp([], horizon_days=1, settle_bar_ms=0) == 0


def test_pmv_of_an_agent_that_states_the_price_is_zero() -> None:
    """A zero stance contributes a zero move, and is not silently dropped from the mean."""
    bars = daily_bars([(ppm_from_bp(5_000), 5_000), (ppm_from_bp(5_500), 5_500), (ppm_from_bp(6_000), 6_000)])
    assert pmv_bp(bars, horizon_days=1, settle_bar_ms=2 * DAY_MS) == 0


# --------------------------------------------------------------------------------------------------
# The whole binary record, and the zero-denominator rule at the top level
# --------------------------------------------------------------------------------------------------
def test_score_binary_market_over_no_bar_is_all_zeros_and_canonical() -> None:
    score = score_binary_market([], outcome=1, close_at_ms=0, settle_bar_ms=0, interval_ms=DAILY_MS)
    assert score.n_forecast_bars == 0
    assert score.agent_brier_tw_micro == 0
    assert score.market_brier_tw_micro == 0
    assert score.skill_micro == 0
    assert score.skill_vs_5000_micro == 0
    assert score.log_micronats == 0
    assert score.pmv_1d_bp == 0
    assert score.pmv_7d_bp == 0
    assert len(score.horizons) == 4
    assert canonical_json(score.to_dict())


def test_every_score_is_an_integer_and_survives_canonical_json() -> None:
    bars = daily_bars([(700_000, 6_300), (650_000, 6_400), (900_000, 9_100)])
    score = score_binary_market(
        bars, outcome=1, close_at_ms=2 * DAY_MS, settle_bar_ms=2 * DAY_MS, interval_ms=DAILY_MS
    )
    payload = score.to_dict()
    rendered = canonical_json(payload)  # raises NonCanonicalValueError on a float (section 4.1)
    assert "." not in rendered
    assert score.skill_micro != 0  # the record is not the degenerate one this rule is easiest to pass on
    for key, value in payload.items():
        if key != "horizons":
            assert isinstance(value, int)
    for bucket in score.horizons:
        for field_name, field_value in bucket.to_dict().items():
            assert isinstance(field_value, int if field_name != "bucket" else str)


# --------------------------------------------------------------------------------------------------
# Ruling R3 and PRD 4.5: the migrated v1 path, where the time-weighted Brier differs from v1's
# --------------------------------------------------------------------------------------------------
#: The market's own time-weighted Brier over the 145 migrated daily bars of demo-brexit-2016.
DEMO_BREXIT_MARKET_BRIER_TW_MICRO = 484_094
#: v1's own average over the 12 hand-written control points of the same market (``pmx.v1.engine``).
V1_BREXIT_CONTROL_POINT_BRIER_MICRO = 363_416
#: The documented difference of ruling R3: v1's control points cluster near the resolution, where the
#: price was finally right, so its average understated the market's error by this much.
DEMO_BREXIT_CONTROL_POINT_BIAS_MICRO = 120_678


def demo_market(market_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((DEMO_MARKETS / f"{market_id}.json").read_text(encoding="utf-8"))
    return payload


def market_baseline_bars(market: dict[str, Any]) -> list[ForecastBar]:
    """The market's own statement on each of its bars: ``last_close_bp``, carried as ruling R11 says."""
    bars: list[ForecastBar] = []
    last_close_bp = int(market["first_price_bp"])
    for row in market["bars"]:
        assert isinstance(row, dict)
        bars.append(
            ForecastBar(
                t_ms=int(row["t_ms"]), prob_ppm=ppm_from_bp(last_close_bp), market_price_bp=last_close_bp
            )
        )
        last_close_bp = int(row["close_bp"])
    return bars


def test_migrated_bar_closes_are_the_v1_cent_prices_times_one_hundred() -> None:
    """Identity 3 of section 7.10, which is what makes the Brier comparison below a fair one."""
    from pmx.v1.data.bundled import _MARKETS  # the frozen legacy pack: control points in whole cents

    v1_market: dict[str, Any] = next(row for row in _MARKETS if row["id"] == "brexit-2016")
    control_points = v1_market["prices"]
    assert isinstance(control_points, list)
    market = demo_market("demo-brexit-2016")
    bars = market["bars"]
    assert isinstance(bars, list)
    first = control_points[0]
    last = control_points[-1]
    assert isinstance(first, list)
    assert isinstance(last, list)
    assert int(market["first_price_bp"]) == int(first[1]) * 100
    assert int(market["final_price_bp"]) == int(last[1]) * 100
    v1_prices_bp = {int(point[1]) * 100 for point in control_points if isinstance(point, list)}
    closes_bp = {int(row["close_bp"]) for row in bars if isinstance(row, dict)}
    # Every daily close is a v1 control point carried forward; the reverse does not hold, because four
    # of the twelve points are intraday prints of the referendum night and share one daily bar.
    assert closes_bp <= v1_prices_bp
    assert len(closes_bp) == 7


def test_time_weighted_brier_on_the_migrated_path_differs_from_the_v1_control_point_mean() -> None:
    """Ruling R3: the two numbers are both right and are not the same number.

    v1 averaged 6 to 12 control points per market, and its points cluster where the price moved (near the
    resolution). The migration carries those points forward over 145 daily bars, so a month spent priced
    at 26 percent on a market that resolved YES now weighs a month instead of one point. The difference is
    pinned here so that a later change of either arithmetic is caught rather than absorbed.
    """
    from pmx.v1.data.bundled import _MARKETS
    from pmx.v1.scoring import brier_micro as v1_brier_micro
    from pmx.v1.scoring import clamp_price, price_to_ppm

    market = demo_market("demo-brexit-2016")
    bars = market["bars"]
    assert isinstance(bars, list)
    assert len(bars) == 145
    assert int(market["interval_min"]) == 1_440
    baseline = market_baseline_bars(market)
    weighted = market_brier_tw_micro(baseline, outcome=int(market["resolution"]), interval_ms=DAILY_MS)
    assert weighted == DEMO_BREXIT_MARKET_BRIER_TW_MICRO

    v1_market: dict[str, Any] = next(row for row in _MARKETS if row["id"] == "brexit-2016")
    control_points = v1_market["prices"]
    assert isinstance(control_points, list)
    v1_scores = [
        v1_brier_micro(price_to_ppm(clamp_price(int(point[1]))), int(v1_market["resolution"]))
        for point in control_points
        if isinstance(point, list)
    ]
    assert len(v1_scores) == 12
    v1_mean = sum(v1_scores) // len(v1_scores)
    assert v1_mean == V1_BREXIT_CONTROL_POINT_BRIER_MICRO
    assert weighted - v1_mean == DEMO_BREXIT_CONTROL_POINT_BIAS_MICRO
    assert weighted != v1_mean


def test_the_migrated_grid_is_regular_so_the_weighting_itself_is_not_the_difference() -> None:
    """The 145 bars are daily, so the weighted mean equals the plain mean: the bias is the point count."""
    market = demo_market("demo-brexit-2016")
    baseline = market_baseline_bars(market)
    outcome = int(market["resolution"])
    plain = plain_mean_micro([brier_micro(bar.market_prob_ppm, outcome) for bar in baseline])
    assert market_brier_tw_micro(baseline, outcome=outcome, interval_ms=DAILY_MS) == plain


def test_the_market_follower_identity_holds_on_every_market_of_the_demo_pack() -> None:
    paths = sorted(DEMO_MARKETS.glob("demo-*.json"))
    assert len(paths) == 12
    for path in paths:
        market = json.loads(path.read_text(encoding="utf-8"))
        bars = market_baseline_bars(market)
        outcome = int(market["resolution"])
        assert skill_micro(bars, outcome=outcome, interval_ms=DAILY_MS) == 0
        assert market_brier_tw_micro(bars, outcome=outcome, interval_ms=DAILY_MS) > 0


# --------------------------------------------------------------------------------------------------
# 17.5 The continuous kinds: the directional Brier, the pinball loss and the random walk
# --------------------------------------------------------------------------------------------------
def test_directional_brier_worked_values_and_the_tie_rule() -> None:
    """The three values 17.5 pins for a 700_000 up-probability."""
    assert directional_brier_micro(700_000, 1) == 90_000
    assert directional_brier_micro(700_000, -1) == 490_000
    assert directional_brier_micro(700_000, 0) == 290_000


@settings(max_examples=200, deadline=None)
@given(sign=st.integers(min_value=-1, max_value=1))
def test_the_random_walk_scores_the_constant_on_every_realisation(sign: int) -> None:
    assert directional_brier_micro(RANDOM_WALK_UP_PPM, sign) == RANDOM_WALK_BRIER_MICRO
    assert directional_skill_micro(directional_brier_micro(RANDOM_WALK_UP_PPM, sign)) == 0


def test_pinball_worked_example_of_section_17_5() -> None:
    quantiles = (6_300_000, 6_325_000, 6_341_257, 6_356_000, 6_380_000)
    realised = 6_352_010
    reference = 6_341_257
    assert QUANTILE_LEVELS_PPM == (100_000, 250_000, 500_000, 750_000, 900_000)
    assert pinball_micro(quantiles, realised, reference) == 666
    assert baseline_pinball_micro(realised, reference) == 848
    assert pinball_skill_micro(848, 666) == 182


def test_pinball_is_relative_to_the_reference_so_two_venues_pool() -> None:
    """A one-permille error on a six-figure future and on a five-digit FX rate is the same mistake."""
    big_ref = 6_000_000
    small_ref = 100_000
    big = pinball_micro(baseline_quantiles_ticks(big_ref), big_ref + big_ref // 1_000, big_ref)
    small = pinball_micro(baseline_quantiles_ticks(small_ref), small_ref + small_ref // 1_000, small_ref)
    assert big == small == 500


def test_pinball_refuses_a_tuple_that_is_not_five_long_and_reports_zero_on_a_zero_reference() -> None:
    with pytest.raises(ValueError):
        pinball_micro((1, 2, 3), 5, 10)
    assert pinball_micro(baseline_quantiles_ticks(0), 5, 0) == 0


@settings(max_examples=300, deadline=None)
@given(
    reference=st.integers(min_value=1, max_value=10_000_000),
    move=st.integers(min_value=-1_000_000, max_value=1_000_000),
    horizon=st.integers(min_value=1, max_value=168),
)
def test_random_walk_skill_is_zero_by_construction(reference: int, move: int, horizon: int) -> None:
    """AC-23 and ruling R158, on both losses at once, over any realisation the tape can produce."""
    realised = max(1, reference + move)
    resolution = random_walk_resolution(
        forecast_bar_ms=0, horizon_bars=horizon, price_ref_ticks=reference, price_realised_ticks=realised
    )
    assert resolution.directional_brier_micro == RANDOM_WALK_BRIER_MICRO
    assert resolution.pinball_micro == resolution.baseline_pinball_micro
    score = score_continuous_horizon([resolution], horizon_bars=horizon)
    assert score.skill_micro == 0
    assert score.pinball_skill_micro == 0
    assert score.n_resolved == 1
    assert score.n_quantile_forecasts == 1
    assert score.pmv_ticks == 0  # a 500_000 statement leans nowhere


def test_resolve_horizon_fills_the_scored_core_of_the_event() -> None:
    resolution = resolve_horizon(
        forecast_bar_ms=DAY_MS,
        horizon_bars=1,
        up_probability_ppm=700_000,
        quantiles_ticks=(6_300_000, 6_325_000, 6_341_257, 6_356_000, 6_380_000),
        price_ref_ticks=6_341_257,
        price_realised_ticks=6_352_010,
        carried=True,
    )
    assert resolution.realised_sign == 1
    assert resolution.directional_brier_micro == 90_000
    assert resolution.pinball_micro == 666
    assert resolution.baseline_pinball_micro == 848
    assert resolution.carried is True
    payload = resolution.to_dict()
    assert canonical_json(payload)
    assert payload["quantiles_ticks"] == [6_300_000, 6_325_000, 6_341_257, 6_356_000, 6_380_000]


def test_a_direction_only_agent_is_scored_on_direction_and_says_so() -> None:
    resolution = resolve_horizon(
        forecast_bar_ms=0,
        horizon_bars=1,
        up_probability_ppm=700_000,
        quantiles_ticks=None,
        price_ref_ticks=1_000_000,
        price_realised_ticks=1_010_000,
    )
    assert resolution.pinball_micro is None
    assert resolution.baseline_pinball_micro > 0
    score = score_continuous_horizon([resolution], horizon_bars=1)
    assert score.n_resolved == 1
    assert score.n_quantile_forecasts == 0
    assert score.pinball_micro == 0
    assert score.baseline_pinball_micro == 0
    assert score.pinball_skill_micro == 0
    assert score.dir_brier_micro == 90_000
    assert score.skill_micro == RANDOM_WALK_BRIER_MICRO - 90_000


def test_the_continuous_aggregate_is_the_plain_mean_and_the_bucket_is_h_n() -> None:
    resolutions = [
        resolve_horizon(
            forecast_bar_ms=index * DAY_MS,
            horizon_bars=24,
            up_probability_ppm=700_000,
            quantiles_ticks=None,
            price_ref_ticks=1_000_000,
            price_realised_ticks=1_000_000 + (10_000 if index % 2 == 0 else -10_000),
        )
        for index in range(4)
    ]
    score = score_continuous_horizon(resolutions, horizon_bars=24)
    assert score.bucket == "h24"
    assert score.n_resolved == 4
    assert score.dir_brier_micro == plain_mean_micro([90_000, 490_000, 90_000, 490_000])
    assert score.dir_brier_micro == 290_000
    assert score.skill_micro == RANDOM_WALK_BRIER_MICRO - 290_000
    bucket = score.as_bucket()
    assert bucket.bucket == "h24"
    assert bucket.market_brier_tw_micro == RANDOM_WALK_BRIER_MICRO
    assert bucket.skill_micro == score.skill_micro
    assert canonical_json(score.to_dict())


def test_the_pinball_baseline_is_averaged_over_the_forecasts_that_stated_quantiles() -> None:
    """Pairing the two sides is what stops silence from buying pinball skill."""
    stated = resolve_horizon(
        forecast_bar_ms=0,
        horizon_bars=1,
        up_probability_ppm=500_000,
        quantiles_ticks=baseline_quantiles_ticks(1_000_000),
        price_ref_ticks=1_000_000,
        price_realised_ticks=1_001_000,
    )
    silent = resolve_horizon(
        forecast_bar_ms=DAY_MS,
        horizon_bars=1,
        up_probability_ppm=500_000,
        quantiles_ticks=None,
        price_ref_ticks=1_000_000,
        price_realised_ticks=1_500_000,  # a bar where the baseline's pinball is enormous
    )
    score = score_continuous_horizon([stated, silent], horizon_bars=1)
    assert score.n_resolved == 2
    assert score.n_quantile_forecasts == 1
    assert score.baseline_pinball_micro == stated.baseline_pinball_micro
    assert score.pinball_skill_micro == 0


def test_a_horizon_with_nothing_resolved_reports_zeros() -> None:
    score = score_continuous_horizon([], horizon_bars=7)
    assert score.n_resolved == 0
    assert score.dir_brier_micro == 0
    assert score.skill_micro == 0
    assert score.pinball_micro == 0
    assert score.pinball_skill_micro == 0
    assert score.pmv_ticks == 0
    assert score.pmv_bp == 0
    assert score.as_bucket().market_brier_tw_micro == 0


def test_score_continuous_market_returns_one_row_per_declared_horizon_in_order() -> None:
    resolutions = [
        resolve_horizon(
            forecast_bar_ms=0,
            horizon_bars=horizon,
            up_probability_ppm=600_000,
            quantiles_ticks=None,
            price_ref_ticks=1_000_000,
            price_realised_ticks=1_005_000,
        )
        for horizon in (1, 24)
    ]
    rows = score_continuous_market(resolutions, horizons_bars=(1, 24, 168))
    assert tuple(row.bucket for row in rows) == ("h1", "h24", "h168")
    assert tuple(row.n_resolved for row in rows) == (1, 1, 0)


def test_continuous_pmv_reads_the_move_in_the_direction_the_agent_leaned() -> None:
    up = resolve_horizon(
        forecast_bar_ms=0,
        horizon_bars=1,
        up_probability_ppm=900_000,
        quantiles_ticks=None,
        price_ref_ticks=1_000_000,
        price_realised_ticks=1_010_000,
    )
    down = resolve_horizon(
        forecast_bar_ms=DAY_MS,
        horizon_bars=1,
        up_probability_ppm=100_000,
        quantiles_ticks=None,
        price_ref_ticks=1_000_000,
        price_realised_ticks=1_010_000,
    )
    assert score_continuous_horizon([up], horizon_bars=1).pmv_ticks == 10_000
    assert score_continuous_horizon([up], horizon_bars=1).pmv_bp == 100
    assert score_continuous_horizon([down], horizon_bars=1).pmv_ticks == -10_000
    assert score_continuous_horizon([down], horizon_bars=1).pmv_bp == -100


# --------------------------------------------------------------------------------------------------
# 12.2 Calibration
# --------------------------------------------------------------------------------------------------
def test_bins_are_deciles_and_the_top_bin_takes_certainty() -> None:
    assert CALIBRATION_BINS == 10
    assert calib.bin_of(0) == 0
    assert calib.bin_of(99_999) == 0
    assert calib.bin_of(100_000) == 1
    assert calib.bin_of(999_999) == 9
    assert calib.bin_of(PPM_ONE) == 9


def test_reliability_curve_worked_example() -> None:
    """Four forecasts in one bin: two at 700_000 and two at 800_000, one of each realising YES."""
    entries = [
        calib.binary_entry(category="politics", horizon_bucket="7d", prob_ppm=700_000, outcome=1),
        calib.binary_entry(category="politics", horizon_bucket="7d", prob_ppm=700_000, outcome=0),
        calib.binary_entry(category="politics", horizon_bucket="7d", prob_ppm=800_000, outcome=1),
        calib.binary_entry(category="politics", horizon_bucket="7d", prob_ppm=800_000, outcome=0),
    ]
    bins = calib.reliability_bins(entries)
    assert len(bins) == CALIBRATION_BINS
    seven = bins[7]
    eight = bins[8]
    assert (seven.n, seven.mean_prob_ppm, seven.n_yes, seven.yes_rate_ppm) == (2, 700_000, 1, 500_000)
    assert (eight.n, eight.mean_prob_ppm, eight.n_yes, eight.yes_rate_ppm) == (2, 800_000, 1, 500_000)
    # ECE: (2 * 200_000 + 2 * 300_000) // 4
    assert calib.ece_ppm(bins) == 250_000
    # Sharpness: (2 * 200_000 + 2 * 300_000) // 4, the distance from 500_000
    assert calib.sharpness_ppm(bins) == 250_000


def test_a_calibrated_but_unsharp_agent_has_a_zero_ece_and_a_zero_sharpness() -> None:
    """Why sharpness is reported beside the ECE: half of "always 500_000" is a perfect score."""
    entries = [
        calib.binary_entry(category="other", horizon_bucket="30d", prob_ppm=500_000, outcome=index % 2)
        for index in range(10)
    ]
    slice_ = calib.calibration_slice(entries, category="other", horizon_bucket="30d")
    assert slice_.ece_ppm == 0
    assert slice_.sharpness_ppm == 0


def test_an_empty_bin_and_an_empty_slice_report_zero_rather_than_raising() -> None:
    """Ruling R2 and the preamble of section 12: nine of ten bins are empty for market_follower."""
    entries = [calib.binary_entry(category="crypto", horizon_bucket="0d", prob_ppm=250_000, outcome=1)]
    bins = calib.reliability_bins(entries)
    assert sum(1 for item in bins if item.n == 0) == 9
    for item in bins:
        if item.n == 0:
            assert (item.mean_prob_ppm, item.yes_rate_ppm, item.n_yes_x2) == (0, 0, 0)
    empty = calib.calibration_slice([], category="crypto", horizon_bucket="0d")
    assert empty.n == 0
    assert empty.ece_ppm == 0
    assert empty.sharpness_ppm == 0
    assert len(empty.bins) == CALIBRATION_BINS
    assert empty.bin_views() == ()
    assert calib.calibration_table([]) == ()
    assert calib.yes_rate_ppm(n=0, n_yes_x2=0) == 0


def test_a_flat_realisation_is_half_a_yes_and_is_never_dropped() -> None:
    """Ruling R194: the ledger stores n_yes_x2, so a tie adds one and an up adds two."""
    entries = [
        calib.continuous_entry(kind="perp", horizon_bars=1, up_probability_ppm=550_000, realised_sign=1),
        calib.continuous_entry(kind="perp", horizon_bars=1, up_probability_ppm=550_000, realised_sign=0),
        calib.continuous_entry(kind="perp", horizon_bars=1, up_probability_ppm=550_000, realised_sign=-1),
    ]
    bins = calib.reliability_bins(entries)
    five = bins[5]
    assert five.n == 3
    assert five.n_yes_x2 == 3  # 2 + 1 + 0
    assert five.n_yes == 1
    assert five.yes_rate_ppm == calib.yes_rate_ppm(n=3, n_yes_x2=3) == 500_000


def test_yes_rate_is_one_spelling_over_two_n() -> None:
    assert calib.yes_rate_ppm(n=4, n_yes_x2=8) == PPM_ONE
    assert calib.yes_rate_ppm(n=4, n_yes_x2=0) == 0
    assert calib.yes_rate_ppm(n=3, n_yes_x2=1) == round_half_up(PPM_ONE * 1, 6)
    binary = [calib.binary_entry(category="tech", horizon_bucket="2d", prob_ppm=150_000, outcome=1)] * 3
    bins = calib.reliability_bins(binary)
    assert bins[1].n_yes_x2 == 2 * bins[1].n_yes
    assert bins[1].yes_rate_ppm == PPM_ONE


def test_the_calibration_table_pools_nothing_across_kinds_or_horizons() -> None:
    entries = [
        calib.continuous_entry(kind="perp", horizon_bars=1, up_probability_ppm=900_000, realised_sign=1),
        calib.continuous_entry(kind="perp", horizon_bars=24, up_probability_ppm=900_000, realised_sign=-1),
        calib.continuous_entry(kind="fx", horizon_bars=1, up_probability_ppm=900_000, realised_sign=1),
        calib.binary_entry(category="politics", horizon_bucket="30d", prob_ppm=900_000, outcome=1),
    ]
    table = calib.calibration_table(entries)
    assert tuple((item.category, item.horizon_bucket) for item in table) == (
        ("fx", "h1"),
        ("perp", "h1"),
        ("perp", "h24"),
        ("politics", "30d"),
    )
    assert all(item.n == 1 for item in table)
    perp_24 = next(item for item in table if (item.category, item.horizon_bucket) == ("perp", "h24"))
    assert perp_24.ece_ppm == 900_000  # stated 900_000, realised a down move
    perp_1 = next(item for item in table if (item.category, item.horizon_bucket) == ("perp", "h1"))
    assert perp_1.ece_ppm == 100_000
    assert canonical_json([item.to_dict() for item in table])


def test_bin_views_carry_the_ledger_and_drop_only_the_empty_bins() -> None:
    entries = [
        calib.binary_entry(category="politics", horizon_bucket="7d", prob_ppm=650_000, outcome=1),
        calib.binary_entry(category="politics", horizon_bucket="7d", prob_ppm=250_000, outcome=0),
    ]
    table = calib.calibration_table(entries)
    views = calib.calibration_bin_views(table)
    assert len(views) == 2
    assert tuple(view.bin for view in views) == (2, 6)
    for view in views:
        assert view.category == "politics"
        assert view.horizon_bucket == "7d"
        assert view.n == 1
        assert canonical_json(view.to_dict())
    assert views[1].n_yes == 1
    assert views[0].n_yes == 0


def test_a_flat_realisation_at_the_horizon_is_scored_half_each_way_and_costs_the_baseline_nothing() -> None:
    """The tie rule end to end: ``realised == reference`` is the case a directional score must not reward."""
    assert realised_sign_of(11, 10) == 1
    assert realised_sign_of(9, 10) == -1
    assert realised_sign_of(10, 10) == 0
    flat = resolve_horizon(
        forecast_bar_ms=0,
        horizon_bars=1,
        up_probability_ppm=700_000,
        quantiles_ticks=baseline_quantiles_ticks(1_000_000),
        price_ref_ticks=1_000_000,
        price_realised_ticks=1_000_000,
    )
    assert flat.realised_sign == 0
    assert flat.directional_brier_micro == 290_000
    # The baseline's five quantiles are the reference, and the reference is what happened: no loss at all.
    assert flat.baseline_pinball_micro == 0
    assert flat.pinball_micro == 0
    score = score_continuous_horizon([flat], horizon_bars=1)
    assert score.skill_micro == RANDOM_WALK_BRIER_MICRO - 290_000 == -40_000
    assert score.pinball_skill_micro == 0
    assert score.pmv_ticks == 0  # the price did not move, so leaning up earned nothing


def test_the_two_means_refuse_a_mismatched_series_rather_than_truncating_it() -> None:
    """``zip(strict=True)``: a weight list shorter than the value list is a caller's bug, not a shorter mean."""
    with pytest.raises(ValueError):
        weighted_mean_micro([1, 2, 3], [1, 1])
    assert weighted_mean_micro([], []) == 0
    assert weighted_mean_micro([500_000], [0]) == 0  # ruling R2: a zero weight sum is zero, not a raise
    assert plain_mean_micro([]) == 0
    assert plain_mean_micro([1, 2]) == 2  # half up


def test_a_forecast_bar_carries_the_market_statement_beside_the_agents() -> None:
    """The two Briers of 12.1 are always over the same bars because one record holds both statements."""
    bar = ForecastBar(t_ms=DAY_MS, prob_ppm=700_000, market_price_bp=6_327)
    assert bar.market_prob_ppm == ppm_from_bp(6_327) == 632_700
    assert bar.to_dict() == {"t_ms": DAY_MS, "prob_ppm": 700_000, "market_price_bp": 6_327}
    assert canonical_json(bar.to_dict())


def test_the_bin_view_carries_the_tie_count_as_soon_as_the_declared_field_exists() -> None:
    """Ruling R194 and section 17.9: ``CalibrationBinView.n_yes_x2`` is D1's field, landed by gate G2.

    The curve always carries the exact ledger, so the tie is never lost inside this module; the view is
    D1's dataclass and carries it the day the declared field exists. Both halves are asserted, so the day
    gate G2 lands the field this test starts checking the stronger statement instead of being rewritten.
    """
    entries = [
        calib.continuous_entry(kind="fx", horizon_bars=24, up_probability_ppm=550_000, realised_sign=0),
        calib.continuous_entry(kind="fx", horizon_bars=24, up_probability_ppm=550_000, realised_sign=1),
    ]
    slice_ = calib.calibration_slice(entries, category="fx", horizon_bucket="h24")
    assert slice_.bins[5].n_yes_x2 == 3  # 1 for the tie, 2 for the up: an odd ledger
    assert slice_.bins[5].yes_rate_ppm == 750_000
    views = slice_.bin_views()
    assert len(views) == 1
    declared = {field.name for field in dataclasses.fields(CalibrationBinView)}
    ledger_field = "n_yes_x2"  # named through a variable: the attribute does not exist before gate G2
    if ledger_field in declared:
        assert getattr(views[0], ledger_field) == 3
        assert calib.yes_rate_ppm(n=views[0].n, n_yes_x2=getattr(views[0], ledger_field)) == 750_000
    else:
        # Before the gate the view holds only the whole count, and the odd half lives in the curve.
        assert views[0].n_yes == 1
        assert slice_.bins[5].n_yes_x2 == 2 * views[0].n_yes + 1


# --------------------------------------------------------------------------------------------------
# 10.3 The integer logit table, which lives here because there is one platform-independent logarithm
# --------------------------------------------------------------------------------------------------
def test_the_logit_table_has_the_declared_shape_and_pinned_values() -> None:
    """Section 10.3: a 10 001-entry table, and the three values a reader can check by hand."""
    assert LOGIT_TABLE_SIZE == 10_001
    assert len(LOGIT_TABLE) == LOGIT_TABLE_SIZE
    assert (LOGIT_TABLE_STEPS, LOGIT_MIN_INDEX, LOGIT_MAX_INDEX, LOGIT_EVEN_INDEX) == (10_000, 1, 9_999, 5_000)
    assert PPM_PER_LOGIT_STEP == 100
    # ln(1/2) - ln(1/2) = 0; ln(0.25/0.75) = -1.0986; ln(0.0001/0.9999) = -9.2102.
    assert logit_milli(500_000) == 0
    assert logit_milli(250_000) == -1_099
    assert logit_milli(750_000) == 1_099
    assert logit_milli(100) == -9_210
    assert logit_milli(999_900) == 9_210
    assert all(isinstance(value, int) for value in LOGIT_TABLE)


def test_the_logit_table_is_non_decreasing_and_exactly_antisymmetric() -> None:
    """Both properties are what let a milli weight be added to and subtracted from without a bias."""
    assert all(LOGIT_TABLE[index] <= LOGIT_TABLE[index + 1] for index in range(LOGIT_TABLE_STEPS))
    assert all(LOGIT_TABLE[index] == -LOGIT_TABLE[LOGIT_TABLE_STEPS - index] for index in range(LOGIT_TABLE_SIZE))
    # The table is not strictly increasing, and cannot be: near even odds a basis point of probability is
    # four tenths of a milli-nat. This is asserted rather than left implicit because it is why
    # ``unlogit_ppm`` needs a stated tie rule at all.
    assert any(LOGIT_TABLE[index] == LOGIT_TABLE[index + 1] for index in range(LOGIT_MIN_INDEX, LOGIT_MAX_INDEX))


def test_the_two_unrepresentable_ends_are_clamped_and_never_raise() -> None:
    """``logit(0)`` and ``logit(1)`` are infinite; a genome's prior may still be either (section 10.1)."""
    assert LOGIT_TABLE[0] == LOGIT_TABLE[LOGIT_MIN_INDEX]
    assert LOGIT_TABLE[LOGIT_TABLE_STEPS] == LOGIT_TABLE[LOGIT_MAX_INDEX]
    assert logit_milli(0) == logit_milli(100) == -9_210
    assert logit_milli(PPM_ONE) == logit_milli(999_900) == 9_210
    assert logit_milli(-5) == -9_210
    assert logit_milli(PPM_ONE + 5) == 9_210
    assert unlogit_ppm(10**9) == LOGIT_MAX_INDEX * PPM_PER_LOGIT_STEP == 999_900
    assert unlogit_ppm(-(10**9)) == LOGIT_MIN_INDEX * PPM_PER_LOGIT_STEP == 100


def test_the_index_rounds_to_the_nearest_basis_point_with_the_tie_toward_even_odds() -> None:
    assert logit_index_of(500_000) == 5_000
    assert logit_index_of(250_049) == 2_500
    assert logit_index_of(250_051) == 2_501
    # A tie: 250_050 ppm is half a basis point, and it rounds up (toward 5_000), while its mirror
    # 749_950 rounds down (toward 5_000), so the two indices sum to BP_ONE and the logits are mirrored.
    assert logit_index_of(250_050) == 2_501
    assert logit_index_of(749_950) == 7_499
    assert logit_index_of(250_050) + logit_index_of(749_950) == LOGIT_TABLE_STEPS
    assert logit_milli(250_050) == -logit_milli(749_950)


@settings(max_examples=400, deadline=None)
@given(prob_ppm=st.integers(min_value=0, max_value=PPM_ONE))
def test_logit_is_antisymmetric_on_the_ppm_grid(prob_ppm: int) -> None:
    assert logit_milli(prob_ppm) == -logit_milli(PPM_ONE - prob_ppm)


@settings(max_examples=400, deadline=None)
@given(logit_value=st.integers(min_value=-20_000, max_value=20_000))
def test_unlogit_is_representable_antisymmetric_monotone_and_idempotent(logit_value: int) -> None:
    """The four properties ``newsbayes`` relies on to update its own prior without drifting."""
    probability = unlogit_ppm(logit_value)
    assert 100 <= probability <= 999_900
    assert probability % PPM_PER_LOGIT_STEP == 0
    assert unlogit_ppm(-logit_value) == PPM_ONE - probability
    assert unlogit_ppm(logit_value + 1) >= probability
    assert unlogit_ppm(logit_milli(probability)) == probability


@settings(max_examples=400, deadline=None)
@given(prob_ppm=st.integers(min_value=0, max_value=PPM_ONE))
def test_the_round_trip_is_exact_in_milli_nats_and_within_the_declared_ppm_bound(prob_ppm: int) -> None:
    """The value round trip is exact; the probability round trip loses at most the table's resolution."""
    milli = logit_milli(prob_ppm)
    assert logit_milli(unlogit_ppm(milli)) == milli
    if 100 <= prob_ppm <= 999_900:
        assert abs(unlogit_ppm(milli) - prob_ppm) <= LOGIT_ROUND_TRIP_PPM_MAX


def test_the_declared_round_trip_bound_is_attained_and_not_slack() -> None:
    """A bound nobody reaches would hide a regression, so the worst case is searched for and pinned."""
    worst = max(abs(unlogit_ppm(logit_milli(prob)) - prob) for prob in range(0, PPM_ONE + 1, 25))
    assert worst == LOGIT_ROUND_TRIP_PPM_MAX == 250
    on_the_price_grid = max(
        abs(unlogit_ppm(logit_milli(prob)) - prob) for prob in range(100, 999_901, PPM_PER_LOGIT_STEP)
    )
    assert on_the_price_grid == 200  # two basis points, at even odds


def test_the_newsbayes_update_of_section_10_3_moves_the_prior_the_way_the_hits_point() -> None:
    """The one arithmetic 10.3 asks for: a log-odds sum in integers, read back as a probability."""
    prior_ppm = 630_000  # the market at 6_300 bp, which is what ``prior_permille`` weighs
    weight_per_hit_milli = 200
    bullish = unlogit_ppm(logit_milli(prior_ppm) + 3 * weight_per_hit_milli)
    bearish = unlogit_ppm(logit_milli(prior_ppm) - 3 * weight_per_hit_milli)
    assert logit_milli(prior_ppm) == 532
    assert bullish > prior_ppm > bearish
    assert bullish == 756_200
    assert bearish == 483_100
    # Symmetry: the same evidence in the two directions from even odds gives mirrored probabilities.
    assert (unlogit_ppm(600), unlogit_ppm(-600)) == (645_600, 354_400)
    assert unlogit_ppm(600) == PPM_ONE - unlogit_ppm(-600)
    # A wall of evidence saturates at a tradable probability rather than at certainty.
    assert unlogit_ppm(logit_milli(prior_ppm) + 10_000 * weight_per_hit_milli) == 999_900


def test_the_logit_table_reaches_no_platform_library() -> None:
    """Ruling 1.3's reason, applied to the genome side: ``math.log`` never enters a family's output."""
    identifiers = module_identifiers(REPO_ROOT / "src" / "pmx" / "scoring.py")
    for banned in ("math", "log", "log2", "log10", "exp", "float", "np", "numpy"):
        assert banned not in identifiers
    assert "Decimal" in identifiers
    assert "localcontext" in identifiers


def module_imports(path: Path) -> tuple[str, ...]:
    """Every module a file imports, in source order (a docstring mentioning one is not an import)."""
    names: list[str] = []
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return tuple(names)


def module_identifiers(path: Path) -> frozenset[str]:
    """Every identifier a file binds or reads: names, attributes, arguments, functions and classes."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.ClassDef):
            found.add(node.name)
        elif isinstance(node, ast.alias):
            found.add(node.asname or node.name)
    return frozenset(found)


def test_calibration_is_not_time_weighted() -> None:
    """Section 12.2 states it so that nobody aligns it with 12.1 later: bins count forecasts.

    The structural form is stronger than a scan: a ``CalibrationEntry`` carries no instant and no
    duration, so a time weight is not expressible in this module's inputs at all.
    """
    entries = [
        calib.binary_entry(category="world", horizon_bucket="30d", prob_ppm=900_000, outcome=1),
        calib.binary_entry(category="world", horizon_bucket="30d", prob_ppm=100_000, outcome=0),
    ]
    slice_ = calib.calibration_slice(entries, category="world", horizon_bucket="30d")
    assert slice_.bins[9].n == 1
    assert slice_.bins[1].n == 1
    assert slice_.n == 2
    assert [field.name for field in dataclasses.fields(calib.CalibrationEntry)] == [
        "category",
        "horizon_bucket",
        "prob_ppm",
        "yes_x2",
    ]
    identifiers = module_identifiers(REPO_ROOT / "src" / "pmx" / "metrics" / "calibration.py")
    for banned in ("interval_ms", "t_ms", "weights", "weighted_mean_micro", "bar_weights_ms"):
        assert banned not in identifiers


def test_calibration_imports_nothing_from_execution_and_reads_no_fill() -> None:
    """The plan's done-when for E3, asserted here as well as in the architecture test's rule 2.

    The whitelist is exact, so a new import is a deliberate act. It is the stdlib plus ``pmx.types``:
    the module dropped ``typing`` and a duplicate ``dataclasses`` when gate G2 landed the C1b names it
    needed in ``pmx.types``, which is what moved the tuple and not what it stands for.
    """
    path = REPO_ROOT / "src" / "pmx" / "metrics" / "calibration.py"
    assert module_imports(path) == (
        "__future__",
        "collections.abc",
        "dataclasses",
        "pmx.types",
    )
    assert not [name for name in module_imports(path) if name.startswith(("pmx.engine", "pmx.journal"))]
    identifiers = module_identifiers(path)
    for banned in ("Fill", "fee_cents", "cash_delta_cents", "position", "filled", "Execution"):
        assert banned not in identifiers


def test_scoring_reads_no_fill_either() -> None:
    """The separation is the module's reason to exist: a score never touches money (12.1).

    The whitelist is exact for the same reason as ``calibration``'s. It lost ``re`` and ``pmx`` when
    gate G2 landed ``RE_HORIZON_BUCKET`` in ``pmx.types`` (ruling R188), so the horizon-bucket pattern
    has one spelling and this module compiles no regular expression of its own.
    """
    path = REPO_ROOT / "src" / "pmx" / "scoring.py"
    assert module_imports(path) == (
        "__future__",
        "bisect",
        "collections.abc",
        "dataclasses",
        "decimal",
        "pmx.types",
    )
    assert not [name for name in module_imports(path) if name.startswith(("pmx.engine", "pmx.journal"))]
    identifiers = module_identifiers(path)
    for banned in ("Fill", "fee_cents", "cash_delta_cents", "bankroll_cents", "Execution"):
        assert banned not in identifiers
