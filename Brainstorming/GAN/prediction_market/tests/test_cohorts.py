"""DS2: the cohort, the unit of comparative analysis (CONTRACTS_V2 18.5, decision D-S7, ruling R266).

What these tests are really guarding:

* **a cohort spans the folds** (ruling R293). The bolded sentence "a cohort never crosses a fold" was
  deleted as stale, because read as the cluster rule of R248 it would pull every market of a dense Kalshi
  series into one fold and collapse the train fold onto the sealed one. What replaced it is tested here:
  a cohort has no fold of its own, every market keeps the fold 7.7 gave it, and the three per-fold counts
  are what those folds left;
* **exactly one cohort per market**, keyed on the *primary* subject. A market with four subjects is one
  market in one cohort and not four rows a comparison would then count it four times in;
* ``platform-meta`` and ``other`` **belong to no cohort**, and the markets are counted rather than
  vanished;
* the refusals fire **before any measurement** and are never weakened (ruling R283). There is no
  ``pmx claim --cohort`` to test, and that absence is asserted too: a per-cohort sealed read is a second
  bite at the same sealed markets;
* ``usable_for_paired_test`` is false when **any** fold is empty (decision D-S13), which is the defect
  the flag exists for: all six cohorts that reached ten markets on the prototype sat inside one fold.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

import pytest
from jsonschema import Draft202012Validator

from pmx import cohorts as cohorts_module
from pmx.cohorts import (
    COHORT_ID_MAX_CHARS,
    COHORT_MIN_TRAIN,
    COHORT_SIZE_BUCKETS,
    RE_COHORT_ID,
    Cohort,
    cohort_id_for_meta,
    cohort_id_of,
    cohort_ids_by_market,
    cohort_key_of,
    cohort_or_refuse,
    cohort_rows,
    cohort_size_bucket,
    cohort_size_histogram,
    cohorts_per_provider,
    facets_of,
    list_cohorts,
    usable_cohorts,
)
from pmx.errors import CohortRefusedError, PmxError, SchemaError
from pmx.types import MarketMeta

SRC: Final = Path(__file__).resolve().parents[1] / "src" / "pmx"
SCHEMAS: Final = SRC / "schemas"


@dataclass(frozen=True, slots=True)
class TaggedMeta:
    """A ``MarketMeta`` carrying 7.2's five taxonomy fields.

    Those five fields are 18.8's deferral row for ``src/pmx/types.py``, which names DS1 as the package
    that applies them, so this package may not add them and reads them through
    :func:`pmx.cohorts.facets_of` instead. This double carries them, which is what the cohort code sees
    the day they land; the test below feeds a **real** ``MarketMeta`` through the same door and asserts
    the untagged answer, so both sides of the agreement are covered.
    """

    id: str
    provider: str
    category: str
    fold: str
    subject: tuple[str, ...]
    structure: str
    horizon: str


def _meta(
    market_id: str,
    *,
    fold: str,
    subject: Sequence[str] = ("bitcoin",),
    structure: str = "threshold-above",
    horizon: str = "month",
    provider: str = "kalshi",
    category: str = "crypto",
) -> TaggedMeta:
    return TaggedMeta(
        id=market_id,
        provider=provider,
        category=category,
        fold=fold,
        subject=tuple(subject),
        structure=structure,
        horizon=horizon,
    )


def _names_read(source: Path) -> frozenset[str]:
    """Every name the module actually reads, as an ``ast`` walk rather than a substring scan.

    A substring scan of a module whose docstring names the things it must not do reports the docstring,
    which is how a scan test passes for the wrong reason or fails for no reason.
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
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.FunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "\n" not in node.value:
            names.add(node.value)
    return frozenset(names)


def _validator(pointer: Sequence[str]) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / "dataset.v1.json").read_text(encoding="utf-8"))
    node = schema
    for step in pointer:
        node = node[step]
    return Draft202012Validator({**node, "$defs": schema["$defs"]})


