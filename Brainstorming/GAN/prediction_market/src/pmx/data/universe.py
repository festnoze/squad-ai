"""The documented universe rule: which Kalshi series a build takes, stated over series and reported.

Decision D-R13 and ruling R258 (CONTRACTS_V2 7.4): **the series list is an output of the builder, not an
input**. The 731 series of the first build were picked by hand and were category-biased, and a universe a
reader cannot recompute is not a denominator. So the rule is arithmetic over the settled walk: every
series with at least ``universe_min_settled`` settled markets inside the window and at least
``universe_min_volume_cents`` of volume, counted from the series' own markets, with the count before and
after each filter written into the manifest's ``universe`` block (7.8).

Why the rule is stated over **series** and never over markets, which is not a style choice
(``docs/MEASURE_2026-09-09_KALSHI_UNIVERSE.md``, measured against the live public API on 2026-09-09):

* the settled listing holds at least 60 000 markets inside the one-year window, so the market count is
  not the constraint;
* the median market life in those 60 000 is 0.04 days and **not one of them lives a week**, so a
  market-level newest-first walk is saturated by the auto-generated shards of 7.4 and cannot find the
  tradable universe at any budget;
* ``GET /trade-api/v2/series`` answers without credentials and returns 13 917 series, which is what makes
  a series-driven rule buildable at all.

Nothing here opens a socket, reads a clock or draws a random number: the rule is a pure function of the
rows the builder already holds, so two builds over the same staged markets list the same universe and the
manifest block is evidence rather than a claim.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from pmx.errors import InvalidConfigError

__all__ = [
    "CONTRACT_SETTLEMENT_CENTS",
    "MILLI_PER_CONTRACT",
    "RE_KALSHI_SERIES",
    "RE_SERIES_LIST_ENTRY",
    "SERIES_LIST_SEPARATORS",
    "WEATHER_CATEGORY",
    "WEATHER_SERIES_LABEL",
    "MarketUniverseRow",
    "SeriesStat",
    "UniverseReport",
    "UniverseRule",
    "notional_cents_of",
    "read_series_list",
    "render_series_list",
    "series_of",
    "universe_of",
]

#: A Kalshi series ticker is the prefix of a market ticker before the first dash (7.4, the same reading
#: the ``kalshi_shards`` filter and the series-to-category map of ruling R170 use). It is also the
#: pattern ``dataset.v1.json`` pins on ``universe.series[].series``, so every row this module produces
#: satisfies the schema by construction.
RE_KALSHI_SERIES: Final = re.compile(r"^[A-Z0-9]{1,32}$")

#: What a **list file** may hold, which is deliberately wider. The list the first build shipped carries
#: entries such as ``BTCD-B``: the exchange honours a narrowing that is not the bare prefix, and a reader
#: that refused one would refuse the file the rebuild starts from. Entries are kept verbatim, because
#: what the file is for is being passed back to the provider as ``series_ticker`` (ruling R100), and
#: reducing ``BTCD-B`` to ``BTCD`` would silently ask for a different thing.
RE_SERIES_LIST_ENTRY: Final = re.compile(r"^[A-Z0-9][A-Z0-9-]{0,31}$")

#: ``data/datasets/y2026/kalshi_series.txt`` as it exists today is **one single comma-separated line**,
#: not one ticker per line (``docs/MEASURE_2026-09-09_KALSHI_UNIVERSE.md`` section 4.2): a reader that
#: splits on newlines passes the whole file as one ticker and gets zero markets back, silently. The
#: reader here therefore splits on both, and :func:`render_series_list` normalises the file to one ticker
#: per line now that the list is a build output.
SERIES_LIST_SEPARATORS: Final = (",", "\n", "\r", "\t", " ")

#: A weather series is kept and labelled rather than dropped (7.4): its outcome is forecastable from a
#: public numerical model, which is a property a reader must be able to see on the market and not a
#: reason to hide the market. The label is a builder label of the controlled vocabulary of 7.14.
WEATHER_SERIES_LABEL: Final = "forecastable_from_public_models"

#: The category of section 2 that names a weather series in D2's sealed series-to-category map.
WEATHER_CATEGORY: Final = "weather"

#: A binary contract settles at one dollar, which is one hundred cents.
CONTRACT_SETTLEMENT_CENTS: Final = 100

#: ``volume_milli`` counts contracts times one thousand (7.2).
MILLI_PER_CONTRACT: Final = 1_000


def notional_cents_of(volume_milli: int) -> int:
    """Traded volume in cents at the contract's settlement value: ``volume_milli * 100 // 1000``.

    Section 7.4 states the universe rule's volume bar in cents (``universe_min_volume_cents``) while a
    market's tape counts contracts in ``volume_milli`` (7.2), so the two meet here, once, with the
    conversion written down instead of inlined at a call site. A binary contract settles at one dollar,
    so a contract traded is at most one dollar of notional and this is the exchange's own "volume in
    dollars" reading of a contract count. It is an **upper bound** on the cash that changed hands (a
    contract that traded at 30 cents moved 30 cents, not 100), which is the safe direction for a bar a
    series must clear to enter the universe: no series enters on a volume it did not have.
    """
    if volume_milli < 0:
        raise InvalidConfigError("volume_milli must not be negative", volume_milli=volume_milli)
    return volume_milli * CONTRACT_SETTLEMENT_CENTS // MILLI_PER_CONTRACT


def series_of(provider_id: str) -> str:
    """The series ticker of a provider market id: the prefix before the first dash, upper case.

    ``KXCPI-26-B`` is series ``KXCPI``. A provider id with no dash is its own series. The upper case is
    the exchange's spelling and is what D2's sealed maps are keyed on.
    """
    return provider_id.split("-", 1)[0].strip().upper()


def read_series_list(text: str) -> tuple[str, ...]:
    """The series of a list file, sorted and unique, whatever separator the file happens to use.

    The correction of ``docs/MEASURE_2026-09-09_KALSHI_UNIVERSE.md`` section 4.2 lives here: the file
    shipped by the first build is one comma-separated line, so a reader that splits on newlines alone
    passes 731 tickers as one ticker and asks the exchange for a series that does not exist. Splitting on
    every separator the file could plausibly use costs nothing and turns a silent zero into a list.
    """
    normalised = text
    for separator in SERIES_LIST_SEPARATORS:
        normalised = normalised.replace(separator, "\n")
    found = {part.strip().upper() for part in normalised.split("\n") if part.strip()}
    unknown = sorted(item for item in found if RE_SERIES_LIST_ENTRY.fullmatch(item) is None)
    if unknown:
        raise InvalidConfigError("a series list holds something that is not a series ticker", found=unknown)
    return tuple(sorted(found))


def render_series_list(series: Iterable[str]) -> str:
    """The list file as a build output: one ticker per line, sorted, with a trailing newline."""
    return "".join(f"{ticker}\n" for ticker in read_series_list("\n".join(series)))


@dataclass(frozen=True, slots=True)
class UniverseRule:
    """The two bars of 7.4, as the manifest's ``universe.rule`` block states them."""

    min_settled: int
    min_volume_cents: int

    def __post_init__(self) -> None:
        if self.min_settled < 0:
            raise InvalidConfigError("universe_min_settled must not be negative", value=self.min_settled)
        if self.min_volume_cents < 0:
            raise InvalidConfigError(
                "universe_min_volume_cents must not be negative", value=self.min_volume_cents
            )

    def admits(self, stat: SeriesStat) -> bool:
        return stat.n_settled >= self.min_settled and stat.volume_cents >= self.min_volume_cents

    def to_dict(self) -> dict[str, object]:
        return {"min_settled": self.min_settled, "min_volume_cents": self.min_volume_cents}


