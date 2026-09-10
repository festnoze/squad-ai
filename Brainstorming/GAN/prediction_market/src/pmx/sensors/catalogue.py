"""The closed sensor catalogue of CONTRACTS_V2 section 18.1 (package S1).

Fifteen named, versioned, costed views of as-of information. A sensor gates the ``MarketView`` and
``Observation`` fields it names (8.3, ruling R230: what is not sensed is not seen, by subtraction) and
produces one fixed-width integer ``SensorBlock`` whose layout is its ``features`` tuple.

Three properties of this module are load bearing and each is asserted by ``tests/test_sensors.py``:

* ``SENSORS`` reproduces ``tests/fixtures/contract/sensor.catalogue.json`` **byte for byte**. That
  fixture is amendment C1c's normative table, not S1's, so a disagreement is a contract issue and never
  a licence to edit the fixture (ruling R286).
* ``granularity_ms`` and ``lag_ms`` are **derived**, never hand written (ruling R287): the maxima of
  ``SOURCE_GRANULARITY_MS`` and ``SAFETY_LAG_MS_BY_SOURCE`` (18.3) over the sensor's sources, and ``0``
  for a sensor with none, so the column a reader consults when asking whether a sensor can leak names
  that sensor's **worst** source and never its best.
* ``SensorFeatureSpec.sentinel`` is a field and never a sentence in a description (ruling R285): a
  signed quantity's sentinel is ``0``, a ``minutes_since_*``, ``bars_since_*``, ``bars_to_*`` or
  ``*_days_since_*`` count's is its ``hi``, and every other feature's is its ``lo``.

``CATALOGUE_HASH`` is what a run records, so a catalogue change is visible on the face of every run
(ruling R231). Adding, removing or renaming a feature bumps the sensor's ``version`` and therefore the
hash.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Protocol

from pmx.journal import canonical_json
from pmx.types import (
    MS_PER_DAY,
    MS_PER_MINUTE,
    MS_PER_SECOND,
    SAFETY_LAG_MS_DEFAULT,
    Bar,
    CashEventView,
    HiveView,
    MarketMeta,
    MemoryView,
    NewsView,
    Trade,
    sha256_hex,
)

#: Section 18.7's sensor regex, beside its owning module as ruling R121 requires. The alternation is the
#: contract's own order, which is the reading order of 18.1's table and not the catalogue's key order.
RE_SENSOR = re.compile(
    r"^(tape|microstructure|volume_profile|cross_asset|calendar|wiki_daily|comments|hn|gdelt_recent"
    r"|filings|macro_releases|wiki_asof|hive_insights|hive_reputation|memory)$"
)

#: The declaration document of this catalogue (7.13, ``src/pmx/schemas/sensor.v1.json``).
SENSOR_SCHEMA_VERSION = "sensor.v1"

#: 18.3's two per-source tables. They are contracted to live in ``pmx.types`` (D1), which does not carry
#: them yet: 18.8's first row hands them to DS1 and A1, and until one of those lots lands them S1 keeps a
#: private mirror of 18.3's values so that the derivation of ruling R287 has something to read. The test
#: pins both tables against 18.3 verbatim; the only change the import needs is the ``from`` clause.
_SOURCE_GRANULARITY_MS: Mapping[str, int] = {
    "cboe": MS_PER_DAY,
    "edgar": MS_PER_SECOND,
    "fred": MS_PER_SECOND,
    "gdelt": 15 * MS_PER_MINUTE,
    "hn": MS_PER_SECOND,
    "manifold_comment": 1,
    "wayback": MS_PER_DAY,
    "wikipedia_asof": MS_PER_DAY,
    "wikipedia_current_events": MS_PER_DAY,
}
_SAFETY_LAG_MS_BY_SOURCE: Mapping[str, int] = {
    "cboe": SAFETY_LAG_MS_DEFAULT,
    "edgar": MS_PER_MINUTE,
    "fred": 0,
    "gdelt": 15 * MS_PER_MINUTE,
    "hn": 5 * MS_PER_MINUTE,
    "manifold_comment": MS_PER_MINUTE,
    "wayback": SAFETY_LAG_MS_DEFAULT,
    "wikipedia_asof": SAFETY_LAG_MS_DEFAULT,
    "wikipedia_current_events": SAFETY_LAG_MS_DEFAULT,
}

#: The name prefixes and infix of ruling R285's second clause: a count of how long ago something
#: happened, or how long until it does, reads its ``hi`` when nothing has happened at all.
_ELAPSED_PREFIXES = ("minutes_since_", "bars_since_", "bars_to_")
_ELAPSED_INFIX = "_days_since_"


def sentinel_for(name: str, *, lo: int, hi: int) -> int:
    """The value a feature takes when its input is missing (ruling R285).

    A signed quantity reads ``0`` and never its floor: an unknown gap, return or z score is no gap, and
    the floor of a signed range would read minus one hundred percent over the opening bars of every
    market, which is a constant the miner would find and promote. A count of elapsed or remaining time
    reads its ``hi``: nothing has happened yet is arbitrarily long ago. Everything else reads its ``lo``.
    """
    if lo < 0:
        return 0
    if name.startswith(_ELAPSED_PREFIXES) or _ELAPSED_INFIX in name:
        return hi
    return lo


def derived_granularity_ms(sources: Sequence[str]) -> int:
    """``max(SOURCE_GRANULARITY_MS[s] for s in sources)``, ``0`` without a source (ruling R287)."""
    return max((_SOURCE_GRANULARITY_MS[source] for source in sources), default=0)


def derived_lag_ms(sources: Sequence[str]) -> int:
    """``max(SAFETY_LAG_MS_BY_SOURCE[s] for s in sources)``, ``0`` without a source (ruling R287)."""
    return max((_SAFETY_LAG_MS_BY_SOURCE[source] for source in sources), default=0)


@dataclass(frozen=True, slots=True)
class SensorFeatureSpec:
    """16.5's ``FeatureSpec`` fields plus ``sentinel`` (R285) and ``features_v1_index`` (18.1).

    ``source`` is the sensor's own name and ``asof_only`` is always ``True``: a sensor reads the as-of
    views of 8.3 and nothing else. ``features_v1_index`` is the entry's position in the thirty-seven wide
    ``features.v1`` vector when the feature is one of its fields, and ``None`` otherwise.
    """

    index: int
    name: str
    unit: str
    lo: int
    hi: int
    scale: int
    description: str
    source: str
    sentinel: int
    features_v1_index: int | None
    asof_only: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "name": self.name,
            "unit": self.unit,
            "lo": self.lo,
            "hi": self.hi,
            "scale": self.scale,
            "description": self.description,
            "source": self.source,
            "asof_only": self.asof_only,
            "sentinel": self.sentinel,
            "features_v1_index": self.features_v1_index,
        }


@dataclass(frozen=True, slots=True)
class SensorSpec:
    """One row of the catalogue: what a sensor costs, what it gates, and what its block carries."""

    name: str
    version: str
    cost_units: int
    granularity_ms: int
    lag_ms: int
    sources: tuple[str, ...]
    market_fields: tuple[str, ...]
    observation_fields: tuple[str, ...]
    per_market: bool
    features: tuple[SensorFeatureSpec, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "cost_units": self.cost_units,
            "granularity_ms": self.granularity_ms,
            "lag_ms": self.lag_ms,
            "sources": list(self.sources),
            "market_fields": list(self.market_fields),
            "observation_fields": list(self.observation_fields),
            "per_market": self.per_market,
            "features": [feature.to_dict() for feature in self.features],
        }

    def feature_index(self, name: str) -> int:
        """The position of ``name`` inside this sensor's block."""
        for feature in self.features:
            if feature.name == name:
                return feature.index
        raise KeyError(name)