# --------------------------------------------------------------------------------------------------
# The id, and what carries no cohort at all
# --------------------------------------------------------------------------------------------------
def test_the_cohort_id_is_the_five_segments_of_the_identifier_table() -> None:
    """18.7: ``co-<provider>-<category>-<subject>-<structure>-<horizon>``, at most 96 characters."""
    cohort_id = cohort_id_of(
        provider="kalshi",
        category="crypto",
        subject="bitcoin",
        structure="threshold-above",
        horizon="month",
    )
    assert cohort_id == "co-kalshi-crypto-bitcoin-threshold-above-month"
    assert RE_COHORT_ID.fullmatch(cohort_id) is not None
    # A subject with a digit is admitted by the table's third segment, and one with a dash by all three.
    assert cohort_id_of(
        provider="manifold", category="tech", subject="gpt4", structure="by-date", horizon="year-plus"
    ) == "co-manifold-tech-gpt4-by-date-year-plus"
    assert cohort_id_of(
        provider="kalshi", category="finance", subject="gold-silver", structure="range-band", horizon="week"
    ) == "co-kalshi-finance-gold-silver-range-band-week"
    # A value that cannot be spelled in an id yields no cohort here, rather than a seal-time failure on
    # dataset.v1.json's pattern or journal.v2.json's (ruling R288).
    assert cohort_id_of(
        provider="kalshi", category="crypto", subject="Bitcoin", structure="threshold-above", horizon="month"
    ) is None
    assert cohort_id_of(
        provider="kalshi", category="crypto", subject="bitcoin", structure="threshold_above", horizon="month"
    ) is None
    assert cohort_id_of(
        provider="kalshi",
        category="crypto",
        subject="s" * 90,
        structure="threshold-above",
        horizon="month",
    ) is None
    assert COHORT_ID_MAX_CHARS == 96


def test_platform_meta_and_other_belong_to_no_cohort() -> None:
    """18.5: a self-referential market is not a forecast, and a facet nothing decided is not a group."""
    for subject in ("platform-meta", "other", ""):
        assert cohort_id_of(
            provider="manifold",
            category="economics",
            subject=subject,
            structure="threshold-above",
            horizon="week",
        ) is None
    for structure in ("other", ""):
        assert cohort_id_of(
            provider="manifold", category="economics", subject="bitcoin", structure=structure, horizon="week"
        ) is None
    for horizon in ("other", ""):
        assert cohort_id_of(
            provider="manifold",
            category="economics",
            subject="bitcoin",
            structure="threshold-above",
            horizon=horizon,
        ) is None
    # And through the meta door, which is what MarketMeta.cohort_id is (7.2).
    assert cohort_id_for_meta(_meta("m1", fold="train", subject=("platform-meta",))) is None
    assert cohort_id_for_meta(_meta("m2", fold="train", subject=("other",))) is None
    assert cohort_id_for_meta(_meta("m3", fold="train", structure="other")) is None
    assert cohort_id_for_meta(_meta("m4", fold="train")) == "co-kalshi-crypto-bitcoin-threshold-above-month"
    # The markets are excluded from the cohorts and not from the dataset: the counts still see them.
    metas = [
        _meta("m1", fold="train", subject=("platform-meta",)),
        _meta("m2", fold="train", subject=("other",)),
        _meta("m3", fold="train"),
    ]
    found = list_cohorts(metas)
    assert len(found) == 1
    assert found[0].market_ids == ("m3",)


def test_a_market_belongs_to_exactly_one_cohort_keyed_on_the_primary_subject() -> None:
    """18.5: ``subject[0]``, the tagger's precedence order, and not one row per subject."""
    meta = _meta("m1", fold="train", subject=("bitcoin", "crypto-other", "ai-models", "single-equity"))
    assert cohort_key_of(meta) == ("kalshi", "crypto", "bitcoin", "threshold-above", "month")
    found = list_cohorts([meta])
    assert len(found) == 1
    assert found[0].subject == "bitcoin"
    assert found[0].n == 1
    # Reordering the subjects moves the market to another cohort, which is why 7.14 makes the order part
    # of the lexicon version (ruling R301) and why a reorder is a new dataset hash.
    reordered = replace(meta, subject=("ai-models", "bitcoin"))
    assert cohort_id_for_meta(reordered) == "co-kalshi-crypto-ai-models-threshold-above-month"


def test_a_meta_without_the_taxonomy_fields_belongs_to_no_cohort() -> None:
    """7.2: ``Dataset.cohorts`` is ``()`` on a dataset built before the taxonomy.

    The real ``pmx.types.MarketMeta`` is used here on purpose: the five taxonomy fields of 7.2 are
    18.8's deferral row for D1's file, so until they land every real meta reads untagged, and the answer
    a dataset built before the taxonomy must give is no cohort rather than a crash or a cohort of empty
    strings.
    """
    real = MarketMeta(
        id="kalshi-KXBTCMAXMON-26APR30-T80000",
        provider="kalshi",
        category="crypto",
        tags=("bitcoin", "month", "threshold-above"),
        event_key=None,
        created_at_ms=0,
        close_at_ms=1,
        resolved_at_ms=2,
        resolution=1,
        interval_min=1_440,
        n_bars=30,
        hardness_tags=(),
        fee_schedule_id="kalshi-general-2026-09",
        fold="train",
    )
    assert facets_of(real) == ((), "", "")
    assert cohort_key_of(real) is None
    assert cohort_id_for_meta(real) is None
    assert list_cohorts([real]) == ()
    # A field present and of the wrong type reads as untagged too, and lands in no cohort rather than in
    # a cohort whose id is a repr.
    assert facets_of(_meta("m", fold="train", subject=("bitcoin",))) == (
        ("bitcoin",),
        "threshold-above",
        "month",
    )