@dataclass(frozen=True, slots=True)
class MarketUniverseRow:
    """One settled market of the walk, reduced to what the universe rule reads.

    ``kept`` is whether the quality filters of 7.4 kept it, which is the "after" of the counts the
    manifest reports; the rule itself is decided on the "before", because a series with a hundred settled
    markets is a real series whatever this build's density bar did to it.
    """

    series: str
    volume_cents: int
    kept: bool


@dataclass(frozen=True, slots=True)
class SeriesStat:
    """One row of ``manifest.universe.series`` (7.8): a series with its counts, its volume and its labels."""

    series: str
    n_settled: int
    n_kept: int
    volume_cents: int
    labels: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "series": self.series,
            "n_settled": self.n_settled,
            "n_kept": self.n_kept,
            "volume_cents": self.volume_cents,
            "labels": list(self.labels),
        }


@dataclass(frozen=True, slots=True)
class UniverseReport:
    """``manifest.universe`` (7.8, ruling R258): the rule, every series it saw, and the two counts.

    ``series`` holds **every** series of the walk and not only the survivors, sorted by ticker, because
    the point of the block is that a reader can recompute the rule: the rejected rows are the denominator
    the accepted rows are a share of.
    """

    rule: UniverseRule
    series: tuple[SeriesStat, ...]
    n_series_before: int
    n_series_after: int

    @property
    def passing(self) -> tuple[SeriesStat, ...]:
        """The series the rule admits, in ticker order: what the next build passes as ``series_ticker``."""
        return tuple(stat for stat in self.series if self.rule.admits(stat))

    @property
    def series_tickers(self) -> tuple[str, ...]:
        return tuple(stat.series for stat in self.passing)

    @property
    def n_markets_kept(self) -> int:
        """Kept markets inside the admitted series: the market count the cohort target of 7.4 is read on."""
        return sum(stat.n_kept for stat in self.passing)

    def to_dict(self) -> dict[str, object]:
        return {
            "rule": self.rule.to_dict(),
            "series": [stat.to_dict() for stat in self.series],
            "n_series_before": self.n_series_before,
            "n_series_after": self.n_series_after,
        }


