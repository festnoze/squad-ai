"""DS2: the tag taxonomy and the deterministic tagger (CONTRACTS_V2 7.14, 18.5, 18.7).

What these tests are really guarding, beyond "the tagger tags":

* the vocabulary is **closed**. ``tags`` was a raw dump of 201 provider strings, every one of which
  matched ``market.v2``'s pattern, so the only thing that can stop the drift coming back is a refusal of
  a value the shipped vocabulary does not carry;
* the tagger is **deterministic to the byte**. A tag decides which cohort a market lands in, so a tag
  that moved between two rebuilds would move a claim. Two runs are compared as canonical JSON, and the
  two lexicon files are compared byte for byte after the copy that puts them inside ``dataset_hash``;
* the ``horizon`` facet is derived from the market's **declared life** and from nothing else. A question
  that says "before August 1, 2026" and lives four days is a week, and the test says so;
* a tag **cannot leak** (7.9). The tagger is handed a market whose ``resolution``, ``resolved_at_ms``,
  ``final_price_bp``, ``quality`` and bars are poisoned, and the facets do not move;
* ``platform-meta`` catches the self-referential markets **and** the provider's own non-predictive
  label, because the two sets were measured over the same 67 Manifold markets and are not the same set
  (7 against 8, 6 in common), so trusting either alone leaves real non-forecasts in forecast cohorts;
* coverage is **per venue** and its label is per venue. One global bar would either be unreachable on
  Manifold or would hide a Kalshi regression behind Manifold's untagged tail.

The fixtures under ``tests/fixtures/ds2/`` carry the 287 markets of the first real build reduced to the
eight fields the tagger may read, and fifteen of them with the facets a reader can check by eye.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

import pytest
from jsonschema import Draft202012Validator

from pmx.cohorts import Cohort, list_cohorts
from pmx.data import taxonomy as taxonomy_module
from pmx.data.taxonomy import (
    BUILDER_LABELS,
    FACET_SOURCE_KEYWORDS,
    FACET_SOURCE_OTHER,
    FACET_SOURCE_SERIES,
    HORIZON_BOUNDS_MS,
    HORIZONS,
    LABEL_FORECASTABLE,
    RE_FACET_VALUE,
    SERIES_FACETS_FILE,
    SUBJECTS_MAX,
    TAGS_FILE,
    TAXONOMY_AUDIT_FILE,
    TAXONOMY_AUDIT_N,
    TAXONOMY_COVERAGE_MIN_PERMILLE,
    TAXONOMY_DIR,
    TAXONOMY_LABEL_OK,
    TAXONOMY_LABEL_WEAK,
    TAXONOMY_MIN_USABLE_COHORTS,
    TAXONOMY_WEAK_LABEL,
    Facets,
    SeriesFacets,
    TaggedMarket,
    TagLexicon,
    apply_facets,
    check_series_facets,
    check_tags,
    copy_lexicons,
    horizon_of,
    load_series_facets,
    load_tag_lexicon,
    provider_labels_of,
    sample_taxonomy_audit,
    series_ticker_of,
    tag_market,
    taxonomy_audit_from_dict,
    taxonomy_audit_manifest_path,
    taxonomy_audit_path,
    taxonomy_block,
    tokens_of,
    venue_taxonomy,
    weak_venues,
)
from pmx.errors import InvalidConfigError, SchemaError
from pmx.types import MS_PER_DAY

FIXTURES: Final = Path(__file__).resolve().parent / "fixtures" / "ds2"
SCHEMAS: Final = Path(__file__).resolve().parents[1] / "src" / "pmx" / "schemas"
LEXICONS: Final = Path(__file__).resolve().parents[1] / "src" / "pmx" / "lexicons"


# --------------------------------------------------------------------------------------------------
# The market the tagger sees: exactly the eight fields TaggableMarket declares (7.9, 7.14)
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FixtureMarket:
    """A market reduced to what the tagger may read.

    This is not a convenience. ``pmx.types.Market`` carries ``resolution``, ``resolved_at_ms``,
    ``final_price_bp``, ``quality`` and its bars, and the leak test below builds a subclass that carries
    them poisoned to prove the tagger cannot see them.
    """

    id: str
    provider: str
    provider_id: str
    category: str
    question: str
    tags: tuple[str, ...]
    created_at_ms: int
    close_at_ms: int


@dataclass(frozen=True, slots=True)
class PoisonedMarket(FixtureMarket):
    """The same market with every field of 7.9 present and wrong.

    ``resolution`` says no on a market that resolved yes, ``final_price_bp`` says the tape ended at par,
    ``resolved_at_ms`` sits a year past the close and ``quality`` claims a million prints. If any of the
    five reached a facet, this class would move one.
    """

    resolution: int = 1
    resolved_at_ms: int = 0
    final_price_bp: int = 9_999
    first_price_bp: int = 1
    quality: Mapping[str, object] | None = None
    bars: tuple[object, ...] = ()
    trades: tuple[object, ...] = ()
    wiki_subjects: tuple[str, ...] = ("Bitcoin", "Gold")


def _market(payload: Mapping[str, object]) -> FixtureMarket:
    return FixtureMarket(
        id=str(payload["id"]),
        provider=str(payload["provider"]),
        provider_id=str(payload["provider_id"]),
        category=str(payload["category"]),
        question=str(payload["question"]),
        tags=tuple(str(value) for value in payload["tags"]),  # type: ignore[union-attr]
        created_at_ms=int(payload["created_at_ms"]),  # type: ignore[arg-type]
        close_at_ms=int(payload["close_at_ms"]),  # type: ignore[arg-type]
    )


def _read(name: str) -> Mapping[str, object]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _validator(pointer: Sequence[str]) -> Draft202012Validator:
    """A validator for one subschema of ``dataset.v1.json``, with the document's ``$defs`` beside it.

    The blocks this module writes are ``$ref``-heavy (``sha256``, ``nonNegInt``, ``audit``), and a
    subschema lifted out of its document resolves none of them, so the refs would raise instead of
    validating and the test would pass for the wrong reason.
    """
    schema = json.loads((SCHEMAS / "dataset.v1.json").read_text(encoding="utf-8"))
    node = schema
    for step in pointer:
        node = node[step]
    return Draft202012Validator({**node, "$defs": schema["$defs"]})


def _names_read(source: Path) -> frozenset[str]:
    """Every attribute name and every imported module name the module actually reads.

    An ``ast`` walk rather than a substring scan, so a field named in a docstring (this module names all
    five of 7.9's in its own prose, on purpose) is not a false positive and a field read through a
    variable is not a false negative.
    """
    import ast

    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "\n" not in node.value:
            # A short string constant is a key or a getattr name and is a read; a docstring is not.
            names.add(node.value)
    return frozenset(names)


@pytest.fixture(scope="module")
def lexicon() -> TagLexicon:
    return load_tag_lexicon()


@pytest.fixture(scope="module")
def series_facets() -> Mapping[str, SeriesFacets]:
    return load_series_facets()


@pytest.fixture(scope="module")
def real_markets() -> tuple[FixtureMarket, ...]:
    rows = _read("y2026_questions.json")["markets"]
    assert isinstance(rows, list)
    return tuple(_market(row) for row in rows)


@pytest.fixture(scope="module")
def real_folds() -> Mapping[str, str]:
    rows = _read("y2026_questions.json")["markets"]
    assert isinstance(rows, list)
    return {str(row["id"]): str(row["fold"]) for row in rows}


@dataclass(frozen=True, slots=True)
class FixtureMeta:
    """A tagged ``MarketMeta`` for the cohort call, which is what ``list_cohorts`` reads (18.5)."""

    id: str
    provider: str
    category: str
    fold: str
    subject: tuple[str, ...]
    structure: str
    horizon: str


def _tagged(
    markets: Sequence[FixtureMarket],
    folds: Mapping[str, str],
    *,
    lexicon: TagLexicon,
    series_facets: Mapping[str, SeriesFacets],
) -> tuple[tuple[TaggedMarket, ...], tuple[Cohort, ...]]:
    rows: list[TaggedMarket] = []
    metas: list[FixtureMeta] = []
    for market in markets:
        facets = tag_market(market, lexicon=lexicon, series_facets=series_facets)
        rows.append(TaggedMarket(market_id=market.id, provider=market.provider, facets=facets))
        metas.append(
            FixtureMeta(
                id=market.id,
                provider=market.provider,
                category=market.category,
                fold=folds[market.id],
                subject=facets.subject,
                structure=facets.structure,
                horizon=facets.horizon,
            )
        )
    return tuple(rows), list_cohorts(metas)


# --------------------------------------------------------------------------------------------------
# The vocabulary is closed, and a value outside it is refused
# --------------------------------------------------------------------------------------------------
def test_the_shipped_vocabulary_is_closed_and_every_value_is_a_facet_slug(lexicon: TagLexicon) -> None:
    """7.14: three facets, a builder label list, and every value a lowercase slug of 18.7's table."""
    assert lexicon.version == "tags.v1"
    assert lexicon.horizons == HORIZONS
    assert set(lexicon.builder) <= set(BUILDER_LABELS)
    for value in (*lexicon.subject_values, *lexicon.structure_values):
        assert RE_FACET_VALUE.fullmatch(value) is not None, value
    # The counted fallback is part of the vocabulary on both facets, so "nothing decided" is a value and
    # not an absence (7.14, stage 3).
    assert "other" in lexicon.subject_values
    assert "other" in lexicon.structure_values
    # Every value the contract names by hand is shipped. This list is 7.14's table, not a sample of it.
    for subject in (
        "bitcoin", "gold-silver", "gas-prices", "oil", "cpi-inflation", "treasury-yields",
        "equity-index", "single-equity", "precipitation", "temperature", "elections-us",
        "us-executive", "armed-conflict", "ai-models", "spaceflight", "net-worth", "platform-meta",
        "central-bank-rates", "employment", "fx-major", "epidemics", "storms", "court-rulings", "other",
    ):
        assert subject in lexicon.subject_values, subject
    for structure in (
        "threshold-above", "threshold-below", "count-over-period", "head-to-head", "range-band",
        "by-date", "multi-outcome-leg", "recurring-series-leg", "other",
    ):
        assert structure in lexicon.structure_values, structure
    # And the closure itself: a tags value is a facet value or a builder label, nothing else.
    assert lexicon.values == frozenset(
        {*lexicon.subject_values, *lexicon.structure_values, *HORIZONS, *lexicon.builder, "other"}
    )


def test_a_tags_value_outside_the_vocabulary_is_refused(lexicon: TagLexicon) -> None:
    """7.2 and 7.14: the builder refuses a ``tags`` value outside ``tags.v1.json`` (``SchemaError``).

    The three refused shapes are the three the old field had: a raw Kalshi series ticker, a provider
    group slug, and the market's own category repeated as a tag (58 of the 287 markets did exactly that).
    """
    check_tags(["bitcoin", "month", "threshold-above"], lexicon=lexicon)  # the control: it accepts
    for unknown in ("kxaaagasm", "crypto-speculation", "economics-default", "nonpredictive"):
        with pytest.raises(SchemaError, match="outside the controlled vocabulary"):
            check_tags(sorted({"bitcoin", unknown}), lexicon=lexicon)
    with pytest.raises(SchemaError, match="sorted and unique"):
        check_tags(["month", "bitcoin"], lexicon=lexicon)
    with pytest.raises(SchemaError, match="sorted and unique"):
        check_tags(["bitcoin", "bitcoin"], lexicon=lexicon)
    with pytest.raises(SchemaError, match="at most sixteen"):
        check_tags(sorted(lexicon.values)[:17], lexicon=lexicon)


def test_the_two_lexicons_never_name_a_value_the_other_does_not_ship(
    lexicon: TagLexicon, series_facets: Mapping[str, SeriesFacets]
) -> None:
    """The series map's values are vocabulary values (ruling R295's two files, edited by one package)."""
    check_series_facets(series_facets, lexicon=lexicon)
    with pytest.raises(InvalidConfigError, match="does not ship"):
        check_series_facets(
            {"KXFAKE": SeriesFacets(series="KXFAKE", subjects=("not-a-subject",))}, lexicon=lexicon
        )
    with pytest.raises(InvalidConfigError, match="does not ship"):
        check_series_facets(
            {"KXFAKE": SeriesFacets(series="KXFAKE", subjects=("bitcoin",), structure="not-a-shape")},
            lexicon=lexicon,
        )


def test_a_malformed_vocabulary_is_refused_rather_than_read_as_an_empty_one(tmp_path: Path) -> None:
    """A missing or broken ``tags.v1.json`` raises, and does not degrade to "tag everything other".

    The linker of 7.6 degrades to "no stop words" on a missing file because a worse link is still a
    link. A missing tag vocabulary would tag all 287 markets ``other``, produce a dataset with no cohort
    at all, and pass every schema on the way out: a build that looks like a build and carries no
    comparison. So the read raises.
    """
    with pytest.raises(InvalidConfigError, match="not there"):
        load_tag_lexicon(tmp_path / "absent")
    (tmp_path / TAGS_FILE).write_text("{not json", encoding="utf-8")
    with pytest.raises(InvalidConfigError, match="readable JSON"):
        load_tag_lexicon(tmp_path)
    good = json.loads((LEXICONS / TAGS_FILE).read_text(encoding="utf-8"))
    for index, (mutation, match) in enumerate((
        ({**good, "version": "tags.v2"}, "new vocabulary version"),
        ({**good, "facets": {**good["facets"], "horizon": ["intraday", "week"]}}, "five values are fixed"),
        ({**good, "facets": {**good["facets"], "builder": ["invented_label"]}}, "unknown builder label"),
        (
            {
                **good,
                "facets": {
                    **good["facets"],
                    "subject": {k: v for k, v in good["facets"]["subject"].items() if k != "other"},
                },
            },
            "counted other fallback",
        ),
        (
            {
                **good,
                "facets": {
                    **good["facets"],
                    "structure": {"threshold-above": {"patterns": ["([unclosed"]}, "other": {"patterns": []}},
                },
            },
            "not a regular expression",
        ),
    )):
        directory = tmp_path / f"broken{index}"
        directory.mkdir()
        (directory / TAGS_FILE).write_text(json.dumps(mutation), encoding="utf-8")
        with pytest.raises(InvalidConfigError, match=match):
            load_tag_lexicon(directory)


# --------------------------------------------------------------------------------------------------
# The three facets on questions a reader can check
# --------------------------------------------------------------------------------------------------
def test_the_three_facets_on_hand_checkable_questions(
    lexicon: TagLexicon, series_facets: Mapping[str, SeriesFacets]
) -> None:
    """Fifteen real markets, their facets written out in the fixture with the reason for each (7.14)."""
    cases = _read("hand_checked_facets.json")["cases"]
    assert isinstance(cases, list)
    assert len(cases) == 15
    for case in cases:
        market = _market(case["market"])
        expect = case["expect"]
        facets = tag_market(market, lexicon=lexicon, series_facets=series_facets)
        assert list(facets.subject) == expect["subject"], (market.question, case["why"])
        assert facets.structure == expect["structure"], (market.question, case["why"])
        assert facets.horizon == expect["horizon"], (market.question, case["why"])
        assert facets.source == expect["source"], (market.question, case["why"])
        # And every one of them carries at most four subjects with the primary first (7.14).
        assert 1 <= len(facets.subject) <= SUBJECTS_MAX
        assert facets.primary_subject == facets.subject[0]


def test_the_series_map_wins_outright_and_a_facet_it_omits_falls_through(
    lexicon: TagLexicon, series_facets: Mapping[str, SeriesFacets]
) -> None:
    """Stage 1 beats stage 2 for what it declares, and only for what it declares (7.14, ruling R267)."""
    market = FixtureMarket(
        id="kalshi-KXBTCMAXMON-26APR30-T80000",
        provider="kalshi",
        provider_id="KXBTCMAXMON-26APR30-T80000",
        category="crypto",
        question="Will the gold close price be above $4626.99 on Apr 30, 2026?",
        tags=("crypto", "kxbtcmaxmon"),
        created_at_ms=0,
        close_at_ms=10 * MS_PER_DAY,
    )
    # The question says gold and the series says bitcoin. The series wins, which is the whole point of a
    # sealed provider mapping: a templated Kalshi question is a worse source than the exchange's own
    # series, and 145 of the 220 Kalshi markets are templated.
    facets = tag_market(market, lexicon=lexicon, series_facets=series_facets)
    assert facets.subject == ("bitcoin",)
    assert facets.source == FACET_SOURCE_SERIES
    # The same series declares no structure, so the question's own "above" decides it.
    assert series_facets["KXBTCMAXMON"].structure is None
    assert facets.structure == "threshold-above"
    # A series that declares a structure overrides the question's wording for that facet alone.
    combo = replace(
        market,
        provider_id="KXTOPMODEL-26AUG",
        question="Will the gold close price be above $4626.99 on Apr 30, 2026?",
    )
    assert series_facets["KXTOPMODEL"].structure == "multi-outcome-leg"
    overridden = tag_market(combo, lexicon=lexicon, series_facets=series_facets)
    assert overridden.structure == "multi-outcome-leg"
    assert overridden.subject == ("ai-models",)
    # A series nothing knows falls entirely to the keyword rules.
    unknown = replace(market, provider_id="KXNOSUCHSERIES-26AUG")
    assert series_ticker_of(unknown) == "KXNOSUCHSERIES"
    assert "KXNOSUCHSERIES" not in series_facets
    fallen = tag_market(unknown, lexicon=lexicon, series_facets=series_facets)
    assert fallen.subject == ("gold-silver",)
    assert fallen.source == FACET_SOURCE_KEYWORDS
    # And a Manifold market has no series at all, which is why its coverage is the lower of the two.
    assert series_ticker_of(replace(market, provider="manifold")) is None


def test_a_facet_nothing_decided_is_a_counted_other_and_not_a_guess(
    lexicon: TagLexicon, series_facets: Mapping[str, SeriesFacets]
) -> None:
    """Stage 3 (7.14): ``other`` on both facets, ``source = "other"``, and still a valid ``Facets``."""
    market = FixtureMarket(
        id="manifold-zzz",
        provider="manifold",
        provider_id="zzz",
        category="other",
        question="Will anyone ask out @admit at the 2026 USAMO?",
        tags=("college-admissions",),
        created_at_ms=0,
        close_at_ms=17 * MS_PER_DAY,
    )
    facets = tag_market(market, lexicon=lexicon, series_facets=series_facets)
    assert facets.subject == ("other",)
    assert facets.structure == "other"
    assert facets.source == FACET_SOURCE_OTHER
    assert facets.horizon == "month"
    assert facets.tags == ("month", "other")


def test_a_weather_subject_carries_the_builder_label_and_others_do_not(
    lexicon: TagLexicon, series_facets: Mapping[str, SeriesFacets]
) -> None:
    """7.14's ``builder`` list: a label a market may carry, not a facet it must (decision D-R13)."""
    snow = FixtureMarket(
        id="kalshi-KXNYCSNOWM-25DEC",
        provider="kalshi",
        provider_id="KXNYCSNOWM-25DEC",
        category="weather",
        question="Snow in New York City in Dec 2025? (Above 10.0 inches)",
        tags=("weather",),
        created_at_ms=0,
        close_at_ms=30 * MS_PER_DAY,
    )
    facets = tag_market(snow, lexicon=lexicon, series_facets=series_facets)
    assert facets.subject == ("precipitation",)
    assert facets.labels == (LABEL_FORECASTABLE,)
    assert LABEL_FORECASTABLE in facets.tags
    bitcoin = replace(snow, provider_id="KXBTCMAXMON-26APR30", question="Will BTC be above $80000.00?")
    assert tag_market(bitcoin, lexicon=lexicon, series_facets=series_facets).labels == ()
    with pytest.raises(SchemaError, match="builder label the vocabulary does not ship"):
        Facets(subject=("bitcoin",), structure="threshold-above", horizon="month", labels=("invented",))


# --------------------------------------------------------------------------------------------------
# The horizon is derived from the life, never from the text
# --------------------------------------------------------------------------------------------------
def test_the_horizon_is_derived_from_the_declared_life_and_from_nothing_else(
    lexicon: TagLexicon, series_facets: Mapping[str, SeriesFacets]
) -> None:
    """7.14 and 18.5: ``close_at_ms - created_at_ms``, the venue's published close, never a date in the
    question and never ``resolved_at_ms``.

    The boundaries are ruling R301's: moving one is a new lexicon version and a new dataset hash.
    """
    assert HORIZON_BOUNDS_MS == (
        ("intraday", MS_PER_DAY),
        ("week", 7 * MS_PER_DAY),
        ("month", 31 * MS_PER_DAY),
        ("quarter", 183 * MS_PER_DAY),
    )
    assert horizon_of(0, 0) == "intraday"
    assert horizon_of(0, MS_PER_DAY - 1) == "intraday"
    assert horizon_of(0, MS_PER_DAY) == "week"
    assert horizon_of(0, 7 * MS_PER_DAY - 1) == "week"
    assert horizon_of(0, 7 * MS_PER_DAY) == "month"
    assert horizon_of(0, 31 * MS_PER_DAY - 1) == "month"
    assert horizon_of(0, 31 * MS_PER_DAY) == "quarter"
    assert horizon_of(0, 183 * MS_PER_DAY - 1) == "quarter"
    assert horizon_of(0, 183 * MS_PER_DAY) == "year-plus"
    # A provider that published a close at or before its own creation gets intraday, not a crash.
    assert horizon_of(10 * MS_PER_DAY, 0) == "intraday"
    # And the text cannot move it: the same question at three lives gets three horizons, and a question
    # naming a year two years out on a four-day life is a week.
    question = "Will Russia and Ukraine agree to a ceasefire before August 1, 2028?"
    for life_days, expected in ((0, "intraday"), (4, "week"), (20, "month"), (90, "quarter"), (300, "year-plus")):
        market = FixtureMarket(
            id=f"manifold-h{life_days}",
            provider="manifold",
            provider_id=f"h{life_days}",
            category="world",
            question=question,
            tags=(),
            created_at_ms=1_700_000_000_000,
            close_at_ms=1_700_000_000_000 + life_days * MS_PER_DAY,
        )
        assert tag_market(market, lexicon=lexicon, series_facets=series_facets).horizon == expected


# --------------------------------------------------------------------------------------------------
# A tag cannot leak (7.9)
# --------------------------------------------------------------------------------------------------
def test_a_poisoned_market_does_not_move_a_single_facet(
    lexicon: TagLexicon, series_facets: Mapping[str, SeriesFacets]
) -> None:
    """7.14's own test, stated there: poison every field of 7.9 and check the facets do not move.

    The tagger reads the question, the provider and its id, the declared life and the raw provider
    labels. All five exist before the market's first bar, which is why a facet, a provider label and a
    cohort id may sit in a ``MarketView`` and in a rule's scope at every bar.
    """
    clean = FixtureMarket(
        id="kalshi-KXCPI-26AUG",
        provider="kalshi",
        provider_id="KXCPI-26AUG",
        category="economics",
        question="Will CPI rise more than 0.3% in August 2026? (Above 0.3%)",
        tags=("economics", "kxcpi"),
        created_at_ms=1_700_000_000_000,
        close_at_ms=1_700_000_000_000 + 20 * MS_PER_DAY,
    )
    expected = tag_market(clean, lexicon=lexicon, series_facets=series_facets)
    assert expected.subject == ("cpi-inflation",)
    assert expected.structure == "threshold-above"
    assert expected.horizon == "month"
    poisoned = PoisonedMarket(
        id=clean.id,
        provider=clean.provider,
        provider_id=clean.provider_id,
        category=clean.category,
        question=clean.question,
        tags=clean.tags,
        created_at_ms=clean.created_at_ms,
        close_at_ms=clean.close_at_ms,
        resolution=0,
        resolved_at_ms=clean.close_at_ms + 365 * MS_PER_DAY,
        final_price_bp=10_000,
        first_price_bp=0,
        quality={"n_trades": 1_000_000, "traded_bars": 0, "tape_kind": "trades"},
        bars=({"t_ms": 0, "close_bp": 9_999},) * 500,
        trades=({"t_ms": 0, "price_bp": 1},) * 500,
        wiki_subjects=("Bitcoin", "Gold as an investment"),
    )
    assert tag_market(poisoned, lexicon=lexicon, series_facets=series_facets) == expected
    # And the protocol is the mechanism, not a convention: the module reads none of 7.9's field names,
    # under any spelling, including through getattr.
    read = _names_read(Path(taxonomy_module.__file__))
    for banned in (
        "final_price_bp", "first_price_bp", "resolved_at_ms", "resolution", "bars", "trades",
        "quality", "wiki_subjects", "sealed_market", "fold",
    ):
        assert banned not in read, banned
    # The control: it does read the eight fields it is allowed to.
    for allowed in ("question", "provider", "provider_id", "tags", "created_at_ms", "close_at_ms"):
        assert allowed in read, allowed


# --------------------------------------------------------------------------------------------------
# platform-meta: the reconciliation of two measured sets that are not the same set
# --------------------------------------------------------------------------------------------------
def test_platform_meta_catches_the_question_and_the_provider_label_and_their_union(
    lexicon: TagLexicon, series_facets: Mapping[str, SeriesFacets], real_markets: tuple[FixtureMarket, ...]
) -> None:
    """Decision D-S14: 7 self-referential questions, 8 ``nonpredictive`` labels, and not the same set.

    Measured over the same 67 Manifold markets of the first build: the union is nine markets, six are in
    both sets, one is self-referential without the label ("We sell >2x the boosts now that we add 5k
    liquidity to the AMM?") and two carry the label without a self-referential question ("Daily Coinflip",
    "Will Zanda Zhu remain in Masters after Season 40?"). Trusting either set alone leaves real
    non-forecasts inside forecast cohorts, which is why 7.14 asks for one audited subject.
    """
    manifold = [market for market in real_markets if market.provider == "manifold"]
    assert len(manifold) == 67
    by_question: dict[str, FixtureMarket] = {market.question: market for market in manifold}

    def is_meta(market: FixtureMarket) -> bool:
        return "platform-meta" in tag_market(
            market, lexicon=lexicon, series_facets=series_facets
        ).subject

    # The question half alone: the same markets with their provider labels stripped, so only the
    # keyword rule can fire.
    from_question = {market.question for market in manifold if is_meta(replace(market, tags=()))}
    from_label = {market.question for market in manifold if "nonpredictive" in market.tags}
    union = {market.question for market in manifold if is_meta(market)}
    assert len(from_question) == 7, sorted(from_question)
    assert len(from_label) == 8, sorted(from_label)
    assert len(from_question & from_label) == 6
    assert union == from_question | from_label
    assert len(union) == 9
    # The one market each half misses, named, because that is the measurement decision D-S14 rests on.
    assert from_question - from_label == {
        "We sell >2x the boosts now that we add 5k liquidity to the AMM?"
    }
    assert from_label - from_question == {
        "Daily Coinflip",
        "Will Zanda Zhu remain in Masters after Season 40?",
    }
    # And each half proved on a market the other misses: with its label stripped, "Daily Coinflip" is
    # not self-referential by its two words and falls to other; with its label it is platform-meta.
    assert tag_market(
        replace(by_question["Daily Coinflip"], tags=()), lexicon=lexicon, series_facets=series_facets
    ).subject == ("other",)
    assert tag_market(
        by_question["Daily Coinflip"], lexicon=lexicon, series_facets=series_facets
    ).subject == ("platform-meta",)
    assert tag_market(
        replace(by_question["We sell >2x the boosts now that we add 5k liquidity to the AMM?"], tags=()),
        lexicon=lexicon,
        series_facets=series_facets,
    ).subject == ("platform-meta",)


def test_platform_meta_is_first_in_precedence_and_therefore_the_cohort_key(
    lexicon: TagLexicon, series_facets: Mapping[str, SeriesFacets]
) -> None:
    """7.14: a self-referential market that also mentions a real subject is still ``platform-meta``.

    Precedence order is the file's order and ``platform-meta`` is first, because a market about itself is
    not a forecast of the world whatever else it names, and 18.5 keys the cohort on ``subject[0]``.
    """
    assert lexicon.subject_values[0] == "platform-meta"
    market = FixtureMarket(
        id="manifold-meta-btc",
        provider="manifold",
        provider_id="meta-btc",
        category="crypto",
        question="Will this market be above 50% when Bitcoin closes above $80,000?",
        tags=("bitcoin", "nonpredictive"),
        created_at_ms=0,
        close_at_ms=6 * MS_PER_DAY,
    )
    facets = tag_market(market, lexicon=lexicon, series_facets=series_facets)
    assert facets.primary_subject == "platform-meta"
    # Even when the sealed series map answered first: a Kalshi ticker cannot buy a market out of it.
    kalshi = replace(market, provider="kalshi", provider_id="KXBTCMAXMON-26APR30")
    assert tag_market(kalshi, lexicon=lexicon, series_facets=series_facets).primary_subject == "platform-meta"


# --------------------------------------------------------------------------------------------------
# Determinism, byte for byte, and the copy into the walk of 4.3
# --------------------------------------------------------------------------------------------------
def test_two_runs_of_the_tagger_agree_byte_for_byte(
    real_markets: tuple[FixtureMarket, ...], real_folds: Mapping[str, str]
) -> None:
    """7.14: "byte-identical across two runs is a DS2 test", and here it is over all 287 markets.

    The caches are cleared between the runs, so the second run re-reads both lexicon files off disk: a
    tagger that was deterministic only because it kept the first parse in memory would pass a weaker
    version of this test and fail a rebuild.
    """
    taxonomy_module._TAGS_CACHE.clear()
    taxonomy_module._SERIES_CACHE.clear()
    first_rows, first_cohorts = _tagged(
        real_markets, real_folds, lexicon=load_tag_lexicon(), series_facets=load_series_facets()
    )
    taxonomy_module._TAGS_CACHE.clear()
    taxonomy_module._SERIES_CACHE.clear()
    second_rows, second_cohorts = _tagged(
        real_markets, real_folds, lexicon=load_tag_lexicon(), series_facets=load_series_facets()
    )
    first = json.dumps(
        [row.facets.to_dict() | {"id": row.market_id} for row in first_rows], sort_keys=True
    ).encode("utf-8")
    second = json.dumps(
        [row.facets.to_dict() | {"id": row.market_id} for row in second_rows], sort_keys=True
    ).encode("utf-8")
    assert first == second
    assert [cohort.to_dict() for cohort in first_cohorts] == [
        cohort.to_dict() for cohort in second_cohorts
    ]


def test_the_two_lexicons_are_copied_into_the_dataset_byte_for_byte(tmp_path: Path) -> None:
    """7.8 and ruling R267: ``taxonomy/`` is inside the walk of 4.3, so both files enter ``dataset_hash``.

    Byte for byte and not "same JSON": the walk hashes file bytes, so a re-serialisation that changed a
    space would move every dataset hash for nothing. A second copy over the first writes the same bytes
    and therefore moves nothing, which is what makes a rebuild reproducible.
    """
    tags_hash, series_hash = copy_lexicons(tmp_path)
    out = tmp_path / TAXONOMY_DIR
    for name in (TAGS_FILE, SERIES_FACETS_FILE):
        assert (out / name).read_bytes() == (LEXICONS / name).read_bytes()
    assert copy_lexicons(tmp_path) == (tags_hash, series_hash)
    assert tags_hash != series_hash
    assert len(tags_hash) == 64 and len(series_hash) == 64
    assert load_tag_lexicon().sha256 == tags_hash
    # A dataset path pattern of dataset.v1.json admits exactly this prefix (18.8's widening).
    validator = _validator(("properties", "files", "items", "properties", "path"))
    assert "taxonomy" in validator.schema["pattern"]
    assert validator.is_valid(f"{TAXONOMY_DIR}/{TAGS_FILE}")
    assert validator.is_valid(f"{TAXONOMY_DIR}/{SERIES_FACETS_FILE}")


def test_the_tagger_reads_no_clock_and_no_random_number(lexicon: TagLexicon) -> None:
    """Ruling R267: no network, no wall clock, no randomness in the tagging path.

    Architecture rule 12 already binds the import graph for the gateway and the LLM package; this scans
    for the other two, which no architecture rule covers under ``data/``.
    """
    read = _names_read(Path(taxonomy_module.__file__))
    for banned in ("time", "datetime", "now", "utcnow", "random", "socket", "httpx", "requests", "urllib"):
        assert banned not in read, banned
    # The one random draw in the module is the audit sample, and it comes from a registered substream of
    # section 6.3 seeded by the caller, not from module randomness.
    assert "RngTree" in read
    assert tokens_of("Will CPI rise more than 0.3%?", frozenset()) == frozenset(
        {"will", "cpi", "rise", "more", "than"}
    )
    assert tokens_of("Will CPI rise?", frozenset({"will"})) == frozenset({"cpi", "rise"})


# --------------------------------------------------------------------------------------------------
# tags, provider_labels and the payload the builder writes
# --------------------------------------------------------------------------------------------------
def test_the_raw_provider_strings_move_to_provider_labels_and_tags_becomes_the_facet_union(
    lexicon: TagLexicon, series_facets: Mapping[str, SeriesFacets]
) -> None:
    """7.2 and 7.14: ``tags`` is the facet union, the provider's own strings live in ``provider_labels``."""
    market = FixtureMarket(
        id="kalshi-KXAAAGASM-25DEC31-2.85",
        provider="kalshi",
        provider_id="KXAAAGASM-25DEC31-2.85",
        category="economics",
        question="Will average **gas prices** be above $2.85? (Above 2.85)",
        tags=("economics", "kxaaagasm"),
        created_at_ms=0,
        close_at_ms=30 * MS_PER_DAY,
    )
    facets = tag_market(market, lexicon=lexicon, series_facets=series_facets)
    assert facets.subject == ("gas-prices",)
    assert facets.tags == ("gas-prices", "month", "threshold-above")
    payload = apply_facets(
        {"id": market.id, "tags": list(market.tags)},
        facets,
        provider_labels=provider_labels_of(market),
        lexicon=lexicon,
    )
    assert payload["tags"] == ["gas-prices", "month", "threshold-above"]
    assert payload["provider_labels"] == ["economics", "kxaaagasm"]
    assert payload["subject"] == ["gas-prices"]
    assert payload["structure"] == "threshold-above"
    assert payload["horizon"] == "month"
    # The refusal runs inside apply_facets, so a vocabulary and a tagger that disagree cannot write a file.
    with pytest.raises(SchemaError, match="outside the controlled vocabulary"):
        apply_facets(
            {"id": market.id},
            Facets(subject=("bitcoin",), structure="threshold-above", horizon="month"),
            provider_labels=(),
            lexicon=TagLexicon(
                version="tags.v1",
                subjects=(),
                structures=(),
                horizons=HORIZONS,
                builder=(),
            ),
        )
    # A provider string that cannot be written to market.v2 is normalised, not smuggled through.
    messy = replace(market, tags=("Crypto Speculation!", "a" * 40, "ok_label"))
    assert provider_labels_of(messy) == ("a" * 32, "crypto-speculation", "ok_label")
    # The label list is capped at sixteen and sorted, which is market.v2's rule.
    many = replace(market, tags=tuple(f"label-{index:02d}" for index in range(20)))
    labels = provider_labels_of(many)
    assert len(labels) == 16
    assert list(labels) == sorted(labels)
    # A malformed label reaching apply_facets is a SchemaError and not a silent drop.
    with pytest.raises(SchemaError, match="market.v2's pattern"):
        apply_facets({"id": market.id}, facets, provider_labels=("Not A Label",), lexicon=lexicon)


# --------------------------------------------------------------------------------------------------
# Coverage per venue, its label, and the measured shape of the first real build
# --------------------------------------------------------------------------------------------------
def _rows(provider: str, subjects: Sequence[str], structure: str = "threshold-above") -> list[TaggedMarket]:
    return [
        TaggedMarket(
            market_id=f"{provider}-{index}",
            provider=provider,
            facets=Facets(subject=(subject,), structure=structure, horizon="month"),
        )
        for index, subject in enumerate(subjects)
    ]


def test_coverage_is_measured_per_venue_and_labelled_per_venue(lexicon: TagLexicon) -> None:
    """Ruling R268 in the form decision D-S14 corrected it: 900 permille on ``subject``, per venue.

    Two ways to be weak and they are different failures, so the test separates them: coverage below the
    bar with plenty of cohorts, and coverage at the bar with too few cohorts.
    """
    assert TAXONOMY_COVERAGE_MIN_PERMILLE == 900
    assert TAXONOMY_MIN_USABLE_COHORTS == 10
    cohorts = tuple(
        Cohort(
            cohort_id=f"co-kalshi-crypto-bitcoin-threshold-above-month{index or ''}".replace("month0", "month"),
            category="crypto",
            subject="bitcoin",
            structure="threshold-above",
            horizon="month",
            provider="kalshi",
            n_train=30,
            n_validation=1,
            n_sealed=1,
            usable=True,
            usable_for_paired_test=True,
            market_ids=(),
        )
        for index in range(10)
    )
    # Exactly at the bar: nine covered of ten is 900 permille, which is ok when the cohorts are there.
    at_bar = venue_taxonomy("kalshi", _rows("kalshi", ["bitcoin"] * 9 + ["other"]), cohorts)
    assert at_bar.subject_coverage_permille == 900
    assert at_bar.label == TAXONOMY_LABEL_OK
    assert at_bar.n_other_subject == 1
    # One market below it is weak, and the label moves with the coverage and not with anything else.
    below = venue_taxonomy("kalshi", _rows("kalshi", ["bitcoin"] * 8 + ["other"] * 2), cohorts)
    assert below.subject_coverage_permille == 800
    assert below.label == TAXONOMY_LABEL_WEAK
    # Full coverage with nine usable cohorts is weak too: coverage with no comparison behind it is a
    # tagger that works on a dataset that carries nothing (decision D-S13).
    thin = venue_taxonomy("kalshi", _rows("kalshi", ["bitcoin"] * 10), cohorts[:9])
    assert thin.subject_coverage_permille == 1_000
    assert thin.n_cohorts_usable == 9
    assert thin.label == TAXONOMY_LABEL_WEAK
    # A venue's label is its own: Manifold weak does not make Kalshi weak.
    rows = _rows("kalshi", ["bitcoin"] * 10) + _rows("manifold", ["other"] * 10)
    block = taxonomy_block(
        rows, cohorts, lexicon=lexicon, lexicon_hash="0" * 64, series_facets_hash="1" * 64
    )
    per_venue = block["per_venue"]
    assert isinstance(per_venue, dict)
    assert per_venue["kalshi"]["label"] == TAXONOMY_LABEL_OK
    assert per_venue["manifold"]["label"] == TAXONOMY_LABEL_WEAK
    assert weak_venues(block) == ("manifold",)
    assert TAXONOMY_WEAK_LABEL == "taxonomy:weak"
    # A structure coverage below the bar does NOT make a venue weak: ruling R268 states the label on the
    # subject facet, because the subject is what a cohort is keyed on.
    structures = venue_taxonomy("kalshi", _rows("kalshi", ["bitcoin"] * 10, structure="other"), cohorts)
    assert structures.structure_coverage_permille == 0
    assert structures.label == TAXONOMY_LABEL_OK


def test_a_platform_meta_market_counts_as_covered_and_is_counted_separately(lexicon: TagLexicon) -> None:
    """7.14: naming a non-forecast is a tagging success, and the count is reported beside the coverage."""
    row = venue_taxonomy("manifold", _rows("manifold", ["platform-meta"] * 5 + ["other"] * 5), ())
    assert row.subject_coverage_permille == 500
    assert row.n_platform_meta == 5
    assert row.n_other_subject == 5
    assert row.n_distinct_subjects == 1


def test_the_coverage_measured_over_the_first_real_build(
    real_markets: tuple[FixtureMarket, ...],
    real_folds: Mapping[str, str],
    lexicon: TagLexicon,
    series_facets: Mapping[str, SeriesFacets],
) -> None:
    """AC-34 restated (ruling R273): per-venue coverage above 90 percent on Kalshi's subject facet, the
    measured structure vocabulary populated, ``platform-meta`` out of the forecast cohorts, and
    Manifold's ``other`` bucket reported rather than hidden.

    The prototype of ``docs/REVIEW_2026-09-09_SCALE_TAGS.md`` section G reached 800 permille on Kalshi
    and 642 on Manifold. This vocabulary is measured here so a later edit that regresses it fails a test
    rather than a rebuild.
    """
    rows, cohorts = _tagged(real_markets, real_folds, lexicon=lexicon, series_facets=series_facets)
    kalshi = venue_taxonomy("kalshi", rows, cohorts)
    manifold = venue_taxonomy("manifold", rows, cohorts)
    assert (kalshi.n_markets, manifold.n_markets) == (220, 67)
    assert kalshi.subject_coverage_permille >= TAXONOMY_COVERAGE_MIN_PERMILLE
    assert kalshi.structure_coverage_permille >= TAXONOMY_COVERAGE_MIN_PERMILLE
    assert kalshi.n_distinct_subjects >= 20
    # Manifold's untagged tail is real and is reported, not hidden. It is also not unbounded here: the
    # bar is that it does not get worse than the prototype's 642 permille.
    assert manifold.subject_coverage_permille >= 642
    assert manifold.n_other_subject > 0
    assert manifold.n_platform_meta == 9
    # Every structure value of 7.14's measured table occurs in the build.
    seen = {row.facets.structure for row in rows}
    for structure in (
        "threshold-above", "threshold-below", "count-over-period", "head-to-head", "range-band",
        "by-date", "multi-outcome-leg", "recurring-series-leg", "other",
    ):
        assert structure in seen, structure
    # threshold-above dominates Kalshi, which is what "145 measured" was evidence of.
    kalshi_structures = [row.facets.structure for row in rows if row.provider == "kalshi"]
    assert kalshi_structures.count("threshold-above") >= 140
    # No platform-meta market reached a cohort, on either venue.
    meta_ids = {row.market_id for row in rows if "platform-meta" in row.facets.subject}
    assert meta_ids and not (meta_ids & {market_id for c in cohorts for market_id in c.market_ids})
    # And the whole block validates against dataset.v1.json's taxonomy schema.
    block = taxonomy_block(
        rows, cohorts, lexicon=lexicon, lexicon_hash="a" * 64, series_facets_hash="b" * 64
    )
    errors = sorted(
        _validator(("properties", "taxonomy")).iter_errors(block), key=lambda error: str(error.path)
    )
    assert errors == [], [error.message for error in errors]
    assert block["version"] == "tags.v1"
    assert sum(int(value) for value in block["cohort_size_histogram"].values()) == len(cohorts)  # type: ignore[union-attr]


# --------------------------------------------------------------------------------------------------
# The fifty-tagging audit: tracked, keyed by the hash it audits, deterministic
# --------------------------------------------------------------------------------------------------
def test_the_audit_draws_fifty_taggings_deterministically_and_reports_zero_until_reviewed(
    real_markets: tuple[FixtureMarket, ...],
    real_folds: Mapping[str, str],
    lexicon: TagLexicon,
    series_facets: Mapping[str, SeriesFacets],
) -> None:
    """7.14 and rulings R268 and R296: fifty taggings, the ``dataset.subsample`` substream, tracked."""
    rows, _cohorts = _tagged(real_markets, real_folds, lexicon=lexicon, series_facets=series_facets)
    questions = {market.id: market.question for market in real_markets}
    dataset_hash = "9" * 64
    audit = sample_taxonomy_audit(rows, questions, dataset_hash=dataset_hash, sample_seed=7)
    assert audit.n == TAXONOMY_AUDIT_N == 50
    assert len(audit.taggings) == 50
    # Deterministic in the dataset and in nothing else, so an interrupted reviewer comes back to the
    # same fifty and a second reviewer cannot shop for a friendlier sample.
    again = sample_taxonomy_audit(rows, questions, dataset_hash=dataset_hash, sample_seed=7)
    assert audit.to_dict() == again.to_dict()
    # A different seed draws a different fifty. The comparison is on the drawn **market ids** and not on
    # the rendered dict, because the dict carries ``sample_seed`` itself: comparing the dicts would pass
    # on a draw that ignored the seed entirely, which is a mutation that survived the first shape of this
    # assertion.
    drawn = {row.market_id for row in audit.taggings}
    other = {
        row.market_id
        for row in sample_taxonomy_audit(
            rows, questions, dataset_hash=dataset_hash, sample_seed=8
        ).taggings
    }
    assert drawn != other
    assert len(other) == 50
    # The population is every tagged market, other taggings included: a facet nothing decided is exactly
    # what a reviewer needs to see.
    assert {row.market_id for row in audit.taggings} <= {row.market_id for row in rows}
    assert all(row.question for row in audit.taggings)
    # Unreviewed reads zero, not a flattering absence.
    assert audit.n_reviewed == 0
    assert audit.precision_permille == 0
    # The arithmetic, with unsure counting in neither half.
    reviewed = replace(
        audit,
        taggings=(
            replace(audit.taggings[0], verdicts={"subject": "correct", "structure": "correct", "horizon": "correct"}),
            replace(audit.taggings[1], verdicts={"subject": "wrong", "structure": "correct", "horizon": "unsure"}),
        ),
    )
    assert (reviewed.n_correct, reviewed.n_wrong) == (4, 1)
    assert reviewed.precision_permille == 800
    with pytest.raises(SchemaError, match="correct, wrong or unsure"):
        replace(audit.taggings[0], verdicts={"subject": "probably"})
    with pytest.raises(SchemaError, match="facet that is not audited"):
        replace(audit.taggings[0], verdicts={"vibe": "correct"})
    with pytest.raises(SchemaError, match="non-negative"):
        sample_taxonomy_audit(rows, questions, dataset_hash=dataset_hash, sample_seed=7, n=-1)
    # It round-trips, verdicts included, so a review can be read back and the precision recomputed.
    assert taxonomy_audit_from_dict(json.loads(json.dumps(reviewed.to_dict()))).precision_permille == 800
    with pytest.raises(SchemaError, match="malformed"):
        taxonomy_audit_from_dict({"dataset_hash": dataset_hash, "sample_seed": 1, "n": 1})


def test_the_audit_lives_in_the_tracked_audits_tree_keyed_by_the_hash_it_audits(tmp_path: Path) -> None:
    """Ruling R296: ``audits/<dataset_hash[:16]>/taxonomy.json``, outside every dataset hash.

    A top-level tree the ignore file never mentions, because git cannot re-include a file under an
    excluded directory and fifty reviewer verdicts are the least reproducible artefact of a build wave.
    """
    dataset_hash = "0123456789abcdef" + "f" * 48
    path = taxonomy_audit_path(tmp_path, dataset_hash)
    assert path == tmp_path / "audits" / "0123456789abcdef" / TAXONOMY_AUDIT_FILE
    manifest_path = taxonomy_audit_manifest_path(dataset_hash)
    assert manifest_path == "audits/0123456789abcdef/taxonomy.json"
    validator = _validator(("$defs", "audit", "properties", "path"))
    assert validator.is_valid(manifest_path)
    assert not validator.is_valid("data/datasets/y2026/audit/taxonomy.json")
    with pytest.raises(SchemaError, match="sixty-four hex"):
        taxonomy_audit_manifest_path("short")
    # The .gitignore never names audits/, so the tree is tracked with no change to it.
    ignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8")
    assert "audits/" not in ignore


def test_the_manifest_audit_block_is_the_three_keys_the_schema_admits(
    real_markets: tuple[FixtureMarket, ...],
    real_folds: Mapping[str, str],
    lexicon: TagLexicon,
    series_facets: Mapping[str, SeriesFacets],
) -> None:
    """7.8: ``taxonomy.audit {path, n, precision_permille}``, or ``null`` before a build drew one."""
    rows, cohorts = _tagged(real_markets, real_folds, lexicon=lexicon, series_facets=series_facets)
    questions = {market.id: market.question for market in real_markets}
    dataset_hash = "c" * 64
    audit = sample_taxonomy_audit(rows, questions, dataset_hash=dataset_hash, sample_seed=3)
    block = audit.manifest_block(taxonomy_audit_manifest_path(dataset_hash))
    assert sorted(block) == ["n", "path", "precision_permille"]
    assert _validator(("$defs", "audit")).is_valid(block)
    whole = taxonomy_block(
        rows, cohorts, lexicon=lexicon, lexicon_hash="a" * 64, series_facets_hash="b" * 64, audit=block
    )
    assert _validator(("properties", "taxonomy")).is_valid(whole)
    assert taxonomy_block(
        rows, cohorts, lexicon=lexicon, lexicon_hash="a" * 64, series_facets_hash="b" * 64
    )["audit"] is None
