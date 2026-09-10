"""Package S1: the sensor catalogue of CONTRACTS_V2 section 18.1.

What these tests hold down, in the order 18.1 states it:

* the catalogue reproduces ``tests/fixtures/contract/sensor.catalogue.json`` **byte for byte**. That
  fixture is amendment C1c's, not S1's, so if this test fails the answer is a contract issue and never an
  edit to the fixture (ruling R286);
* ``granularity_ms`` and ``lag_ms`` are the derived maxima of 18.3's two per-source tables (ruling R287),
  which is why ``macro_releases`` reads a day and six hours and not a second and nothing;
* every one of the seventy-five sentinels obeys ruling R285's one rule, asserted against the fixture and
  not against the code that builds it;
* the catalogue hash is stable across two constructions and moves when any row moves;
* ``market_id`` is ``None`` exactly for ``hive_reputation`` (ruling R286);
* a market younger than the window a feature measures reads that feature's sentinel and never a floor;
* an unknown sensor name is refused with ``InvalidConfigError``;
* the budget arithmetic of ruling R281 is integer: the full diet costs ``17`` and the default allowance
  is ``18``, so a full-diet genome can still afford one ``propose_rule``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from pmx.engine.observation import resolve_sensor_set
from pmx.errors import InvalidConfigError
from pmx.journal import canonical_json
from pmx.sensors import (
    calendar,
    comments,
    cross_asset,
    filings,
    gdelt_recent,
    hive_insights,
    hive_reputation,
    hn,
    macro_releases,
    memory,
    microstructure,
    tape,
    volume_profile,
    wiki_asof,
    wiki_daily,
)
from pmx.sensors.catalogue import (
    _CATALOGUE_TABLE,
    CATALOGUE_HASH,
    FULL_DIET_COST_UNITS,
    RE_SENSOR,
    SENSOR_BY_NEWS_SOURCE,
    SENSOR_NAMES,
    SENSORS,
    SensorBlock,
    _spec_of,
    block_of,
    derived_granularity_ms,
    derived_lag_ms,
    ln1p_milli,
    sentinel_for,
)
from pmx.types import (
    MS_PER_DAY,
    MS_PER_HOUR,
    MS_PER_MINUTE,
    MS_PER_SECOND,
    SAFETY_LAG_MS_DEFAULT,
    Bar,
    CalibrationBinView,
    CashEventView,
    ForecastView,
    HiveLessonView,
    HiveView,
    MarketMeta,
    MarketView,
    MemoryView,
    NewsView,
    NoteView,
    Observation,
    ReputationView,
    Trade,
    sha256_hex,
)

CONTRACT_FIXTURE = Path(__file__).parent / "fixtures" / "contract" / "sensor.catalogue.json"
S1_FIXTURES = Path(__file__).parent / "fixtures" / "s1"

#: The fifteen rows of 18.1's table, spelled here from the contract and not read from the code:
#: (name, cost_units, granularity_ms, lag_ms, sources, per_market).
CONTRACT_ROWS: tuple[tuple[str, int, int, int, tuple[str, ...], bool], ...] = (
    ("calendar", 0, 0, 0, (), True),
    ("comments", 1, 1, 60_000, ("manifold_comment",), True),
    ("cross_asset", 1, 0, 0, (), True),
    ("filings", 2, 1_000, 60_000, ("edgar",), True),
    ("gdelt_recent", 2, 900_000, 900_000, ("gdelt",), True),
    ("hive_insights", 1, 0, 0, (), True),
    ("hive_reputation", 1, 0, 0, (), False),
    ("hn", 2, 1_000, 300_000, ("hn",), True),
    ("macro_releases", 1, 86_400_000, 21_600_000, ("cboe", "fred"), True),
    ("memory", 0, 0, 0, (), True),
    ("microstructure", 1, 0, 0, (), True),
    ("tape", 0, 0, 0, (), True),
    ("volume_profile", 1, 0, 0, (), True),
    ("wiki_asof", 3, 86_400_000, 21_600_000, ("wikipedia_asof",), True),
    ("wiki_daily", 1, 86_400_000, 21_600_000, ("wayback", "wikipedia_current_events"), True),
)

#: 18.3's two tables, verbatim. They are contracted to ``pmx.types`` and the catalogue mirrors them until
#: DS1 or A1 lands them there (18.8's first row); this is what pins the mirror to the contract.
CONTRACT_SOURCE_GRANULARITY_MS = {
    "wikipedia_current_events": MS_PER_DAY,
    "wikipedia_asof": MS_PER_DAY,
    "wayback": MS_PER_DAY,
    "cboe": MS_PER_DAY,
    "gdelt": 15 * MS_PER_MINUTE,
    "manifold_comment": 1,
    "hn": 1_000,
    "edgar": 1_000,
    "fred": 1_000,
}
CONTRACT_SAFETY_LAG_MS_BY_SOURCE = {
    "wikipedia_current_events": SAFETY_LAG_MS_DEFAULT,
    "wikipedia_asof": SAFETY_LAG_MS_DEFAULT,
    "wayback": SAFETY_LAG_MS_DEFAULT,
    "cboe": SAFETY_LAG_MS_DEFAULT,
    "gdelt": 15 * MS_PER_MINUTE,
    "manifold_comment": MS_PER_MINUTE,
    "hn": 5 * MS_PER_MINUTE,
    "edgar": MS_PER_MINUTE,
    "fred": 0,
}

#: The fifteen ``sense`` bodies, by sensor name.
SENSE_BY_NAME = {
    "calendar": calendar.sense,
    "comments": comments.sense,
    "cross_asset": cross_asset.sense,
    "filings": filings.sense,
    "gdelt_recent": gdelt_recent.sense,
    "hive_insights": hive_insights.sense,
    "hive_reputation": hive_reputation.sense,
    "hn": hn.sense,
    "macro_releases": macro_releases.sense,
    "memory": memory.sense,
    "microstructure": microstructure.sense,
    "tape": tape.sense,
    "volume_profile": volume_profile.sense,
    "wiki_asof": wiki_asof.sense,
    "wiki_daily": wiki_daily.sense,
}

#: The budget arithmetic of ruling R281, spelled from the contract. ``SENSOR_BUDGET_UNITS_DEFAULT`` and
#: ``RULE_PROPOSAL_COST_UNITS`` are ``pmx.types`` names A1 and O2 land in lot 6 (18.8's last-but-five row).
RULE_PROPOSAL_COST_UNITS = 1
SENSOR_BUDGET_UNITS_DEFAULT = 18
SENSOR_COST_MAX = 10

INTERVAL_MIN = 60
BAR_MS = INTERVAL_MIN * MS_PER_MINUTE
NOW_MS = 1_699_999_200_000
MARKET_ID = "kalshi-s1-demo"


# --------------------------------------------------------------------------------------------------
# The reference input: one frozen object satisfying 12.11's ``SensorInputs``, field for field
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Inputs:
    """A stand-in for 12.11's ``SensorInputs`` while it is still D1's declared-not-applied shape.

    The fields, their names, their types and their order are 12.11's verbatim, so this object satisfies
    ``pmx.sensors.catalogue.SensorInputsLike`` structurally and will satisfy ``pmx.types.SensorInputs``
    the day it lands.
    """

    meta: MarketMeta
    bars: tuple[Bar, ...] = ()
    quotes: tuple[int, int] | None = None
    trades: tuple[Trade, ...] = ()
    news: Mapping[str, tuple[NewsView, ...]] = field(default_factory=dict)
    cash_events: tuple[CashEventView, ...] = ()
    hive: HiveView | None = None
    memory: MemoryView | None = None
    peers: Mapping[str, tuple[Bar, ...]] = field(default_factory=dict)
    research: Mapping[str, object] = field(default_factory=dict)


def make_meta(*, created_bars_back: int = 100, close_bars_ahead: int = 50) -> MarketMeta:
    return MarketMeta(
        id=MARKET_ID,
        provider="kalshi",
        category="politics",
        tags=("election",),
        event_key="s1-event",
        created_at_ms=NOW_MS - created_bars_back * BAR_MS,
        close_at_ms=NOW_MS + close_bars_ahead * BAR_MS,
        resolved_at_ms=NOW_MS + close_bars_ahead * BAR_MS,
        resolution=-1,
        interval_min=INTERVAL_MIN,
        n_bars=created_bars_back,
        hardness_tags=(),
        fee_schedule_id="demo-zero",
        fold="train",
    )


def make_bars(count: int, *, first_close_bp: int = 4_000, step_bp: int = 25) -> tuple[Bar, ...]:
    """``count`` completed bars ending at ``NOW_MS - BAR_MS``, a clean ramp so every window is measurable."""
    bars: list[Bar] = []
    for index in range(count):
        t_ms = NOW_MS - (count - index) * BAR_MS
        close_bp = first_close_bp + index * step_bp
        bars.append(
            Bar(
                t_ms=t_ms,
                open_bp=close_bp - step_bp,
                high_bp=close_bp + 10,
                low_bp=close_bp - 30,
                close_bp=close_bp,
                vwap_bp=close_bp,
                volume_milli=1_000 + 10 * index,
                n_trades=2 + index % 3,
                yes_bid_bp=close_bp - 20,
                yes_ask_bp=close_bp + 20,
                open_interest=5_000 + index,
            )
        )
    return tuple(bars)


def make_news(source: str, *, count: int, spacing_ms: int, kind: str, text: str, url: str) -> tuple[NewsView, ...]:
    return tuple(
        NewsView(
            news_id=f"{source[:4]}-2023{index:04d}",
            source=source,
            kind=kind,
            published_at_ms=NOW_MS - (index + 1) * spacing_ms,
            headline=f"{source} headline {index}: the vote approves the measure",
            text=text,
            section="8-K" if source == "edgar" else None,
            url=url.format(index=index),
            match_score_permille=900 - 50 * index,
        )
        for index in range(count)
    )


def reference_inputs() -> Inputs:
    """The full input every sensor is exercised against: every source populated, every view present."""
    bars = make_bars(40)
    return Inputs(
        meta=make_meta(),
        bars=bars,
        quotes=(bars[-1].close_bp - 15, bars[-1].close_bp + 25),
        trades=tuple(
            Trade(t_ms=NOW_MS - (index + 1) * (BAR_MS // 2), price_bp=4_900, size_milli=1_000, side="yes")
            for index in range(12)
        ),
        news={
            "wikipedia_current_events": make_news(
                "wikipedia_current_events",
                count=4,
                spacing_ms=MS_PER_DAY // 2,
                kind="headline",
                text="The council approves the plan and wins the vote.",
                url="https://en.wikipedia.org/wiki/Portal:Current_events#{index}",
            ),
            "wayback": make_news(
                "wayback",
                count=2,
                spacing_ms=6 * MS_PER_DAY,
                kind="frontpage",
                text="An earlier capture rejects and denies the same plan.",
                url="https://web.archive.org/web/{index}",
            ),
            "manifold_comment": make_news(
                "manifold_comment",
                count=3,
                spacing_ms=BAR_MS // 2,
                kind="comment",
                text="A comment on the market.",
                url="https://manifold.markets/x#{index}",
            ),
            "hn": (
                NewsView(
                    news_id="hn-20230101-0001",
                    source="hn",
                    kind="story",
                    published_at_ms=NOW_MS - 3 * MS_PER_HOUR,
                    headline="A story about the vote",
                    text="points=412 comments=87\nthe body of the story",
                    section=None,
                    url="https://news.ycombinator.com/item?id=1",
                    match_score_permille=800,
                ),
                NewsView(
                    news_id="hn-20230101-0002",
                    source="hn",
                    kind="story",
                    published_at_ms=NOW_MS - 20 * MS_PER_HOUR,
                    headline="An older story",
                    text="points=95 comments=12\nthe body of the older story",
                    section=None,
                    url="https://news.ycombinator.com/item?id=2",
                    match_score_permille=100,
                ),
            ),
            "gdelt": (
                NewsView(
                    news_id="gd-20230101-0001",
                    source="gdelt",
                    kind="article",
                    published_at_ms=NOW_MS - 15 * MS_PER_MINUTE,
                    headline="An article",
                    text="the body",
                    section=None,
                    url="https://www.reuters.com/world/a",
                    match_score_permille=700,
                ),
                NewsView(
                    news_id="gd-20230101-0002",
                    source="gdelt",
                    kind="article",
                    published_at_ms=NOW_MS - 5 * MS_PER_HOUR,
                    headline="Another article",
                    text="the body",
                    section=None,
                    url="https://apnews.com/article/b",
                    match_score_permille=600,
                ),
                NewsView(
                    news_id="gd-20230101-0003",
                    source="gdelt",
                    kind="article",
                    published_at_ms=NOW_MS - 6 * MS_PER_HOUR,
                    headline="A third article",
                    text="the body",
                    section=None,
                    url="https://www.reuters.com/world/c",
                    match_score_permille=500,
                ),
            ),
            "edgar": make_news(
                "edgar",
                count=2,
                spacing_ms=4 * BAR_MS,
                kind="filing",
                text="the filing body",
                url="https://www.sec.gov/Archives/{index}",
            ),
            "fred": (
                NewsView(
                    news_id="fred-20230101-0001",
                    source="fred",
                    kind="release",
                    published_at_ms=NOW_MS - 9 * BAR_MS,
                    headline="CPIAUCSL release",
                    text="value=307.026",
                    section=None,
                    url="https://alfred.stlouisfed.org/series?seid=CPIAUCSL",
                    match_score_permille=400,
                ),
            ),
            "cboe": (
                NewsView(
                    news_id="cboe-20230101-0001",
                    source="cboe",
                    kind="release",
                    published_at_ms=NOW_MS - 30 * BAR_MS,
                    headline="VIX close",
                    text="value=14.35",
                    section=None,
                    url="https://cdn.cboe.com/vix",
                    match_score_permille=300,
                ),
            ),
        },
        cash_events=(
            CashEventView(kind="dividend", t_ms=NOW_MS - 5 * BAR_MS, applied_at_ms=NOW_MS - 4 * BAR_MS, detail={}),
            CashEventView(kind="funding", t_ms=NOW_MS - 60 * BAR_MS, applied_at_ms=NOW_MS - 60 * BAR_MS, detail={}),
        ),
        hive=HiveView(
            lessons=(
                HiveLessonView(
                    entry_id="h-00000001",
                    author_id="alpha",
                    author_skill_micro=1_000,
                    text="a lesson",
                    market_ids=(MARKET_ID,),
                    visible_from_ms=NOW_MS - BAR_MS,
                ),
                HiveLessonView(
                    entry_id="h-00000002",
                    author_id="beta",
                    author_skill_micro=-500,
                    text="a lesson from the future",
                    market_ids=(MARKET_ID,),
                    visible_from_ms=NOW_MS + BAR_MS,
                ),
            ),
            reputations=(
                ReputationView(agent_id="alpha", category="politics", n=30, skill_micro=12_000, pnl_cents=400),
                ReputationView(agent_id="beta", category="politics", n=30, skill_micro=-3_000, pnl_cents=-100),
                ReputationView(agent_id="gamma", category="politics", n=1, skill_micro=0, pnl_cents=0),
            ),
            forecasts=(
                ForecastView(agent_id="alpha", market_id=MARKET_ID, bar_ms=NOW_MS - BAR_MS, prob_ppm=600_000),
            ),
            prev_bar_forecasts=(
                ForecastView(agent_id="beta", market_id=MARKET_ID, bar_ms=NOW_MS - BAR_MS, prob_ppm=400_000),
                ForecastView(agent_id="beta", market_id="kalshi-other", bar_ms=NOW_MS - BAR_MS, prob_ppm=500_000),
            ),
        ),
        memory=MemoryView(
            calibration=(
                CalibrationBinView(category="politics", horizon_bucket="7d", bin=7, n=20, n_yes=15, n_yes_x2=30),
                CalibrationBinView(category="politics", horizon_bucket="7d", bin=2, n=10, n_yes=3, n_yes_x2=6),
                CalibrationBinView(category="crypto", horizon_bucket="7d", bin=8, n=5, n_yes=4, n_yes_x2=8),
            ),
            notes=(
                NoteView(written_at_ms=NOW_MS - 2 * BAR_MS, market_id=MARKET_ID, text="a note"),
                NoteView(written_at_ms=NOW_MS - 3 * BAR_MS, market_id=MARKET_ID, text="another note"),
                NoteView(written_at_ms=NOW_MS - 4 * BAR_MS, market_id="kalshi-other", text="elsewhere"),
            ),
        ),
        peers={
            "manifold-twin": make_bars(40, first_close_bp=3_500),
            "kalshi-sibling": make_bars(40, first_close_bp=4_600),
            "binance-btcusdt-perp": make_bars(40, first_close_bp=6_000, step_bp=40),
        },
        research={
            "wiki_asof": (
                NewsView(
                    news_id="wasof-20230101-0001",
                    source="wikipedia_asof",
                    kind="background",
                    published_at_ms=NOW_MS - 9 * MS_PER_DAY,
                    headline="Subject revision one",
                    text="the earlier revision mentions alpha beta gamma",
                    section=None,
                    url="https://en.wikipedia.org/w/index.php?oldid=1",
                    match_score_permille=1_000,
                ),
                NewsView(
                    news_id="wasof-20230101-0002",
                    source="wikipedia_asof",
                    kind="background",
                    published_at_ms=NOW_MS - 3 * MS_PER_DAY,
                    headline="Subject revision two",
                    text="the later revision mentions alpha delta epsilon",
                    section=None,
                    url="https://en.wikipedia.org/w/index.php?oldid=2",
                    match_score_permille=1_000,
                ),
            )
        },
    )


def sense_all(inputs: Inputs, *, now_ms: int = NOW_MS) -> dict[str, SensorBlock]:
    return {name: SENSE_BY_NAME[name](inputs, now_ms=now_ms, spec=SENSORS[name]) for name in SENSOR_NAMES}


def values_of(inputs: Inputs, name: str, *, now_ms: int = NOW_MS) -> dict[str, int]:
    """One block as ``{feature name: value}``, which is how a rule's predicate names it."""
    block = SENSE_BY_NAME[name](inputs, now_ms=now_ms, spec=SENSORS[name])
    return {feature.name: block.values[feature.index] for feature in SENSORS[name].features}


