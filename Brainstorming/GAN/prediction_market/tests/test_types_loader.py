"""D1: the unit system, the strict models, the dataset loader, seal and verify, and the v1 migration.

These tests pin the things every other package of pmx v2 depends on being true, in the order of
CONTRACTS_V2: the conversions of section 1 (with the worked examples of 1.4 as literals), the identifier
regexes of section 2, the orderings of section 3, the grid of section 5, the strict models of section 7.2
and 7.3, the loader's structural and as-of refusals, the integrity pair of section 7.8, and the twelve
migration identities of section 7.10.

Everything here is offline and deterministic. Two kinds of dataset are used and both are built in the
test rather than recorded, so a fixture can never drift from the loader it is meant to exercise:

* the **committed demo pack** (``data/demo_v1/``), regenerated into ``tmp_path`` and compared byte for
  byte against what is on disk, which is what keeps the committed pack honest;
* a **synthetic imported dataset** with a recent freeze, because the demo pack is exempt from the window
  rules of section 5.6 and cannot be sealed, so the seal, verify and leak paths need a market that a real
  build could have produced.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

import pmx
from pmx.data import loader as loader_module
from pmx.data.loader import (
    DatasetVerification,
    dataset_files,
    dataset_hash_of,
    load_dataset,
    load_manifest,
    load_market_file,
    read_canonical_text,
    seal_dataset,
    verify_dataset,
    verify_dataset_report,
    write_canonical_json,
    write_canonical_jsonl,
    write_manifest,
)
from pmx.data.migrate_v1 import (
    DEMO_FREEZE_DATE,
    DEMO_WIKI_SUBJECTS,
    bundled_v1_markets,
    migrate_market,
    migrate_markets,
    migrate_v1,
    parse_v1_instant,
)
from pmx.data.schema import (
    SCHEMA_DIR,
    SCHEMA_FILES,
    instrument_from_payload,
    load_schema,
    manifest_from_payload,
    market_from_payload,
    news_item_from_payload,
    schema_path,
    validate_against_schema,
)
from pmx.data.sessions import (
    SessionRule,
    calendar_from_payload,
    check_calendar,
    days_since_previous_close,
    generate_calendar,
    in_session,
    is_session_close,
    next_bar_ms,
    prev_bar_ms,
    session_bars,
    session_index,
)
from pmx.errors import (
    DatasetHashMismatchError,
    InvalidConfigError,
    LeakError,
    NonCanonicalValueError,
    PmxError,
    SchemaError,
    SealError,
)
from pmx.journal import canonical_json
from pmx.types import (
    BINARY_POINT_VALUE_MICRO,
    BINARY_TICK_SIZE_MICRO,
    BP_ONE,
    CATEGORIES,
    HORIZON_BUCKETS,
    INSTRUMENT_KINDS,
    LEXICON_COUNT,
    MS_PER_DAY,
    PHASE_ORDER,
    PPM_ONE,
    PRICE_MAX_BP,
    PRICE_MIN_BP,
    RE_AGENT_ID,
    RE_FEE_SCHEDULE_ID,
    RE_MARKET_ID,
    RE_NEWS_ID,
    REMOVED_FILTER_KEYS,
    RNG_ALGORITHM_VERSION,
    SAFETY_LAG_MS_DEFAULT,
    Bar,
    BuildConfig,
    BuiltBy,
    ContinuousInstrument,
    DatasetCounts,
    DatasetFilters,
    DatasetManifest,
    DatasetNews,
    DatasetSplit,
    DatasetWindow,
    Market,
    MarketQuality,
    NewsItem,
    NewsView,
    PortfolioView,
    RunConfig,
    Session,
    SessionCalendar,
    Trade,
    bar_of,
    bp_from_ppm,
    bp_from_v1_cents,
    bp_ratio,
    brier_micro,
    cash_out_cents,
    clamp_ppm,
    clamp_price_bp,
    continuous_calendar,
    cost_cents,
    day_key,
    day_start_ms,
    default_horizons_bars,
    hardness_tags_of,
    interval_ms,
    iso_date_from_ms,
    market_set_hash,
    meta_of,
    milli_ratio,
    month_edges_for,
    ms_from_iso_date,
    neg_ln_micronats,
    ppm_from_bp,
    price_micro,
    proceeds_cents,
    rank_news,
    round_half_up,
    sort_markets,
    sorted_agent_ids,
    sorted_market_ids,
)

REPO = Path(__file__).resolve().parent.parent
DEMO_PACK = REPO / "data" / "demo_v1"
CONTRACT_FIXTURES = REPO / "tests" / "fixtures" / "contract"
SYNTH_FREEZE_DATE = "2026-09-07"


# --------------------------------------------------------------------------------------------------
# 1.2 and 1.4 The unit system
# --------------------------------------------------------------------------------------------------
def test_price_and_probability_conversions_round_trip_and_clamp() -> None:
    assert ppm_from_bp(6_327) == 632_700
    assert bp_from_ppm(632_700) == 6_327
    assert bp_from_ppm(418_700) == 4_187  # section 1.4: a Manifold price of 0.4187
    # A tradable price is never 0 and never 1: those are settlement values.
    assert bp_from_ppm(0) == PRICE_MIN_BP
    assert bp_from_ppm(PPM_ONE) == PRICE_MAX_BP
    assert clamp_price_bp(0) == 1 and clamp_price_bp(10_000) == 9_999
    assert clamp_ppm(-5) == 0 and clamp_ppm(PPM_ONE + 5) == PPM_ONE
    assert bp_from_v1_cents(63) == 6_300


def test_the_worked_brier_and_skill_example_of_section_1_4() -> None:
    assert brier_micro(700_000, 1) == 90_000
    assert brier_micro(630_000, 1) == 136_900
    assert brier_micro(630_000, 1) - brier_micro(700_000, 1) == 46_900
    assert brier_micro(0, 0) == 0 and brier_micro(PPM_ONE, 1) == 0
    assert brier_micro(PPM_ONE, 0) == PPM_ONE


def test_cash_rounding_is_always_against_the_agent() -> None:
    """Section 1.4: 40 contracts at 6 327 bp cost 2 531 cents and sell back for 2 530."""
    assert cost_cents(40, 6_327) == 2_531
    assert proceeds_cents(40, 6_327) == 2_530
    assert cost_cents(40, 6_327) - proceeds_cents(40, 6_327) == 1
    # Opening 40 NO at a YES price of 6 327 bp.
    assert cost_cents(40, BP_ONE - 6_327) == 1_470
    # An exact multiple loses nothing to rounding.
    assert cost_cents(4, 5_000) == proceeds_cents(4, 5_000) == 200


def test_round_half_up_and_the_signed_ratios() -> None:
    assert round_half_up(1, 2) == 1
    assert round_half_up(3, 2) == 2
    assert round_half_up(0, 7) == 0
    # A loss and the mirror gain report the same magnitude, which `//` would not do.
    assert bp_ratio(-1_850, 100_000) == -185
    assert bp_ratio(1_850, 100_000) == 185
    assert bp_ratio(1, 3) == 3_333 and bp_ratio(-1, 3) == -3_333
    assert milli_ratio(12, 85) == 141
    assert milli_ratio(-12, 85) == -141


def test_a_zero_denominator_is_the_callers_problem_and_never_a_silent_zero() -> None:
    """Section 1.2: every ratio is 0 when its denominator is 0, and the caller returns that 0 itself."""
    for call in (
        lambda: round_half_up(5, 0),
        lambda: bp_ratio(5, 0),
        lambda: milli_ratio(5, 0),
    ):
        with pytest.raises(ValueError, match="denominator"):
            call()


def test_the_logarithm_is_the_pinned_decimal_one() -> None:
    """Section 1.3: `Decimal.ln` is correctly rounded, so these integers hold on every platform."""
    assert neg_ln_micronats(500_000) == 693_147
    assert neg_ln_micronats(10_000) == 4_605_170
    assert neg_ln_micronats(990_000) == 10_050


# --------------------------------------------------------------------------------------------------
# 2 Identifiers and enumerations
# --------------------------------------------------------------------------------------------------
def test_the_identifier_regexes_accept_the_contract_and_refuse_windows_hostile_ids() -> None:
    assert RE_MARKET_ID.fullmatch("demo-brexit-2016")
    assert RE_MARKET_ID.fullmatch("kalshi-KXPRES-24-DJT")
    assert RE_MARKET_ID.fullmatch("kalshi:KXBTC") is None  # a colon is not a legal Windows file name
    assert RE_MARKET_ID.fullmatch("bovada-anything") is None
    assert RE_AGENT_ID.fullmatch("market_follower")
    assert RE_AGENT_ID.fullmatch("p017-3fa9c2e1")
    assert RE_AGENT_ID.fullmatch("Market_Follower") is None
    assert RE_NEWS_ID.fullmatch("wce-20160623-0007")
    assert RE_NEWS_ID.fullmatch("wce-2016-0007") is None
    assert RE_FEE_SCHEDULE_ID.fullmatch("demo-zero")
    assert RE_FEE_SCHEDULE_ID.fullmatch("kalshi-general-2026-09")
    assert RE_FEE_SCHEDULE_ID.fullmatch("demo zero") is None


def test_the_category_tuple_is_the_lexicon_index() -> None:
    """Section 7.6: `LEXICON_COUNT` is the length of `CATEGORIES`, so A1 never counts D5's files."""
    assert LEXICON_COUNT == len(CATEGORIES) == 12
    assert CATEGORIES[0] == "politics" and CATEGORIES[-1] == "other"
    assert len(set(CATEGORIES)) == len(CATEGORIES)
    assert HORIZON_BUCKETS == ("30d", "7d", "2d", "0d")
    assert PHASE_ORDER.index("generation") == PHASE_ORDER.index("close") + 1
    assert PHASE_ORDER[-1] == "post"


# --------------------------------------------------------------------------------------------------
# 3 Canonical ordering
# --------------------------------------------------------------------------------------------------
def test_canonical_orderings_are_by_code_point_and_never_by_insertion() -> None:
    assert sorted_market_ids(["kalshi-b", "demo-a", "kalshi-b"]) == ("demo-a", "kalshi-b")
    assert sorted_agent_ids({"trend", "follower", "Aa"}) == ("Aa", "follower", "trend")
    markets = _demo_markets()
    ordered = sort_markets(markets)
    assert [m.id for m in ordered] == [
        m.id for m in sorted(markets, key=lambda x: (x.resolved_at_ms, x.id))
    ]
    assert [m.resolved_at_ms for m in ordered] == sorted(m.resolved_at_ms for m in ordered)