# --------------------------------------------------------------------------------------------------
# A cohort spans the folds (ruling R293)
# --------------------------------------------------------------------------------------------------
def test_a_cohort_has_no_fold_of_its_own_and_its_three_counts_are_what_the_folds_left() -> None:
    """Ruling R293, the sentence that replaced "a cohort never crosses a fold".

    Six markets of one cohort spread 3/2/1 over the folds. The cohort reports 3, 2 and 1; not one market
    moved, and the cohort carries no fold field at all. On the deleted reading, all six would have been
    pulled into one fold and the paired test the cohort exists for would be gone.
    """
    metas = [
        _meta("m1", fold="train"),
        _meta("m2", fold="train"),
        _meta("m3", fold="train"),
        _meta("m4", fold="validation"),
        _meta("m5", fold="validation"),
        _meta("m6", fold="sealed"),
    ]
    found = list_cohorts(metas)
    assert len(found) == 1
    cohort = found[0]
    assert (cohort.n_train, cohort.n_validation, cohort.n_sealed) == (3, 2, 1)
    assert cohort.n == 6
    assert cohort.market_ids == ("m1", "m2", "m3", "m4", "m5", "m6")
    assert not hasattr(cohort, "fold")
    assert "fold" not in cohort.to_dict()
    # And the folds the metas carry are untouched: listing cohorts moves no market.
    assert [meta.fold for meta in metas] == ["train", "train", "train", "validation", "validation", "sealed"]
    # A fold value the split never assigns is counted in none of the three, so a cohort's counts never
    # exceed its membership.
    stray = list_cohorts([*metas, _meta("m7", fold="all")])[0]
    assert (stray.n_train, stray.n_validation, stray.n_sealed) == (3, 2, 1)
    assert stray.n == 6
    assert len(stray.market_ids) == 7


def test_the_usable_flags_are_two_different_bars() -> None:
    """18.5 and decision D-S13: ``usable`` is the leaderboard bar, ``usable_for_paired_test`` the analysis
    bar, and a cohort can clear the first and fail the second.

    That is the whole reason the flag exists: on the prototype all six cohorts that reached ten markets
    sat entirely inside one fold, so a cohort can be big and carry neither a paired lower bound nor an
    out-of-time replication.
    """
    assert COHORT_MIN_TRAIN == 30
    # Thirty in train and one in each of the others: usable both ways.
    metas = [_meta(f"t{index}", fold="train") for index in range(30)]
    metas += [_meta("v1", fold="validation"), _meta("s1", fold="sealed")]
    good = list_cohorts(metas)[0]
    assert (good.n_train, good.usable, good.usable_for_paired_test) == (30, True, True)
    # One market fewer in train: not usable at all, which is the refusal below.
    fewer = list_cohorts(metas[1:])[0]
    assert (fewer.n_train, fewer.usable, fewer.usable_for_paired_test) == (29, False, False)
    # Thirty in train and an empty sealed fold: usable for a leaderboard row, not for a paired test.
    for missing in ("validation", "sealed"):
        subset = [meta for meta in metas if meta.fold != missing]
        cohort = list_cohorts(subset)[0]
        assert cohort.n_train == 30
        assert cohort.usable is True
        assert cohort.usable_for_paired_test is False, missing
    # A hundred markets all in the train fold: the prototype's defect, and the flag catches it.
    confined = list_cohorts([_meta(f"c{index}", fold="train") for index in range(100)])[0]
    assert confined.usable is True
    assert confined.usable_for_paired_test is False