# --------------------------------------------------------------------------------------------------
# The catalogue against the normative fixture
# --------------------------------------------------------------------------------------------------
def catalogue_document() -> str:
    return canonical_json(
        {
            "catalogue_hash": CATALOGUE_HASH,
            "schema_version": "sensor.v1",
            "sensors": [spec.to_dict() for spec in SENSORS.values()],
        }
    )


def test_the_catalogue_reproduces_the_normative_fixture_byte_for_byte() -> None:
    """``tests/fixtures/contract/sensor.catalogue.json`` is amendment C1c's and S1 implements it exactly.

    A failure here is a contract issue to report, never a licence to edit the fixture (ruling R286).
    """
    assert catalogue_document().encode("utf-8") + b"\n" == CONTRACT_FIXTURE.read_bytes()


def test_the_catalogue_hash_is_the_fixtures_and_is_the_hash_of_the_sensor_list() -> None:
    fixture = json.loads(CONTRACT_FIXTURE.read_text(encoding="utf-8"))
    assert fixture["catalogue_hash"] == CATALOGUE_HASH
    assert sha256_hex(
        canonical_json([spec.to_dict() for spec in SENSORS.values()]).encode("utf-8")
    ) == CATALOGUE_HASH


def test_the_hash_is_stable_across_two_constructions() -> None:
    """Two independent builds of the same table hash the same: nothing in a spec depends on identity,
    insertion order or a clock."""
    first = {row[0]: _spec_of(row) for row in sorted(_CATALOGUE_TABLE, key=lambda r: r[0])}
    second = {row[0]: _spec_of(row) for row in sorted(_CATALOGUE_TABLE, key=lambda r: r[0])}
    hashes = {
        sha256_hex(canonical_json([spec.to_dict() for spec in built.values()]).encode("utf-8"))
        for built in (first, second)
    }
    assert hashes == {CATALOGUE_HASH}