@dataclass(frozen=True, slots=True)
class SensorBlock:
    """One sensor's integer block for one ``(market, bar)`` or, when ``per_market`` is ``False``, for one
    observation.

    ``market_id`` is ``None`` exactly when ``spec.per_market`` is ``False``, which on the shipped
    catalogue is ``hive_reputation`` and nothing else (ruling R286). ``values`` is one integer per
    ``spec.features`` entry, in block order, each clamped to ``[lo, hi]``.
    """

    sensor: str
    version: str
    market_id: str | None
    values: tuple[int, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "sensor": self.sensor,
            "version": self.version,
            "market_id": self.market_id,
            "values": list(self.values),
        }


class SensorInputsLike(Protocol):
    """The read side of 12.11's ``SensorInputs``: what a ``sense`` body of 18.1 may read and nothing else.

    ``SensorInputs`` itself is contracted to ``pmx.types`` (D1) and 18.8's ruling R278 row hands it to a
    later lot, so S1 codes against this structural protocol, in the idiom section 13 already uses for
    ``InstrumentLike``, ``MemoryLike`` and ``HiveLike``. The field list, the names, the types and the
    order are 12.11's verbatim, so D1's frozen dataclass satisfies this protocol on the day it lands and
    no ``sense`` body changes: only the annotation does.
    """

    @property
    def meta(self) -> MarketMeta: ...

    @property
    def bars(self) -> tuple[Bar, ...]: ...

    @property
    def quotes(self) -> tuple[int, int] | None: ...

    @property
    def trades(self) -> tuple[Trade, ...]: ...

    @property
    def news(self) -> Mapping[str, tuple[NewsView, ...]]: ...

    @property
    def cash_events(self) -> tuple[CashEventView, ...]: ...

    @property
    def hive(self) -> HiveView | None: ...

    @property
    def memory(self) -> MemoryView | None: ...

    @property
    def peers(self) -> Mapping[str, tuple[Bar, ...]]: ...

    @property
    def research(self) -> Mapping[str, object]: ...