# --------------------------------------------------------------------------------------------------
# The refusals (ruling R283)
# --------------------------------------------------------------------------------------------------
def test_a_cohort_below_the_minimum_or_with_an_empty_fold_is_refused_before_any_measurement() -> None:
    """18.5: ``cohort_or_refuse`` raises ``CohortRefusedError`` on three things and never weakens a bar."""
    usable = Cohort(
        cohort_id="co-kalshi-crypto-bitcoin-threshold-above-month",
        category="crypto",
        subject="bitcoin",
        structure="threshold-above",
        horizon="month",
        provider="kalshi",
        n_train=30,
        n_validation=4,
        n_sealed=6,
        usable=True,
        usable_for_paired_test=True,
        market_ids=(),
    )
    assert cohort_or_refuse([usable], usable.cohort_id) is usable
    with pytest.raises(CohortRefusedError, match="no cohort of this dataset carries that id"):
        cohort_or_refuse([usable], "co-kalshi-crypto-ethereum-threshold-above-month")
    small = replace(usable, n_train=29, usable=False, usable_for_paired_test=False)
    with pytest.raises(CohortRefusedError, match="below the minimum train fold"):
        cohort_or_refuse([small], small.cohort_id)
    unpaired = replace(usable, n_sealed=0, usable_for_paired_test=False)
    with pytest.raises(CohortRefusedError, match="empty fold carries no paired test"):
        cohort_or_refuse([unpaired], unpaired.cohort_id)
    # The error is its own class and a PmxError, so a caller pinning one does not catch a schema failure.
    assert issubclass(CohortRefusedError, PmxError)
    assert not issubclass(CohortRefusedError, SchemaError)
    with pytest.raises(CohortRefusedError):
        cohort_or_refuse([], usable.cohort_id)