@pytest.mark.parametrize(
    "sensor_name,mutate",
    [
        ("hn", lambda spec: replace(spec, cost_units=spec.cost_units + 1)),
        ("tape", lambda spec: replace(spec, version="tape.v2")),
        ("comments", lambda spec: replace(spec, features=spec.features[::-1])),
        ("wiki_daily", lambda spec: replace(spec, lag_ms=spec.lag_ms + 1)),
        ("memory", lambda spec: replace(spec, per_market=False)),
        (
            "calendar",
            lambda spec: replace(
                spec, features=(replace(spec.features[0], sentinel=spec.features[0].sentinel - 1), *spec.features[1:])
            ),
        ),
    ],
)
def test_the_hash_moves_when_a_row_moves(sensor_name: str, mutate: object) -> None:
    """Any change to any field of any row changes ``CATALOGUE_HASH``, which is what makes the hash a
    record of which catalogue a run read (ruling R231)."""
    moved = dict(SENSORS)
    assert callable(mutate)
    moved[sensor_name] = mutate(SENSORS[sensor_name])
    assert moved[sensor_name] != SENSORS[sensor_name]
    moved_hash = sha256_hex(
        canonical_json([spec.to_dict() for spec in moved.values()]).encode("utf-8")
    )
    assert moved_hash != CATALOGUE_HASH