def universe_of(
    rows: Sequence[MarketUniverseRow],
    *,
    rule: UniverseRule,
    series_categories: Mapping[str, str] = {},
) -> UniverseReport:
    """The universe rule of 7.4 applied to the settled walk: the block the manifest carries.

    ``series_categories`` is D2's sealed series-to-category map (ruling R170), read by the caller and
    passed in for the reason the excluded-series list is: the builder never imports a provider's
    importer. It is used for one thing here, the weather label of 7.4: a series the map calls
    ``weather`` is **kept** and carries :data:`WEATHER_SERIES_LABEL`, because its outcome is forecastable
    from a public numerical model and a reader must see that on the market rather than have the market
    quietly removed.
    """
    settled: dict[str, int] = {}
    kept: dict[str, int] = {}
    volume: dict[str, int] = {}
    for row in rows:
        ticker = row.series.strip().upper()
        if RE_KALSHI_SERIES.fullmatch(ticker) is None:
            raise InvalidConfigError("a universe row carries something that is not a series", series=row.series)
        if row.volume_cents < 0:
            raise InvalidConfigError("a universe row carries a negative volume", series=ticker)
        settled[ticker] = settled.get(ticker, 0) + 1
        kept[ticker] = kept.get(ticker, 0) + (1 if row.kept else 0)
        volume[ticker] = volume.get(ticker, 0) + row.volume_cents
    categories = {series.strip().upper(): value for series, value in series_categories.items()}
    stats = tuple(
        SeriesStat(
            series=ticker,
            n_settled=settled[ticker],
            n_kept=kept[ticker],
            volume_cents=volume[ticker],
            labels=(WEATHER_SERIES_LABEL,) if categories.get(ticker) == WEATHER_CATEGORY else (),
        )
        for ticker in sorted(settled)
    )
    return UniverseReport(
        rule=rule,
        series=stats,
        n_series_before=len(stats),
        n_series_after=sum(1 for stat in stats if rule.admits(stat)),
    )