def test_rank_news_puts_the_best_link_first_then_the_oldest_then_the_id() -> None:
    def view(news_id: str, score: int, published_at_ms: int) -> NewsView:
        return NewsView(
            news_id=news_id,
            source="wikipedia_current_events",
            kind="headline",
            published_at_ms=published_at_ms,
            headline="h",
            text="",
            section=None,
            url="",
            match_score_permille=score,
        )

    a = view("wce-20160101-0001", 300, 100)
    b = view("wce-20160101-0002", 900, 200)
    c = view("wce-20160101-0003", 900, 100)
    assert [item.news_id for item in rank_news([a, b, c])] == [c.news_id, b.news_id, a.news_id]


# --------------------------------------------------------------------------------------------------
# 5 The grid and the one date parser
# --------------------------------------------------------------------------------------------------
def test_the_bar_grid_is_integer_arithmetic_on_the_open_time() -> None:
    assert interval_ms(1_440) == MS_PER_DAY
    assert interval_ms(60) == 3_600_000
    day = ms_from_iso_date("2016-06-24")
    assert day % MS_PER_DAY == 0
    assert bar_of(day + 1, 1_440) == day
    assert bar_of(day + MS_PER_DAY - 1, 1_440) == day
    assert bar_of(day + MS_PER_DAY, 1_440) == day + MS_PER_DAY
    assert bar_of(day + 3_600_000 + 59, 60) == day + 3_600_000
    assert day_start_ms(day + 12 * 3_600_000) == day


def test_the_date_parser_is_exact_and_refuses_what_is_not_a_date() -> None:
    assert ms_from_iso_date("1970-01-01") == 0
    assert ms_from_iso_date("2026-09-07") == 1_788_739_200_000
    assert iso_date_from_ms(1_788_739_200_000) == "2026-09-07"
    assert iso_date_from_ms(ms_from_iso_date("2016-06-24") + MS_PER_DAY - 1) == "2016-06-24"
    assert day_key(ms_from_iso_date("2016-06-24")) == "20160624"
    for bad in ("2016-6-24", "2016-02-30", "20160624", "2016-06-24T00:00", ""):
        with pytest.raises(SchemaError):
            ms_from_iso_date(bad)