def test_the_catalogue_is_closed_and_every_name_matches_the_regex() -> None:
    assert len(SENSORS) == 15
    assert tuple(sorted(SENSORS)) == SENSOR_NAMES
    for name in SENSOR_NAMES:
        assert RE_SENSOR.match(name), name
        assert SENSORS[name].name == name


@pytest.mark.parametrize("name", ["", "Tape", "tape ", "tapes", "hive", "nope", "volume", "tape|hn", "wiki"])
def test_the_regex_refuses_a_name_outside_the_fifteen(name: str) -> None:
    assert RE_SENSOR.match(name) is None


@pytest.mark.parametrize("row", CONTRACT_ROWS, ids=[row[0] for row in CONTRACT_ROWS])
def test_every_row_carries_the_cost_granularity_lag_and_sources_of_the_contract(
    row: tuple[str, int, int, int, tuple[str, ...], bool],
) -> None:
    name, cost_units, granularity_ms, lag_ms, sources, per_market = row
    spec = SENSORS[name]
    assert (spec.cost_units, spec.granularity_ms, spec.lag_ms) == (cost_units, granularity_ms, lag_ms)
    assert spec.sources == sources
    assert spec.per_market is per_market
    assert spec.version == f"{name}.v1"
    assert 0 <= spec.cost_units <= SENSOR_COST_MAX


def test_the_source_tables_are_18_3_verbatim() -> None:
    """The mirror S1 keeps until ``pmx.types`` carries the two tables (18.8's first row)."""
    for source, granularity_ms in CONTRACT_SOURCE_GRANULARITY_MS.items():
        assert derived_granularity_ms((source,)) == granularity_ms, source
    for source, lag_ms in CONTRACT_SAFETY_LAG_MS_BY_SOURCE.items():
        assert derived_lag_ms((source,)) == lag_ms, source
    assert derived_granularity_ms(()) == 0
    assert derived_lag_ms(()) == 0


@pytest.mark.parametrize("name", [row[0] for row in CONTRACT_ROWS])
def test_granularity_and_lag_are_the_derived_maxima_over_the_sources(name: str) -> None:
    """Ruling R287: the pair names the sensor's **worst** source and never its best."""
    spec = SENSORS[name]
    assert spec.granularity_ms == max(
        (CONTRACT_SOURCE_GRANULARITY_MS[source] for source in spec.sources), default=0
    )
    assert spec.lag_ms == max((CONTRACT_SAFETY_LAG_MS_BY_SOURCE[source] for source in spec.sources), default=0)


def test_macro_releases_reads_a_day_and_six_hours_because_cboe_is_day_stamped() -> None:
    """The one row where the derivation mattered: ``fred`` is second stamped and unlagged, ``cboe`` is
    day stamped and six hours late, and the sensor advertises the second (ruling R287)."""
    spec = SENSORS["macro_releases"]
    assert spec.sources == ("cboe", "fred")
    assert (spec.granularity_ms, spec.lag_ms) == (MS_PER_DAY, SAFETY_LAG_MS_DEFAULT)
    assert derived_granularity_ms(("fred",)) == MS_PER_SECOND
    assert derived_lag_ms(("fred",)) == 0


# --------------------------------------------------------------------------------------------------
# The sentinel rule (ruling R285), asserted against the fixture
# --------------------------------------------------------------------------------------------------
def fixture_features() -> list[dict[str, object]]:
    fixture = json.loads(CONTRACT_FIXTURE.read_text(encoding="utf-8"))
    return [feature for sensor in fixture["sensors"] for feature in sensor["features"]]


def test_the_fixture_fills_all_seventy_five_sentinels_by_one_rule() -> None:
    features = fixture_features()
    assert len(features) == 75
    for feature in features:
        name, lo, hi = feature["name"], feature["lo"], feature["hi"]
        assert isinstance(name, str) and isinstance(lo, int) and isinstance(hi, int)
        assert feature["sentinel"] == sentinel_for(name, lo=lo, hi=hi), name


def test_every_sentinel_is_inside_its_bounds_and_no_signed_feature_takes_its_lo() -> None:
    for feature in fixture_features():
        lo, hi, sentinel, name = feature["lo"], feature["hi"], feature["sentinel"], feature["name"]
        assert isinstance(lo, int) and isinstance(hi, int) and isinstance(sentinel, int)
        assert lo <= sentinel <= hi, name
        if lo < 0:
            assert sentinel == 0 != lo, name


def test_the_elapsed_counts_read_their_hi_and_nothing_else_does() -> None:
    """"Nothing has happened yet" is arbitrarily long ago, and only an elapsed or remaining count says so."""
    elapsed = {
        feature["name"] for feature in fixture_features() if feature["sentinel"] == feature["hi"] != feature["lo"]
    }
    assert elapsed == {
        "bars_since_last_release",
        "bars_since_listed",
        "bars_to_close",
        "bars_to_next_release",
        "minutes_since_article",
        "minutes_since_comment",
        "minutes_since_filing",
        "minutes_since_story",
        "wiki_asof_days_since_revision",
    }