def block_of(spec: SensorSpec, market_id: str | None, values: Sequence[int | None]) -> SensorBlock:
    """The one implementation of the block rule of 18.1, shared by the fifteen ``sense`` bodies.

    ``None`` in ``values`` is a **missing input** and takes ``spec.sentinel`` and nothing else; every
    other value is clamped to its feature's ``[lo, hi]``. Writing the substitution once is what keeps
    fifteen modules from each spelling the sentinel rule slightly differently.
    """
    if len(values) != len(spec.features):
        raise ValueError(f"{spec.name}: {len(values)} values for {len(spec.features)} features")
    resolved: list[int] = []
    for feature, value in zip(spec.features, values, strict=True):
        if value is None:
            resolved.append(feature.sentinel)
        else:
            resolved.append(max(feature.lo, min(feature.hi, value)))
    return SensorBlock(
        sensor=spec.name,
        version=spec.version,
        market_id=market_id if spec.per_market else None,
        values=tuple(resolved),
    )


def ln1p_milli(value: int) -> int:
    """``ln(1 + value)`` in milli-nats, integer and platform stable (1.3).

    ``math.log`` reaches the platform libm and is not bit identical across glibc, msvcrt and macOS, so it
    never touches a feature a rule is mined on. ``Decimal.ln`` is correctly rounded by the decimal
    specification, exactly as ``pmx.types.neg_ln_micronats`` is; a non-positive argument reads ``0``.
    """
    if value <= 0:
        return 0
    with localcontext() as ctx:
        ctx.prec = 40
        result = Decimal(1 + value).ln() * Decimal(1_000)
        return int(result.to_integral_value(rounding=ROUND_HALF_UP))


# The table below is the fixture's, field for field. ``index``, ``source``, ``asof_only``, ``sentinel``,
# ``granularity_ms`` and ``lag_ms`` are derived from it, so none of the six can drift by a typo.
# Row: (name, version, cost_units, per_market, sources, market_fields, observation_fields, features)
# Feature: (name, unit, lo, hi, scale, features_v1_index, description)
_FeatureRow = tuple[str, str, int, int, int, int | None, str]
_SensorRow = tuple[str, str, int, bool, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[_FeatureRow, ...]]

