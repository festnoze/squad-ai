"""DS1: the documented universe rule of section 7.4 (decision D-R13, ruling R258).

Every test here is offline and reads no network: the rule is a pure function of the rows the builder
already holds, which is the whole point of moving the series list from a hand-picked input to a build
output. The fixtures are recorded shapes, not live answers, and
``docs/MEASURE_2026-09-09_KALSHI_UNIVERSE.md`` is where the live measurement that decided the rule's
shape lives.

The two corrections that measurement forced are each pinned by a test below: the series list file that
shipped with the first build is **one comma-separated line**, so a reader that splits on newlines gets
one bogus ticker and zero markets; and the rule has to be stated over series rather than over markets,
because not one of sixty thousand settled markets in the window lives a week.
"""

from __future__ import annotations

import pytest

from pmx.data.builder import (
    UNIVERSE_MIN_SETTLED_DEFAULT,
    UNIVERSE_MIN_VOLUME_CENTS_DEFAULT,
    universe_of_facts,
)
from pmx.data.universe import (
    WEATHER_SERIES_LABEL,
    MarketUniverseRow,
    SeriesStat,
    UniverseRule,
    notional_cents_of,
    read_series_list,
    render_series_list,
    series_of,
    universe_of,
)
from pmx.errors import InvalidConfigError

RULE = UniverseRule(min_settled=3, min_volume_cents=1_000)


def rows(*specs: tuple[str, int, bool]) -> list[MarketUniverseRow]:
    return [
        MarketUniverseRow(series=series, volume_cents=volume, kept=kept) for series, volume, kept in specs
    ]


# --------------------------------------------------------------------------------------------------
# The series ticker and the two unit conversions
# --------------------------------------------------------------------------------------------------
def test_the_series_is_the_ticker_prefix_before_the_first_dash() -> None:
    assert series_of("KXCPI-26-B") == "KXCPI"
    assert series_of("kxcpi-26-b") == "KXCPI"  # the exchange's spelling is upper case
    assert series_of("KXBTC") == "KXBTC"  # no dash: the market is its own series
    assert series_of(" KXFED-26-C ") == "KXFED"


def test_volume_in_cents_is_the_contract_count_at_the_settlement_value() -> None:
    """``volume_milli`` counts contracts times a thousand; a binary settles at one dollar (7.2, 7.4)."""
    assert notional_cents_of(1_000) == 100  # one contract, one dollar
    assert notional_cents_of(0) == 0
    assert notional_cents_of(1_234_567) == 123_456  # integer division, never a float and never rounded up
    with pytest.raises(InvalidConfigError):
        notional_cents_of(-1)


# --------------------------------------------------------------------------------------------------
# The rule
# --------------------------------------------------------------------------------------------------
def test_a_series_enters_on_both_bars_and_neither_bar_alone_is_enough() -> None:
    report = universe_of(
        rows(
            # three settled, plenty of volume: in
            ("KXCPI", 400, True), ("KXCPI", 400, True), ("KXCPI", 400, False),
            # three settled, not enough volume: out
            ("KXTHIN", 100, True), ("KXTHIN", 100, True), ("KXTHIN", 100, True),
            # heavy volume, only two settled: out
            ("KXONE", 90_000, True), ("KXONE", 90_000, True),
        ),
        rule=RULE,
    )
    assert report.n_series_before == 3
    assert report.n_series_after == 1
    assert report.series_tickers == ("KXCPI",)
    assert [stat.series for stat in report.series] == ["KXCPI", "KXONE", "KXTHIN"]  # sorted, all of them


def test_the_counts_are_before_and_after_the_quality_filters_and_the_rule_reads_the_before() -> None:
    """7.4: a series with enough settled markets is a real series whatever this build's density bar did."""
    report = universe_of(
        rows(("KXCPI", 500, False), ("KXCPI", 500, False), ("KXCPI", 500, True)), rule=RULE
    )
    stat = report.series[0]
    assert (stat.n_settled, stat.n_kept, stat.volume_cents) == (3, 1, 1_500)
    assert report.n_series_after == 1  # decided on n_settled == 3, not on n_kept == 1
    assert report.n_markets_kept == 1


def test_a_weather_series_is_kept_and_labelled_rather_than_dropped() -> None:
    report = universe_of(
        rows(("KXHIGHNY", 900, True), ("KXHIGHNY", 900, True), ("KXHIGHNY", 900, True),
             ("KXCPI", 900, True), ("KXCPI", 900, True), ("KXCPI", 900, True)),
        rule=RULE,
        series_categories={"KXHIGHNY": "weather", "KXCPI": "economics"},
    )
    labels = {stat.series: stat.labels for stat in report.series}
    assert labels["KXHIGHNY"] == (WEATHER_SERIES_LABEL,)
    assert labels["KXCPI"] == ()
    assert "KXHIGHNY" in report.series_tickers  # kept, not dropped


def test_the_manifest_block_is_the_shape_section_7_8_states() -> None:
    report = universe_of(rows(("KXCPI", 5_000, True)), rule=RULE)
    block = report.to_dict()
    assert set(block) == {"rule", "series", "n_series_before", "n_series_after"}
    assert block["rule"] == {"min_settled": 3, "min_volume_cents": 1_000}
    assert block["series"] == [
        {"series": "KXCPI", "n_settled": 1, "n_kept": 1, "volume_cents": 5_000, "labels": []}
    ]
    assert (block["n_series_before"], block["n_series_after"]) == (1, 0)