def test_the_month_edges_are_the_thirteen_of_section_7_7() -> None:
    start = ms_from_iso_date("2025-09-08")
    edges = month_edges_for(start)
    assert len(edges) == 13
    offsets = [(edge - start) // MS_PER_DAY for edge in edges]
    assert offsets == [0, 30, 60, 91, 121, 152, 182, 212, 243, 273, 304, 334, 365]


# --------------------------------------------------------------------------------------------------
# 7.5 Hardness tags
# --------------------------------------------------------------------------------------------------
def _flat_bars(prices: Sequence[int]) -> tuple[Bar, ...]:
    return tuple(
        Bar(
            t_ms=index * MS_PER_DAY,
            open_bp=price,
            high_bp=price,
            low_bp=price,
            close_bp=price,
            vwap_bp=price,
            volume_milli=0,
            n_trades=0,
            yes_bid_bp=None,
            yes_ask_bp=None,
            open_interest=None,
        )
        for index, price in enumerate(prices)
    )


def _tags(prices: Sequence[int], *, resolution: int, illiquid: bool = False) -> tuple[str, ...]:
    """Section 7.5 over a flat daily tape whose settlement is inside its last bar."""
    bars = _flat_bars(prices)
    resolved_at_ms = bars[-1].t_ms + MS_PER_DAY - 1 if bars else 0
    return hardness_tags_of(bars, resolution=resolution, resolved_at_ms=resolved_at_ms, illiquid=illiquid)


def test_hardness_tags_follow_section_7_5_and_the_d_4_correction() -> None:
    # `trivial` is the market whose outcome was never in doubt, not the one that never became certain.
    assert _tags([9_600] * 10, resolution=1) == ("trivial",)
    assert _tags([200] * 10, resolution=0) == ("trivial",)
    assert _tags([5_100] * 10, resolution=1) == ()
    # `upset`: the last thirty days averaged on the wrong side of 5 000.
    assert "upset" in _tags([2_000] * 10, resolution=1)
    assert "upset" in _tags([8_000] * 10, resolution=0)
    assert "upset" not in _tags([8_000] * 10, resolution=1)
    # `whipsaw`: strictly more than four crossings of 5 000.
    assert "whipsaw" not in _tags([4_000, 6_000, 4_000, 6_000, 4_000], resolution=1)
    assert "whipsaw" in _tags([4_000, 6_000, 4_000, 6_000, 4_000, 6_000], resolution=1)
    # The relative tag is the caller's to pass, and the result is always sorted.
    assert _tags([200] * 10, resolution=0, illiquid=True) == ("illiquid", "trivial")
    assert hardness_tags_of((), resolution=1, resolved_at_ms=0) == ()


def test_upset_reads_the_last_thirty_days_of_life_and_not_the_whole_tape() -> None:
    """The window of section 7.5 is a real restriction, and both tapes here prove it by disagreeing.

    A market that spent its first fifty days at 8 000, fell to 2 000 for its last thirty and then resolved
    YES is an upset: what the tag reads is the price the market died at. Averaged over the whole tape the
    mean is 5 750 and the tag would not fire, so the eighty-day tape is a test of the window rather than
    of the sign. The mirror tape (2 000 then 8 000, resolved YES) is the same experiment reversed: its
    last thirty days are right and its whole-tape mean is 4 250, so an unwindowed reading would tag it.
    """
    assert "upset" in _tags([8_000] * 50 + [2_000] * 30, resolution=1)
    assert "upset" not in _tags([2_000] * 50 + [8_000] * 30, resolution=1)
    # And the whole life is the window when the life is shorter than thirty days.
    assert "upset" in _tags([2_000] * 10, resolution=1)
    assert "upset" not in _tags([8_000] * 10, resolution=1)


# --------------------------------------------------------------------------------------------------
# 7.2 The market's own methods
# --------------------------------------------------------------------------------------------------
def test_bar_at_and_bars_before_are_the_as_of_rules_of_section_5_4() -> None:
    market = load_market_file(DEMO_PACK / "markets" / "demo-brexit-2016.json")
    first = market.bars[0].t_ms
    assert market.bar_at(first) is market.bars[0]
    assert market.bar_at(first + MS_PER_DAY - 1) is market.bars[0]
    assert market.bar_at(first - MS_PER_DAY) is None
    assert market.bar_at(market.bars[-1].t_ms + MS_PER_DAY) is None
    # A bar is completed only when it has fully elapsed: at its own open, nothing of it is visible.
    assert market.bars_before(first, 90) == ()
    assert market.bars_before(first + MS_PER_DAY, 90) == (market.bars[0],)
    assert market.bars_before(first + 5 * MS_PER_DAY, 2) == tuple(market.bars[3:5])
    assert market.bars_before(first + 5 * MS_PER_DAY, 0) == ()
    assert len(market.bars_before(market.bars[-1].t_ms, 720)) == len(market.bars) - 1


def test_a_market_keeps_tuples_even_when_an_importer_hands_lists() -> None:
    """The declared type is a tuple because a market is an immutable record the engine slices."""
    market = load_market_file(DEMO_PACK / "markets" / "demo-brexit-2016.json")
    relaxed = Market(
        **{
            **{field: getattr(market, field) for field in market.__slots__},
            "bars": list(market.bars),
            "tags": ["a", "b"],
        }
    )
    assert isinstance(relaxed.bars, tuple) and isinstance(relaxed.tags, tuple)
    assert relaxed.bars == market.bars


def test_meta_of_is_the_leak_free_projection() -> None:
    market = load_market_file(DEMO_PACK / "markets" / "demo-brexit-2016.json")
    meta = meta_of(market, fold="train")
    rendered = meta.to_dict()
    assert meta.n_bars == len(market.bars) and meta.fold == "train"
    # MarketMeta is for the scorer and the selector: it carries the outcome, and no price at all.
    assert "resolution" in rendered
    for forbidden in ("bars", "trades", "first_price_bp", "final_price_bp", "quality", "question"):
        assert forbidden not in rendered


# --------------------------------------------------------------------------------------------------
# 8.1 and 7.4 The configs refuse what they cap
# --------------------------------------------------------------------------------------------------
def test_run_config_defaults_are_canonical_and_hashable() -> None:
    config = RunConfig(seed=7, market_ids_hash=market_set_hash(["demo-a", "demo-b"]))
    rendered = config.to_dict()
    assert json.loads(canonical_json(rendered)) == rendered
    assert rendered["research_budget_by_agent"] == []
    assert rendered["fold"] == "all"
    assert config.interval_ms == MS_PER_DAY
    assert config.research_budget_for("anyone") == 10


def test_run_config_refuses_every_value_outside_its_cap() -> None:
    cases: tuple[dict[str, object], ...] = (
        {"seed": -1},
        {"seed": 2**63},
        {"interval_min": 15},
        {"bankroll_cents": 0},
        {"volume_cap_permille": 1_001},
        {"slippage_bp_per_pct": -1},
        {"ruin_floor_cents": -1},
        {"bars_window": 721},
        {"trades_window": 1_001},
        {"news_per_market": 51},
        {"news_global": 201},
        {"hive_lessons": 51},
        {"hive_forecasts": 2_001},
        {"markets_per_obs_max": 201},
        {"markets_per_obs_max": 0},
        {"research_budget_units": -1},
        {"fold": "everything"},
        {"t0_ms": 10, "t1_ms": 10},
        {"contamination_hash": "nothex"},
        {"market_ids_hash": "nothex"},
        {"research_budget_by_agent": (("b", 1), ("a", 1))},
        {"research_budget_by_agent": (("a", -1),)},
        {"research_budget_by_agent": (("Bad Agent", 1),)},
    )
    for override in cases:
        overrides = {"seed": 1, **override}
        with pytest.raises(InvalidConfigError):
            RunConfig(**overrides)  # type: ignore[arg-type]


def test_the_per_agent_research_budget_overrides_the_scalar() -> None:
    config = RunConfig(seed=1, research_budget_units=10, research_budget_by_agent=(("greedy", 0),))
    assert config.research_budget_for("greedy") == 0
    assert config.research_budget_for("thrifty") == 10


def test_build_config_renders_a_null_limit_as_zero_because_the_manifest_forbids_null() -> None:
    build = BuildConfig(freeze_date="2026-09-07", providers=("kalshi", "manifold"))
    rendered = build.to_dict()
    assert rendered["limit_per_provider"] == 0
    assert rendered["providers"] == ["kalshi", "manifold"]
    assert build.freeze_ms == ms_from_iso_date("2026-09-07")
    assert json.loads(canonical_json(rendered)) == rendered
    for override in (
        {"freeze_date": "07-09-2026"},
        {"providers": ()},
        {"providers": ("bovada",)},
        {"providers": ("manifold", "kalshi")},
        {"interval_min": 5},
        {"min_traded_bars_per_day_permille": 1_001},
        {"news_sources": ("twitter",)},
        {"limit_per_provider": -1},
    ):
        with pytest.raises(InvalidConfigError):
            BuildConfig(**{"freeze_date": "2026-09-07", "providers": ("kalshi",), **override})  # type: ignore[arg-type]


def test_market_set_hash_is_stable_order_free_and_sensitive() -> None:
    a = market_set_hash(["demo-b", "demo-a"])
    b = market_set_hash(["demo-a", "demo-b"])
    c = market_set_hash(["demo-a", "demo-c"])
    assert a == b != c
    assert len(a) == 64


# --------------------------------------------------------------------------------------------------
# 7.13 and 4.1 The schemas and the strict models
# --------------------------------------------------------------------------------------------------
def test_every_schema_lives_inside_the_package_and_resolves() -> None:
    assert SCHEMA_DIR == REPO / "src" / "pmx" / "schemas"
    for name in SCHEMA_FILES:
        assert schema_path(name).is_file()
        assert load_schema(name)["$schema"].endswith("2020-12/schema")  # type: ignore[union-attr]
    with pytest.raises(SchemaError):
        schema_path("market.v1.json")
    with pytest.raises(SchemaError):
        load_schema("nope.json")


def test_load_schema_hands_out_a_copy_so_one_reader_cannot_poison_the_next() -> None:
    first = load_schema("market.v2.json")
    first["title"] = "tampered"
    assert load_schema("market.v2.json")["title"] == "pmx market v2"


def test_the_strict_models_refuse_the_float_the_json_schema_accepts() -> None:
    """Section 4.1: `3200.0` is an integer to JSON Schema, and that is the hole pydantic closes."""
    payload = _fixture("market.demo-brexit-2016.json")
    payload["bars"][0]["close_bp"] = 3_200.0
    validate_against_schema("market.v2.json", payload)  # the schema is happy, which is the point
    with pytest.raises(SchemaError, match="strict model"):
        market_from_payload(payload)


def test_the_strict_models_refuse_a_string_where_an_integer_belongs() -> None:
    payload = _fixture("market.demo-brexit-2016.json")
    payload["created_at_ms"] = str(payload["created_at_ms"])
    with pytest.raises(SchemaError):
        market_from_payload(payload)


def test_the_market_schema_refuses_an_unknown_key_a_zero_price_and_a_bad_id() -> None:
    for mutate in (
        lambda p: p.update(resolution_prob=1),
        lambda p: p["bars"][0].update(low_bp=0),
        lambda p: p.update(id="kalshi:KXBTC"),
        lambda p: p.update(source="synthetic"),
        lambda p: p.update(fee_schedule_id="demo zero"),
        lambda p: p.pop("wiki_subjects"),
    ):
        payload = _fixture("market.demo-brexit-2016.json")
        mutate(payload)
        with pytest.raises(SchemaError):
            market_from_payload(payload)


def test_the_news_model_reads_the_contract_fixture_and_refuses_a_contradicting_kind() -> None:
    item = news_item_from_payload(_fixture("news.wce-20160623-0007.json"))
    assert item.news_id == "wce-20160623-0007"
    assert item.visible_from_ms - item.published_at_ms == SAFETY_LAG_MS_DEFAULT
    assert item.published_at_ms % MS_PER_DAY == 0  # the end of the page day, section 5.5
    assert item.score_for(item.match_ids[0]) == item.match_scores_permille[0]
    assert item.score_for("demo-not-linked") == 0
    payload = _fixture("news.wce-20160623-0007.json")
    payload["kind"] = "comment"
    with pytest.raises(SchemaError):
        news_item_from_payload(payload)


def test_the_manifest_model_reads_the_contract_fixture() -> None:
    manifest = manifest_from_payload(_fixture("dataset.manifest.json"))
    assert manifest.name == "demo_v1" and manifest.sealed is False
    assert manifest.is_demo_pack is True
    assert manifest.split.fold_of(manifest.split.train_end_ms - 1) == "train"
    assert manifest.split.fold_of(manifest.split.train_end_ms) == "validation"
    assert manifest.split.fold_of(manifest.split.validation_end_ms) == "sealed"
    assert set(manifest.filters.removed) == set(REMOVED_FILTER_KEYS)
    assert json.loads(canonical_json(manifest.to_dict())) == _fixture("dataset.manifest.json")


# --------------------------------------------------------------------------------------------------
# 4.2 and 4.3 Bytes and digests
# --------------------------------------------------------------------------------------------------
def test_a_carriage_return_is_refused_and_never_normalised(tmp_path: Path) -> None:
    """Section 4.2: on Windows the default text mode would leave the hash right and the bytes wrong."""
    good = tmp_path / "good.json"
    write_canonical_json(good, {"b": 2, "a": 1})
    assert good.read_bytes() == b'{"a":1,"b":2}\n'
    assert read_canonical_text(good) == '{"a":1,"b":2}\n'
    bad = tmp_path / "bad.json"
    bad.write_bytes(b'{"a":1}\r\n')
    with pytest.raises(NonCanonicalValueError, match="carriage return"):
        read_canonical_text(bad)


def test_the_dataset_hash_is_the_listing_of_section_4_3(tmp_path: Path) -> None:
    (tmp_path / "markets").mkdir()
    write_canonical_json(tmp_path / "markets" / "demo-a.json", {"a": 1})
    write_canonical_jsonl(tmp_path / "news" / "20160624.jsonl", [{"b": 2}, {"c": 3}])
    files = dataset_files(tmp_path)
    assert [entry.path for entry in files] == ["markets/demo-a.json", "news/20160624.jsonl"]
    assert files[0].bytes == len((tmp_path / "markets" / "demo-a.json").read_bytes())
    listing = "\n".join(f"{entry.path} {entry.sha256}" for entry in files) + "\n"
    import hashlib

    assert dataset_hash_of(files) == hashlib.sha256(listing.encode("utf-8")).hexdigest()
    # The contract's own manifest fixture is the cross-check of the formula.
    fixture = manifest_from_payload(_fixture("dataset.manifest.json"))
    assert dataset_hash_of(fixture.files) == fixture.dataset_hash


# --------------------------------------------------------------------------------------------------
# 7.10 The migration
# --------------------------------------------------------------------------------------------------
def test_parse_v1_instant_reads_both_v1_label_shapes() -> None:
    assert parse_v1_instant("2016-06-24") == ms_from_iso_date("2016-06-24")
    assert parse_v1_instant("2016-06-23T20:00") == ms_from_iso_date("2016-06-23") + 20 * 3_600_000
    for bad in ("2016-06-23 20:00", "2016-06-23T20", "yesterday"):
        with pytest.raises(SchemaError):
            parse_v1_instant(bad)


def test_the_migration_reproduces_the_contract_fixture_field_for_field() -> None:
    """Ruling R97 closed the one divergence: the migrated market is now the fixture, field for field.

    Section 7.10 item 4 used to require ``wiki_subjects == []`` while C0's own fixture carried a real
    article title and ``test_contract_schemas.py`` asserted that field was non-empty. The fixture won:
    a demo pack with no subjects is invisible to the linker of section 7.6, which compares an item's
    ``wiki_links`` against exactly this field.
    """
    v1 = _v1_market("brexit-2016")
    migrated = migrate_market(v1).to_dict()
    fixture = _fixture("market.demo-brexit-2016.json")
    assert migrated["bars"] == fixture["bars"]
    differing = {key for key in set(migrated) | set(fixture) if migrated.get(key) != fixture.get(key)}
    assert differing == set()
    assert migrated["wiki_subjects"] == ["2016 United Kingdom European Union membership referendum"]


def test_every_migration_identity_of_section_7_10() -> None:
    v1_markets = {market.id: market for market in bundled_v1_markets()}
    migrated = migrate_markets()
    assert len(migrated) == 12
    for market in migrated:
        v1 = v1_markets[market.provider_id]
        # 4: the fixed metadata of the pack
        assert market.id == f"demo-{v1.id}"
        assert market.provider == "demo" and market.source == "reconstructed"
        assert market.currency == "usd" and market.fee_schedule_id == "demo-zero"
        assert market.trades == ()
        # 4 (ruling R97): the hand-written subject table of the reconstructed pack, sorted.
        assert market.wiki_subjects == DEMO_WIKI_SUBJECTS[v1.id]
        assert market.wiki_subjects == tuple(sorted(market.wiki_subjects))
        assert all(title.strip() == title and title for title in market.wiki_subjects)
        assert market.schema_version == pmx.MARKET_SCHEMA
        assert market.category in CATEGORIES
        # 1: the grid is daily and aligned
        assert market.interval_min == 1_440
        assert all(bar.t_ms % MS_PER_DAY == 0 for bar in market.bars)
        # 2: dense from the created bar to the resolved bar, no gap and no duplicate
        assert market.bars[0].t_ms == bar_of(market.created_at_ms, 1_440)
        assert market.bars[-1].t_ms == bar_of(market.resolved_at_ms, 1_440)
        stamps = [bar.t_ms for bar in market.bars]
        assert stamps == list(range(stamps[0], stamps[-1] + MS_PER_DAY, MS_PER_DAY))
        # 3: the prices are the v1 cents times 100
        assert market.first_price_bp == bp_from_v1_cents(v1.prices[0].price)
        assert market.final_price_bp == bp_from_v1_cents(v1.prices[-1].price)
        assert market.bars[-1].close_bp == market.final_price_bp
        # 5: no volume, because v1 has none
        assert all(bar.volume_milli == 0 and bar.n_trades == 0 for bar in market.bars)
        assert market.quality.volume_milli_total == 0 and market.quality.traded_bars == 0
        assert market.quality.unique_bettors is None
        assert market.quality.life_days == (market.resolved_at_ms - market.created_at_ms) // MS_PER_DAY
        # 6: the hardness tags are section 7.5 over the migrated bars
        assert market.hardness_tags == hardness_tags_of(
            market.bars, resolution=market.resolution, resolved_at_ms=market.resolved_at_ms
        )


def test_a_bar_between_two_control_points_carries_the_previous_price_flat() -> None:
    market = migrate_market(_v1_market("brexit-2016"))
    flat = market.bars[1]
    assert flat.open_bp == flat.high_bp == flat.low_bp == flat.close_bp == flat.vwap_bp == 3_200
    # The night of the referendum: two control points in one bar keep the open of the previous close and
    # show the move in the range.
    night = market.bars[-1]
    assert (night.open_bp, night.high_bp, night.low_bp, night.close_bp) == (3_000, 9_800, 3_000, 9_800)
    assert night.vwap_bp == night.close_bp  # no volume in the source, so no volume weighting


def test_brexit_carries_upset_and_the_pack_spreads_the_tags() -> None:
    tags = {market.id: market.hardness_tags for market in migrate_markets()}
    assert "upset" in tags["demo-brexit-2016"]
    assert "upset" in tags["demo-trump-2016"]
    assert tags["demo-fed-hike-mar-2022"] == ()  # the crowd was right and confident


def test_the_migration_is_deterministic_byte_for_byte(tmp_path: Path) -> None:
    first = migrate_v1(tmp_path / "one")
    second = migrate_v1(tmp_path / "two")
    assert first.manifest.dataset_hash == second.manifest.dataset_hash
    for entry in first.manifest.files:
        assert (tmp_path / "one" / entry.path).read_bytes() == (tmp_path / "two" / entry.path).read_bytes()
    assert (tmp_path / "one" / "manifest.json").read_bytes() == (tmp_path / "two" / "manifest.json").read_bytes()


def test_the_committed_demo_pack_is_what_the_migration_produces_today(tmp_path: Path) -> None:
    """The pack is generated and committed, so a stale commit has to be a failing test."""
    fresh = migrate_v1(tmp_path / "demo_v1")
    committed = load_dataset(DEMO_PACK, verify=True)
    assert fresh.manifest.dataset_hash == committed.manifest.dataset_hash
    assert fresh.manifest.to_dict() == committed.manifest.to_dict()
    assert len(committed.manifest.files) == 12, "one file per demo market, and the hash covers them all"
    for entry in committed.manifest.files:
        assert (DEMO_PACK / entry.path).read_bytes() == (tmp_path / "demo_v1" / entry.path).read_bytes()


def test_the_demo_manifest_says_what_the_pack_is(tmp_path: Path) -> None:
    dataset = migrate_v1(tmp_path / "demo_v1")
    manifest = dataset.manifest
    assert manifest.name == "demo_v1" and manifest.sealed is False
    assert manifest.providers == ("demo",) and manifest.is_demo_pack
    assert manifest.interval_min == 1_440
    assert manifest.freeze_date == DEMO_FREEZE_DATE
    assert manifest.freeze_ms == ms_from_iso_date(DEMO_FREEZE_DATE)
    assert manifest.safety_lag_ms == SAFETY_LAG_MS_DEFAULT
    assert manifest.counts.markets == 12 == len(dataset.metas)
    assert manifest.counts.per_provider == {"demo": 12}
    assert sum(manifest.counts.per_category.values()) == 12
    assert manifest.counts.resolution_yes + manifest.counts.resolution_no == 12
    assert manifest.counts.hardness_tags["upset"] == 3
    assert manifest.news.n_items == 0 and manifest.news.sources == ()
    assert set(manifest.filters.removed) == set(REMOVED_FILTER_KEYS)
    assert all(count == 0 for count in manifest.filters.removed.values())
    assert manifest.built_by == BuiltBy(
        pmx_version=pmx.__version__,
        contract_version=pmx.CONTRACT_VERSION,
        rng_algorithm_version=RNG_ALGORITHM_VERSION,
    )
    # The window is the pack's own life, and the split is section 7.7's formula over it (section 7.1).
    assert manifest.window.start_ms == day_start_ms(
        min(dataset.market(meta.id).created_at_ms for meta in dataset.metas)
    )
    assert manifest.window.end_ms == max(meta.resolved_at_ms for meta in dataset.metas) + 1
    assert manifest.split.month_edges_ms == month_edges_for(manifest.window.start_ms)
    counts = (manifest.split.n_train, manifest.split.n_validation, manifest.split.n_sealed)
    assert sum(counts) == 12
    folds = [meta.fold for meta in dataset.metas]
    assert (folds.count("train"), folds.count("validation"), folds.count("sealed")) == counts


# --------------------------------------------------------------------------------------------------
# 7.2, 7.8 and 7.9 The loader
# --------------------------------------------------------------------------------------------------
def test_the_demo_pack_loads_with_its_folds_and_lazy_tapes() -> None:
    dataset = load_dataset(DEMO_PACK)
    assert len(dataset.metas) == 12
    assert [meta.id for meta in dataset.metas] == sorted(
        (meta.id for meta in dataset.metas),
        key=lambda market_id: (dataset.meta(market_id).resolved_at_ms, market_id),
    )
    brexit = dataset.market("demo-brexit-2016")
    assert brexit is dataset.market("demo-brexit-2016")  # loaded once, cached per dataset
    assert len(brexit.bars) == 145
    assert dataset.meta("demo-brexit-2016").fold == "train"
    assert dataset.news_global(brexit.resolved_at_ms) == ()
    assert dataset.news_for("demo-brexit-2016", brexit.resolved_at_ms) == ()
    assert dataset.background_for("demo-brexit-2016", brexit.resolved_at_ms) == ()
    with pytest.raises(SchemaError):
        dataset.meta("demo-nothing")


def test_verify_passes_on_the_committed_pack_and_fails_on_a_single_byte(tmp_path: Path) -> None:
    pack = tmp_path / "demo_v1"
    shutil.copytree(DEMO_PACK, pack)
    report = verify_dataset(pack)
    assert report.ok and report.dataset_hash == report.expected
    assert report.mismatched_files == () and report.missing_files == () and report.extra_files == ()
    target = pack / "markets" / "demo-brexit-2016.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["notes"] = payload["notes"] + "."
    write_canonical_json(target, payload)
    with pytest.raises(DatasetHashMismatchError) as caught:
        verify_dataset(pack)
    assert caught.value.context["mismatched_files"] == ["markets/demo-brexit-2016.json"]
    broken = verify_dataset_report(pack)
    assert isinstance(broken, DatasetVerification) and not broken.ok
    assert broken.to_dict()["mismatched_files"] == ["markets/demo-brexit-2016.json"]


def test_verify_notices_a_file_that_was_added_or_removed(tmp_path: Path) -> None:
    pack = tmp_path / "demo_v1"
    shutil.copytree(DEMO_PACK, pack)
    (pack / "markets" / "demo-titan-sub-found-2023.json").unlink()
    report = verify_dataset_report(pack)
    assert report.missing_files == ("markets/demo-titan-sub-found-2023.json",)
    shutil.copytree(DEMO_PACK, pack / "again")
    fresh = tmp_path / "again"
    shutil.copytree(DEMO_PACK, fresh)
    write_canonical_json(fresh / "markets" / "demo-extra.json", {"a": 1})
    assert verify_dataset_report(fresh).extra_files == ("markets/demo-extra.json",)


def test_seal_refuses_a_reconstructed_market(tmp_path: Path) -> None:
    """Section 7.8: a plausible price path is a test vehicle, not evidence, so the pack cannot be sealed."""
    pack = tmp_path / "demo_v1"
    shutil.copytree(DEMO_PACK, pack)
    before = (pack / "manifest.json").read_bytes()
    with pytest.raises(SealError) as caught:
        seal_dataset(pack)
    assert caught.value.context["n"] == 12
    assert (pack / "manifest.json").read_bytes() == before  # the refusal changed nothing


def test_seal_stamps_an_imported_dataset_and_rehashes_it(tmp_path: Path) -> None:
    root = _synthetic_dataset(tmp_path / "y2026")
    assert load_manifest(root).sealed is False
    sealed = seal_dataset(root)
    assert sealed.sealed is True
    assert sealed.dataset_hash == dataset_hash_of(dataset_files(root))
    assert verify_dataset(root).ok
    assert load_manifest(root).sealed is True
    assert load_dataset(root, verify=True).manifest.sealed is True


def test_a_market_off_its_grid_or_with_a_gap_is_refused(tmp_path: Path) -> None:
    root = _synthetic_dataset(tmp_path / "gap")
    market_path = root / "markets" / "kalshi-KXTEST.json"
    payload = json.loads(market_path.read_text(encoding="utf-8"))
    dropped = dict(payload)
    dropped["bars"] = payload["bars"][:5] + payload["bars"][6:]
    write_canonical_json(market_path, dropped)
    with pytest.raises(SchemaError, match="dense"):
        load_market_file(market_path, manifest=load_manifest(root))
    off_grid = dict(payload)
    off_grid["bars"] = [dict(bar) for bar in payload["bars"]]
    for bar in off_grid["bars"]:
        bar["t_ms"] += 1
    off_grid["created_at_ms"] += 1
    write_canonical_json(market_path, off_grid)
    with pytest.raises(SchemaError):
        load_market_file(market_path, manifest=load_manifest(root))


def test_a_market_whose_tape_contradicts_itself_is_refused(tmp_path: Path) -> None:
    root = _synthetic_dataset(tmp_path / "bad")
    market_path = root / "markets" / "kalshi-KXTEST.json"
    original = json.loads(market_path.read_text(encoding="utf-8"))
    manifest = load_manifest(root)
    for mutate, match in (
        (lambda p: p.update(final_price_bp=p["bars"][-1]["close_bp"] + 1), "final_price_bp"),
        (lambda p: p["bars"][3].update(low_bp=p["bars"][3]["close_bp"] + 1), "range"),
        (lambda p: p["bars"][3].update(yes_bid_bp=9_000, yes_ask_bp=100), "ask"),
        (lambda p: p["bars"][3].update(volume_milli=0, n_trades=4), "zero-volume"),
        (lambda p: p.update(trades=[t.copy() for t in reversed(p["trades"])]), "canonical order"),
        (lambda p: p.update(interval_min=60), "grid"),
        (lambda p: p.update(tags=["z", "a"]), "sorted"),
        (lambda p: p.update(close_at_ms=p["created_at_ms"] - 1), "created_at_ms"),
        (lambda p: p.update(close_at_ms=p["resolved_at_ms"] + 1), "close_at_ms"),
    ):
        payload = json.loads(json.dumps(original))
        mutate(payload)
        write_canonical_json(market_path, payload)
        with pytest.raises(SchemaError, match=match):
            load_market_file(market_path, manifest=manifest)
    write_canonical_json(market_path, original)
    assert load_market_file(market_path, manifest=manifest).id == "kalshi-KXTEST"


def test_a_market_file_named_after_something_else_is_refused(tmp_path: Path) -> None:
    root = _synthetic_dataset(tmp_path / "misnamed")
    source = root / "markets" / "kalshi-KXTEST.json"
    target = root / "markets" / "kalshi-KXOTHER.json"
    target.write_bytes(source.read_bytes())
    source.unlink()
    with pytest.raises(SchemaError, match="file name"):
        load_market_file(target, manifest=load_manifest(root))


def test_a_market_that_resolves_after_the_freeze_is_a_leak(tmp_path: Path) -> None:
    root = _synthetic_dataset(tmp_path / "leaky")
    manifest = load_manifest(root)
    market_path = root / "markets" / "kalshi-KXTEST.json"
    payload = json.loads(market_path.read_text(encoding="utf-8"))
    days = (manifest.freeze_ms + MS_PER_DAY - payload["resolved_at_ms"]) // MS_PER_DAY + 1
    shift = days * MS_PER_DAY
    payload["created_at_ms"] += shift
    payload["close_at_ms"] += shift
    payload["resolved_at_ms"] += shift
    payload["bars"] = [{**bar, "t_ms": bar["t_ms"] + shift} for bar in payload["bars"]]
    payload["trades"] = [{**trade, "t_ms": trade["t_ms"] + shift} for trade in payload["trades"]]
    write_canonical_json(market_path, payload)
    with pytest.raises(LeakError, match="freeze"):
        load_market_file(market_path, manifest=manifest)


def test_the_demo_pack_exemption_is_only_for_the_demo_pack(tmp_path: Path) -> None:
    """Section 7.1: an unsealed demo-only pack skips the section 5.6 window, and nothing else does."""
    market = load_market_file(DEMO_PACK / "markets" / "demo-brexit-2016.json")
    demo_manifest = load_manifest(DEMO_PACK)
    assert demo_manifest.is_demo_pack
    loader_module.check_market_structure(market, manifest=demo_manifest)
    not_demo = _with(demo_manifest, providers=("demo", "kalshi"))
    assert not not_demo.is_demo_pack
    with pytest.raises(SchemaError):
        loader_module.check_market_structure(market, manifest=not_demo)
    once_sealed = _with(demo_manifest, sealed=True)
    assert not once_sealed.is_demo_pack
    with pytest.raises(SchemaError):
        loader_module.check_market_structure(market, manifest=once_sealed)


def test_a_manifest_that_contradicts_itself_is_refused(tmp_path: Path) -> None:
    root = _synthetic_dataset(tmp_path / "manifest")
    payload = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for mutate, match in (
        (lambda p: p.update(freeze_ms=p["freeze_ms"] + MS_PER_DAY), "freeze_ms"),
        (lambda p: p["window"].update(end_ms=p["window"]["start_ms"]), "window is empty"),
        (lambda p: p["filters"]["removed"].pop("density"), "density"),
        (lambda p: p["split"].update(month_edges_ms=[0] * 13), "month edges"),
    ):
        broken = json.loads(json.dumps(payload))
        mutate(broken)
        write_canonical_json(root / "manifest.json", broken)
        with pytest.raises(SchemaError, match=match):
            load_manifest(root)
    write_canonical_json(root / "manifest.json", payload)
    assert load_manifest(root).name == "y2026"


def test_a_dataset_whose_market_count_or_provider_disagrees_is_refused(tmp_path: Path) -> None:
    root = _synthetic_dataset(tmp_path / "counts")
    payload = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    payload["counts"]["markets"] = 2
    write_canonical_json(root / "manifest.json", payload)
    with pytest.raises(SchemaError, match="market count"):
        load_dataset(root)
    payload["counts"]["markets"] = 1
    payload["providers"] = ["manifold"]
    payload["counts"]["per_provider"] = {"manifold": 1}
    write_canonical_json(root / "manifest.json", payload)
    with pytest.raises(SchemaError, match="provider"):
        load_dataset(root)


def test_a_dataset_with_no_manifest_or_no_market_is_refused(tmp_path: Path) -> None:
    """A dataset with nothing to run on is refused, and the refusal names what is missing.

    A manifest that counts one market over an empty ``markets/`` directory is refused by the count
    check of 7.2, which is read before the walk and says which two numbers disagree; the bare "dataset
    holds no market" refusal stands behind it, for a manifest that counts none.
    """
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SchemaError, match="manifest"):
        load_dataset(empty)
    root = _synthetic_dataset(tmp_path / "nomarkets")
    (root / "markets" / "kalshi-KXTEST.json").unlink()
    with pytest.raises(SchemaError, match="market count is not the number of market files") as error:
        load_dataset(root)
    assert error.value.context["counted"] == 0
    assert error.value.context["manifest_count"] == 1