_CATALOGUE_TABLE: tuple[_SensorRow, ...] = (
    (
        "calendar", "calendar.v1", 0, True,
        (),
        ("close_at_ms", "hours_to_next_bar", "session_calendar_id"),
        (),
        (
            ("bars_to_close", "count", 0, 100000, 1, 14,
             "Bars from now_ms to close_at_ms; close_at_ms is public on every venue."),
            ("ms_to_close_log_milli", "milli", 0, 30000, 1000, 15,
             "ln(1 + close_at_ms - now_ms), in milli-nats."),
            ("bars_since_listed", "count", 0, 100000, 1, 16,
             "Completed bars since the market was listed."),
            ("day_of_week", "index", 0, 6, 1, 17,
             "Day of week of now_ms, Monday is 0."),
            ("hour_of_day", "index", 0, 23, 1, 18,
             "Hour of day of now_ms in UTC."),
            ("hours_to_next_bar", "count", 0, 100000, 1, None,
             "Whole hours from now_ms to the instrument's next bar open on its session calendar, 0 on a continuous "
             "calendar."),
            ("session_close_within_1b", "flag", 0, 1, 1, None,
             "1 when the next bar is the last of the session (is_session_close), else 0."),
        ),
    ),
    (
        "comments", "comments.v1", 1, True,
        ("manifold_comment",),
        ("news",),
        ("news",),
        (
            ("comment_count_1b", "count", 0, 100000, 1, None,
             "Manifold comments on this market visible at now_ms and published in the last completed bar."),
            ("comment_count_24b", "count", 0, 100000, 1, None,
             "Manifold comments visible at now_ms and published in the last twenty-four completed bars."),
            ("commenter_count_24b", "count", 0, 100000, 1, None,
             "Distinct author_key values among those comments."),
            ("minutes_since_comment", "count", 0, 100000, 1, None,
             "Whole minutes from the most recent visible comment to now_ms; 100000 when none is visible."),
        ),
    ),
    (
        "cross_asset", "cross_asset.v1", 1, True,
        (),
        ("twins", "underlying_id"),
        (),
        (
            ("cluster_gap_bp", "bp", -10000, 10000, 10000, 27,
             "This market's last price minus its as-of cluster peers' mean last price."),
            ("cluster_peer_count", "count", 0, 64, 1, 28,
             "Members of this market's as-of cluster other than itself."),
            ("constraint_residual_ppm", "ppm", -1000000, 1000000, 1000000, 29,
             "Residual of the as-of constraint this market sits in, 0 when none."),
            ("constraint_count", "count", 0, 64, 1, 30,
             "As-of constraints this market sits in."),
            ("twins_count", "count", 0, 64, 1, None,
             "Twins of this market (the same event on another venue) listed at now_ms."),
            ("underlying_ret_1b_bp", "bp", -10000, 10000, 10000, None,
             "Last-bar return of the underlying instrument in bp_ratio, 0 when the market has none."),
        ),
    ),
    (
        "filings", "filings.v1", 2, True,
        ("edgar",),
        ("news",),
        ("news",),
        (
            ("filings_30b", "count", 0, 1000, 1, None,
             "EDGAR filings linked to this instrument's issuer, visible at now_ms and accepted in the last thirty "
             "completed bars."),
            ("filings_8k_30b", "count", 0, 1000, 1, None,
             "Of those, the current reports (form 8-K)."),
            ("minutes_since_filing", "count", 0, 100000, 1, None,
             "Whole minutes from the most recent visible linked filing's acceptance time to now_ms; 100000 when none "
             "is visible."),
        ),
    ),
    (
        "gdelt_recent", "gdelt_recent.v1", 2, True,
        ("gdelt",),
        ("news",),
        ("news",),
        (
            ("gdelt_articles_1b", "count", 0, 100000, 1, None,
             "GDELT articles linked to this market, visible at now_ms and seen in the last completed bar."),
            ("gdelt_articles_24b", "count", 0, 100000, 1, None,
             "Linked GDELT articles visible at now_ms and seen in the last twenty-four completed bars."),
            ("gdelt_domains_24b", "count", 0, 100000, 1, None,
             "Distinct source domains among those articles."),
            ("minutes_since_article", "count", 0, 100000, 1, None,
             "Whole minutes from the most recent visible linked article's seendate to now_ms; 100000 when none is "
             "visible."),
        ),
    ),
    (
        "hive_insights", "hive_insights.v1", 1, True,
        (),
        (),
        ("hive.forecasts", "hive.insights", "hive.lessons", "hive.prev_bar_forecasts", "hive.resolutions"),
        (
            ("insights_firing", "count", 0, 50, 1, None,
             "Promoted, undemoted insights whose rule fires on this market at now_ms (HiveView.insights)."),
            ("insight_best_lower_bp", "bp", 0, 10000, 10000, None,
             "Largest lower_bp among the firing insights, 0 when none fires."),
            ("insight_lift_up_bp", "bp", 0, 100000, 10000, None,
             "Sum of lift_bp over the firing insights whose claim direction is +1, 0 when none."),
            ("insight_lift_down_bp", "bp", 0, 100000, 10000, None,
             "Sum of lift_bp over the firing insights whose claim direction is -1, 0 when none."),
            ("lessons_visible", "count", 0, 1000, 1, None,
             "Hive lessons visible at now_ms for this market's category."),
            ("peer_forecasts_visible", "count", 0, 1000, 1, None,
             "Other agents' forecasts on this market visible at now_ms (forecasts and prev_bar_forecasts)."),
        ),
    ),
    (
        "hive_reputation", "hive_reputation.v1", 1, False,
        (),
        (),
        ("hive.reputations",),
        (
            ("peer_reputations", "count", 0, 1000, 1, None,
             "Reputation entries visible at now_ms (HiveView.reputations)."),
            ("peers_positive_reputation", "count", 0, 1000, 1, None,
             "Of those, the peers whose reputation is positive."),
            ("peers_negative_reputation", "count", 0, 1000, 1, None,
             "Of those, the peers whose reputation is negative."),
        ),
    ),
    (
        "hn", "hn.v1", 2, True,
        ("hn",),
        ("news",),
        ("news",),
        (
            ("hn_story_points", "count", 0, 100000, 1, None,
             "Highest points among the Hacker News stories linked to this market and visible at now_ms within the "
             "last 1440 minutes, 0 when none."),
            ("hn_story_comments", "count", 0, 100000, 1, None,
             "Comment count of that story, 0 when none."),
            ("hn_mentions_subject", "flag", 0, 1, 1, None,
             "1 when a visible linked story names one of the market's wiki_subjects through the linker, else 0."),
            ("minutes_since_story", "count", 0, 100000, 1, None,
             "Whole minutes from the most recent visible linked story to now_ms; 100000 when none is visible."),
            ("hn_stories_24h", "count", 0, 100000, 1, None,
             "Linked stories visible at now_ms and published in the last 1440 minutes."),
        ),
    ),
    (
        "macro_releases", "macro_releases.v1", 1, True,
        ("cboe", "fred"),
        ("news",),
        ("news",),
        (
            ("bars_to_next_release", "count", 0, 100000, 1, None,
             "Bars from now_ms to the next scheduled release of a series linked to this market; 100000 when none is "
             "scheduled."),
            ("bars_since_last_release", "count", 0, 100000, 1, None,
             "Bars since the most recent visible release of a linked series; 100000 when none is visible."),
            ("release_revision_abs_bp", "bp", 0, 100000, 10000, None,
             "Absolute revision of the latest visible vintage against the previous vintage of the same observation, "
             "in bp of the previous value; 0 when none or fewer than two vintages."),
            ("vix_last_milli", "milli", 0, 1000000, 1000, None,
             "The last visible VIX close times 1000, 0 when the dataset carries no cboe release."),
        ),
    ),
    (
        "memory", "memory.v1", 0, True,
        (),
        (),
        ("memory",),
        (
            ("memory_n_resolved", "count", 0, 1000000, 1, None,
             "The agent's own resolved forecasts recorded in its memory at now_ms."),
            ("memory_category_n", "count", 0, 1000000, 1, None,
             "Of those, the ones in this market's category."),
            ("memory_category_hits_permille", "permille", 0, 1000, 1000, None,
             "Share of the category's resolved forecasts that were on the right side of 500000 ppm, 0 when none."),
            ("memory_market_forecasts", "count", 0, 100000, 1, None,
             "The agent's own earlier forecasts on this market recorded in its memory."),
        ),
    ),
    (
        "microstructure", "microstructure.v1", 1, True,
        (),
        ("bars.yes_ask_bp", "bars.yes_bid_bp", "best_ask_bp", "best_bid_bp", "trades"),
        (),
        (
            ("spread_bp", "bp", 0, 10000, 10000, 2,
             "best_ask_bp minus best_bid_bp of the last completed bar, 0 when unknown."),
            ("mid_minus_last_bp", "bp", -10000, 10000, 10000, None,
             "Mid of best_bid_bp and best_ask_bp minus last_price_bp, 0 when either quote is unknown."),
            ("prints_10b", "count", 0, 100000, 1, None,
             "Prints (trades) in the last ten completed bars, 0 when the tape carries no prints."),
        ),
    ),
    (
        "tape", "tape.v1", 0, True,
        (),
        (
            "bars.close_bp",
            "bars.high_bp",
            "bars.low_bp",
            "bars.open_bp",
            "bars.t_ms",
            "bars.vwap_bp",
            "first_price_bp",
            "last_price_bp",
        ),
        (),
        (
            ("last_price_bp", "bp", 0, 10000, 10000, 0,
             "Close of the last completed bar, else first_price_bp."),
            ("logit_last_milli", "milli", -50000, 50000, 1000, 1,
             "logit_milli of last_price_bp."),
            ("ret_1b_bp", "bp", -10000, 10000, 10000, 3,
             "Price change over the last completed bar."),
            ("ret_7b_bp", "bp", -10000, 10000, 10000, 4,
             "Price change over the last seven completed bars."),
            ("ret_30b_bp", "bp", -10000, 10000, 10000, 5,
             "Price change over the last thirty completed bars."),
            ("ret_90b_bp", "bp", -10000, 10000, 10000, 6,
             "Price change over the last ninety completed bars."),
            ("realised_vol_bp_30b", "bp", 0, 10000, 10000, 7,
             "Mean absolute bar return over the last thirty completed bars."),
            ("dist_from_high_bp_30b", "bp", 0, 10000, 10000, 8,
             "Last price minus the highest close of the last thirty bars."),
            ("dist_from_low_bp_30b", "bp", 0, 10000, 10000, 9,
             "Last price minus the lowest close of the last thirty bars."),
            ("provider_index", "index", 0, 4, 1, 19,
             "Index into the provider list of CONTRACTS_V2 section 2."),
            ("category_index", "index", 0, 11, 1, 20,
             "Index into pmx.types.CATEGORIES."),
        ),
    ),
    (
        "volume_profile", "volume_profile.v1", 1, True,
        (),
        (
            "bars.n_trades",
            "bars.open_interest",
            "bars.volume_milli",
            "cash_events",
            "n_trades_to_date",
            "volume_milli_7d",
            "volume_milli_to_date",
        ),
        (),
        (
            ("volume_milli_1b_log_milli", "milli", 0, 30000, 1000, 10,
             "ln(1 + volume_milli) of the last completed bar, in milli-nats."),
            ("volume_milli_z_milli_30b", "milli", -10000, 10000, 1000, 11,
             "Last bar volume as a z score over the last thirty bars."),
            ("volume_milli_to_date_log_milli", "milli", 0, 30000, 1000, 12,
             "ln(1 + volume_milli_to_date), in milli-nats."),
            ("n_trades_to_date_log_milli", "milli", 0, 30000, 1000, 13,
             "ln(1 + n_trades_to_date), in milli-nats."),
            ("open_interest_log_milli", "milli", 0, 30000, 1000, None,
             "ln(1 + open_interest) of the last completed bar, in milli-nats, 0 when unknown."),
            ("cash_events_30b", "count", 0, 1000, 1, None,
             "Cash events applied to this instrument in the last thirty completed bars (funding, dividends, splits, "
             "rolls, borrow, carry)."),
        ),
    ),
    (
        "wiki_asof", "wiki_asof.v1", 3, True,
        ("wikipedia_asof",),
        (),
        ("research",),
        (
            ("wiki_asof_revisions_granted", "count", 0, 1000, 1, None,
             "Point-in-time revisions of the market's subjects in the agent's granted requests, visible at now_ms."),
            ("wiki_asof_days_since_revision", "count", 0, 100000, 1, None,
             "Whole days from the most recent granted revision to now_ms; 100000 when none is granted."),
            ("wiki_asof_text_delta_permille", "permille", 0, 1000, 1000, None,
             "Share of the latest granted revision's tokens absent from the previous one, 0 when fewer than two "
             "revisions are granted."),
        ),
    ),
    (
        "wiki_daily", "wiki_daily.v1", 1, True,
        ("wayback", "wikipedia_current_events"),
        ("news",),
        ("news",),
        (
            ("news_count_1d", "count", 0, 1000, 1, 21,
             "News items visible at now_ms linked to this market in the last day."),
            ("news_count_7d", "count", 0, 1000, 1, 22,
             "News items visible at now_ms linked to this market in the last seven days."),
            ("news_direction_milli_7d", "milli", -1000, 1000, 1000, 23,
             "Lexicon direction score over the seven-day window."),
            ("news_intensity_milli_7d", "milli", 0, 1000, 1000, 24,
             "Lexicon intensity score over the seven-day window."),
            ("news_novelty_milli_7d", "milli", 0, 1000, 1000, 25,
             "Novelty of the window against the previous seven days."),
            ("news_match_score_permille_max", "permille", 0, 1000, 1000, 26,
             "Best link score among the visible items."),
        ),
    ),
)