def test_there_is_no_per_cohort_claim_surface_anywhere(tmp_path: Path) -> None:
    """Ruling R283: the ``--cohort`` flag, the claim body's ``cohort_id`` and the ledger field are deleted.

    A per-cohort sealed read is a second bite at the same sealed markets, and a genome that may claim
    each cohort separately can cherry-pick the one that cleared. The cohort statement is a row of the one
    claim instead, so this module offers no door that would take a claim per cohort, and neither does the
    claim path. Asserted by scan, because the way this comes back is somebody adding the convenient flag.
    """
    read = _names_read(SRC / "cohorts.py")
    for banned in ("claim", "sealed_market", "open_sealed_test", "access.jsonl", "claims"):
        assert banned not in read, banned
    # And no command-line or HTTP surface anywhere takes a cohort to claim.
    for path in (SRC / "optimizer" / "claims.py", SRC / "cli.py", SRC / "cli_run.py"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "--cohort" not in text, str(path)
    assert not (tmp_path / "nothing").exists()


# --------------------------------------------------------------------------------------------------
# The manifest rows, the histogram and the per-venue counts
# --------------------------------------------------------------------------------------------------
def test_the_manifest_row_is_every_field_but_the_market_ids_and_it_validates() -> None:
    """7.8 and 18.5: ``Cohort.to_dict`` is the manifest row, and ``market_ids`` is never in it.

    A manifest that listed the ids of every cohort would restate the whole market index once per facet
    combination, and the row's job is a count.
    """
    metas = [_meta(f"m{index}", fold="train") for index in range(3)]
    metas.append(_meta("mv", fold="validation"))
    cohort = list_cohorts(metas)[0]
    row = cohort.to_dict()
    assert "market_ids" not in row
    assert sorted(row) == [
        "category", "cohort_id", "horizon", "n_sealed", "n_train", "n_validation", "provider",
        "structure", "subject", "usable", "usable_for_paired_test",
    ]
    errors = list(_validator(("properties", "cohorts")).iter_errors([row]))
    assert errors == [], [error.message for error in errors]
    # cohort_rows is the manifest's list: sorted by id, one row each, and nothing else.
    many = list_cohorts(
        [
            _meta("a", fold="train", subject=("bitcoin",)),
            _meta("b", fold="train", subject=("ethereum",)),
            _meta("c", fold="train", subject=("gold-silver",), category="finance", provider="manifold"),
        ]
    )
    rows = cohort_rows(many)
    assert [entry["cohort_id"] for entry in rows] == sorted(str(entry["cohort_id"]) for entry in rows)
    assert list(_validator(("properties", "cohorts")).iter_errors(rows)) == []
    assert cohort_ids_by_market(many) == {
        "a": "co-kalshi-crypto-bitcoin-threshold-above-month",
        "b": "co-kalshi-crypto-ethereum-threshold-above-month",
        "c": "co-manifold-finance-gold-silver-threshold-above-month",
    }


def test_list_cohorts_is_sorted_and_is_the_one_implementation() -> None:
    """18.5: sorted by ``cohort_id``, so a manifest row and a loader object can never disagree on order."""
    metas = [
        _meta("m1", fold="train", subject=("ethereum",)),
        _meta("m2", fold="train", subject=("bitcoin",)),
        _meta("m3", fold="train", subject=("crypto-other",)),
    ]
    found = list_cohorts(metas)
    assert [cohort.cohort_id for cohort in found] == sorted(cohort.cohort_id for cohort in found)
    # And it is order-independent: shuffling the metas gives the identical tuple.
    assert list_cohorts(list(reversed(metas))) == found


def test_the_histogram_carries_every_bucket_and_the_measured_shape() -> None:
    """7.8: ``cohort_size_histogram``, zeros included.

    A histogram that omits its empty buckets reads as one whose buckets were chosen after the fact, and
    the headline measurement of decision D-S12 is exactly an empty bucket: zero cohorts of thirty or
    more over the 287 markets of the first build.
    """
    assert COHORT_SIZE_BUCKETS == ("1", "2-4", "5-9", "10-29", "30+")
    assert cohort_size_bucket(0) == "1"
    assert cohort_size_bucket(1) == "1"
    assert cohort_size_bucket(2) == "2-4"
    assert cohort_size_bucket(4) == "2-4"
    assert cohort_size_bucket(5) == "5-9"
    assert cohort_size_bucket(9) == "5-9"
    assert cohort_size_bucket(10) == "10-29"
    assert cohort_size_bucket(29) == "10-29"
    assert cohort_size_bucket(30) == "30+"
    assert cohort_size_bucket(1_000) == "30+"
    assert cohort_size_histogram(()) == dict.fromkeys(COHORT_SIZE_BUCKETS, 0)
    metas = [_meta("solo", fold="train", subject=("bitcoin",))]
    metas += [_meta(f"pair{index}", fold="train", subject=("ethereum",)) for index in range(3)]
    metas += [_meta(f"mid{index}", fold="train", subject=("gold-silver",)) for index in range(7)]
    histogram = cohort_size_histogram(list_cohorts(metas))
    assert histogram == {"1": 1, "2-4": 1, "5-9": 1, "10-29": 0, "30+": 0}
    assert sum(histogram.values()) == len(list_cohorts(metas))


def test_the_per_provider_count_is_of_usable_cohorts_only() -> None:
    """Decision D-S11: the venue targets are stated in **usable** cohorts (40 on Kalshi, 8 on Manifold).

    A venue with two hundred cohorts of one market has no comparison in it, so counting every non-empty
    cohort against the target would report a build as reaching a bar it does not reach.
    """
    metas = [_meta(f"k{index}", fold="train", subject=("bitcoin",)) for index in range(30)]
    metas += [_meta("k-small", fold="train", subject=("ethereum",))]
    metas += [
        _meta(f"m{index}", fold="train", subject=("bitcoin",), provider="manifold") for index in range(2)
    ]
    found = list_cohorts(metas)
    assert len(found) == 3
    assert len(usable_cohorts(found)) == 1
    assert cohorts_per_provider(found) == {"kalshi": 1}
    assert cohorts_per_provider(()) == {}


def test_the_cohort_module_imports_neither_the_gateway_nor_the_llm_package() -> None:
    """Architecture rule 12 (ruling R245), asserted here as well as in ``tests/test_architecture.py``.

    A tag decides which cohort a market lands in, so a cohort a model wrote would move a claim between
    two rebuilds. The module-level check is cheap and it fails in the file a reader is already looking at.
    """
    read = _names_read(Path(cohorts_module.__file__))
    for banned in ("pmx.gateway", "pmx.llm", "socket", "httpx", "requests", "urllib"):
        assert banned not in read, banned
    assert "pmx.errors" in read


def test_a_cohort_whose_markets_sit_outside_the_three_folds_is_usable_for_nothing() -> None:
    """17.6 and ruling R186: a continuous instrument carries ``fold = "all"`` and belongs to every fold.

    Such a meta is untagged today and therefore lands in no cohort at all, which the real-``MarketMeta``
    test above pins. This is the other half: if a meta ever reached the cohort code carrying facets and a
    fold outside 7.7's three, the cohort it forms counts it in none of the three and is refused by both
    bars rather than reported as a comparison of size zero.
    """
    metas = [_meta(f"c{index}", fold="all") for index in range(50)]
    cohort = list_cohorts(metas)[0]
    assert (cohort.n_train, cohort.n_validation, cohort.n_sealed) == (0, 0, 0)
    assert cohort.n == 0
    assert len(cohort.market_ids) == 50
    assert cohort.usable is False
    assert cohort.usable_for_paired_test is False
    with pytest.raises(CohortRefusedError, match="below the minimum train fold"):
        cohort_or_refuse([cohort], cohort.cohort_id)