# --------------------------------------------------------------------------------------------------
# 5.5, 7.1 and 7.3 The news as-of rules
# --------------------------------------------------------------------------------------------------
def test_news_loads_with_the_safety_lag_and_is_filtered_by_visible_from(tmp_path: Path) -> None:
    root = _synthetic_dataset(tmp_path / "news", with_news=True)
    dataset = load_dataset(root)
    published = ms_from_iso_date("2026-06-02")
    visible = published + SAFETY_LAG_MS_DEFAULT
    assert dataset.news_global(visible - 1) == ()
    items = dataset.news_global(visible)
    assert [item.news_id for item in items] == ["wce-20260601-0001"]
    assert dataset.news_for("kalshi-KXTEST", visible)[0].news_id == "wce-20260601-0001"
    assert dataset.news_for("kalshi-KXOTHER", visible) == ()
    # The id names the page day D and the file names day_start_ms(published_at_ms), which is D + 1.
    assert (root / "news" / "20260602.jsonl").is_file()
    assert day_key(day_start_ms(items[0].published_at_ms)) == "20260602"


def test_a_news_item_whose_lag_or_day_file_is_wrong_is_refused(tmp_path: Path) -> None:
    root = _synthetic_dataset(tmp_path / "badnews", with_news=True)
    manifest = load_manifest(root)
    path = root / "news" / "20260602.jsonl"
    payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    wrong_lag = {**payload, "visible_from_ms": payload["visible_from_ms"] + 1}
    write_canonical_jsonl(path, [wrong_lag])
    with pytest.raises(SchemaError, match="safety lag"):
        loader_module.load_news_file(path, manifest=manifest)
    moved = root / "news" / "20260603.jsonl"
    write_canonical_jsonl(moved, [payload])
    with pytest.raises(SchemaError, match="wrong day file"):
        loader_module.load_news_file(moved, manifest=manifest)