def test_the_signed_features_are_the_eleven_the_fixture_carries() -> None:
    """Ruling R285's five plus the six the same rule covers: each reads ``0`` and never minus one hundred
    percent over the opening bars of every market."""
    signed = {feature["name"] for feature in fixture_features() if feature["lo"] < 0}
    assert signed == {
        "cluster_gap_bp",
        "constraint_residual_ppm",
        "logit_last_milli",
        "mid_minus_last_bp",
        "news_direction_milli_7d",
        "ret_1b_bp",
        "ret_7b_bp",
        "ret_30b_bp",
        "ret_90b_bp",
        "underlying_ret_1b_bp",
        "volume_milli_z_milli_30b",
    }
    assert {"ret_7b_bp", "ret_30b_bp", "ret_90b_bp", "mid_minus_last_bp", "volume_milli_z_milli_30b"} <= signed
    for feature in fixture_features():
        if feature["name"] in signed:
            assert feature["sentinel"] == 0


# --------------------------------------------------------------------------------------------------
# The vocabulary, the ``features.v1`` slice and the block shape
# --------------------------------------------------------------------------------------------------
def test_feature_names_are_unique_across_the_catalogue_and_number_seventy_five() -> None:
    """S2's ``pmx.rules.vocabulary.FEATURE_NAMES`` is exactly this union (18.1), so a duplicate name would
    make one predicate mean two things."""
    names = [feature.name for spec in SENSORS.values() for feature in spec.features]
    assert len(names) == 75
    assert len(set(names)) == 75


def test_every_block_is_indexed_from_zero_and_declares_its_own_sensor() -> None:
    for spec in SENSORS.values():
        assert [feature.index for feature in spec.features] == list(range(len(spec.features)))
        for feature in spec.features:
            assert feature.source == spec.name
            assert feature.asof_only is True
            assert feature.scale >= 1
            assert feature.lo <= feature.hi


def test_features_v1_indices_cover_the_thirty_one_non_portfolio_fields_exactly_once() -> None:
    """``features.v1`` is unchanged (18.1): every field but the six of the ``portfolio`` block belongs to
    exactly one sensor block, and the two ``category`` fields sit under the always-on ``tape``."""
    indices = [
        feature.features_v1_index
        for spec in SENSORS.values()
        for feature in spec.features
        if feature.features_v1_index is not None
    ]
    assert sorted(indices) == list(range(31))
    tape_indices = {
        feature.features_v1_index for feature in SENSORS["tape"].features if feature.features_v1_index is not None
    }
    assert {19, 20} <= tape_indices


def test_a_torch_policy_diet_is_every_sensor_carrying_a_features_v1_index() -> None:
    """Ruling R299: the family's ``required_sensors``, computed from the catalogue and not hand written."""
    carriers = {
        spec.name
        for spec in SENSORS.values()
        if any(feature.features_v1_index is not None for feature in spec.features)
    }
    assert carriers == {"tape", "calendar", "microstructure", "volume_profile", "cross_asset", "wiki_daily"}


def test_market_id_is_none_exactly_for_the_one_observation_level_sensor() -> None:
    """Ruling R286, decided in favour of the fixture: ``hive_reputation`` and nothing else."""
    assert {name for name, spec in SENSORS.items() if not spec.per_market} == {"hive_reputation"}
    blocks = sense_all(reference_inputs())
    for name, block in blocks.items():
        assert (block.market_id is None) is (not SENSORS[name].per_market), name
        assert block.market_id in (None, MARKET_ID)


def test_sensor_by_news_source_is_a_function_over_the_catalogues_sources() -> None:
    pairs = [(source, spec.name) for spec in SENSORS.values() for source in spec.sources]
    assert len(pairs) == len(SENSOR_BY_NEWS_SOURCE) == 9
    assert dict(pairs) == SENSOR_BY_NEWS_SOURCE
    assert SENSOR_BY_NEWS_SOURCE["cboe"] == SENSOR_BY_NEWS_SOURCE["fred"] == "macro_releases"
    assert SENSOR_BY_NEWS_SOURCE["wayback"] == SENSOR_BY_NEWS_SOURCE["wikipedia_current_events"] == "wiki_daily"
    assert SENSOR_BY_NEWS_SOURCE["hn"] == "hn"


def test_the_gated_fields_name_real_view_fields() -> None:
    """A gate names a ``MarketView`` or ``Observation`` field, or a dotted path whose head is one, so no
    sensor can gate a field that does not exist (ruling R233's three nested gates included)."""
    market_fields = {f.name for f in MarketView.__dataclass_fields__.values()}
    observation_fields = {f.name for f in Observation.__dataclass_fields__.values()}
    bar_fields = {f.name for f in Bar.__dataclass_fields__.values()}
    for spec in SENSORS.values():
        for gated in spec.market_fields:
            head, _, tail = gated.partition(".")
            assert head in market_fields, gated
            if tail:
                assert head == "bars" and tail in bar_fields, gated
        for gated in spec.observation_fields:
            head, _, tail = gated.partition(".")
            assert head in observation_fields, gated


# --------------------------------------------------------------------------------------------------
# The budget arithmetic (rulings R235 and R281)
# --------------------------------------------------------------------------------------------------
def test_the_budget_arithmetic_is_integer_and_a_full_diet_can_still_propose() -> None:
    """Ruling R281 replaced the stale "the sum is 17" allowance: the default is ``17 + 1``, so the eight
    v1 archetypes, which all carry the full diet, are not permanently barred from proposing a rule."""
    per_sensor = [SENSORS[name].cost_units for name in SENSOR_NAMES]
    assert all(isinstance(cost, int) and 0 <= cost <= SENSOR_COST_MAX for cost in per_sensor)
    assert FULL_DIET_COST_UNITS == sum(per_sensor) == 17
    assert SENSOR_BUDGET_UNITS_DEFAULT == FULL_DIET_COST_UNITS + RULE_PROPOSAL_COST_UNITS == 18
    assert FULL_DIET_COST_UNITS + RULE_PROPOSAL_COST_UNITS <= SENSOR_BUDGET_UNITS_DEFAULT


def test_the_free_sensors_are_the_three_the_contract_names() -> None:
    assert {name for name, spec in SENSORS.items() if spec.cost_units == 0} == {"tape", "calendar", "memory"}