def test_the_rule_is_a_pure_function_of_the_rows_and_not_of_their_order() -> None:
    specs = (("KXA", 900, True), ("KXB", 4_000, True), ("KXA", 900, False), ("KXB", 4_000, True))
    first = universe_of(rows(*specs), rule=RULE)
    second = universe_of(rows(*reversed(specs)), rule=RULE)
    assert first.to_dict() == second.to_dict()


def test_a_malformed_row_is_refused_rather_than_counted() -> None:
    with pytest.raises(InvalidConfigError):
        universe_of(rows(("KX CPI", 10, True)), rule=RULE)
    with pytest.raises(InvalidConfigError):
        universe_of(rows(("KXCPI", -1, True)), rule=RULE)
    with pytest.raises(InvalidConfigError):
        UniverseRule(min_settled=-1, min_volume_cents=0)
    with pytest.raises(InvalidConfigError):
        UniverseRule(min_settled=0, min_volume_cents=-1)


def test_the_rule_admits_exactly_at_the_bar_and_not_below_it() -> None:
    stat = SeriesStat(series="KXCPI", n_settled=3, n_kept=3, volume_cents=1_000)
    assert RULE.admits(stat) is True
    assert RULE.admits(SeriesStat(series="KXCPI", n_settled=2, n_kept=2, volume_cents=1_000)) is False
    assert RULE.admits(SeriesStat(series="KXCPI", n_settled=3, n_kept=3, volume_cents=999)) is False


# --------------------------------------------------------------------------------------------------
# The series list file: the measurement's second correction
# --------------------------------------------------------------------------------------------------
def test_a_comma_separated_series_file_reads_as_its_tickers_and_not_as_one() -> None:
    """``data/datasets/y2026/kalshi_series.txt`` is one comma-separated line, not one ticker per line.

    A reader that splits on newlines passes the whole file to the exchange as a single ``series_ticker``
    and gets zero markets back, silently, which is what happened on the first attempt of the measurement
    (``docs/MEASURE_2026-09-09_KALSHI_UNIVERSE.md`` section 4.2).
    """
    assert read_series_list("KXCPI,KXFED,KXBTC") == ("KXBTC", "KXCPI", "KXFED")
    assert read_series_list("KXCPI\nKXFED\nKXBTC\n") == ("KXBTC", "KXCPI", "KXFED")
    assert read_series_list("KXCPI, KXFED\nKXBTC KXGOLD\t") == ("KXBTC", "KXCPI", "KXFED", "KXGOLD")
    assert read_series_list("  \n , \n") == ()


def test_the_list_a_build_writes_is_one_ticker_per_line_sorted_and_unique() -> None:
    assert render_series_list(("KXFED", "KXCPI", "kxfed")) == "KXCPI\nKXFED\n"
    assert render_series_list(()) == ""


def test_a_list_entry_may_carry_a_dash_but_not_anything_else() -> None:
    """The list the first build shipped carries ``BTCD-B``, so a reader that refused a dash is useless.

    An entry is kept verbatim rather than reduced to its prefix: the file exists to be passed back to
    the provider as ``series_ticker`` (ruling R100), and ``BTCD-B`` and ``BTCD`` are different requests.
    A row of the manifest's ``universe`` block is the stricter thing and is always derived by
    :func:`series_of`, so it never carries a dash.
    """
    assert read_series_list("BTCD-B,KXCPI") == ("BTCD-B", "KXCPI")
    with pytest.raises(InvalidConfigError):
        read_series_list("KXCPI,#!?")
    with pytest.raises(InvalidConfigError):
        read_series_list("KXCPI,-LEADINGDASH")


# --------------------------------------------------------------------------------------------------
# The builder's adapter, which is what puts the rule on a build
# --------------------------------------------------------------------------------------------------
def test_the_defaults_are_the_numbers_section_7_4_states() -> None:
    assert (UNIVERSE_MIN_SETTLED_DEFAULT, UNIVERSE_MIN_VOLUME_CENTS_DEFAULT) == (5, 100_000)


def test_the_builder_adapter_counts_the_walk_and_reads_only_the_universe_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manifold has no series, so it is never counted into the Kalshi universe block."""
    from tests.test_builder import facts as market_facts_of

    walked = [
        market_facts_of(id="kalshi-KXCPI-26-A", provider_id="KXCPI-26-A"),
        market_facts_of(id="kalshi-KXCPI-26-B", provider_id="KXCPI-26-B"),
        market_facts_of(id="manifold-abc", provider="manifold", provider_id="abc"),
    ]
    report = universe_of_facts(
        walked,
        frozenset({"kalshi-KXCPI-26-A"}),
        rule=UniverseRule(min_settled=2, min_volume_cents=0),
    )
    assert [stat.series for stat in report.series] == ["KXCPI"]
    assert (report.series[0].n_settled, report.series[0].n_kept) == (2, 1)
    assert report.n_series_after == 1