def _spec_of(row: _SensorRow) -> SensorSpec:
    name, version, cost_units, per_market, sources, market_fields, observation_fields, features = row
    return SensorSpec(
        name=name,
        version=version,
        cost_units=cost_units,
        granularity_ms=derived_granularity_ms(sources),
        lag_ms=derived_lag_ms(sources),
        sources=sources,
        market_fields=market_fields,
        observation_fields=observation_fields,
        per_market=per_market,
        features=tuple(
            SensorFeatureSpec(
                index=index,
                name=feature_name,
                unit=unit,
                lo=lo,
                hi=hi,
                scale=scale,
                description=description,
                source=name,
                sentinel=sentinel_for(feature_name, lo=lo, hi=hi),
                features_v1_index=features_v1_index,
            )
            for index, (feature_name, unit, lo, hi, scale, features_v1_index, description) in enumerate(features)
        ),
    )


#: The catalogue, keys sorted. It is closed: fifteen rows and no sixteenth.
SENSORS: Mapping[str, SensorSpec] = {row[0]: _spec_of(row) for row in sorted(_CATALOGUE_TABLE, key=lambda r: r[0])}

#: ``tuple(sorted(SENSORS))``: the resolved sensor set of a genome that bought everything (ruling R231).
SENSOR_NAMES: tuple[str, ...] = tuple(sorted(SENSORS))

#: What a run records (18.1): ``sha256(canonical_json([spec.to_dict() for spec in SENSORS.values()]))``.
CATALOGUE_HASH: str = sha256_hex(canonical_json([spec.to_dict() for spec in SENSORS.values()]).encode("utf-8"))

#: The source-to-sensor map the news gate of ruling R233 applies: an item reaches a view only when the
#: diet bought the sensor that reads its source. Every source of the catalogue appears exactly once,
#: which the test asserts, so the map is a function and no item is bought twice.
SENSOR_BY_NEWS_SOURCE: Mapping[str, str] = {source: spec.name for spec in SENSORS.values() for source in spec.sources}

#: The full diet's cost per bar (18.1). ``SENSOR_BUDGET_UNITS_DEFAULT`` is this plus
#: ``RULE_PROPOSAL_COST_UNITS`` (ruling R281) and belongs to ``pmx.types`` (D1), so it is not spelled here.
FULL_DIET_COST_UNITS: int = sum(spec.cost_units for spec in SENSORS.values())