def test_a_diet_costs_the_sum_of_its_rows_and_a_drop_is_the_most_expensive_non_tape_row() -> None:
    """``diet_cost_units`` of 18.1 in the only form S1 can state it before ``Genome`` carries ``sensors``:
    integer arithmetic over the catalogue, with no float and no cash movement anywhere near it."""
    diet = ("tape", "wiki_asof", "hn", "calendar")
    assert sum(SENSORS[name].cost_units for name in diet) == 5
    # The sensor drop of ruling R235: the most expensive non-``tape`` row first, ties by name descending.
    def most_expensive(names: tuple[str, ...]) -> str:
        return max((name for name in names if name != "tape"), key=lambda name: (SENSORS[name].cost_units, name))

    assert most_expensive(diet) == "wiki_asof"
    assert most_expensive(("tape", "comments", "cross_asset")) == "cross_asset"
    assert SENSORS["comments"].cost_units == SENSORS["cross_asset"].cost_units == 1


# --------------------------------------------------------------------------------------------------
# An unknown sensor name
# --------------------------------------------------------------------------------------------------
def test_an_unknown_sensor_name_is_refused_with_the_projects_error_type() -> None:
    """18.1: a genome that names a sensor outside the catalogue is refused, and a sensor name comes from a
    genome, so the error is ``InvalidConfigError`` and never a silently narrower diet."""
    with pytest.raises(InvalidConfigError):
        resolve_sensor_set(["tape", "not_a_sensor"])
    with pytest.raises(InvalidConfigError):
        resolve_sensor_set(["TAPE"])
    assert resolve_sensor_set(None) is None
    with pytest.raises(KeyError):
        _ = SENSORS["not_a_sensor"]


# --------------------------------------------------------------------------------------------------
# ``block_of``: the sentinel substitution and the clamp
# --------------------------------------------------------------------------------------------------
def test_block_of_substitutes_the_sentinel_for_a_missing_input_and_clamps_the_rest() -> None:
    spec = SENSORS["comments"]
    block = block_of(spec, MARKET_ID, [None, 10**9, -5, None])
    assert block.values == (0, 100_000, 0, 100_000)
    assert block.sensor == "comments" and block.version == "comments.v1"
    assert block.to_dict() == {
        "sensor": "comments",
        "version": "comments.v1",
        "market_id": MARKET_ID,
        "values": [0, 100_000, 0, 100_000],
    }


def test_block_of_refuses_a_width_that_is_not_the_specs() -> None:
    with pytest.raises(ValueError, match="values for"):
        block_of(SENSORS["tape"], MARKET_ID, [0, 0, 0])


@pytest.mark.parametrize("name", SENSOR_NAMES)
def test_every_sense_body_returns_a_block_of_its_own_width_and_bounds(name: str) -> None:
    spec = SENSORS[name]
    block = SENSE_BY_NAME[name](reference_inputs(), now_ms=NOW_MS, spec=spec)
    assert isinstance(block, SensorBlock)
    assert (block.sensor, block.version) == (spec.name, spec.version)
    assert len(block.values) == len(spec.features)
    for feature, value in zip(spec.features, block.values, strict=True):
        assert isinstance(value, int) and not isinstance(value, bool)
        assert feature.lo <= value <= feature.hi, feature.name


def test_ln1p_milli_is_integer_and_platform_stable() -> None:
    """``Decimal.ln``, never ``math.log``: the same feature must hash the same on glibc and on msvcrt."""
    assert ln1p_milli(0) == 0
    assert ln1p_milli(-1) == 0
    assert ln1p_milli(1) == 693
    assert ln1p_milli(999) == 6_908
    assert ln1p_milli(1_000_000) == 13_816


# --------------------------------------------------------------------------------------------------
# The sentinel rule on a market younger than the window a feature measures
# --------------------------------------------------------------------------------------------------
def test_a_market_younger_than_the_window_reads_the_sentinel_and_never_the_floor() -> None:
    """Ruling R285's own example. Three completed bars: the seven, thirty and ninety bar returns have no
    window to measure, so each reads ``0`` and not ``-10000``, which would be a constant minus one hundred
    percent over the opening bars of every market and the strongest signal in the miner's search.
    """
    young = replace(reference_inputs(), bars=make_bars(3), quotes=None)
    values = values_of(young, "tape")
    assert values["ret_1b_bp"] == 25
    assert values["ret_7b_bp"] == values["ret_30b_bp"] == values["ret_90b_bp"] == 0
    for name in ("ret_7b_bp", "ret_30b_bp", "ret_90b_bp"):
        feature = SENSORS["tape"].features[SENSORS["tape"].feature_index(name)]
        assert feature.lo == -10_000 and feature.sentinel == 0
    assert values["last_price_bp"] == 4_050


def test_a_market_with_no_completed_bar_reads_sentinels_and_not_zeros_that_look_measured() -> None:
    empty = Inputs(meta=make_meta())
    tape_values = values_of(empty, "tape")
    assert tape_values["last_price_bp"] == 0
    assert tape_values["logit_last_milli"] == 0
    assert tape_values["realised_vol_bp_30b"] == 0
    assert values_of(empty, "microstructure")["prints_10b"] == 0
    assert values_of(empty, "volume_profile")["volume_milli_z_milli_30b"] == 0
    assert values_of(empty, "comments")["minutes_since_comment"] == 100_000
    assert values_of(empty, "hn")["minutes_since_story"] == 100_000
    assert values_of(empty, "wiki_asof")["wiki_asof_days_since_revision"] == 100_000
    assert values_of(empty, "macro_releases")["bars_since_last_release"] == 100_000


def test_an_unquoted_tape_reads_the_spread_sentinel_and_not_a_zero_spread() -> None:
    unquoted = replace(reference_inputs(), quotes=None)
    values = values_of(unquoted, "microstructure")
    assert values["spread_bp"] == 0 and values["mid_minus_last_bp"] == 0
    quoted = values_of(reference_inputs(), "microstructure")
    assert quoted["spread_bp"] == 40
    assert quoted["mid_minus_last_bp"] == 5


def test_a_flat_volume_window_has_no_z_score() -> None:
    """A z score with no dispersion is undefined, not zero standard deviations."""
    flat = replace(reference_inputs(), bars=make_bars(40, step_bp=0))
    flat_bars = tuple(replace(bar, volume_milli=1_000) for bar in flat.bars)
    values = values_of(replace(flat, bars=flat_bars), "volume_profile")
    assert values["volume_milli_z_milli_30b"] == 0


def test_a_diet_without_a_hive_or_a_memory_reads_sentinels_throughout() -> None:
    blind = replace(reference_inputs(), hive=None, memory=None)
    assert set(values_of(blind, "hive_insights").values()) == {0}
    assert set(values_of(blind, "hive_reputation").values()) == {0}
    assert set(values_of(blind, "memory").values()) == {0}