def test_news_after_the_freeze_and_a_backdated_snapshot_are_leaks(tmp_path: Path) -> None:
    root = _synthetic_dataset(tmp_path / "leaknews", with_news=True)
    manifest = load_manifest(root)
    path = root / "news" / "20260602.jsonl"
    payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    after_freeze = manifest.freeze_ms + MS_PER_DAY
    future = {
        **payload,
        "published_at_ms": after_freeze,
        "visible_from_ms": after_freeze + manifest.safety_lag_ms,
    }
    write_canonical_jsonl(root / "news" / f"{day_key(after_freeze)}.jsonl", [future])
    with pytest.raises(LeakError, match="after the freeze"):
        loader_module.load_news_file(root / "news" / f"{day_key(after_freeze)}.jsonl", manifest=manifest)
    # The highest-value leak in the design: today's article stamped with an early day.
    published = ms_from_iso_date("2026-06-10")
    snapshot = _news_payload(
        news_id="wasof-20260401-0001",
        source="wikipedia_asof",
        kind="background",
        published_at_ms=published,
        safety_lag_ms=manifest.safety_lag_ms,
        revid=99,
        asof_day="2026-04-01",
    )
    target = root / "wiki_asof" / "kalshi-KXTEST" / "20260401.json"
    write_canonical_json(target, snapshot)
    with pytest.raises(LeakError, match="newer than the day it claims"):
        loader_module.load_background_file(target, manifest=manifest, market_id="kalshi-KXTEST")


def test_a_background_snapshot_loads_and_names_its_market(tmp_path: Path) -> None:
    root = _synthetic_dataset(tmp_path / "background", with_news=True)
    manifest = load_manifest(root)
    published = ms_from_iso_date("2026-04-01") + 12 * 3_600_000
    snapshot = _news_payload(
        news_id="wasof-20260401-0001",
        source="wikipedia_asof",
        kind="background",
        published_at_ms=published,
        safety_lag_ms=manifest.safety_lag_ms,
        revid=99,
        asof_day="2026-04-01",
        match_ids=["kalshi-KXTEST"],
    )
    write_canonical_json(root / "wiki_asof" / "kalshi-KXTEST" / "20260401.json", snapshot)
    dataset = load_dataset(root)
    assert dataset.background_for("kalshi-KXTEST", published + manifest.safety_lag_ms - 1) == ()
    got = dataset.background_for("kalshi-KXTEST", published + manifest.safety_lag_ms)
    assert [item.news_id for item in got] == ["wasof-20260401-0001"]
    assert got[0].revid == 99 and got[0].asof_day == "2026-04-01"
    with pytest.raises(SchemaError, match="names the market"):
        loader_module.load_background_file(
            root / "wiki_asof" / "kalshi-KXTEST" / "20260401.json",
            manifest=manifest,
            market_id="kalshi-KXOTHER",
        )


def test_only_a_background_snapshot_carries_a_revision(tmp_path: Path) -> None:
    root = _synthetic_dataset(tmp_path / "revid", with_news=True)
    manifest = load_manifest(root)
    path = root / "news" / "20260602.jsonl"
    payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    write_canonical_jsonl(path, [{**payload, "revid": 12}])
    with pytest.raises(SchemaError, match="revid"):
        loader_module.load_news_file(path, manifest=manifest)


def test_news_out_of_order_in_a_file_is_refused(tmp_path: Path) -> None:
    root = _synthetic_dataset(tmp_path / "order", with_news=True)
    manifest = load_manifest(root)
    day = ms_from_iso_date("2026-06-02")
    first = _news_payload(
        news_id="wce-20260601-0001",
        source="wikipedia_current_events",
        kind="headline",
        published_at_ms=day + 100,
        safety_lag_ms=manifest.safety_lag_ms,
    )
    second = _news_payload(
        news_id="wce-20260601-0002",
        source="wikipedia_current_events",
        kind="headline",
        published_at_ms=day + 50,
        safety_lag_ms=manifest.safety_lag_ms,
    )
    path = root / "news" / "20260602.jsonl"
    write_canonical_jsonl(path, [first, second])
    with pytest.raises(SchemaError, match="canonical order"):
        loader_module.load_news_file(path, manifest=manifest)


# --------------------------------------------------------------------------------------------------
# 13.1 The error taxonomy
# --------------------------------------------------------------------------------------------------
def test_every_error_renders_its_context_in_a_stable_order() -> None:
    error = SchemaError("bad thing", market_id="demo-a", at="bars/0")
    assert str(error) == "bad thing at='bars/0' market_id='demo-a'"
    assert error.context["market_id"] == "demo-a"
    assert isinstance(error, PmxError)
    assert str(SchemaError("plain")) == "plain"
    assert repr(SchemaError("plain", n=1)) == "SchemaError('plain', n=1)"