# --------------------------------------------------------------------------------------------------
# The measured values of the reference input, pinned
# --------------------------------------------------------------------------------------------------
def test_the_reference_blocks_match_the_pinned_fixture() -> None:
    """One pinned document over the fifteen blocks: a body that starts measuring something else, or stops
    measuring what it did, moves a number here."""
    expected = json.loads((S1_FIXTURES / "blocks.expected.json").read_text(encoding="utf-8"))
    produced = {name: block.to_dict() for name, block in sense_all(reference_inputs()).items()}
    assert produced == expected


def test_the_measured_values_a_reader_can_check_by_hand() -> None:
    """A handful of values recomputed here from the reference input, so the pinned fixture above is not
    the only witness that a body measures what its description says."""
    inputs = reference_inputs()
    assert values_of(inputs, "tape")["ret_1b_bp"] == 25
    assert values_of(inputs, "tape")["ret_30b_bp"] == 750
    assert values_of(inputs, "tape")["provider_index"] == 0
    assert values_of(inputs, "tape")["category_index"] == 0
    assert values_of(inputs, "tape")["dist_from_high_bp_30b"] == 0
    assert values_of(inputs, "tape")["dist_from_low_bp_30b"] == 725
    assert values_of(inputs, "calendar")["bars_to_close"] == 50
    assert values_of(inputs, "calendar")["bars_since_listed"] == 100
    assert values_of(inputs, "calendar")["hour_of_day"] == (NOW_MS % MS_PER_DAY) // MS_PER_HOUR
    assert values_of(inputs, "hn")["hn_story_points"] == 412
    assert values_of(inputs, "hn")["hn_story_comments"] == 87
    assert values_of(inputs, "hn")["hn_stories_24h"] == 2
    assert values_of(inputs, "hn")["minutes_since_story"] == 180
    assert values_of(inputs, "gdelt_recent")["gdelt_domains_24b"] == 2
    assert values_of(inputs, "gdelt_recent")["minutes_since_article"] == 15
    assert values_of(inputs, "filings")["filings_8k_30b"] == 2
    assert values_of(inputs, "macro_releases")["vix_last_milli"] == 14_350
    assert values_of(inputs, "macro_releases")["bars_since_last_release"] == 9
    assert values_of(inputs, "memory")["memory_n_resolved"] == 35
    assert values_of(inputs, "memory")["memory_category_n"] == 30
    assert values_of(inputs, "memory")["memory_category_hits_permille"] == 733
    assert values_of(inputs, "memory")["memory_market_forecasts"] == 2
    assert values_of(inputs, "hive_reputation")["peer_reputations"] == 3
    assert values_of(inputs, "hive_reputation")["peers_positive_reputation"] == 1
    assert values_of(inputs, "hive_reputation")["peers_negative_reputation"] == 1
    assert values_of(inputs, "hive_insights")["lessons_visible"] == 1
    assert values_of(inputs, "hive_insights")["peer_forecasts_visible"] == 2
    assert values_of(inputs, "cross_asset")["cluster_peer_count"] == 2
    assert values_of(inputs, "cross_asset")["twins_count"] == 1
    assert values_of(inputs, "cross_asset")["cluster_gap_bp"] == -50
    assert values_of(inputs, "cross_asset")["underlying_ret_1b_bp"] == 53
    assert values_of(inputs, "volume_profile")["cash_events_30b"] == 1
    assert values_of(inputs, "wiki_daily")["news_count_1d"] == 1
    assert values_of(inputs, "wiki_daily")["news_count_7d"] == 5


def test_a_hive_lesson_from_the_future_is_not_visible() -> None:
    """Every value is as-of by 5.4, and a lesson stamped after ``now_ms`` is the poisoned-future case."""
    inputs = reference_inputs()
    assert values_of(inputs, "hive_insights")["lessons_visible"] == 1
    later = values_of(inputs, "hive_insights", now_ms=NOW_MS + 2 * BAR_MS)
    assert later["lessons_visible"] == 2


def test_a_news_item_outside_the_window_is_not_counted() -> None:
    inputs = reference_inputs()
    assert values_of(inputs, "wiki_daily")["news_count_7d"] == 5
    assert values_of(inputs, "wiki_daily")["news_count_1d"] == 1
    older = replace(
        inputs,
        news={
            **inputs.news,
            "wikipedia_current_events": tuple(
                replace(item, published_at_ms=item.published_at_ms - 30 * MS_PER_DAY)
                for item in inputs.news["wikipedia_current_events"]
            ),
        },
    )
    assert values_of(older, "wiki_daily")["news_count_7d"] == 1
    assert values_of(older, "wiki_daily")["news_count_1d"] == 0


def test_the_domain_of_a_url_is_pure_string_work() -> None:
    assert gdelt_recent.domain_of("https://www.reuters.com/world/a") == "reuters.com"
    assert gdelt_recent.domain_of("http://apnews.com:8080/article/b") == "apnews.com"
    assert gdelt_recent.domain_of("apnews.com/x") == "apnews.com"


def test_a_story_line_without_the_counts_carries_no_points() -> None:
    """18.3 fixes the first line as ``points=<n> comments=<n>``; anything else is a missing input."""
    inputs = reference_inputs()
    broken = replace(
        inputs,
        news={
            **inputs.news,
            "hn": tuple(replace(item, text="no counts here\nbody") for item in inputs.news["hn"]),
        },
    )
    values = values_of(broken, "hn")
    assert values["hn_story_points"] == 0 and values["hn_story_comments"] == 0
    assert values["hn_stories_24h"] == 2


def test_the_sense_bodies_are_pure_functions_of_their_inputs() -> None:
    """Called twice on the same input, a sensor returns the same block: no clock, no randomness, no
    accumulated state (architecture rule 6's discipline, applied to the sensors)."""
    inputs = reference_inputs()
    first = {name: block.to_dict() for name, block in sense_all(inputs).items()}
    second = {name: block.to_dict() for name, block in sense_all(inputs).items()}
    assert first == second


def test_no_sensor_module_reaches_for_a_socket_or_a_model() -> None:
    """Architecture rule 12 in miniature, kept beside the package it binds: ``tests/test_architecture.py``
    enforces it over the tree, and this says why it matters here."""
    sources: Sequence[str] = [
        (Path(__file__).parents[1] / "src" / "pmx" / "sensors" / f"{name}.py").read_text(encoding="utf-8")
        for name in [*SENSOR_NAMES, "catalogue"]
    ]
    for text in sources:
        assert "pmx.gateway" not in text
        assert "pmx.llm" not in text
        assert "import socket" not in text


# --------------------------------------------------------------------------------------------------
# The windows and the shapes a ramp cannot show
# --------------------------------------------------------------------------------------------------
def test_block_of_drops_the_market_id_of_an_observation_level_row() -> None:
    """``block_of`` and not the body is what enforces ruling R286, so it is asserted on ``block_of``."""
    assert block_of(SENSORS["hive_reputation"], MARKET_ID, [0, 0, 0]).market_id is None
    assert block_of(SENSORS["memory"], MARKET_ID, [0, 0, 0, 0]).market_id == MARKET_ID


def test_the_distances_from_the_extremes_are_both_positive_inside_a_range() -> None:
    """A monotone ramp puts the last price on its own high, which hides a sign error; a peak in the
    middle of the window does not."""
    inputs = reference_inputs()
    peaked = list(make_bars(40))
    peaked[20] = replace(peaked[20], close_bp=8_000, high_bp=8_010)
    values = values_of(replace(inputs, bars=tuple(peaked)), "tape")
    assert values["dist_from_high_bp_30b"] == 8_000 - 4_975
    assert values["dist_from_low_bp_30b"] == 4_975 - 4_250


def test_a_print_older_than_ten_bars_is_not_in_prints_10b() -> None:
    inputs = reference_inputs()
    old_prints = (
        *inputs.trades,
        Trade(t_ms=NOW_MS - 30 * BAR_MS, price_bp=4_000, size_milli=1_000, side="yes"),
        Trade(t_ms=NOW_MS - 11 * BAR_MS, price_bp=4_100, size_milli=1_000, side="no"),
    )
    assert values_of(replace(inputs, trades=old_prints), "microstructure")["prints_10b"] == 12


def test_a_cash_event_older_than_thirty_bars_is_not_in_cash_events_30b() -> None:
    inputs = reference_inputs()
    events = (
        *inputs.cash_events,
        CashEventView(kind="split", t_ms=NOW_MS - 35 * BAR_MS, applied_at_ms=NOW_MS - 35 * BAR_MS, detail={}),
    )
    assert values_of(replace(inputs, cash_events=events), "volume_profile")["cash_events_30b"] == 1


def test_a_filing_that_is_not_a_current_report_is_counted_once_and_not_twice() -> None:
    inputs = reference_inputs()
    filings_items = (
        *inputs.news["edgar"],
        NewsView(
            news_id="edg-20230101-0009",
            source="edgar",
            kind="filing",
            published_at_ms=NOW_MS - 2 * BAR_MS,
            headline="10-K annual report",
            text="the filing body",
            section="10-K",
            url="https://www.sec.gov/Archives/9",
            match_score_permille=500,
        ),
    )
    values = values_of(replace(inputs, news={**inputs.news, "edgar": filings_items}), "filings")
    assert values["filings_30b"] == 3
    assert values["filings_8k_30b"] == 2


def test_one_granted_revision_is_no_text_delta() -> None:
    """A delta needs two revisions; one is a missing input and reads ``0``, never a delta against itself."""
    inputs = reference_inputs()
    one = tuple(inputs.research["wiki_asof"])[:1]  # type: ignore[index]
    values = values_of(replace(inputs, research={"wiki_asof": one}), "wiki_asof")
    assert values["wiki_asof_revisions_granted"] == 1
    assert values["wiki_asof_text_delta_permille"] == 0
    assert values["wiki_asof_days_since_revision"] == 9


def test_a_revision_stamped_after_now_never_reaches_the_block() -> None:
    """The poisoned-future case of 5.4, applied to a granted research payload."""
    inputs = reference_inputs()
    granted = tuple(inputs.research["wiki_asof"])  # type: ignore[arg-type]
    poisoned = (
        *granted,
        replace(granted[-1], news_id="wasof-20230101-0003", published_at_ms=NOW_MS + MS_PER_DAY),
    )
    values = values_of(replace(inputs, research={"wiki_asof": poisoned}), "wiki_asof")
    assert values["wiki_asof_revisions_granted"] == 2
    assert values["wiki_asof_days_since_revision"] == 3
    assert values_of(replace(inputs, research={"wiki_asof": "not a payload"}), "wiki_asof") == {
        "wiki_asof_revisions_granted": 0,
        "wiki_asof_days_since_revision": 100_000,
        "wiki_asof_text_delta_permille": 0,
    }


def test_a_story_older_than_1440_minutes_is_outside_the_hn_window() -> None:
    """18.3's ``hn`` window is 1440 minutes, which is one day whatever the grid, and a story that falls
    out of it is a missing input: the two counts read their ``lo`` and ``minutes_since_story`` its ``hi``,
    not the age of a story the window no longer holds."""
    inputs = reference_inputs()
    stale = tuple(
        replace(item, published_at_ms=NOW_MS - (25 + index) * MS_PER_HOUR)
        for index, item in enumerate(inputs.news["hn"])
    )
    values = values_of(replace(inputs, news={**inputs.news, "hn": stale}), "hn")
    assert values["hn_stories_24h"] == 0
    assert values["hn_story_points"] == 0
    assert values["hn_story_comments"] == 0
    assert values["hn_mentions_subject"] == 0
    assert values["minutes_since_story"] == 100_000
    # One minute inside the window is inside it: the boundary is 1440 minutes and not the whole history.
    fresh = (replace(stale[0], published_at_ms=NOW_MS - 1_439 * MS_PER_MINUTE), *stale[1:])
    inside = values_of(replace(inputs, news={**inputs.news, "hn": fresh}), "hn")
    assert inside["hn_stories_24h"] == 1
    assert inside["hn_story_points"] == 412
    assert inside["minutes_since_story"] == 1_439


def test_a_filing_older_than_thirty_bars_is_outside_the_filings_window() -> None:
    """``filings_30b`` counts the last thirty completed bars and nothing earlier, while
    ``minutes_since_filing`` is unwindowed: it answers "how long since the last one", which a window
    would turn into "how long since the last one I still count"."""
    inputs = reference_inputs()
    window_start_ms = inputs.bars[-30].t_ms
    filings_items = (
        *inputs.news["edgar"],
        replace(inputs.news["edgar"][0], news_id="edg-20230101-0031", published_at_ms=window_start_ms - 1),
        replace(inputs.news["edgar"][0], news_id="edg-20230101-0030", published_at_ms=window_start_ms),
    )
    values = values_of(replace(inputs, news={**inputs.news, "edgar": filings_items}), "filings")
    assert values["filings_30b"] == 3
    assert values["filings_8k_30b"] == 3
    assert values["minutes_since_filing"] == 4 * INTERVAL_MIN