# --------------------------------------------------------------------------------------------------
# Helpers: the contract fixtures, the v1 source, and a synthetic imported dataset
# --------------------------------------------------------------------------------------------------
def _fixture(name: str) -> dict:  # type: ignore[type-arg]
    loaded = json.loads((CONTRACT_FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _v1_market(market_id: str) -> object:
    for market in bundled_v1_markets():
        if market.id == market_id:
            return market
    raise AssertionError(f"no v1 market {market_id}")


def _demo_markets() -> tuple[Market, ...]:
    dataset = load_dataset(DEMO_PACK)
    return tuple(dataset.market(meta.id) for meta in dataset.metas)


def _with(manifest: DatasetManifest, **overrides: object) -> DatasetManifest:
    fields = {name: getattr(manifest, name) for name in manifest.__slots__}
    fields.update(overrides)
    return DatasetManifest(**fields)  # type: ignore[arg-type]


def _news_payload(
    *,
    news_id: str,
    source: str,
    kind: str,
    published_at_ms: int,
    safety_lag_ms: int,
    revid: int | None = None,
    asof_day: str | None = None,
    match_ids: Sequence[str] = ("kalshi-KXTEST",),
) -> dict[str, object]:
    return {
        "schema_version": "news.v1",
        "news_id": news_id,
        "source": source,
        "kind": kind,
        "published_at_ms": published_at_ms,
        "revid": revid,
        "asof_day": asof_day,
        "visible_from_ms": published_at_ms + safety_lag_ms,
        "fetched_at_ms": published_at_ms + 3 * MS_PER_DAY,
        "url": "https://en.wikipedia.org/wiki/Portal:Current_events",
        "headline": "A dated thing happened",
        "text": "The body of the item.",
        "section": "politics",
        "wiki_links": ["Some Article"],
        "source_urls": [],
        "match_ids": list(match_ids),
        "match_scores_permille": [420] * len(match_ids),
        "lang": "en",
        "author_key": None,
    }


def _synthetic_market(*, freeze_ms: int) -> Market:
    """One ``imported`` market a real build could have produced, inside the window of section 5.6."""
    created_at_ms = day_start_ms(freeze_ms - 200 * MS_PER_DAY)
    n_bars = 60
    resolved_at_ms = created_at_ms + (n_bars - 1) * MS_PER_DAY + 12 * 3_600_000
    bars: list[Bar] = []
    price = 4_000
    for index in range(n_bars):
        price = clamp_price_bp(price + (37 * index) % 200 - 90)
        bars.append(
            Bar(
                t_ms=created_at_ms + index * MS_PER_DAY,
                open_bp=price,
                high_bp=clamp_price_bp(price + 50),
                low_bp=clamp_price_bp(price - 50),
                close_bp=price,
                vwap_bp=price,
                volume_milli=12_000,
                n_trades=3,
                yes_bid_bp=clamp_price_bp(price - 20),
                yes_ask_bp=clamp_price_bp(price + 20),
                open_interest=1_000,
            )
        )
    trades = tuple(
        Trade(t_ms=bar.t_ms + 3_600_000, price_bp=bar.close_bp, size_milli=4_000, side="yes") for bar in bars
    )
    return Market(
        schema_version="market.v2",
        id="kalshi-KXTEST",
        provider="kalshi",
        provider_id="KXTEST",
        url="https://kalshi.com/markets/kxtest",
        question="Will the synthetic thing happen?",
        description="Resolution criteria as published.",
        category="politics",
        tags=("election", "synthetic"),
        wiki_subjects=("A Synthetic Thing",),
        currency="usd",
        source="imported",
        created_at_ms=created_at_ms,
        close_at_ms=resolved_at_ms,
        resolved_at_ms=resolved_at_ms,
        resolution=1,
        resolution_source="venue",
        event_key="KXTEST-EVENT",
        interval_min=1_440,
        bars=tuple(bars),
        trades=trades,
        first_price_bp=bars[0].open_bp,
        final_price_bp=bars[-1].close_bp,
        hardness_tags=hardness_tags_of(tuple(bars), resolution=1, resolved_at_ms=resolved_at_ms),
        quality=MarketQuality(
            n_trades=len(trades),
            unique_bettors=80,
            life_days=(resolved_at_ms - created_at_ms) // MS_PER_DAY,
            volume_milli_total=sum(bar.volume_milli for bar in bars),
            traded_bars=len(bars),
        ),
        fee_schedule_id="kalshi-general-2026-09",
        notes="",
    )


def _synthetic_dataset(root: Path, *, with_news: bool = False, name: str = "y2026") -> Path:
    """Write an unsealed ``imported`` dataset with a recent freeze, and return its directory.

    The demo pack cannot exercise seal, the window rules or the news paths: it is exempt from section 5.6
    by construction and it carries no news. This is the smallest dataset that a real build could have
    produced, so the refusals under test are the refusals a real dataset would meet.
    """
    freeze_date = SYNTH_FREEZE_DATE
    freeze_ms = ms_from_iso_date(freeze_date)
    market = _synthetic_market(freeze_ms=freeze_ms)
    window = DatasetWindow(start_ms=freeze_ms - 365 * MS_PER_DAY, end_ms=freeze_ms - MS_PER_DAY)
    edges = month_edges_for(window.start_ms)
    if market.resolved_at_ms < edges[8]:
        fold = "train"
    elif market.resolved_at_ms < edges[10]:
        fold = "validation"
    else:
        fold = "sealed"
    news_items: list[dict[str, object]] = []
    if with_news:
        news_items.append(
            _news_payload(
                news_id="wce-20260601-0001",
                source="wikipedia_current_events",
                kind="headline",
                published_at_ms=ms_from_iso_date("2026-06-02"),
                safety_lag_ms=SAFETY_LAG_MS_DEFAULT,
            )
        )
    manifest = DatasetManifest(
        schema_version="dataset.v1",
        name=name,
        freeze_date=freeze_date,
        freeze_ms=freeze_ms,
        window=window,
        interval_min=1_440,
        providers=("kalshi",),
        safety_lag_ms=SAFETY_LAG_MS_DEFAULT,
        filters=DatasetFilters(
            config=BuildConfig(freeze_date=freeze_date, providers=("kalshi",)).to_dict(),
            removed=dict.fromkeys(REMOVED_FILTER_KEYS, 0),
        ),
        counts=DatasetCounts(
            markets=1,
            per_provider={"kalshi": 1},
            per_category={market.category: 1},
            resolution_yes=1,
            resolution_no=0,
            hardness_tags={tag: 1 for tag in market.hardness_tags},
        ),
        news=DatasetNews(
            sources=(),
            n_items=len(news_items),
            n_linked=len(news_items),
        ),
        split=DatasetSplit(
            month_edges_ms=edges,
            train_end_ms=edges[8],
            validation_end_ms=edges[10],
            n_train=1 if fold == "train" else 0,
            n_validation=1 if fold == "validation" else 0,
            n_sealed=1 if fold == "sealed" else 0,
        ),
        files=(),
        dataset_hash="0" * 64,
        built_by=BuiltBy(
            pmx_version=pmx.__version__,
            contract_version=pmx.CONTRACT_VERSION,
            rng_algorithm_version=RNG_ALGORITHM_VERSION,
        ),
        sealed=False,
        notes="Synthetic dataset for D1's loader tests.",
    )
    root.mkdir(parents=True, exist_ok=True)
    write_canonical_json(root / "markets" / f"{market.id}.json", market.to_dict())
    for item in news_items:
        published = item["published_at_ms"]
        assert isinstance(published, int)
        write_canonical_jsonl(root / "news" / f"{day_key(day_start_ms(published))}.jsonl", [item])
    write_manifest(root, loader_module.reseal_hash(root, manifest))
    return root


def test_the_synthetic_dataset_helper_builds_something_the_loader_accepts(tmp_path: Path) -> None:
    """The helper is load-bearing for a dozen refusal tests, so its happy path is a test of its own."""
    root = _synthetic_dataset(tmp_path / "happy", with_news=True)
    dataset = load_dataset(root, verify=True)
    assert [meta.id for meta in dataset.metas] == ["kalshi-KXTEST"]
    market = dataset.market("kalshi-KXTEST")
    assert market.source == "imported" and market.provider == "kalshi"
    assert len(market.bars) == 60 and market.trades[0].side == "yes"
    assert dataset.manifest.sealed is False
    assert verify_dataset(root).ok
    item = news_item_from_payload(_fixture("news.wce-20160623-0007.json"))
    assert isinstance(item, NewsItem)


# --------------------------------------------------------------------------------------------------
# 17.2 pmx.data.sessions: the one implementation of session membership (ruling R174)
#
# The module was landed by gate G2 with no test of its own. Every predicate below is the one the
# engine's calendar, the loader's density check and the borrow charge of 17.3 read, so a formula that
# drifts here moves a fill, a bar set and a cash event at once.
# --------------------------------------------------------------------------------------------------
XNYS_OPEN_MINUTE = 13 * 60 + 30
XNYS_CLOSE_MINUTE = 20 * 60
#: A Monday 00:00Z and the Friday of that week.
SESSION_MONDAY = ms_from_iso_date("2026-03-02")
SESSION_FRIDAY = SESSION_MONDAY + 4 * MS_PER_DAY
MS_PER_HOUR_LOCAL = 3_600_000


def _weekday_calendar(*, holidays: Sequence[str] = ()) -> SessionCalendar:
    """Two weeks of 13:30Z to 20:00Z weekday sessions, generated from the rule of an exchange."""
    return generate_calendar(
        calendar_id="xnys",
        description="A weekday venue, 13:30Z to 20:00Z, for D1's session tests.",
        source_url="https://www.nyse.com/markets/hours-calendars",
        as_of_date="2026-09-08",
        window_start_ms=SESSION_MONDAY,
        window_end_ms=SESSION_MONDAY + 14 * MS_PER_DAY,
        rules=(
            SessionRule(
                from_date="2026-03-02",
                to_date="2026-03-16",
                weekdays=(0, 1, 2, 3, 4),
                open_minute=XNYS_OPEN_MINUTE,
                close_minute=XNYS_CLOSE_MINUTE,
            ),
        ),
        holidays=holidays,
    )


def test_generate_calendar_emits_one_session_per_weekday_and_drops_a_holiday() -> None:
    """17.2: a dated rule plus its holidays, sorted, non-overlapping and inside its own window."""
    calendar = _weekday_calendar()
    assert calendar.calendar_id == "xnys" and calendar.is_continuous is False
    assert len(calendar.sessions) == 10, "ten weekdays in a fortnight"
    assert [session.open_ms - day_start_ms(session.open_ms) for session in calendar.sessions] == [
        XNYS_OPEN_MINUTE * 60_000
    ] * 10
    assert all(
        session.close_ms - session.open_ms == (XNYS_CLOSE_MINUTE - XNYS_OPEN_MINUTE) * 60_000
        for session in calendar.sessions
    )
    opens = [session.open_ms for session in calendar.sessions]
    assert opens == sorted(opens)
    assert day_start_ms(SESSION_MONDAY + 5 * MS_PER_DAY) not in [day_start_ms(value) for value in opens]
    with_holiday = _weekday_calendar(holidays=("2026-03-04",))
    assert len(with_holiday.sessions) == 9
    assert with_holiday.holidays == ("2026-03-04",)
    assert day_start_ms(SESSION_MONDAY + 2 * MS_PER_DAY) not in [
        day_start_ms(session.open_ms) for session in with_holiday.sessions
    ]


def test_generate_calendar_refuses_two_rules_that_overlap() -> None:
    """An overlapping schedule is a data error and is never merged silently (17.2)."""
    with pytest.raises(SchemaError, match="overlap"):
        generate_calendar(
            calendar_id="xnys",
            description="Two rules that cover the same afternoon.",
            source_url="https://example.invalid/rules",
            as_of_date="2026-09-08",
            window_start_ms=SESSION_MONDAY,
            window_end_ms=SESSION_MONDAY + 7 * MS_PER_DAY,
            rules=(
                SessionRule(
                    from_date="2026-03-02",
                    to_date="2026-03-09",
                    weekdays=(0,),
                    open_minute=XNYS_OPEN_MINUTE,
                    close_minute=XNYS_CLOSE_MINUTE,
                ),
                SessionRule(
                    from_date="2026-03-02",
                    to_date="2026-03-09",
                    weekdays=(0,),
                    open_minute=XNYS_OPEN_MINUTE + 60,
                    close_minute=XNYS_CLOSE_MINUTE + 60,
                ),
            ),
        )


def test_in_session_is_the_intersection_of_the_bar_and_the_session_never_the_containment() -> None:
    """17.2: ``t < close_ms and t + interval_ms > open_ms``, which a daily bar satisfies."""
    open_ms = SESSION_MONDAY + 13 * MS_PER_HOUR_LOCAL
    close_ms = SESSION_MONDAY + 20 * MS_PER_HOUR_LOCAL
    sessions = (Session(open_ms=open_ms, close_ms=close_ms),)
    assert in_session(sessions, SESSION_MONDAY, interval_min=1_440) is True
    assert in_session(sessions, SESSION_MONDAY + MS_PER_DAY, interval_min=1_440) is False
    assert in_session(sessions, SESSION_MONDAY + 12 * MS_PER_HOUR_LOCAL, interval_min=60) is False
    assert in_session(sessions, SESSION_MONDAY + 13 * MS_PER_HOUR_LOCAL, interval_min=60) is True
    assert in_session(sessions, SESSION_MONDAY + 19 * MS_PER_HOUR_LOCAL, interval_min=60) is True
    assert in_session(sessions, close_ms, interval_min=60) is False, "the close is exclusive"
    assert session_index(sessions, SESSION_MONDAY, interval_min=1_440) == 0
    assert session_index((), SESSION_MONDAY, interval_min=1_440) is None
    assert in_session(continuous_calendar(), 0, interval_min=60) is True, "ruling R185"


def test_the_next_bar_after_friday_is_monday_and_the_previous_one_is_friday() -> None:
    """17.2 and ruling R187: the latency rule of 16.2 waits for the venue's next bar, not the grid's."""
    calendar = _weekday_calendar()
    assert next_bar_ms(calendar, SESSION_MONDAY, interval_min=1_440) == SESSION_MONDAY + MS_PER_DAY
    assert next_bar_ms(calendar, SESSION_FRIDAY, interval_min=1_440) == SESSION_MONDAY + 7 * MS_PER_DAY
    assert prev_bar_ms(calendar, SESSION_MONDAY + 7 * MS_PER_DAY, interval_min=1_440) == SESSION_FRIDAY
    assert prev_bar_ms(calendar, SESSION_MONDAY, interval_min=1_440) is None
    last_bar = SESSION_MONDAY + 11 * MS_PER_DAY
    assert next_bar_ms(calendar, last_bar, interval_min=1_440) is None, "the calendar has no session left"
    assert next_bar_ms((), SESSION_MONDAY, interval_min=1_440) is None
    assert prev_bar_ms((), SESSION_MONDAY, interval_min=1_440) is None


def test_session_bars_is_the_grid_inside_the_sessions_and_refuses_an_off_grid_start() -> None:
    """Ruling R149: the bars of a session instrument are the grid points its calendar covers."""
    calendar = _weekday_calendar()
    bars = session_bars(
        calendar, start_ms=SESSION_MONDAY, end_ms=SESSION_MONDAY + 14 * MS_PER_DAY, interval_min=1_440
    )
    assert len(bars) == 10
    assert bars[0] == SESSION_MONDAY and bars[4] == SESSION_FRIDAY
    assert bars[5] == SESSION_MONDAY + 7 * MS_PER_DAY, "no weekend bar"
    assert bars == tuple(sorted(set(bars)))
    hourly = session_bars(
        calendar, start_ms=SESSION_MONDAY, end_ms=SESSION_MONDAY + MS_PER_DAY, interval_min=60
    )
    assert hourly == tuple(SESSION_MONDAY + hour * MS_PER_HOUR_LOCAL for hour in range(13, 20))
    with pytest.raises(SchemaError, match="not on the grid"):
        session_bars(
            calendar, start_ms=SESSION_MONDAY + 1, end_ms=SESSION_MONDAY + MS_PER_DAY, interval_min=1_440
        )


def test_a_session_close_is_charged_once_and_a_weekend_is_charged_on_monday() -> None:
    """17.3: ``borrow_fee`` and ``carry`` are per session, with the days since the previous close."""
    calendar = _weekday_calendar()
    assert is_session_close(calendar, SESSION_MONDAY, interval_min=1_440) is True
    assert is_session_close(calendar, SESSION_MONDAY + 5 * MS_PER_DAY, interval_min=1_440) is False
    assert days_since_previous_close(calendar, SESSION_MONDAY, interval_min=1_440) == 1, "the first session"
    assert days_since_previous_close(calendar, SESSION_MONDAY + MS_PER_DAY, interval_min=1_440) == 1
    assert days_since_previous_close(calendar, SESSION_MONDAY + 7 * MS_PER_DAY, interval_min=1_440) == 3
    assert days_since_previous_close(calendar, SESSION_MONDAY + 5 * MS_PER_DAY, interval_min=1_440) is None
    assert is_session_close(calendar, SESSION_MONDAY + 19 * MS_PER_HOUR_LOCAL, interval_min=60) is True
    assert is_session_close(calendar, SESSION_MONDAY + 18 * MS_PER_HOUR_LOCAL, interval_min=60) is False
    assert is_session_close(continuous_calendar(), SESSION_MONDAY, interval_min=1_440) is False


def test_a_calendar_read_from_a_file_is_checked_and_continuous_is_never_one() -> None:
    """Ruling R185: the one calendar that is synthesised cannot arrive through the file door."""
    calendar = calendar_from_payload(_fixture("session_calendar.xnys.json"))
    assert calendar.calendar_id == "xnys"
    assert calendar.sessions == tuple(sorted(calendar.sessions, key=lambda session: session.open_ms))
    assert calendar.window.start_ms <= calendar.sessions[0].open_ms
    assert calendar.sessions[-1].close_ms <= calendar.window.end_ms
    payload = _fixture("session_calendar.xnys.json")
    payload["calendar_id"] = "continuous"
    # The schema refuses the id before the model is built, which is the outer of the two doors; the
    # loader refuses the file name too (see the continuous walk below), so neither spelling gets in.
    with pytest.raises(SchemaError, match="continuous"):
        calendar_from_payload(payload)
    with pytest.raises(SchemaError, match="outside the calendar window"):
        check_calendar(
            SessionCalendar(
                calendar_id="xnys",
                description="A session that starts before its own window.",
                source_url="https://example.invalid",
                as_of_date="2026-09-08",
                window=DatasetWindow(start_ms=SESSION_MONDAY + 2, end_ms=SESSION_MONDAY + MS_PER_DAY),
                sessions=(Session(open_ms=SESSION_MONDAY + 1, close_ms=SESSION_MONDAY + 3),),
            )
        )


# --------------------------------------------------------------------------------------------------
# 17.2 The loader's continuous walk: instruments/, calendars/, the clip and the _ticks mapping
#
# Gate G2 landed the walk with no test over it: nothing built a dataset carrying an ``instruments/``
# or a ``calendars/`` directory. The helper below is the smallest such dataset, built from the
# contract's own instrument and calendar fixtures so that the file shapes under test are the shipped
# ones, with a window that a real build could have produced.
# --------------------------------------------------------------------------------------------------
#: The contract fixture's own window: three XNYS session days from 2026-02-28, freeze after them.
WALK_FREEZE_DATE = "2026-09-07"


def _instrument_dataset(root: Path, *, with_calendar: bool = True) -> Path:
    """A dataset of one equity instrument and one sealed calendar, and nothing else.

    ``counts.markets`` is zero and ``instruments.per_kind`` is one, which is what a dataset of a single
    continuous instrument is: 17.2 walks ``markets/`` and ``instruments/`` separately and cross-checks
    each against its own count.
    """
    instrument = instrument_from_payload(_fixture("instrument.xnas-aapl.json"))
    calendar = calendar_from_payload(_fixture("session_calendar.xnys.json"))
    freeze_ms = ms_from_iso_date(WALK_FREEZE_DATE)
    window = DatasetWindow(
        start_ms=calendar.window.start_ms, end_ms=instrument.bars[-1].t_ms + MS_PER_DAY
    )
    edges = month_edges_for(window.start_ms)
    manifest = DatasetManifest(
        schema_version="dataset.v1",
        name="instruments_v1",
        freeze_date=WALK_FREEZE_DATE,
        freeze_ms=freeze_ms,
        window=window,
        interval_min=1_440,
        providers=("xnas",),
        safety_lag_ms=SAFETY_LAG_MS_DEFAULT,
        filters=DatasetFilters(
            config=BuildConfig(
                freeze_date=WALK_FREEZE_DATE, providers=("xnas",), kinds=("equity",)
            ).to_dict(),
            removed=dict.fromkeys(REMOVED_FILTER_KEYS, 0),
        ),
        counts=DatasetCounts(
            markets=0,
            per_provider={},
            per_category={},
            resolution_yes=0,
            resolution_no=0,
            hardness_tags={},
        ),
        news=DatasetNews(sources=(), n_items=0, n_linked=0),
        split=DatasetSplit(
            month_edges_ms=edges,
            train_end_ms=edges[8],
            validation_end_ms=edges[10],
            n_train=0,
            n_validation=0,
            n_sealed=0,
            n_instruments_train=0,
            n_instruments_validation=0,
            n_instruments_sealed=0,
        ),
        files=(),
        dataset_hash="0" * 64,
        built_by=BuiltBy(
            pmx_version=pmx.__version__,
            contract_version=pmx.CONTRACT_VERSION,
            rng_algorithm_version=RNG_ALGORITHM_VERSION,
        ),
        sealed=False,
        notes="One continuous instrument, for D1's walk tests.",
        kinds=("equity",),
        instruments={
            "per_kind": {"equity": 1},
            "per_provider": {"xnas": 1},
            "per_vendor": {"yahoo": 1},
            "n_cash_events": {"per_kind": {"equity": len(instrument.cash_events)}},
            "n_calendars": 1 if with_calendar else 0,
        },
        schedules={
            "fee": (instrument.fee_schedule_id,),
            "borrow": (instrument.borrow_schedule_id,) if instrument.borrow_schedule_id else (),
            "carry": (),
        },
    )
    root.mkdir(parents=True, exist_ok=True)
    write_canonical_json(root / "instruments" / f"{instrument.id}.json", instrument.to_dict())
    if with_calendar:
        write_canonical_json(root / "calendars" / f"{calendar.calendar_id}.json", calendar.to_dict())
    write_manifest(root, loader_module.reseal_hash(root, manifest))
    return root


def test_the_loader_walks_an_instruments_directory_and_seals_it_with_its_calendars(tmp_path: Path) -> None:
    """Rulings R149 and R186: one meta per instrument, ``kind`` on it, fold ``all``, hashed files."""
    root = _instrument_dataset(tmp_path / "walk")
    dataset = load_dataset(root, verify=True)
    assert [meta.id for meta in dataset.metas] == ["xnas-AAPL"]
    meta = dataset.metas[0]
    assert meta.kind == "equity" and meta.fold == "all"
    assert meta.resolution == -1 and meta.event_key is None and meta.hardness_tags == ()
    assert meta.created_at_ms == ms_from_iso_date("2026-03-02"), "listed_at_ms under the binary name"
    assert meta.close_at_ms == meta.resolved_at_ms == dataset.manifest.window.end_ms
    assert meta.n_bars == 3
    paths = sorted(entry.path for entry in dataset.manifest.files)
    assert paths == ["calendars/xnys.json", "instruments/xnas-AAPL.json"]
    assert verify_dataset(root).ok
    assert dataset.calendar_ids() == ("continuous", "xnys")
    assert dataset.calendar("xnys").calendar_id == "xnys"
    assert dataset.calendar("continuous").is_continuous, "ruling R185: synthesised, never a file"


def test_the_ticks_fields_of_an_instrument_file_map_onto_one_bar_and_one_trade() -> None:
    """Ruling R173: ``_bp`` carries ticks, so ``open_ticks`` is ``open_bp`` and there is one Bar."""
    payload = _fixture("instrument.xnas-aapl.json")
    first = payload["bars"][0]
    first["bid_ticks"] = 18_860_000
    first["ask_ticks"] = 18_864_000
    first["open_interest_milli"] = 5_000
    payload["trades"] = [
        {"t_ms": first["t_ms"] + 1, "price_ticks": 18_900_000, "size_milli": 2_000, "side": "buy"}
    ]
    instrument = instrument_from_payload(payload)
    bar = instrument.bars[0]
    assert bar.open_bp == first["open_ticks"]
    assert bar.high_bp == first["high_ticks"] and bar.low_bp == first["low_ticks"]
    assert bar.close_bp == first["close_ticks"] and bar.vwap_bp == first["vwap_ticks"]
    assert bar.yes_bid_bp == 18_860_000 and bar.yes_ask_bp == 18_864_000
    assert bar.open_interest == 5_000
    trade = instrument.trades[0]
    assert trade.price_bp == 18_900_000 and trade.size_milli == 2_000 and trade.side == "buy"
    assert instrument.first_price_bp == instrument.first_price_ticks
    assert instrument.created_at_ms == instrument.listed_at_ms
    assert instrument.bar_at(bar.t_ms) is bar
    assert instrument.bars_before(bar.t_ms, 1) == ()
    assert instrument.bars_before(bar.t_ms + MS_PER_DAY, 1) == (bar,)
    assert instrument.instrument is instrument, "the base view of an instrument is the instrument"


def test_an_instrument_naming_a_calendar_the_dataset_does_not_carry_is_refused(tmp_path: Path) -> None:
    """Ruling R185: only ``continuous`` is synthesised; every other calendar is a file of the dataset."""
    root = _instrument_dataset(tmp_path / "nocal", with_calendar=False)
    with pytest.raises(SchemaError, match="session calendar the dataset does not carry"):
        load_dataset(root)


def test_a_calendars_directory_never_carries_the_continuous_calendar(tmp_path: Path) -> None:
    """Ruling R185, at the file door this time: ``calendars/continuous.json`` is refused by name."""
    root = _instrument_dataset(tmp_path / "cont")
    calendar = calendar_from_payload(_fixture("session_calendar.xnys.json"))
    payload = calendar.to_dict()
    payload["calendar_id"] = "xnys"
    write_canonical_json(root / "calendars" / "continuous.json", payload)
    with pytest.raises(SchemaError, match="synthesised, never a file"):
        loader_module.load_calendars(root, manifest=load_manifest(root))


def test_a_bar_outside_every_session_of_its_calendar_is_refused(tmp_path: Path) -> None:
    """Ruling R149: bars are dense **on the calendar**, so a weekend bar is a structural error."""
    calendar = calendar_from_payload(_fixture("session_calendar.xnys.json"))
    payload = _fixture("instrument.xnas-aapl.json")
    weekend = next(
        day_start_ms(payload["bars"][-1]["t_ms"]) + days * MS_PER_DAY
        for days in range(1, 8)
        if not in_session(calendar, day_start_ms(payload["bars"][-1]["t_ms"]) + days * MS_PER_DAY,
                          interval_min=1_440)
    )
    extra = dict(payload["bars"][-1])
    extra["t_ms"] = weekend
    payload["bars"] = [*payload["bars"], extra]
    instrument = instrument_from_payload(payload)
    with pytest.raises(SchemaError, match="dense on the instrument"):
        loader_module.check_instrument_structure(instrument, manifest=None, calendar=calendar)


def test_dataset_market_clips_a_continuous_instrument_and_sealed_market_does_not(tmp_path: Path) -> None:
    """Ruling R182: the clip is at ``split.validation_end_ms`` and only the claim path sees past it."""
    root = _instrument_dataset(tmp_path / "clip")
    dataset = load_dataset(root)
    whole = dataset.sealed_market("xnas-AAPL")
    assert isinstance(whole, ContinuousInstrument)
    assert len(whole.bars) == 3
    cut = whole.bars[1].t_ms
    clipped = whole.clipped(cut)
    assert [bar.t_ms for bar in clipped.bars] == [whole.bars[0].t_ms]
    assert all(event.t_ms < cut for event in clipped.cash_events)
    assert clipped.quality == whole.quality, "quality stays the whole-window statistic"
    narrow = replace(
        dataset,
        manifest=replace(dataset.manifest, split=replace(dataset.manifest.split, validation_end_ms=cut)),
        market_loader=dataset.market_loader,
    )
    served = narrow.market("xnas-AAPL")
    assert isinstance(served, ContinuousInstrument)
    assert [bar.t_ms for bar in served.bars] == [whole.bars[0].t_ms]
    assert len(narrow.sealed_market("xnas-AAPL").bars) == 3, "the claim path holds the whole path"


# --------------------------------------------------------------------------------------------------
# The pmx.types names of amendment C1b that no other test reads
# --------------------------------------------------------------------------------------------------
def test_the_binary_scale_constants_are_the_numbers_ruling_R145_fixed() -> None:
    """R145 against the PRD's ``10_000``: a binary tick is ``100`` micro-units of a one-unit payout."""
    assert BINARY_TICK_SIZE_MICRO == 100
    assert BINARY_POINT_VALUE_MICRO == 1_000_000
    assert INSTRUMENT_KINDS[0] == "binary"
    # The identity that makes the one price model of 17.1 answer for a binary too (R145).
    for size, price_bp in ((1, 1), (3, 6_327), (100, 9_999)):
        assert cost_cents(size, price_bp) == cash_out_cents(
            size * 1_000, price_bp, BINARY_TICK_SIZE_MICRO, BINARY_POINT_VALUE_MICRO
        )
    assert price_micro(6_327, BINARY_TICK_SIZE_MICRO) == 632_700
    assert price_micro(1, BINARY_TICK_SIZE_MICRO) == 100


def test_default_horizons_bars_is_one_bar_one_day_and_one_week() -> None:
    """17.5 and ruling R188: ``(1, 7)`` on a daily grid, ``(1, 24, 168)`` on an hourly one."""
    assert default_horizons_bars(1_440) == (1, 7)
    assert default_horizons_bars(60) == (1, 24, 168)
    # A config that spells the default and one that omits it are one run (ruling R188).
    omitted = RunConfig(seed=1, interval_min=1_440)
    spelled = RunConfig(seed=1, interval_min=1_440, horizons_bars=(1, 7))
    assert omitted.horizons_bars == spelled.horizons_bars == (1, 7)
    assert omitted.to_dict() == spelled.to_dict()
    assert canonical_json(omitted.to_dict()) == canonical_json(spelled.to_dict())
    hourly = RunConfig(seed=1, interval_min=60)
    assert hourly.horizons_bars == (1, 24, 168)


def test_a_portfolio_view_carries_a_debit_balance_and_a_negative_equity() -> None:
    """Rulings R179 and R180: both are journal states of a short, not values to clamp at zero."""
    view = PortfolioView(
        cash_cents=-2_500,
        reserved_cents=0,
        equity_cents=-1_250,
        fees_paid_cents=10,
        peak_equity_cents=100_000,
        drawdown_bp=-10_125,
        n_open_positions=1,
        n_open_orders=0,
        research_units_remaining=0,
    )
    assert view.cash_cents == -2_500 and view.equity_cents == -1_250
    assert view.drawdown_bp <= 0, "a drawdown has no floor and is never positive (R180)"
    assert view.to_dict()["cash_cents"] == -2_500
    assert view.to_dict()["equity_cents"] == -1_250
