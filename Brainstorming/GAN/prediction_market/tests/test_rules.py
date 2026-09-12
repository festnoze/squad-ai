"""S2: the vocabulary, the rule record, the tester, the miner and the ledger (CONTRACTS_V2 18.2).

What these tests are for, in the order the package's done-when lists them and with the arbitration of
rulings R276 to R302 as the reading of record:

* **A rule's id is the statement and never the author.** The contract fixture's id recomputes from its own
  fields, two authors of one statement produce one rule, and a claim, a horizon or a support floor that
  differs produces a different id. The predicate grammar round-trips through canonical JSON, so a rule
  read back off a ledger line is the rule that was written.
* **The decision formula reads the direction and the kind** (ruling R280, correcting R240). The test that
  matters is the one that fails on the first version: a promoted "the price is too high" rule must move a
  belief **down**, and a volatility claim must move it not at all.
* **The family is written down before a single replicate row is read** (18.2 step 1), and a replicate test
  under a family with no earlier registration is refused. The order is asserted over the ledger's own
  append sequence, so registering after the fact fails the test rather than merely looking untidy.
* **Benjamini-Hochberg on a table anybody can check by hand** (ruling R238), and a p-value that can never
  be zero (ruling R282): the ``(b + 1) / (B + 1)`` estimator is what makes ``p`` comparable against
  ``k * q / m``.
* **Promotion is out of time.** A rule that holds on the fit fold and fails on the replicate fold is a
  recorded negative result, never an insight, and the same content is a duplicate the tester refuses to
  re-test on the same fold pair.
* **The live record is as-of** (ruling R276): its window is exactly ``[fit_t1_ms + interval_ms, b)``, it
  grows with ``b`` (a frozen record could never demote a decaying rule) and it never reaches past ``b``
  (an unbounded one would let month 11 demote what an agent trades in month ``k + 2``).
* **The rolling pair is clipped to the training fold** (ruling R277): no rolling replicate month may end
  after ``train_end_ms``, and ``k`` is an argument drawn from what the clip left.
* **AC-27**: the planted fixture yields the rule and its shuffled twin yields nothing. A fixture where
  both pass would be worthless, so the twin is the same document with one column permuted and both halves
  are asserted in one test.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path

import pytest

from pmx.cli_rules import _table as _cli_table
from pmx.cli_rules import main as rules_main
from pmx.errors import InvalidConfigError, NotConfiguredError, SchemaError
from pmx.journal import canonical_json, canonical_sha256
from pmx.metrics.stats import (
    _benjamini_hochberg_k,
    benjamini_hochberg,
    rule_permutation_p_ppm,
)
from pmx.rng import RngTree
from pmx.rules.miner import (
    MINER_OPS,
    RULE_MINER_BEAM,
    RULE_MINER_CANDIDATES_MAX,
    RULE_THRESHOLD_QUANTILES_PPM,
    mine,
    quantiles_ppm,
    template_of,
)
from pmx.rules.rule import (
    CLAIM_KINDS,
    PREDICATE_OPS,
    RE_FAMILY_ID,
    RE_RULE_ID,
    RULE_MIN_MARKETS,
    RULE_MIN_SUPPORT_DEFAULT,
    RULE_PREDICATES_MAX,
    Predicate,
    Rule,
    RuleClaim,
    RuleRefusedError,
    RuleScope,
    make_rule,
    rule_from_dict,
    rule_id_of,
    rule_shift_bp,
    shifted_belief_ppm,
)
from pmx.rules.tester import (
    FDR_Q_PPM,
    RULE_FAMILY_SCREENED_MAX,
    RULE_LIVE_MIN_SUPPORT,
    RULE_PERMUTATIONS_MAX,
    RULE_PERMUTATIONS_MIN,
    BarRow,
    FamilyTemplate,
    HypothesisFamily,
    MarketRows,
    Promotion,
    RowTable,
    RuleLedger,
    RuleTester,
    _median,
    family_id_of,
    headline_pair,
    load_row_table,
    mean_half_away,
    permutations_for,
    rolling_ks,
    rolling_pair,
    scope_rows,
    usual_bp_for,
)
from pmx.rules.vocabulary import (
    FEATURE_NAMES,
    FEATURES,
    FeatureBlock,
    catalogue_source,
    read_feature,
    sensors_for,
)
from pmx.types import (
    MS_PER_HOUR,
    PPM_ONE,
    PRICE_MAX_BP,
    PRICE_MIN_BP,
    MarketMeta,
    bp_ratio,
    default_horizons_bars,
    interval_ms,
    ppm_from_bp,
)


def _table_from_args(dataset: str) -> object:
    """The CLI's own row-table resolution, called directly so the refusal can be inspected."""
    import argparse

    return _cli_table(argparse.Namespace(dataset=dataset, rows=None))


REPO = Path(__file__).resolve().parent.parent
S2 = REPO / "tests" / "fixtures" / "s2"
CONTRACT = REPO / "tests" / "fixtures" / "contract"


# --------------------------------------------------------------------------------------------------
# The vocabulary (18.1's catalogue, read by 18.2's predicates)
# --------------------------------------------------------------------------------------------------
def test_the_vocabulary_is_the_union_of_the_catalogues_feature_names() -> None:
    """18.1: ``FEATURE_NAMES`` is exactly the union of ``spec.features[*].name``, unique across sensors."""
    catalogue = json.loads((CONTRACT / "sensor.catalogue.json").read_text(encoding="utf-8"))
    expected = [feature["name"] for spec in catalogue["sensors"] for feature in spec["features"]]
    assert len(expected) == len(set(expected)), "a feature name occurs under two sensors"
    assert tuple(sorted(expected)) == FEATURE_NAMES
    assert len(FEATURE_NAMES) == 75, "the shipped catalogue carries seventy-five features"


def test_every_feature_knows_its_sensor_its_bounds_and_its_sentinel() -> None:
    catalogue = json.loads((CONTRACT / "sensor.catalogue.json").read_text(encoding="utf-8"))
    for spec in catalogue["sensors"]:
        for position, feature in enumerate(spec["features"]):
            ref = FEATURES[feature["name"]]
            assert ref.sensor == spec["name"]
            assert ref.index == position == feature["index"]
            assert (ref.lo, ref.hi, ref.sentinel) == (feature["lo"], feature["hi"], feature["sentinel"])
            assert ref.lo <= ref.sentinel <= ref.hi


def test_the_catalogue_source_is_named_so_a_reader_knows_which_table_was_read() -> None:
    """S1 ships ``pmx.sensors.catalogue``; until then the normative contract fixture is the table."""
    assert catalogue_source() in ("pmx.sensors.catalogue", "tests/fixtures/contract/sensor.catalogue.json")


def test_reading_a_feature_answers_none_for_an_unbought_sensor_and_the_sentinel_for_a_missing_input() -> None:
    blocks = {"tape": FeatureBlock(sensor="tape", values=(5000,) + (0,) * 10)}
    assert read_feature("last_price_bp", blocks) == 5000
    assert read_feature("ret_7b_bp", blocks) == 0, "a missing input is the sentinel, an ordinary integer"
    assert read_feature("hn_story_points", blocks) is None, "an unbought sensor is absent, not zero"
    assert read_feature("not_a_feature", blocks) is None


def test_sensors_for_is_sorted_unique_and_ignores_a_name_outside_the_catalogue() -> None:
    assert sensors_for(("last_price_bp", "bars_to_close", "ret_7b_bp")) == ("calendar", "tape")
    assert sensors_for(("not_a_feature",)) == ()


# --------------------------------------------------------------------------------------------------
# The record: the id, the grammar and the refusals
# --------------------------------------------------------------------------------------------------
def _sample_rule() -> Rule:
    return rule_from_dict(json.loads((CONTRACT / "rule.sample.json").read_text(encoding="utf-8")))


def test_the_contract_fixtures_id_recomputes_from_its_own_fields() -> None:
    payload = json.loads((CONTRACT / "rule.sample.json").read_text(encoding="utf-8"))
    rule = _sample_rule()
    assert rule.rule_id == payload["rule_id"]
    assert RE_RULE_ID.match(rule.rule_id)
    assert rule.rule_id == rule_id_of(
        rule.scope, rule.condition, rule.claim, rule.horizon_bars, rule.min_support
    )


def test_the_id_is_the_statement_and_never_the_author() -> None:
    """18.2: two authors proposing the same statement produce one rule."""
    first = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=1_000,
        scope=RuleScope(kinds=("binary",)),
        condition=[Predicate(feature="last_price_bp", op="gt", value=7000)],
        claim=RuleClaim(kind="bias", direction=-1, magnitude_bp=1200, factor_ppm=0),
        horizon_bars=0,
    )
    second = make_rule(
        author_kind="agent",
        author_id="calibrator-0a1b2c3d",
        born_at_ms=99_000,
        scope=RuleScope(kinds=("binary",)),
        condition=[Predicate(feature="last_price_bp", op="gt", value=7000)],
        claim=RuleClaim(kind="bias", direction=-1, magnitude_bp=1200, factor_ppm=0),
        horizon_bars=0,
    )
    assert first.rule_id == second.rule_id


@pytest.mark.parametrize(
    "changed",
    [
        {"scope": RuleScope(kinds=("binary",), providers=("kalshi",))},
        {"condition": [Predicate(feature="last_price_bp", op="gt", value=7001)]},
        {"claim": RuleClaim(kind="bias", direction=1, magnitude_bp=1200, factor_ppm=0)},
        {"min_support": 31},
    ],
)
def test_every_hashed_field_moves_the_id(changed: Mapping[str, object]) -> None:
    """The id covers the scope, the condition, the claim, the horizon and the support floor (18.2)."""
    base = {
        "author_kind": "miner",
        "author_id": "miner",
        "born_at_ms": 1_000,
        "scope": RuleScope(kinds=("binary",)),
        "condition": [Predicate(feature="last_price_bp", op="gt", value=7000)],
        "claim": RuleClaim(kind="bias", direction=-1, magnitude_bp=1200, factor_ppm=0),
        "horizon_bars": 0,
    }
    original = make_rule(**base)  # type: ignore[arg-type]
    assert make_rule(**{**base, **changed}).rule_id != original.rule_id  # type: ignore[arg-type]


def test_the_horizon_moves_the_id_too() -> None:
    condition = [Predicate(feature="last_price_bp", op="gt", value=7000)]
    claim = RuleClaim(kind="drift", direction=1, magnitude_bp=200, factor_ppm=0)
    one = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=0,
        scope=RuleScope(),
        condition=condition,
        claim=claim,
        horizon_bars=1,
    )
    seven = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=0,
        scope=RuleScope(),
        condition=condition,
        claim=claim,
        horizon_bars=7,
    )
    assert one.rule_id != seven.rule_id


def test_the_predicate_grammar_round_trips_through_canonical_json() -> None:
    rule = _sample_rule()
    line = canonical_json(rule.to_dict())
    back = rule_from_dict(json.loads(line))
    assert back == rule
    assert canonical_json(back.to_dict()) == line


def test_a_rule_read_back_off_a_ledger_line_is_the_rule_that_was_written(tmp_path: Path) -> None:
    rule = _sample_rule()
    path = tmp_path / "line.jsonl"
    path.write_text(canonical_json({"rule": rule.to_dict()}) + "\n", encoding="utf-8")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert rule_from_dict(payload["rule"]).rule_id == rule.rule_id


@pytest.mark.parametrize(
    "payload",
    [
        {"feature": "not_a_feature", "op": "gt", "value": 1},
        {"feature": "last_price_bp", "op": "between", "value": 1},
        {"feature": "last_price_bp", "op": "gt", "value": 10_001},
        {"feature": "last_price_bp", "op": "gt", "value": -1},
        {"feature": "ret_7b_bp", "op": "gt", "value": 10_001},
    ],
)
def test_a_predicate_outside_the_vocabulary_the_operators_or_the_bounds_is_refused(
    payload: Mapping[str, object],
) -> None:
    with pytest.raises(RuleRefusedError):
        Predicate(**payload)  # type: ignore[arg-type]


def test_a_fourth_predicate_is_refused() -> None:
    condition = [
        Predicate(feature="last_price_bp", op="gt", value=1000),
        Predicate(feature="bars_to_close", op="le", value=7),
        Predicate(feature="ret_7b_bp", op="gt", value=100),
        Predicate(feature="spread_bp", op="le", value=50),
    ]
    assert len(condition) == RULE_PREDICATES_MAX + 1
    with pytest.raises(RuleRefusedError):
        make_rule(
            author_kind="miner",
            author_id="miner",
            born_at_ms=0,
            scope=RuleScope(),
            condition=condition,
            claim=RuleClaim(kind="bias", direction=1, magnitude_bp=100, factor_ppm=0),
            horizon_bars=0,
        )


def test_a_duplicate_feature_and_operator_pair_is_refused() -> None:
    with pytest.raises(RuleRefusedError):
        make_rule(
            author_kind="miner",
            author_id="miner",
            born_at_ms=0,
            scope=RuleScope(),
            condition=[
                Predicate(feature="last_price_bp", op="gt", value=1000),
                Predicate(feature="last_price_bp", op="gt", value=2000),
            ],
            claim=RuleClaim(kind="bias", direction=1, magnitude_bp=100, factor_ppm=0),
            horizon_bars=0,
        )


def test_an_unsorted_condition_is_refused_because_it_would_be_a_second_id() -> None:
    condition = (
        Predicate(feature="ret_7b_bp", op="gt", value=100),
        Predicate(feature="bars_to_close", op="le", value=7),
    )
    claim = RuleClaim(kind="bias", direction=1, magnitude_bp=100, factor_ppm=0)
    with pytest.raises(RuleRefusedError):
        Rule(
            rule_id=rule_id_of(RuleScope(), condition, claim, 0, RULE_MIN_SUPPORT_DEFAULT),
            author_kind="miner",
            author_id="miner",
            born_at_ms=0,
            scope=RuleScope(),
            condition=condition,
            claim=claim,
            horizon_bars=0,
            min_support=RULE_MIN_SUPPORT_DEFAULT,
        )


@pytest.mark.parametrize(
    ("kind", "direction", "magnitude_bp", "factor_ppm", "horizon_bars"),
    [
        ("drift", 1, 100, 0, 0),
        ("volatility", 0, 0, 1_000_000, 0),
        ("bias", 1, 0, 0, 0),
        ("drift", 1, 0, 0, 3),
        ("bias", 0, 100, 0, 0),
        ("volatility", 1, 0, 1_000_000, 3),
        ("bias", 1, 100, 0, 3),
    ],
)
def test_the_claim_kind_fixes_the_horizon_the_direction_and_the_magnitude(
    kind: str, direction: int, magnitude_bp: int, factor_ppm: int, horizon_bars: int
) -> None:
    with pytest.raises(RuleRefusedError):
        make_rule(
            author_kind="miner",
            author_id="miner",
            born_at_ms=0,
            scope=RuleScope(),
            condition=[Predicate(feature="last_price_bp", op="gt", value=1000)],
            claim=RuleClaim(
                kind=kind, direction=direction, magnitude_bp=magnitude_bp, factor_ppm=factor_ppm
            ),
            horizon_bars=horizon_bars,
        )


def test_a_support_floor_below_the_default_is_refused() -> None:
    with pytest.raises(RuleRefusedError):
        make_rule(
            author_kind="miner",
            author_id="miner",
            born_at_ms=0,
            scope=RuleScope(),
            condition=[Predicate(feature="last_price_bp", op="gt", value=1000)],
            claim=RuleClaim(kind="bias", direction=1, magnitude_bp=100, factor_ppm=0),
            horizon_bars=0,
            min_support=RULE_MIN_SUPPORT_DEFAULT - 1,
        )


def test_a_rule_id_that_is_not_the_hash_of_the_statement_is_refused() -> None:
    payload = json.loads((CONTRACT / "rule.sample.json").read_text(encoding="utf-8"))
    payload["rule_id"] = "ru-0000000000000000"
    with pytest.raises(RuleRefusedError):
        rule_from_dict(payload)


def test_an_unsorted_scope_tuple_is_refused() -> None:
    with pytest.raises(RuleRefusedError):
        RuleScope(providers=("manifold", "kalshi"))


def test_the_constants_are_the_contract_numbers() -> None:
    assert RULE_PREDICATES_MAX == 3
    assert PREDICATE_OPS == ("lt", "le", "gt", "ge", "eq", "ne")
    assert CLAIM_KINDS == ("bias", "drift", "volatility")
    assert RULE_MIN_SUPPORT_DEFAULT == 30
    assert FDR_Q_PPM == 50_000
    assert (RULE_PERMUTATIONS_MIN, RULE_PERMUTATIONS_MAX) == (200, 20_000)
    assert RULE_FAMILY_SCREENED_MAX == 1_000
    assert RULE_LIVE_MIN_SUPPORT == 30
    assert (RULE_MINER_BEAM, RULE_MINER_CANDIDATES_MAX) == (32, 10_000)
    assert RULE_THRESHOLD_QUANTILES_PPM == (100_000, 250_000, 500_000, 750_000, 900_000)
    assert set(MINER_OPS) <= set(PREDICATE_OPS)


# --------------------------------------------------------------------------------------------------
# fires, readable_by and the diet (ruling R279)
# --------------------------------------------------------------------------------------------------
def _meta(**changed: object) -> MarketMeta:
    base: dict[str, object] = {
        "id": "kx-1",
        "provider": "kalshi",
        "category": "politics",
        "tags": ("election",),
        "event_key": None,
        "created_at_ms": 0,
        "close_at_ms": 10 * MS_PER_HOUR,
        "resolved_at_ms": 10 * MS_PER_HOUR,
        "resolution": 1,
        "interval_min": 60,
        "n_bars": 5,
        "hardness_tags": (),
        "fee_schedule_id": "kalshi_v1",
        "fold": "train",
        "kind": "binary",
    }
    base.update(changed)
    return MarketMeta(**base)  # type: ignore[arg-type]


def _hn_rule() -> Rule:
    return make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=0,
        scope=RuleScope(),
        condition=[Predicate(feature="hn_story_points", op="gt", value=10)],
        claim=RuleClaim(kind="bias", direction=1, magnitude_bp=100, factor_ppm=0),
        horizon_bars=0,
    )


def test_a_rule_whose_sensor_is_absent_does_not_fire_and_never_raises() -> None:
    """Ruling R279: ``fires`` reads the blocks it is handed and is total."""
    rule = _hn_rule()
    tape_only = {"tape": FeatureBlock(sensor="tape", values=(5000,) + (0,) * 10)}
    assert rule.fires(tape_only, _meta()) is False
    assert rule.readable_by(("tape", "calendar")) is False
    assert rule.readable_by(("tape", "hn")) is True
    with_hn = dict(tape_only)
    with_hn["hn"] = FeatureBlock(sensor="hn", values=(50, 0, 0, 0, 0))
    assert rule.fires(with_hn, _meta()) is True


def test_required_sensors_is_what_a_diet_must_carry() -> None:
    assert _hn_rule().required_sensors == ("hn",)
    assert _sample_rule().required_sensors == ("calendar", "tape")


def test_the_scope_narrows_by_kind_provider_category_and_tags() -> None:
    rule = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=0,
        scope=RuleScope(kinds=("binary",), providers=("kalshi",), categories=("politics",), tags=("election",)),
        condition=[Predicate(feature="last_price_bp", op="gt", value=1000)],
        claim=RuleClaim(kind="bias", direction=1, magnitude_bp=100, factor_ppm=0),
        horizon_bars=0,
    )
    blocks = {"tape": FeatureBlock(sensor="tape", values=(5000,) + (0,) * 10)}
    assert rule.fires(blocks, _meta()) is True
    assert rule.fires(blocks, _meta(provider="manifold")) is False
    assert rule.fires(blocks, _meta(category="crypto")) is False
    assert rule.fires(blocks, _meta(tags=())) is False
    assert rule.fires(blocks, _meta(kind="perp")) is False


def test_a_scope_that_names_a_cohort_matches_nothing_until_a_meta_carries_one() -> None:
    """18.5's ``cohort_id`` reaches ``MarketMeta`` in DS2's lot; a scope may not claim what it cannot read."""
    rule = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=0,
        scope=RuleScope(cohorts=("co-kalshi-politics-election-threshold-week",)),
        condition=[Predicate(feature="last_price_bp", op="gt", value=1000)],
        claim=RuleClaim(kind="bias", direction=1, magnitude_bp=100, factor_ppm=0),
        horizon_bars=0,
    )
    blocks = {"tape": FeatureBlock(sensor="tape", values=(5000,) + (0,) * 10)}
    assert rule.fires(blocks, _meta()) is False


@pytest.mark.parametrize(
    ("op", "value", "expected"),
    [
        ("lt", 5000, False),
        ("le", 5000, True),
        ("gt", 4999, True),
        ("ge", 5001, False),
        ("eq", 5000, True),
        ("ne", 5000, False),
    ],
)
def test_every_operator_of_the_grammar_compares_as_it_reads(op: str, value: int, expected: bool) -> None:
    assert Predicate(feature="last_price_bp", op=op, value=value).holds(5000) is expected


# --------------------------------------------------------------------------------------------------
# The decision formula (ruling R280, correcting ruling R240)
# --------------------------------------------------------------------------------------------------
DOWN = RuleClaim(kind="bias", direction=-1, magnitude_bp=1200, factor_ppm=0)
UP = RuleClaim(kind="bias", direction=1, magnitude_bp=1200, factor_ppm=0)
VOLATILITY = RuleClaim(kind="volatility", direction=0, magnitude_bp=0, factor_ppm=1_500_000)


def test_a_promoted_down_rule_lowers_the_belief_and_the_first_formula_raised_it() -> None:
    """Ruling R280. ``y_row`` is already multiplied by ``direction`` and promotion needs a positive lower
    bound, so a promoted "the price is too high" rule carries a **positive** ``lift_bp``. The first
    spelling, ``sum(lift_bp * weight_permille // 1_000)``, therefore moved the belief up."""
    naive = 800 * 1_000 // 1_000
    corrected = rule_shift_bp([(DOWN, 800)], weight_permille=1_000)
    assert naive == 800
    assert corrected == -800, "the direction multiplies the rounded magnitude"
    assert shifted_belief_ppm(5_000, corrected) < ppm_from_bp(5_000)
    assert shifted_belief_ppm(5_000, naive) > ppm_from_bp(5_000), "what the first version did"


def test_a_down_rule_and_its_mirror_shift_by_equal_amounts() -> None:
    """The direction multiplies the rounded magnitude; rounding the signed product would not agree."""
    assert rule_shift_bp([(DOWN, 777)], weight_permille=500) == -rule_shift_bp(
        [(UP, 777)], weight_permille=500
    )
    assert rule_shift_bp([(DOWN, 777)], weight_permille=500) == -(777 * 500 // 1_000)


def test_a_volatility_insight_enters_no_belief() -> None:
    assert rule_shift_bp([(VOLATILITY, 900)], weight_permille=1_000) == 0
    assert rule_shift_bp([(VOLATILITY, 900), (UP, 100)], weight_permille=1_000) == 100


def test_the_kind_filter_is_a_second_lock_and_not_a_restatement_of_the_direction() -> None:
    """Ruling R280 asks for both halves: the direction **and** the ``bias``-or-``drift`` filter.

    A ``RuleClaim`` built through its constructor always carries ``direction = 0`` on a volatility claim,
    so the arithmetic alone would answer zero and the filter would look redundant. It is not: a claim
    reaching a belief comes off a ledger line, a hive payload or another package, and a record that
    skipped validation is exactly the case a filter is for. This one is built past ``__post_init__``, the
    only way to see the lock work.
    """
    rogue = RuleClaim.__new__(RuleClaim)
    for field, value in (("kind", "volatility"), ("direction", 1), ("magnitude_bp", 0), ("factor_ppm", 1)):
        object.__setattr__(rogue, field, value)
    assert rogue.kind == "volatility" and rogue.direction == 1
    assert rule_shift_bp([(rogue, 900)], weight_permille=1_000) == 0


def test_the_shift_sums_over_the_firing_insights_and_clamps_the_belief() -> None:
    assert rule_shift_bp([(UP, 300), (DOWN, 100)], weight_permille=1_000) == 200
    assert shifted_belief_ppm(9_900, 5_000) == ppm_from_bp(PRICE_MAX_BP), "the price clamp of section 1"
    assert shifted_belief_ppm(100, -5_000) == ppm_from_bp(PRICE_MIN_BP)


# --------------------------------------------------------------------------------------------------
# Benjamini-Hochberg and the rule path's null
# --------------------------------------------------------------------------------------------------
def test_benjamini_hochberg_on_a_hand_computable_table() -> None:
    """``m = 4``, ``q = 50_000`` ppm. Sorted: 1_000, 20_000, 30_000, 900_000.

    ``k = 4``: 900_000 * 4 = 3_600_000 > 200_000. ``k = 3``: 30_000 * 4 = 120_000 <= 150_000, so ``k = 3``
    and the cutoff is 30_000: the first three are rejections and the fourth is not.
    """
    p_values = [30_000, 900_000, 1_000, 20_000]
    assert benjamini_hochberg(p_values) == (True, False, True, True)
    assert _benjamini_hochberg_k(p_values) == 3


def test_benjamini_hochberg_passes_nothing_when_no_k_exists() -> None:
    assert benjamini_hochberg([60_000, 70_000]) == (False, False)
    assert _benjamini_hochberg_k([60_000, 70_000]) == 0
    assert benjamini_hochberg([]) == ()


def test_benjamini_hochberg_is_less_strict_than_bonferroni_and_stricter_than_no_control() -> None:
    p_values = [5_000, 9_000, 12_000, 400_000, 800_000]
    flags = benjamini_hochberg(p_values)
    assert flags == (True, True, True, False, False)
    bonferroni = [p * len(p_values) <= FDR_Q_PPM for p in p_values]
    assert sum(flags) >= sum(bonferroni)
    assert sum(flags) < len(p_values)


def test_the_permutation_p_value_is_never_zero_and_uses_the_b_plus_one_estimator() -> None:
    """Ruling R282: a permutation test may not report ``p = 0``, or it cannot be compared to ``k * q / m``."""
    y_rows = [1_000] * 10 + [-1_000] * 10
    fired = [True] * 10 + [False] * 10
    blocks = ["w2024-01"] * 20
    p = rule_permutation_p_ppm(y_rows, fired, blocks, rng=RngTree(3), permutations=200)
    assert p > 0
    assert p >= 1_000_000 // (200 + 1)


def test_the_permutation_null_is_deterministic_and_answers_nothing_when_nothing_is_planted() -> None:
    """The matched rows carry both signs, so the observed mean is the pool's and luck reaches it often."""
    y_rows = [10, -10, -10, 10, 10, -10, -10, 10]
    fired = [True, True, False, False, True, True, False, False]
    blocks = ["b1"] * 4 + ["b2"] * 4
    first = rule_permutation_p_ppm(y_rows, fired, blocks, rng=RngTree(11), permutations=200)
    second = rule_permutation_p_ppm(y_rows, fired, blocks, rng=RngTree(11), permutations=200)
    assert first == second, "two trees on one seed give one p-value"
    assert 100_000 < first < 1_000_000
    planted = rule_permutation_p_ppm(
        [10, 10, -10, -10] * 2, [True, True, False, False] * 2, blocks, rng=RngTree(11), permutations=200
    )
    assert planted < first, "a real association is rarer under the null than a coin flip"


def test_the_permutation_shuffles_inside_a_block_and_never_across_two() -> None:
    """Ruling R282: every block keeps the number of rows the rule matched in it.

    Both blocks here are pure, one all matched and one all unmatched, so a within-block shuffle can only
    rebuild the observed mean and the p-value is one: luck reaches it every time, which is the honest
    answer when the block structure alone explains the match. A shuffle across blocks would move matched
    labels onto the other block's rows, make the observed mean look extreme and report a small p-value on
    a rule that discovered nothing but its own blocks.
    """
    y_rows = [100] * 4 + [-100] * 4
    fired = [True] * 4 + [False] * 4
    within = rule_permutation_p_ppm(
        y_rows, fired, ["b1"] * 4 + ["b2"] * 4, rng=RngTree(2), permutations=200
    )
    assert within == PPM_ONE
    across = rule_permutation_p_ppm(y_rows, fired, ["b"] * 8, rng=RngTree(2), permutations=200)
    assert across < within // 2


def test_the_permutation_count_follows_the_family() -> None:
    assert permutations_for(0) == RULE_PERMUTATIONS_MIN
    assert permutations_for(10) == RULE_PERMUTATIONS_MIN
    assert permutations_for(50) == 1_000
    assert permutations_for(10_000) == RULE_PERMUTATIONS_MAX


# --------------------------------------------------------------------------------------------------
# A hand-built row table: the folds, the family and the whole procedure
# --------------------------------------------------------------------------------------------------
def _blocks(price_bp: int, feature_bp: int, bars_to_close: int, position: int) -> dict[str, FeatureBlock]:
    tape = [0] * 11
    tape[0] = price_bp
    tape[3] = feature_bp
    calendar = [0] * 7
    calendar[0] = bars_to_close
    calendar[2] = position
    return {
        "tape": FeatureBlock(sensor="tape", values=tuple(tape)),
        "calendar": FeatureBlock(sensor="calendar", values=tuple(calendar)),
    }


def _market(
    market_id: str,
    *,
    resolved_at_ms: int,
    fold: str,
    ups: Sequence[bool],
    resolution: int = 1,
    step_bp: int = 120,
) -> MarketRows:
    bars: list[BarRow] = []
    price = 5_000
    for position, up in enumerate(ups):
        bars.append(
            BarRow(
                t_ms=resolved_at_ms - (len(ups) - position) * MS_PER_HOUR,
                close_bp=price,
                blocks=_blocks(price, 400 if up else -400, len(ups) - position, position),
            )
        )
        price += step_bp if up else -step_bp
    return MarketRows(
        meta=_meta(
            id=market_id,
            resolved_at_ms=resolved_at_ms,
            close_at_ms=resolved_at_ms,
            created_at_ms=bars[0].t_ms - MS_PER_HOUR,
            fold=fold,
            resolution=resolution,
            n_bars=len(bars),
        ),
        bars=tuple(bars),
        block=f"blk-{market_id}",
        fold_key_ms=resolved_at_ms,
    )


@lru_cache(maxsize=8)
def _table(*, months: int = 9, per_month: int = 8, bars: int = 12, steps: tuple[int, ...] = ()) -> RowTable:
    """A small planted world, built in the test rather than read: months, folds, prices and one feature.

    One feature says which way the next bar goes and nothing else does: the walk is a coin flip, so no
    price level, no bar index and no past move predicts it. The draw takes bit 16 of a linear congruential
    stream rather than its low bit, whose period is two and which would plant a second, unintended
    regularity that the miner would find before the real one.
    """
    day = 86_400_000
    start = 1_704_067_200_000
    edges = tuple(start + ((k * 365) // 12) * day for k in range(13))
    train_end = edges[6]
    validation_end = edges[8]
    markets: list[MarketRows] = []
    seed = 1
    for month in range(1, months + 1):
        for index in range(per_month):
            resolved = edges[month - 1] + (2 + 2 * index) * day + 12 * 3_600_000
            pattern: list[bool] = []
            for _position in range(bars):
                seed = (seed * 1_103_515_245 + 12_345) % 2_147_483_648
                pattern.append(bool((seed >> 16) & 1))
            fold = "train" if resolved < train_end else ("validation" if resolved < validation_end else "sealed")
            markets.append(
                _market(
                    f"kx-{month:02d}-{index:02d}",
                    resolved_at_ms=resolved,
                    fold=fold,
                    ups=pattern,
                    resolution=index % 2,
                    step_bp=steps[month - 1] if steps else 120,
                )
            )
    from pmx.types import DatasetSplit

    split = DatasetSplit(
        month_edges_ms=edges,
        train_end_ms=train_end,
        validation_end_ms=validation_end,
        n_train=sum(1 for rows in markets if rows.meta.fold == "train"),
        n_validation=sum(1 for rows in markets if rows.meta.fold == "validation"),
        n_sealed=sum(1 for rows in markets if rows.meta.fold == "sealed"),
    )
    return RowTable(
        dataset_hash="a" * 64,
        interval_min=60,
        split=split,
        markets=tuple(sorted(markets, key=lambda rows: rows.meta.id)),
    )


def _drift_rule(born_at_ms: int, *, value: int = 300, min_support: int = 30) -> Rule:
    return make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=born_at_ms,
        scope=RuleScope(kinds=("binary",), providers=("kalshi",)),
        condition=[Predicate(feature="ret_7b_bp", op="gt", value=value)],
        claim=RuleClaim(kind="drift", direction=1, magnitude_bp=120, factor_ppm=0),
        horizon_bars=1,
        min_support=min_support,
    )


def _template() -> FamilyTemplate:
    return FamilyTemplate(
        scope_keys=("kinds", "providers"),
        features=("ret_7b_bp",),
        claim_kind="drift",
        horizon_bars=1,
        author_kind="miner",
    )


class _RecordingLedger(RuleLedger):
    """A ledger that remembers the order of its appends, so a test can assert what came first."""

    def __init__(self, root: Path, dataset_hash: str) -> None:
        super().__init__(root=root, dataset_hash=dataset_hash)
        self.order: list[str] = []

    def append(self, path: Path, payload: Mapping[str, object]) -> str:
        self.order.append(f"{path.name}:{payload.get('type')}:{payload.get('stage', '')}")
        return super().append(path, payload)


def test_the_rolling_pairs_are_clipped_to_the_training_fold() -> None:
    """Ruling R277: no rolling replicate month may end after ``train_end_ms``."""
    table = _table()
    available = rolling_ks(table.split)
    assert available == (4, 5), "months 1..6 are the training fold, so k of 6 and above is clipped away"
    for k in available:
        assert table.split.month_edges_ms[k + 1] <= table.split.train_end_ms
        pair = rolling_pair(table, k)
        for market_id in pair.replicate_ids:
            rows = next(row for row in table.markets if row.meta.id == market_id)
            assert rows.meta.fold == "train", "a rolling replicate month is inside the training fold"
    with pytest.raises(InvalidConfigError):
        rolling_pair(table, 6)


def test_the_two_fold_anchors_are_properties_of_the_fold_and_bound_what_a_promotion_reads() -> None:
    table = _table()
    pair = rolling_pair(table, 4)
    last_replicate_bar = max(
        rows.bars[-1].t_ms for rows in table.markets if rows.meta.id in set(pair.replicate_ids)
    )
    assert pair.fit_t1_ms >= last_replicate_bar
    assert pair.registered_at_ms < pair.fit_t1_ms
    for market_id in pair.fit_ids:
        rows = next(row for row in table.markets if row.meta.id == market_id)
        assert rows.bars[-1].t_ms <= pair.registered_at_ms


def test_the_headline_pair_is_train_and_validation() -> None:
    table = _table()
    pair = headline_pair(table)
    assert (pair.fit_fold, pair.replicate_fold) == ("train", "validation")
    folds = {
        market_id: next(row for row in table.markets if row.meta.id == market_id).meta.fold
        for market_id in pair.replicate_ids
    }
    assert set(folds.values()) == {"validation"}


def test_the_family_id_names_the_data_and_not_only_the_grammar(tmp_path: Path) -> None:
    """Ruling R284: three runs on one dataset are three families, and each ledger row names its pair."""
    table = _table()
    template = _template()
    four = rolling_pair(table, 4)
    five = rolling_pair(table, 5)
    head = headline_pair(table)
    ids = {
        family_id_of(
            dataset_hash=table.dataset_hash,
            generation=0,
            fit_fold=pair.fit_fold,
            replicate_fold=pair.replicate_fold,
            registered_at_ms=pair.registered_at_ms,
            fit_t1_ms=pair.fit_t1_ms,
            template=template,
        )
        for pair in (four, five, head)
    }
    assert len(ids) == 3
    other_dataset = family_id_of(
        dataset_hash="b" * 64,
        generation=0,
        fit_fold=four.fit_fold,
        replicate_fold=four.replicate_fold,
        registered_at_ms=four.registered_at_ms,
        fit_t1_ms=four.fit_t1_ms,
        template=template,
    )
    assert other_dataset not in ids
    for family_id in ids:
        assert RE_FAMILY_ID.match(family_id)


def test_a_family_whose_id_is_not_the_hash_of_its_fields_is_refused() -> None:
    with pytest.raises(RuleRefusedError):
        HypothesisFamily(
            family_id="hf-0000000000000000",
            dataset_hash="a" * 64,
            generation=0,
            fit_fold="m1..m4",
            replicate_fold="m5",
            template=_template(),
            n_candidates=1,
            n_screened=1,
            fit_t1_ms=2,
            registered_at_ms=1,
        )


def test_the_family_is_registered_before_any_replicate_row_is_read(tmp_path: Path) -> None:
    """18.2 step 1, asserted over the ledger's own append order."""
    table = _table()
    pair = rolling_pair(table, 4)
    ledger = _RecordingLedger(tmp_path, table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    result = tester.run_family(
        [_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=1
    )
    assert result.promotions, "the planted effect must promote, or the order below is vacuous"
    registered = ledger.order.index("families.jsonl:family_registered:")
    replicated = ledger.order.index("rules.jsonl:rule_tested:replicate")
    assert registered < replicated
    assert ledger.order.index("rules.jsonl:rule_tested:fit") < registered


def test_a_replicate_test_under_an_unregistered_family_is_refused(tmp_path: Path) -> None:
    """18.2 step 1: the tester refuses to replicate a rule whose family was written down afterwards."""
    table = _table()
    pair = rolling_pair(table, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    rule = _drift_rule(pair.registered_at_ms)
    unregistered = family_id_of(
        dataset_hash=table.dataset_hash,
        generation=0,
        fit_fold=pair.fit_fold,
        replicate_fold=pair.replicate_fold,
        registered_at_ms=pair.registered_at_ms,
        fit_t1_ms=pair.fit_t1_ms,
        template=_template(),
    )
    with pytest.raises(RuleRefusedError) as refused:
        tester.test_on_fold(
            rule, pair, stage="replicate", family_id=unregistered, ids=pair.replicate_ids
        )
    assert refused.value.context["reason"] == "unregistered_family"
    family = tester.register_family(_template(), pair, n_candidates=1, n_screened=1)
    assert family.family_id == unregistered
    record, _rows = tester.test_on_fold(
        rule, pair, stage="replicate", family_id=unregistered, ids=pair.replicate_ids
    )
    assert record.support > 0


def test_a_family_nobody_can_resolve_is_refused_rather_than_tested(tmp_path: Path) -> None:
    """Ruling R282: ``n_screened`` above ``RULE_PERMUTATIONS_MAX * FDR_Q_PPM // PPM_ONE`` is a split."""
    table = _table()
    pair = rolling_pair(table, 4)
    tester = RuleTester(table, rng=RngTree(5), ledger=RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash))
    with pytest.raises(RuleRefusedError) as refused:
        tester.register_family(
            _template(), pair, n_candidates=RULE_FAMILY_SCREENED_MAX + 1, n_screened=RULE_FAMILY_SCREENED_MAX + 1
        )
    assert refused.value.context["reason"] == "family_too_large"


def test_a_rule_is_promoted_only_after_out_of_time_replication(tmp_path: Path) -> None:
    table = _table()
    pair = rolling_pair(table, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    result = tester.run_family(
        [_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=1
    )
    assert [record.passed for record in result.fit] == [True]
    assert [record.passed for record in result.replicate] == [True]
    promotion = result.promotions[0]
    assert promotion.replicate.fold == pair.replicate_fold
    assert promotion.fit.fold == pair.fit_fold
    assert promotion.fit_t1_ms == pair.fit_t1_ms
    assert promotion.visible_from_ms == pair.fit_t1_ms + interval_ms(table.interval_min)
    rows = ledger.rules()
    assert [row["type"] for row in rows] == ["rule_tested", "rule_tested", "rule_promoted"]
    assert all(row["dataset_hash"] == table.dataset_hash for row in rows)
    assert all(row["fit_fold"] == pair.fit_fold and row["replicate_fold"] == pair.replicate_fold for row in rows)


def test_a_rule_that_fails_the_replicate_fold_is_a_recorded_negative_and_is_never_re_tested(
    tmp_path: Path,
) -> None:
    """18.2 step 4: a negative result is a first-class ledger row and its content is a duplicate."""
    table = _table()
    pair = rolling_pair(table, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    # A support floor no replicate month can meet: the claim holds on the fit fold and cannot replicate.
    rule = _drift_rule(pair.registered_at_ms, min_support=120)
    result = tester.run_family([rule], template=_template(), pair=pair, n_candidates=1)
    assert result.fit[0].passed is True, "the fit fold has the support"
    assert result.replicate[0].passed is False
    assert result.promotions == ()
    negative = [row for row in ledger.rules() if row["stage"] == "replicate"]
    assert len(negative) == 1
    assert negative[0]["passed"] is False
    assert negative[0]["support"] > 0, "a negative result records every number, not an absence"
    assert tester.is_duplicate(rule, pair) is True
    with pytest.raises(RuleRefusedError) as refused:
        tester.run_family([rule], template=_template(), pair=pair, n_candidates=1)
    assert refused.value.context["reason"] == "duplicate"
    # A second tester over the same ledger reads the same refusal off disk.
    reopened = RuleTester(table, rng=RngTree(5), ledger=RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash))
    assert reopened.is_duplicate(rule, pair) is True
    assert reopened.is_duplicate(rule, headline_pair(table)) is False, "another fold pair is another test"


def test_the_ledger_lines_are_chained_and_a_deletion_breaks_the_chain(tmp_path: Path) -> None:
    table = _table()
    pair = rolling_pair(table, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    tester.run_family([_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=1)
    ledger.verify(ledger.rules_path)
    ledger.verify(ledger.families_path)
    assert ledger.rules_path.parts[-2] == table.dataset_hash[:8]
    lines = ledger.rules_path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["prev_sha256"] is None
    ledger.rules_path.write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
    from pmx.errors import SchemaError

    with pytest.raises(SchemaError):
        ledger.verify(ledger.rules_path)


# --------------------------------------------------------------------------------------------------
# The live record (ruling R276)
# --------------------------------------------------------------------------------------------------
def _expected_matched_rows(
    table: RowTable,
    rule: Rule,
    *,
    ids: Sequence[str] | None = None,
    scope: RuleScope | None = None,
    from_ms: int = 0,
    to_ms: int = 1 << 62,
) -> int:
    """Recount the matched rows by hand, so an assertion does not lean on the code it checks.

    Written out rather than delegated: the window, the scope, the horizon and the resolution-bar skip are
    each restated here, which is what makes a disagreement with the tester visible instead of shared.
    """
    wanted = None if ids is None else set(ids)
    selector = scope if scope is not None else rule.scope
    total = 0
    for rows in table.markets:
        if rows.meta.fold == "sealed" or not selector.matches(rows.meta):
            continue
        if wanted is not None and rows.meta.id not in wanted:
            continue
        for position, bar in enumerate(rows.bars):
            if bar.t_ms < from_ms or bar.t_ms >= to_ms:
                continue
            if position + rule.horizon_bars >= len(rows.bars):
                continue
            resolution_bar = (rows.meta.resolved_at_ms // (60 * 60_000)) * (60 * 60_000)
            if rows.bars[position + rule.horizon_bars].t_ms >= resolution_bar:
                continue
            if rule.condition_holds(bar.blocks):
                total += 1
    return total


def _expected_live_support(table: RowTable, rule: Rule, *, from_ms: int, to_ms: int) -> int:
    """The live record's own recount: every non-sealed market in the rule's scope, inside the window."""
    return _expected_matched_rows(table, rule, from_ms=from_ms, to_ms=to_ms)


def test_the_live_window_is_as_of_and_its_bounds_are_exact(tmp_path: Path) -> None:
    """Ruling R276: at bar ``b`` the record covers ``fit_t1_ms + interval_ms <= t < b`` and nothing else."""
    table = _table()
    pair = rolling_pair(table, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    promotion = tester.run_family(
        [_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=1
    ).promotions[0]
    rule = promotion.rule
    step = interval_ms(table.interval_min)
    assert promotion.visible_from_ms == pair.fit_t1_ms + step

    at_the_edge = tester.live_record(promotion, pair, at_ms=promotion.visible_from_ms)
    assert at_the_edge.live_support == 0, "nothing before the first bar the promotion did not read"
    assert at_the_edge.from_ms == promotion.visible_from_ms

    month_seven = table.split.month_edges_ms[7]
    early = tester.live_record(promotion, pair, at_ms=month_seven)
    assert early.to_ms == month_seven
    assert early.live_support == _expected_live_support(
        table, rule, from_ms=promotion.visible_from_ms, to_ms=month_seven
    )
    assert early.live_support > 0

    later = tester.live_record(promotion, pair, at_ms=table.split.validation_end_ms)
    assert later.live_support > early.live_support, (
        "the record grows with b: a record frozen at the replicate fold could never demote a decaying rule"
    )
    assert later.live_support == _expected_live_support(
        table, rule, from_ms=promotion.visible_from_ms, to_ms=table.split.validation_end_ms
    )


def test_the_live_record_never_reads_a_bar_at_or_after_the_recomputing_bar(tmp_path: Path) -> None:
    table = _table()
    pair = rolling_pair(table, 4)
    tester = RuleTester(
        table, rng=RngTree(5), ledger=RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    )
    promotion = tester.run_family(
        [_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=1
    ).promotions[0]
    cut = table.split.month_edges_ms[7]
    bounded = tester.live_record(promotion, pair, at_ms=cut)
    unbounded = tester.live_record(promotion, pair, at_ms=table.split.month_edges_ms[12])
    assert bounded.live_support < unbounded.live_support
    rows_after_the_cut = [
        bar.t_ms
        for market in table.markets
        if market.meta.fold != "sealed"
        for bar in market.bars
        if bar.t_ms >= cut
    ]
    assert rows_after_the_cut, "the fixture must carry bars after the cut, or the bound is untested"
    assert bounded.to_ms == cut


def test_the_live_record_never_reads_a_sealed_market(tmp_path: Path) -> None:
    """Architecture rule 3: the tester reads no sealed bar at any ``b``."""
    table = _table()
    pair = rolling_pair(table, 4)
    tester = RuleTester(
        table, rng=RngTree(5), ledger=RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    )
    promotion = tester.run_family(
        [_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=1
    ).promotions[0]
    sealed = [rows for rows in table.markets if rows.meta.fold == "sealed"]
    assert sealed, "the fixture must carry a sealed fold, or this test proves nothing"
    everything = tester.live_record(promotion, pair, at_ms=table.split.month_edges_ms[12] + MS_PER_HOUR)
    assert everything.live_support == _expected_live_support(
        table,
        promotion.rule,
        from_ms=promotion.visible_from_ms,
        to_ms=table.split.month_edges_ms[12] + MS_PER_HOUR,
    )
    reachable = scope_rows(
        table,
        promotion.rule,
        ids=[rows.meta.id for rows in table.markets],
        usual_bp=0,
    )
    assert all(row.market_id not in {rows.meta.id for rows in sealed} for row in reachable)


def test_a_negative_live_record_demotes_and_the_row_is_written(tmp_path: Path) -> None:
    """18.2 step 7: ``live_support >= RULE_LIVE_MIN_SUPPORT`` and ``live_interval.upper < 0``."""
    table = _table()
    pair = rolling_pair(table, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    # The mirror of the planted rule: it fires on the down bars, so its live record is negative.
    mirror = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=pair.registered_at_ms,
        scope=RuleScope(kinds=("binary",), providers=("kalshi",)),
        condition=[Predicate(feature="ret_7b_bp", op="lt", value=-300)],
        claim=RuleClaim(kind="drift", direction=1, magnitude_bp=120, factor_ppm=0),
        horizon_bars=1,
    )
    family = tester.register_family(_template(), pair, n_candidates=1, n_screened=1)
    record, _rows = tester.test_on_fold(
        mirror, pair, stage="replicate", family_id=family.family_id, ids=pair.replicate_ids
    )
    assert record.passed is False
    from pmx.rules.tester import Promotion

    pretend = Promotion(
        rule=mirror,
        family_id=family.family_id,
        fit=record,
        replicate=record,
        fit_t1_ms=pair.fit_t1_ms,
        visible_from_ms=pair.fit_t1_ms + interval_ms(table.interval_min),
    )
    live = tester.live_record(pretend, pair, at_ms=table.split.validation_end_ms)
    assert live.live_support >= RULE_LIVE_MIN_SUPPORT
    assert live.live_interval.upper < 0
    assert live.demote is True and live.reason == "live_negative"
    tester.demote(live, pair)
    demotions = [row for row in ledger.rules() if row["type"] == "rule_demoted"]
    assert len(demotions) == 1
    assert demotions[0]["reason"] == "live_negative"
    assert demotions[0]["demoted_at_ms"] == table.split.validation_end_ms


def test_an_author_with_a_negative_reputation_demotes_a_rule_that_stopped_working(tmp_path: Path) -> None:
    table = _table()
    pair = rolling_pair(table, 4)
    tester = RuleTester(
        table, rng=RngTree(5), ledger=RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    )
    promotion = tester.run_family(
        [_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=1
    ).promotions[0]
    at_the_edge = tester.live_record(
        promotion, pair, at_ms=promotion.visible_from_ms, author_reputation=-1
    )
    assert at_the_edge.live_interval.lower <= 0
    assert at_the_edge.demote is True and at_the_edge.reason == "author_reputation"
    working = tester.live_record(
        promotion, pair, at_ms=table.split.validation_end_ms, author_reputation=-1
    )
    assert working.live_interval.lower > 0
    assert working.demote is False, "a negative reputation alone does not demote a rule that still works"


# --------------------------------------------------------------------------------------------------
# The transfer test (18.2 step 8, ruling R276)
# --------------------------------------------------------------------------------------------------
def test_a_transfer_test_reads_the_replicate_fold_outside_the_scope_and_never_promotes(tmp_path: Path) -> None:
    table = _table()
    pair = rolling_pair(table, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    promotion = tester.run_family(
        [_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=1
    ).promotions[0]
    records = tester.transfer_tests(promotion, pair)
    assert records == (), "one provider, one category and one kind leave nothing outside the scope"
    promoted = [row for row in ledger.rules() if row["type"] == "rule_promoted"]
    assert len(promoted) == 1, "a transfer test never promotes anything"


def test_a_transfer_test_names_a_target_outside_the_scope_when_the_dataset_has_one(tmp_path: Path) -> None:
    table = _table()
    widened = RowTable(
        dataset_hash=table.dataset_hash,
        interval_min=table.interval_min,
        split=table.split,
        markets=tuple(
            sorted(
                [
                    *table.markets,
                    *[
                        MarketRows(
                            meta=_meta(
                                id=f"mf-{rows.meta.id}",
                                provider="manifold",
                                resolved_at_ms=rows.meta.resolved_at_ms,
                                close_at_ms=rows.meta.close_at_ms,
                                created_at_ms=rows.meta.created_at_ms,
                                fold=rows.meta.fold,
                                resolution=rows.meta.resolution,
                                n_bars=rows.meta.n_bars,
                            ),
                            bars=rows.bars,
                            block=f"blk-mf-{rows.meta.id}",
                            fold_key_ms=rows.fold_key_ms,
                        )
                        for rows in table.markets
                    ],
                ],
                key=lambda rows: rows.meta.id,
            )
        ),
    )
    pair = rolling_pair(widened, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=widened.dataset_hash)
    tester = RuleTester(widened, rng=RngTree(5), ledger=ledger)
    promotion = tester.run_family(
        [_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=1
    ).promotions[0]
    records = tester.transfer_tests(promotion, pair)
    assert [record.target for record in records] == ["providers:manifold"]
    assert records[0].support > 0
    assert records[0].stage == "transfer"
    outside = tester._targets(promotion.rule.scope)
    assert outside == {"categories": (), "kinds": (), "providers": ("manifold",)}, (
        "a facet the scope leaves empty is any, so it has no outside and names no target"
    )
    target = RuleScope(providers=("manifold",))
    assert records[0].support == _expected_matched_rows(
        widened,
        promotion.rule,
        ids=pair.replicate_ids,
        scope=target,
        to_ms=promotion.visible_from_ms,
    ), "a transfer test reads the promotion's own replicate fold and no other month"
    assert _expected_matched_rows(widened, promotion.rule, scope=target) > records[0].support, (
        "the whole dataset carries strictly more of the target's rows than the replicate fold does"
    )
    rows = scope_rows(
        widened,
        promotion.rule,
        ids=pair.replicate_ids,
        usual_bp=0,
        to_ms=promotion.visible_from_ms,
        scope=RuleScope(providers=("manifold",)),
    )
    assert rows and all(row.market_id.startswith("mf-") for row in rows), (
        "a transfer target reads the target's markets and no others"
    )
    assert max(row.t_ms for row in rows) < promotion.visible_from_ms
    for row in ledger.rules():
        if row["type"] == "rule_tested" and row["stage"] == "transfer":
            assert row["target"] == "providers:manifold"


# --------------------------------------------------------------------------------------------------
# The measurement of 18.2's table
# --------------------------------------------------------------------------------------------------
def test_a_bias_row_measures_the_outcome_against_the_price_and_reads_the_direction() -> None:
    table = _table(months=1, per_month=2, bars=4)
    rule = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=0,
        scope=RuleScope(),
        condition=[Predicate(feature="last_price_bp", op="gt", value=0)],
        claim=RuleClaim(kind="bias", direction=-1, magnitude_bp=100, factor_ppm=0),
        horizon_bars=0,
    )
    ids = [rows.meta.id for rows in table.markets]
    rows = scope_rows(table, rule, ids=ids, usual_bp=0)
    for row in rows:
        market = next(m for m in table.markets if m.meta.id == row.market_id)
        bar = next(b for b in market.bars if b.t_ms == row.t_ms)
        expected = -1 * (10_000 * market.meta.resolution - bar.close_bp)
        assert row.y_bp == expected


def test_a_drift_row_skips_a_bar_with_no_h_th_bar_before_the_resolution_bar() -> None:
    table = _table(months=1, per_month=1, bars=4)
    rule = _drift_rule(0)
    market = table.markets[0]
    rows = scope_rows(table, rule, ids=[market.meta.id], usual_bp=0)
    assert len(rows) == len(market.bars) - 1, "the last bar has no bar after it"
    assert max(row.t_ms for row in rows) == market.bars[-2].t_ms


def test_the_usual_move_is_the_fit_folds_and_not_the_fold_under_test(tmp_path: Path) -> None:
    """18.2: ``usual_bp`` is the fit fold's median, on every stage.

    Re-estimating the baseline on the fold under test would re-centre the claim: a market that moves four
    times as far in month five would carry four times the "usual" there, and an excess measured against
    it would report zero for a rule that in fact found a fourfold move. The fixture makes the two medians
    differ on purpose, which is the only way to see which one was used.
    """
    table = _table(steps=(120, 120, 120, 120, 480, 120, 120, 120, 120))
    pair = rolling_pair(table, 4)
    scope = RuleScope(kinds=("binary",), providers=("kalshi",))
    assert usual_bp_for(table, scope, horizon_bars=1, ids=pair.fit_ids) == 120
    assert usual_bp_for(table, scope, horizon_bars=1, ids=pair.replicate_ids) == 480
    rule = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=pair.registered_at_ms,
        scope=scope,
        condition=[Predicate(feature="ret_7b_bp", op="gt", value=300)],
        claim=RuleClaim(kind="volatility", direction=0, magnitude_bp=0, factor_ppm=1_200_000),
        horizon_bars=1,
    )
    tester = RuleTester(
        table, rng=RngTree(5), ledger=RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    )
    result = tester.run_family(
        [rule],
        template=FamilyTemplate(
            scope_keys=("kinds", "providers"),
            features=("ret_7b_bp",),
            claim_kind="volatility",
            horizon_bars=1,
            author_kind="miner",
        ),
        pair=pair,
        n_candidates=1,
    )
    assert result.fit[0].usual_bp == 120
    assert result.fit[0].effect.point == 0, "on the fit fold every move is the usual move"
    assert result.fit[0].passed is False
    assert result.promotions == ()


def test_a_drift_row_whose_target_bar_sits_at_the_resolution_bar_is_skipped() -> None:
    """18.2's skip rule: the ``h``-th completed bar must exist **before** the bar the market resolved in.

    The fixtures above stop one bar short of the resolution bar, so only a market built to run into it can
    tell the two readings apart: with the rule, the row whose target is the resolution bar is dropped;
    without it, an outcome bar becomes a price observation.
    """
    table = _table()
    resolved = table.markets[0].meta.resolved_at_ms
    resolution_bar = (resolved // MS_PER_HOUR) * MS_PER_HOUR
    bars = tuple(
        BarRow(
            t_ms=resolution_bar - (2 - position) * MS_PER_HOUR,
            close_bp=5_000 + 120 * position,
            blocks=_blocks(5_000 + 120 * position, 400, 3 - position, position),
        )
        for position in range(3)
    )
    assert bars[-1].t_ms == resolution_bar, "the last bar sits in the bar the market resolved in"
    running_in = RowTable(
        dataset_hash=table.dataset_hash,
        interval_min=60,
        split=table.split,
        markets=(
            MarketRows(
                meta=_meta(
                    id="kx-runs-in",
                    resolved_at_ms=resolved,
                    close_at_ms=resolved,
                    created_at_ms=bars[0].t_ms - MS_PER_HOUR,
                    fold="train",
                    n_bars=len(bars),
                ),
                bars=bars,
                block="blk-runs-in",
                fold_key_ms=resolved,
            ),
        ),
    )
    rows = scope_rows(running_in, _drift_rule(0), ids=["kx-runs-in"], usual_bp=0)
    assert [row.t_ms for row in rows] == [bars[0].t_ms], (
        "only the first bar has a target bar before the resolution bar"
    )


def test_a_volatility_claim_measures_an_excess_over_the_fit_folds_median(tmp_path: Path) -> None:
    table = _table()
    pair = rolling_pair(table, 4)
    scope = RuleScope(kinds=("binary",), providers=("kalshi",))
    usual = usual_bp_for(table, scope, horizon_bars=1, ids=pair.fit_ids)
    assert usual == 120, "every move of this fixture is 120 bp, so the usual move is 120 bp"
    rule = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=pair.registered_at_ms,
        scope=scope,
        condition=[Predicate(feature="ret_7b_bp", op="gt", value=300)],
        claim=RuleClaim(kind="volatility", direction=0, magnitude_bp=0, factor_ppm=1_200_000),
        horizon_bars=1,
    )
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    result = tester.run_family(
        [rule],
        template=FamilyTemplate(
            scope_keys=("kinds", "providers"),
            features=("ret_7b_bp",),
            claim_kind="volatility",
            horizon_bars=1,
            author_kind="miner",
        ),
        pair=pair,
        n_candidates=1,
    )
    assert result.fit[0].usual_bp == 120
    assert result.fit[0].effect.point == 0, "every move is the usual move, so the excess is zero"
    assert result.fit[0].passed is False
    assert result.promotions == ()


# --------------------------------------------------------------------------------------------------
# The miner
# --------------------------------------------------------------------------------------------------
def test_the_quantiles_are_nearest_rank_and_unique() -> None:
    assert quantiles_ppm([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]) == (1, 2, 5, 7, 8)
    assert quantiles_ppm([5, 5, 5]) == (5,)
    assert quantiles_ppm([]) == ()


def test_the_miner_is_deterministic_and_draws_from_no_substream() -> None:
    table = _table()
    pair = rolling_pair(table, 4)
    scope = RuleScope(kinds=("binary",), providers=("kalshi",))
    claim = RuleClaim(kind="drift", direction=1, magnitude_bp=120, factor_ppm=0)
    first = mine(table, pair, scope=scope, claim=claim, horizon_bars=1, features=("ret_7b_bp", "bars_to_close"))
    second = mine(table, pair, scope=scope, claim=claim, horizon_bars=1, features=("ret_7b_bp", "bars_to_close"))
    assert [candidate.rule.rule_id for candidate in first.candidates] == [
        candidate.rule.rule_id for candidate in second.candidates
    ]
    assert first.n_candidates == second.n_candidates
    source = (REPO / "src" / "pmx" / "rules" / "miner.py").read_text(encoding="utf-8")
    assert "substream" not in source.replace("draws from no substream", "")


def test_the_miner_counts_every_candidate_it_enumerated_and_respects_its_cap() -> None:
    table = _table()
    pair = rolling_pair(table, 4)
    scope = RuleScope(kinds=("binary",), providers=("kalshi",))
    claim = RuleClaim(kind="drift", direction=1, magnitude_bp=120, factor_ppm=0)
    full = mine(table, pair, scope=scope, claim=claim, horizon_bars=1, features=("ret_7b_bp", "bars_to_close"))
    assert full.n_candidates >= len(full.candidates)
    capped = mine(
        table,
        pair,
        scope=scope,
        claim=claim,
        horizon_bars=1,
        features=("ret_7b_bp", "bars_to_close"),
        candidates_max=3,
    )
    assert capped.n_candidates == 3
    assert capped.truncated is True


def test_the_miner_finds_the_planted_feature_and_ranks_it_first() -> None:
    table = _table()
    pair = rolling_pair(table, 4)
    result = mine(
        table,
        pair,
        scope=RuleScope(kinds=("binary",), providers=("kalshi",)),
        claim=RuleClaim(kind="drift", direction=1, magnitude_bp=120, factor_ppm=0),
        horizon_bars=1,
        features=("ret_7b_bp", "bars_to_close", "last_price_bp"),
    )
    assert result.candidates, "the planted world must yield candidates"
    assert all(candidate.lift_bp > 0 for candidate in result.candidates), (
        "a candidate whose measured lift is not positive is not a candidate"
    )
    assert all(candidate.support >= RULE_MIN_SUPPORT_DEFAULT for candidate in result.candidates)
    best = result.candidates[0]
    assert best.lift_bp == 120
    assert any(predicate.feature == "ret_7b_bp" for predicate in best.rule.condition)
    for candidate in result.candidates:
        if candidate.lift_bp == 120:
            assert any(predicate.feature == "ret_7b_bp" for predicate in candidate.rule.condition), (
                "only the planted feature isolates the up bars"
            )
    assert result.template == template_of(
        RuleScope(kinds=("binary",), providers=("kalshi",)),
        ("ret_7b_bp", "bars_to_close", "last_price_bp"),
        RuleClaim(kind="drift", direction=1, magnitude_bp=120, factor_ppm=0),
        1,
    )


# --------------------------------------------------------------------------------------------------
# AC-27: the planted fixture and its shuffled twin
# --------------------------------------------------------------------------------------------------
def _run_fixture(name: str, tmp_path: Path) -> tuple[int, int, int]:
    """Mine and test one fixture end to end; answer ``(mined, screened, promotions)``."""
    table = load_row_table(S2 / name)
    pair = rolling_pair(table, 4)
    scope = RuleScope(kinds=("binary",), providers=("kalshi",))
    claim = RuleClaim(kind="drift", direction=1, magnitude_bp=120, factor_ppm=0)
    mined = mine(
        table, pair, scope=scope, claim=claim, horizon_bars=1, features=("ret_7b_bp", "bars_to_close")
    )
    tester = RuleTester(
        table,
        rng=RngTree(20260910),
        ledger=RuleLedger(root=tmp_path / name.replace(".json", ""), dataset_hash=table.dataset_hash),
    )
    candidates = mined.rules()[:6]
    if not candidates:
        return 0, 0, 0
    result = tester.run_family(
        candidates, template=mined.template, pair=pair, n_candidates=mined.n_candidates
    )
    for promotion in result.promotions:
        assert promotion.rule.claim.direction == 1
        assert any(predicate.feature == "ret_7b_bp" for predicate in promotion.rule.condition), (
            "the planted feature is the only thing in the fixture that predicts the next bar, so "
            "'yields the rule' means a promotion that names it and not merely a promotion"
        )
    return len(mined.candidates), result.family.n_screened, len(result.promotions)


def test_ac_27_the_planted_fixture_yields_the_rule_and_the_shuffled_twin_yields_nothing(
    tmp_path: Path,
) -> None:
    """AC-27. A fixture where both pass is worthless, so both halves are asserted here, in one test."""
    mined, screened, promoted = _run_fixture("planted.json", tmp_path)
    assert mined > 0 and screened > 0 and promoted > 0, "the planted effect must survive the procedure"
    twin_mined, twin_screened, twin_promoted = _run_fixture("shuffled.json", tmp_path)
    assert twin_mined > 0, (
        "the twin must reach the tester with candidates of its own, or 'yields nothing' would only mean "
        "the search found nothing to try"
    )
    assert twin_promoted == 0, "the shuffled twin must promote nothing"
    assert twin_screened < screened


def test_the_two_fixtures_differ_only_in_the_permuted_column() -> None:
    """The twin is the same world with one column shuffled: same prices, same outcomes, same bars."""
    planted = json.loads((S2 / "planted.json").read_text(encoding="utf-8"))
    twin = json.loads((S2 / "shuffled.json").read_text(encoding="utf-8"))
    assert planted["split"] == twin["split"]
    assert len(planted["markets"]) == len(twin["markets"])
    column_planted: list[int] = []
    column_twin: list[int] = []
    for left, right in zip(planted["markets"], twin["markets"], strict=True):
        assert left["meta"] == right["meta"]
        for bar_left, bar_right in zip(left["bars"], right["bars"], strict=True):
            assert bar_left["t_ms"] == bar_right["t_ms"]
            assert bar_left["close_bp"] == bar_right["close_bp"]
            assert bar_left["blocks"]["calendar"] == bar_right["blocks"]["calendar"]
            column_planted.append(bar_left["blocks"]["tape"][3])
            column_twin.append(bar_right["blocks"]["tape"][3])
    assert sorted(column_planted) == sorted(column_twin), "a permutation keeps the marginal distribution"
    assert column_planted != column_twin, "and it moves at least one value"


def test_the_fixture_is_a_row_table_the_loader_reads_back() -> None:
    table = load_row_table(S2 / "planted.json")
    assert table.interval_min == 60
    assert table.purpose == "research"
    assert {rows.meta.fold for rows in table.markets} == {"train", "validation", "sealed"}
    assert rolling_ks(table.split) == (4, 5)
    ids = [rows.meta.id for rows in table.markets]
    assert ids == sorted(ids), "a row table is in canonical order"


def test_a_row_table_carries_the_taxonomy_and_the_cohort_a_scope_names() -> None:
    """7.2, 18.2 and 18.5: ``MarketMeta.to_dict`` round-trips through a row table, the facets included.

    A row table travels on disk as ``MarketMeta.to_dict()``, and amendment C1c put five fields in that
    document. A reader that dropped them would answer ``cohort_id = None`` on every row of a tagged
    dataset, and a ``RuleScope`` naming a cohort would then match nothing at all: a rule silently
    claiming to hold nowhere, which is the one failure a scope must never have, because it is
    indistinguishable from a rule that holds and never fires.
    """
    from pmx.rules.tester import row_table_from_dict

    document = json.loads((S2 / "planted.json").read_text(encoding="utf-8"))
    # the fixture predates the taxonomy and must keep reading back exactly as it did
    before = row_table_from_dict(document)
    assert all(rows.meta.subject == () and rows.meta.cohort_id is None for rows in before.markets)

    facets = {"subject": ["bitcoin"], "structure": "threshold-above", "horizon": "month"}
    tagged = {
        **document,
        "markets": [
            {**market, "meta": {**market["meta"], **facets, "provider_labels": ["kxbtc"]}}
            for market in document["markets"]
        ],
    }
    table = row_table_from_dict(tagged)
    assert table.markets
    for rows in table.markets:
        meta = rows.meta
        assert meta.subject == ("bitcoin",)
        assert meta.structure == "threshold-above" and meta.horizon == "month"
        assert meta.provider_labels == ("kxbtc",)
        expected = f"co-{meta.provider}-{meta.category}-bitcoin-threshold-above-month"
        assert meta.cohort_id == expected
        assert RuleScope(cohorts=(expected,)).matches(meta)
        assert not RuleScope(cohorts=("co-kalshi-politics-oil-threshold-above-month",)).matches(meta)
        # and the document the reader was handed is the document the meta renders back
        assert {key: meta.to_dict()[key] for key in facets} == facets


def test_a_showcase_row_table_is_refused_before_a_row_is_read() -> None:
    """12.7: a showcase dataset has no folds, so it has no rules either."""
    document = json.loads((S2 / "planted.json").read_text(encoding="utf-8"))
    document["purpose"] = "showcase"
    from pmx.rules.tester import ShowcaseRowsError, row_table_from_dict

    with pytest.raises(ShowcaseRowsError):
        row_table_from_dict(document)


# --------------------------------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------------------------------
def test_the_cli_mines_tests_and_renders_a_ledger(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    candidates = tmp_path / "candidates.json"
    assert (
        rules_main(
            [
                "mine",
                "--rows",
                str(S2 / "planted.json"),
                "--rolling",
                "4",
                "--kind",
                "binary",
                "--provider",
                "kalshi",
                "--claim",
                "drift",
                "--direction",
                "1",
                "--magnitude-bp",
                "120",
                "--horizon-bars",
                "1",
                "--features",
                "ret_7b_bp",
                "--out",
                str(candidates),
            ]
        )
        == 0
    )
    mined = json.loads(candidates.read_text(encoding="utf-8"))
    assert mined["rules"], "the planted fixture must yield candidates through the command line too"
    assert rules_main(
        [
            "test",
            "--rows",
            str(S2 / "planted.json"),
            "--rolling",
            "4",
            "--rules",
            str(candidates),
            "--top",
            "2",
            "--ledger-root",
            str(tmp_path),
        ]
    ) == 0
    out = capsys.readouterr().out
    assert "promoted" in out
    assert rules_main(["ledger", "--dataset-hash", "5" * 64, "--ledger-root", str(tmp_path)]) == 0
    assert "families" in capsys.readouterr().out


def test_the_cli_says_which_package_is_missing_rather_than_crashing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A refusal names the package that has not landed, and the group exits 1 rather than tracing back."""
    assert rules_main(["mine", "--dataset", "data/datasets/whatever", "--features", "last_price_bp"]) == 1
    assert "pmx.sensors.catalogue" in capsys.readouterr().err
    with pytest.raises(NotConfiguredError) as refused:
        _table_from_args("data/datasets/whatever")
    assert "pmx.sensors.catalogue" in str(refused.value)


def test_the_cli_group_runs_as_a_module(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "pmx.cli_rules", "--help"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )
    assert completed.returncode == 0
    assert "mine" in completed.stdout and "ledger" in completed.stdout


def test_the_ledger_verb_renders_what_a_run_wrote(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    table = _table()
    pair = rolling_pair(table, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    tester.run_family([_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=7)
    capsys.readouterr()
    assert rules_main(["ledger", "--dataset-hash", table.dataset_hash, "--ledger-root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "1 families" in out
    assert "candidates 7" in out
    assert "rule_tested/replicate: 1" in out


def test_every_rule_the_package_builds_validates_against_rule_v1_json() -> None:
    """The record and its schema are one document: ``to_dict`` is what ``rule.v1.json`` describes."""
    from jsonschema import Draft202012Validator

    schema = json.loads((REPO / "src" / "pmx" / "schemas" / "rule.v1.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    table = _table()
    pair = rolling_pair(table, 4)
    mined = mine(
        table,
        pair,
        scope=RuleScope(kinds=("binary",), providers=("kalshi",)),
        claim=RuleClaim(kind="drift", direction=1, magnitude_bp=120, factor_ppm=0),
        horizon_bars=1,
        features=("ret_7b_bp", "bars_to_close"),
    )
    assert mined.candidates
    for rule in (_sample_rule(), *mined.rules()[:10]):
        assert list(validator.iter_errors(rule.to_dict())) == [], rule.rule_id


def test_the_ledger_verb_counts_the_proposals_of_one_statement(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """18.2: one statement is one rule whatever its authors, and the ledger counts ``n_proposals``.

    The rows come out of the run journals, never out of the tester: ``rule_proposed`` has one emitter,
    ``engine/runner.py`` (ruling R294).
    """
    table = _table()
    pair = rolling_pair(table, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    rule = _drift_rule(pair.registered_at_ms)
    tester.run_family([rule], template=_template(), pair=pair, n_candidates=1)
    assert all(row["type"] != "rule_proposed" for row in ledger.rules()), (
        "the tester never writes a rule_proposed line: that event has one emitter"
    )
    runs = tmp_path / "runs" / "r-0001"
    runs.mkdir(parents=True)
    lines = [
        canonical_json(
            {
                "type": "rule_proposed",
                "run_id": "r-0001",
                "seq": index,
                "bar_ms": 1_000 + index,
                "agent_id": agent,
                "rule_id": rule.rule_id,
            }
        )
        for index, agent in enumerate(("calibrator-0a1b2c3d", "newsbayes-1b2c3d4e"))
    ]
    (runs / "journal.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    capsys.readouterr()
    assert (
        rules_main(
            [
                "ledger",
                "--dataset-hash",
                table.dataset_hash,
                "--ledger-root",
                str(tmp_path),
                "--runs",
                str(tmp_path / "runs"),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "rule_proposed rows" in out
    assert "n_proposals 2" in out
    assert "first by calibrator-0a1b2c3d" in out, "the author of record is the first proposal in order"


# --------------------------------------------------------------------------------------------------
# The two agreements and the architecture rules
# --------------------------------------------------------------------------------------------------
def test_nothing_in_the_package_imports_the_gateway_the_llm_or_numpy() -> None:
    """Architecture rules 4 and 12: a rule a model wrote would move a claim between two rebuilds."""
    for path in sorted((REPO / "src" / "pmx" / "rules").glob("*.py")) + [REPO / "src" / "pmx" / "cli_rules.py"]:
        source = path.read_text(encoding="utf-8")
        assert "pmx.gateway" not in source, path
        assert "pmx.llm" not in source, path
        assert "import numpy" not in source, path


def test_the_two_statistics_are_named_the_way_the_agreement_records_them() -> None:
    """Rulings R238 and R282: both names live in E4's ``pmx.metrics.stats``, and only there.

    The swap this test used to pin conditionally has happened: 12.4 declares ``benjamini_hochberg`` and
    ``rule_permutation_p_ppm`` in ``pmx.metrics.stats``, section 13's agreement put them there, and the
    private stand-ins the tester carried while that file belonged to another package in flight are
    gone. A stand-in that came back would be two spellings of one statistic, which is what the tester's
    own history says costs a wrong ``fdr_k``, so the absence is asserted and not merely assumed.
    """
    import pmx.metrics.stats as stats
    import pmx.rules.tester as tester_module

    assert stats.benjamini_hochberg([30_000, 900_000, 1_000, 20_000]) == (True, False, True, True)
    assert (
        stats.rule_permutation_p_ppm(
            [1, 1, -1, -1], [True, True, False, False], ["b"] * 4, rng=RngTree(1), permutations=200
        )
        > 0
    )
    assert "benjamini_hochberg" in stats.__all__ and "rule_permutation_p_ppm" in stats.__all__
    for gone in ("_benjamini_hochberg", "_rule_permutation_p_ppm"):
        assert not hasattr(tester_module, gone), f"{gone} is a second spelling of a contracted statistic"
    assert tester_module.benjamini_hochberg is stats.benjamini_hochberg
    assert tester_module.rule_permutation_p_ppm is stats.rule_permutation_p_ppm


def test_the_family_procedure_calls_the_two_contracted_statistics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A binding is not a call: the FDR step and the null must go **through** E4's two functions.

    An inline re-implementation at the call site would leave the import in place and every other test
    of this file passing, because the arithmetic would agree on the easy families. So both names are
    replaced with recorders and the family procedure is run: if a call does not arrive, the tester is
    spelling one of the two statistics a second time, which is the drift rulings R238 and R282 removed.
    """
    import pmx.rules.tester as tester_module

    seen: list[str] = []

    def recording_bh(p_values_ppm: Sequence[int], *, q_ppm: int = FDR_Q_PPM) -> tuple[bool, ...]:
        seen.append("benjamini_hochberg")
        return benjamini_hochberg(p_values_ppm, q_ppm=q_ppm)

    def recording_null(
        y_rows: Sequence[int],
        fired: Sequence[bool],
        blocks: Sequence[str],
        *,
        rng: RngTree,
        permutations: int,
    ) -> int:
        seen.append("rule_permutation_p_ppm")
        return rule_permutation_p_ppm(y_rows, fired, blocks, rng=rng, permutations=permutations)

    monkeypatch.setattr(tester_module, "benjamini_hochberg", recording_bh)
    monkeypatch.setattr(tester_module, "rule_permutation_p_ppm", recording_null)
    table = _table()
    pair = rolling_pair(table, 4)
    tester = RuleTester(table, rng=RngTree(5), ledger=RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash))
    result = tester.run_family(
        [_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=1
    )
    assert result.promotions, "the planted effect must promote, or the counts below are vacuous"
    assert seen.count("rule_permutation_p_ppm") == 1, "one null per screened rule"
    assert seen.count("benjamini_hochberg") == 1, "one FDR step per family"


# --------------------------------------------------------------------------------------------------
# The windows the month-edge tests could not see (ruling R276), and the exact family tuple (R284)
# --------------------------------------------------------------------------------------------------
# Each test in this block was written against a mutation that the first pass of this file survived, and
# each of those mutations is a defect the contract names: a half-open bound widened by one bar, a
# transfer test that walks past its promotion's visibility, a family id keyed on a subset of ruling
# R284's tuple, a sealed market reaching the market chooser, a claim promoted on four markets, a rule
# demoted on a flat record or on twenty bad rows, a promotion that ignores its family's FDR flag, a
# miner that counts what it kept instead of what it looked at, and a mean that rounds asymmetrically.


def _table_with_manifold_twins(table: RowTable) -> RowTable:
    """The same world with a second provider, so a scope narrowed to ``kalshi`` has an outside.

    The twins carry the same bars, the same folds and the same group keys, so every fold pair, every
    instant and every planted effect is what the original table had. The only thing added is a facet
    value the rule's scope does not name, which is what a transfer target is.
    """
    twins = [
        MarketRows(
            meta=_meta(
                id=f"mf-{rows.meta.id}",
                provider="manifold",
                resolved_at_ms=rows.meta.resolved_at_ms,
                close_at_ms=rows.meta.close_at_ms,
                created_at_ms=rows.meta.created_at_ms,
                fold=rows.meta.fold,
                resolution=rows.meta.resolution,
                n_bars=rows.meta.n_bars,
            ),
            bars=rows.bars,
            block=f"blk-mf-{rows.meta.id}",
            fold_key_ms=rows.fold_key_ms,
        )
        for rows in table.markets
    ]
    return RowTable(
        dataset_hash=table.dataset_hash,
        interval_min=table.interval_min,
        split=table.split,
        markets=tuple(sorted([*table.markets, *twins], key=lambda rows: rows.meta.id)),
    )


def test_the_row_window_is_half_open_at_a_real_bar_instant() -> None:
    """Ruling R276's interval is ``from_ms <= t < to_ms``, and the bound is pinned **at** a bar.

    Every window this module has runs through one row builder, and the upper bound is the one that leaks:
    ``to_ms`` is the recomputing bar ``b`` of a live record and the ``visible_from_ms`` of a transfer
    test, so a ``>`` where the contract writes ``>=`` reads exactly the one bar the promotion never saw.
    The other window tests cut on a month edge, which falls between two bars, so widening the comparison
    by a single bar moved nothing and they could not see it. This one cuts **on** a bar the fixture
    carries and counts the rows that instant contributes, so a widened bound is a different number here.
    """
    table = _table()
    rule = _drift_rule(table.split.month_edges_ms[4])
    ids = [rows.meta.id for rows in table.markets]
    every_row = scope_rows(table, rule, ids=ids, usual_bp=0)
    stamps = sorted({row.t_ms for row in every_row})
    assert len(stamps) > 4, "the window needs several distinct bar instants to be pinned at all"
    cut = stamps[len(stamps) // 2]
    at_the_cut = [row for row in every_row if row.t_ms == cut]
    assert at_the_cut, "the fixture must carry a row exactly at the cut, or the bound is untested"

    below = scope_rows(table, rule, ids=ids, usual_bp=0, to_ms=cut)
    assert all(row.t_ms < cut for row in below), "a bar at to_ms is outside a half-open window"
    inclusive = scope_rows(table, rule, ids=ids, usual_bp=0, to_ms=cut + 1)
    assert len(inclusive) == len(below) + len(at_the_cut)

    from_the_cut = scope_rows(table, rule, ids=ids, usual_bp=0, from_ms=cut)
    assert any(row.t_ms == cut for row in from_the_cut), "a bar at from_ms is inside the window"
    after_the_cut = scope_rows(table, rule, ids=ids, usual_bp=0, from_ms=cut + 1)
    assert len(from_the_cut) == len(after_the_cut) + len(at_the_cut)
    assert len(below) + len(from_the_cut) == len(every_row), "the two halves partition the rows"


def test_the_live_record_excludes_the_bar_at_the_recomputing_instant(tmp_path: Path) -> None:
    """Ruling R276: as of ``b`` the record covers ``t < b``, so the bar **at** ``b`` is not in it yet.

    The tester recomputes at each generation close with ``b`` the generation's last completed bar, and
    that bar's own measurement reaches into bars after it. Including it is the smallest possible version
    of the leak the ruling names, and a bound written ``>`` instead of ``>=`` includes it.
    """
    table = _table()
    pair = rolling_pair(table, 4)
    tester = RuleTester(
        table, rng=RngTree(5), ledger=RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    )
    promotion = tester.run_family(
        [_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=1
    ).promotions[0]
    ids = [rows.meta.id for rows in table.markets]
    stamps = sorted(
        {
            row.t_ms
            for row in scope_rows(
                table, promotion.rule, ids=ids, usual_bp=0, from_ms=promotion.visible_from_ms
            )
            if row.fired
        }
    )
    assert len(stamps) > 4, "the live window needs matched rows at several instants"
    bar = stamps[len(stamps) // 2]
    as_of_the_bar = tester.live_record(promotion, pair, at_ms=bar)
    one_instant_later = tester.live_record(promotion, pair, at_ms=bar + 1)
    assert as_of_the_bar.to_ms == bar
    assert one_instant_later.live_support > as_of_the_bar.live_support, (
        "the bar at b enters the record from the next instant and not at b itself"
    )


def test_a_transfer_test_reads_no_bar_at_or_after_the_promotions_visibility(tmp_path: Path) -> None:
    """18.2 step 8 as ruling R276 amends it: no bar at or after ``fit_t1_ms + interval_ms``.

    On a pair the tester built itself the bound looks redundant, because ``fit_t1_ms`` is by construction
    the replicate fold's last bar and the ``ids`` filter already stops there. What the bound is for is
    the record's own instants: a promotion carries the visibility its promotion read up to, and the
    transfer test re-tests **that** promotion. Here the anchor sits inside the replicate month, the only
    arrangement in which the window and the fold disagree, and the transfer test must follow the window.
    Drop the bound and the support grows past what the promotion ever saw.
    """
    table = _table_with_manifold_twins(_table())
    pair = rolling_pair(table, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    rule = _drift_rule(pair.registered_at_ms)
    family = tester.register_family(_template(), pair, n_candidates=1, n_screened=1)
    record, _rows = tester.test_on_fold(
        rule, pair, stage="replicate", family_id=family.family_id, ids=pair.replicate_ids
    )
    assert record.passed, "the planted effect must replicate, or the transfer test has nothing to carry"

    stamps = sorted(
        {row.t_ms for row in scope_rows(table, rule, ids=pair.replicate_ids, usual_bp=0) if row.fired}
    )
    assert len(stamps) > 4
    anchor = stamps[len(stamps) // 2]
    early = Promotion(
        rule=rule,
        family_id=family.family_id,
        fit=record,
        replicate=record,
        fit_t1_ms=anchor - interval_ms(table.interval_min),
        visible_from_ms=anchor,
    )
    records = tester.transfer_tests(early, pair)
    assert [row.target for row in records] == ["providers:manifold"]
    target = RuleScope(providers=("manifold",))
    bounded = _expected_matched_rows(table, rule, ids=pair.replicate_ids, scope=target, to_ms=anchor)
    unbounded = _expected_matched_rows(table, rule, ids=pair.replicate_ids, scope=target)
    assert unbounded > bounded, "the replicate fold must carry target rows at and after the anchor"
    assert records[0].support == bounded, "a transfer test stops at the promotion's own visibility"
    rows = scope_rows(table, rule, ids=pair.replicate_ids, usual_bp=0, to_ms=anchor, scope=target)
    assert rows and max(row.t_ms for row in rows) < anchor


def test_the_family_id_is_the_exact_tuple_ruling_r284_states() -> None:
    """``hf-`` + sha256(canonical_json([dataset_hash, generation, fit_fold, replicate_fold,
    registered_at_ms, fit_t1_ms, template]))[:16], recomputed here field by field.

    The three-runs-are-three-families test cannot see a missing member, because the pairs of one dataset
    differ in their instants as well as in their names: drop the fold pair, or drop both instants, and
    the three ids are still three. The id is a content address, so the content is what has to be
    asserted, in the order and with the members the ruling writes down.
    """
    table = _table()
    template = _template()
    pair = rolling_pair(table, 4)
    payload = [
        table.dataset_hash,
        3,
        pair.fit_fold,
        pair.replicate_fold,
        pair.registered_at_ms,
        pair.fit_t1_ms,
        template.to_dict(),
    ]
    assert (
        family_id_of(
            dataset_hash=table.dataset_hash,
            generation=3,
            fit_fold=pair.fit_fold,
            replicate_fold=pair.replicate_fold,
            registered_at_ms=pair.registered_at_ms,
            fit_t1_ms=pair.fit_t1_ms,
            template=template,
        )
        == "hf-" + canonical_sha256(payload)[:16]
    )


def _template_with(**changed: object) -> FamilyTemplate:
    base: dict[str, object] = {
        "scope_keys": ("kinds", "providers"),
        "features": ("ret_7b_bp",),
        "claim_kind": "drift",
        "horizon_bars": 1,
        "author_kind": "miner",
    }
    base.update(changed)
    return FamilyTemplate(**base)  # type: ignore[arg-type]


def test_every_member_of_the_family_tuple_moves_the_id() -> None:
    """Ruling R284, member by member: six fields and the template's own five, each moving the id.

    Without this, a family id keyed on a subset passes every other test in this file. The last block is
    the case the ruling names by hand: two fold pairs that share both instants must still be two
    families, because it is ``--rolling k`` against ``--headline`` that the pre-registration guard has to
    tell apart, not their calendars.
    """
    template = _template_with()
    base: dict[str, object] = {
        "dataset_hash": "a" * 64,
        "generation": 0,
        "fit_fold": "m1..m4",
        "replicate_fold": "m5",
        "registered_at_ms": 1_704_000_000_000,
        "fit_t1_ms": 1_706_000_000_000,
        "template": template,
    }
    reference = family_id_of(**base)  # type: ignore[arg-type]
    changes: tuple[dict[str, object], ...] = (
        {"dataset_hash": "b" * 64},
        {"generation": 1},
        {"fit_fold": "train"},
        {"replicate_fold": "validation"},
        {"registered_at_ms": 1_704_000_003_600},
        {"fit_t1_ms": 1_706_000_003_600},
        {"template": _template_with(features=("bars_to_close",))},
        {"template": _template_with(scope_keys=())},
        {"template": _template_with(claim_kind="volatility")},
        {"template": _template_with(horizon_bars=2)},
        {"template": _template_with(author_kind="agent")},
    )
    ids = {reference}
    for change in changes:
        moved = family_id_of(**{**base, **change})  # type: ignore[arg-type]
        assert moved != reference, change
        ids.add(moved)
    assert len(ids) == len(changes) + 1, "no two changes collide on one id"

    shared_instants = {
        family_id_of(
            dataset_hash="a" * 64,
            generation=0,
            fit_fold=fit,
            replicate_fold=replicate,
            registered_at_ms=1_704_000_000_000,
            fit_t1_ms=1_706_000_000_000,
            template=template,
        )
        for fit, replicate in (("m1..m4", "m5"), ("m1..m5", "m6"), ("train", "validation"))
    }
    assert len(shared_instants) == 3, (
        "three fold pairs that share both instants are still three families (ruling R284)"
    )


def test_in_scope_never_returns_a_sealed_market() -> None:
    """Architecture rule 3 at the one place this module chooses markets rather than rows.

    ``in_scope`` feeds the volatility baseline and the miner's thresholds, both of which also narrow by
    the fit fold's ids, so a sealed market cannot reach them today by two independent routes. This test
    pins the first route on its own: a chooser that admits the sealed fold is one ``ids`` argument away
    from being a leak, and the fold filter is the half that does not depend on a caller.
    """
    table = _table()
    sealed = {rows.meta.id for rows in table.markets if rows.meta.fold == "sealed"}
    assert sealed, "the fixture must carry a sealed fold, or this test proves nothing"
    chosen = {rows.meta.id for rows in table.in_scope(RuleScope())}
    assert chosen, "an empty scope is any, so it must choose every non-sealed market"
    assert not sealed & chosen
    assert chosen == {rows.meta.id for rows in table.markets if rows.meta.fold != "sealed"}
    narrowed = {rows.meta.id for rows in table.in_scope(RuleScope(providers=("manifold",)))}
    assert narrowed == set(), "a scope no market matches chooses nothing rather than everything"


def test_a_claim_needs_five_distinct_markets_however_many_rows_it_matched(tmp_path: Path) -> None:
    """18.2: a claim holds iff ``support >= min_support`` **and** ``n_markets >= RULE_MIN_MARKETS``
    **and** ``interval.lower > 0``.

    The market floor is the one that stops a rule fitted to three long markets: rows are cheap on a
    dense grid and a hundred of them from three markets are three observations, not a hundred. Both
    worlds below carry the same planted effect, the same support and the same positive lower bound, and
    differ only in how many markets the replicate month holds.
    """
    rule = _drift_rule(0)
    for per_month, expected in ((3, False), (6, True)):
        table = _table(months=9, per_month=per_month, bars=40)
        pair = rolling_pair(table, 4)
        ledger = RuleLedger(root=tmp_path / f"m{per_month}", dataset_hash=table.dataset_hash)
        tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
        family = tester.register_family(_template(), pair, n_candidates=1, n_screened=1)
        record, _rows = tester.test_on_fold(
            rule, pair, stage="replicate", family_id=family.family_id, ids=pair.replicate_ids
        )
        assert record.support >= RULE_MIN_SUPPORT_DEFAULT, "both worlds clear the support floor"
        assert record.effect.lower > 0, "both worlds carry the planted effect"
        assert (record.n_markets >= RULE_MIN_MARKETS) is expected
        assert record.passed is expected


def test_a_live_record_whose_upper_bound_is_exactly_zero_does_not_demote(tmp_path: Path) -> None:
    """18.2 step 7: demotion needs ``live_interval.upper < 0``, strictly.

    A rule whose live rows all measure zero has stopped paying and has not started costing. On a flat
    world the interval is degenerate and its upper bound is zero, which is not negative. Demoting there
    would demote every rule the moment the price stops moving, which is a different statement from "the
    rule is wrong", and a demoted rule is never re-promoted.
    """
    flat = _table(months=9, per_month=8, bars=12, steps=(0,) * 9)
    pair = rolling_pair(flat, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=flat.dataset_hash)
    tester = RuleTester(flat, rng=RngTree(5), ledger=ledger)
    rule = _drift_rule(pair.registered_at_ms)
    family = tester.register_family(_template(), pair, n_candidates=1, n_screened=1)
    record, _rows = tester.test_on_fold(
        rule, pair, stage="replicate", family_id=family.family_id, ids=pair.replicate_ids
    )
    assert record.effect.upper == 0 and record.effect.lower == 0
    assert record.passed is False, "a flat world promotes nothing"
    pretend = Promotion(
        rule=rule,
        family_id=family.family_id,
        fit=record,
        replicate=record,
        fit_t1_ms=pair.fit_t1_ms,
        visible_from_ms=pair.fit_t1_ms + interval_ms(flat.interval_min),
    )
    live = tester.live_record(pretend, pair, at_ms=flat.split.validation_end_ms)
    assert live.live_support >= RULE_LIVE_MIN_SUPPORT, "the floor is met, so only the sign decides"
    assert live.live_interval.upper == 0
    assert live.demote is False and live.reason is None
    with pytest.raises(RuleRefusedError):
        tester.demote(live, pair)


def test_a_negative_live_record_below_the_support_floor_does_not_demote(tmp_path: Path) -> None:
    """18.2 step 7: ``live_support >= RULE_LIVE_MIN_SUPPORT`` **and** ``live_interval.upper < 0``.

    The floor is what stops a handful of bad bars from killing a rule. A window narrow enough to hold
    fewer than thirty matched rows is not evidence however negative it looks, so the record reports its
    numbers and the demotion waits for the rows.
    """
    table = _table()
    pair = rolling_pair(table, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    mirror = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=pair.registered_at_ms,
        scope=RuleScope(kinds=("binary",), providers=("kalshi",)),
        condition=[Predicate(feature="ret_7b_bp", op="lt", value=-300)],
        claim=RuleClaim(kind="drift", direction=1, magnitude_bp=120, factor_ppm=0),
        horizon_bars=1,
    )
    family = tester.register_family(_template(), pair, n_candidates=1, n_screened=1)
    record, _rows = tester.test_on_fold(
        mirror, pair, stage="replicate", family_id=family.family_id, ids=pair.replicate_ids
    )
    pretend = Promotion(
        rule=mirror,
        family_id=family.family_id,
        fit=record,
        replicate=record,
        fit_t1_ms=pair.fit_t1_ms,
        visible_from_ms=pair.fit_t1_ms + interval_ms(table.interval_min),
    )
    ids = [rows.meta.id for rows in table.markets]
    matched = sorted(
        row.t_ms
        for row in scope_rows(
            table, mirror, ids=ids, usual_bp=0, from_ms=pretend.visible_from_ms
        )
        if row.fired
    )
    assert len(matched) > RULE_LIVE_MIN_SUPPORT * 2, "the window must be able to cross the floor"
    narrow = tester.live_record(pretend, pair, at_ms=matched[RULE_LIVE_MIN_SUPPORT - 10])
    assert 0 < narrow.live_support < RULE_LIVE_MIN_SUPPORT
    assert narrow.live_interval.upper < 0, "the narrow window is negative, and still not evidence"
    assert narrow.demote is False and narrow.reason is None
    wide = tester.live_record(pretend, pair, at_ms=table.split.validation_end_ms)
    assert wide.live_support >= RULE_LIVE_MIN_SUPPORT
    assert wide.live_interval.upper < 0
    assert wide.demote is True and wide.reason == "live_negative"


def test_the_fdr_flag_gates_a_promotion_even_when_the_claim_holds(tmp_path: Path) -> None:
    """18.2 step 4 and ruling R238: promoted **iff** the claim holds on the replicate fold **and**
    ``fdr_passed``.

    The two halves are independent, and a rule that clears one and fails the other is a recorded
    negative result with every number in the row. The same rule is measured twice here, on the same fold
    and with the same rows: only the family's flag differs, so nothing but the flag can explain the
    verdict.
    """
    table = _table()
    pair = rolling_pair(table, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    rule = _drift_rule(pair.registered_at_ms)
    family = tester.register_family(_template(), pair, n_candidates=2, n_screened=2)
    holding, _rows = tester.test_on_fold(
        rule,
        pair,
        stage="replicate",
        family_id=family.family_id,
        ids=pair.replicate_ids,
        p_value_ppm=4_975,
        fdr_m=2,
        fdr_k=2,
        fdr_passed=True,
    )
    assert holding.effect.lower > 0 and holding.passed is True
    rejected, _rows = tester.test_on_fold(
        rule,
        pair,
        stage="replicate",
        family_id=family.family_id,
        ids=pair.replicate_ids,
        p_value_ppm=900_000,
        fdr_m=2,
        fdr_k=0,
        fdr_passed=False,
    )
    assert rejected.effect.lower == holding.effect.lower, "the claim still holds on the fold"
    assert rejected.support == holding.support
    assert rejected.passed is False, "a family's FDR step is a second gate and not a report"
    rows = [row for row in ledger.rules() if row.get("stage") == "replicate"]
    assert [row["passed"] for row in rows] == [True, False]
    assert [row["fdr_passed"] for row in rows] == [True, False]


def test_a_family_of_two_can_still_reject_which_is_the_arithmetic_r282_corrects() -> None:
    """Ruling R282's aside, refuting the critic: there is no floor at ten candidates.

    The bar is ``p_(k) * m <= k * q``, so at ``m = 2`` a p-value at or under ``q / m`` clears ``k = 1``.
    What R282 fixed is the inadmissible ``p = 0`` and the coarse grid, not a hard floor on the family
    size, and a build that implemented the imagined floor would refuse every small family the
    ``(b + 1) / (B + 1)`` estimator exists to serve.
    """
    assert benjamini_hochberg([20_000, 900_000]) == (True, False)
    assert _benjamini_hochberg_k([20_000, 900_000]) == 1
    assert benjamini_hochberg([25_000]) == (True,), "a family of one rejects at p <= q"
    finest = PPM_ONE // (RULE_PERMUTATIONS_MIN + 1)
    assert finest * 2 <= FDR_Q_PPM, (
        "the minimum permutation count must resolve a p-value fine enough for the k = 1 bar of a family "
        "of two, which is what tying the count to n_screened is for"
    )


def test_the_miner_counts_what_it_looked_at_and_not_what_it_kept() -> None:
    """18.2: every candidate enumerated counts toward ``n_candidates``, whatever the floors did to it.

    A count of survivors is the dishonest version. The family's Benjamini-Hochberg bar charges for
    looking, so a search that dropped nine candidates in ten and reported one would have bought itself a
    cheaper bar by forgetting. One feature and two operators make the arithmetic checkable: the search
    enumerates ``len(MINER_OPS) * len(thresholds)`` conjunctions and can grow no further, because a
    second predicate on the same feature is refused.
    """
    table = _table()
    pair = rolling_pair(table, 4)
    scope = RuleScope(kinds=("binary",), providers=("kalshi",))
    claim = RuleClaim(kind="drift", direction=1, magnitude_bp=120, factor_ppm=0)
    result = mine(table, pair, scope=scope, claim=claim, horizon_bars=1, features=("ret_7b_bp",))
    fit = set(pair.fit_ids)
    observed = [
        value
        for rows in table.in_scope(scope)
        if rows.meta.id in fit
        for bar in rows.bars
        for value in (read_feature("ret_7b_bp", bar.blocks),)
        if value is not None
    ]
    thresholds = quantiles_ppm(observed)
    assert thresholds, "the fit fold must offer the feature, or the count below is zero either way"
    assert result.n_candidates == len(MINER_OPS) * len(thresholds)
    assert result.n_candidates > len(result.candidates), (
        "the floors must have dropped something, or the count and the keep would agree by luck"
    )


def test_the_matched_mean_rounds_half_away_from_zero_so_a_loss_and_its_mirror_agree() -> None:
    """Integers only (section 1): the mean of the matched rows is rounded, and symmetrically.

    Floor division pushes a negative mean one unit further from zero than its positive mirror, so a rule
    and its exact opposite would not report opposite lifts, the miner's order would depend on the sign,
    and the demotion bar of ``upper < 0`` would sit half a unit off centre.
    """
    assert mean_half_away(5, 2) == 3 and mean_half_away(-5, 2) == -3
    assert mean_half_away(7, 3) == 2 and mean_half_away(-7, 3) == -2
    assert mean_half_away(0, 4) == 0
    assert mean_half_away(3, 0) == 0, "no matched row is a mean of zero and never a division"
    for total in range(-11, 12):
        for count in (1, 2, 3, 4, 7):
            assert mean_half_away(total, count) == -mean_half_away(-total, count)


def test_the_replicate_ledger_row_carries_the_permutation_count_the_journal_cannot(tmp_path: Path) -> None:
    """18.2 step 3 asks the replicate row for ``permutations``; 9.4 and ``journal.v2.json`` refuse it.

    The catalogue row of 9.4 lists fourteen fields and ``permutations`` is not among them, and the
    schema's ``rule_tested`` closes its object with ``unevaluatedProperties: false``, so the count cannot
    ride on the journal event without failing the contract's own validator at gate G4. The ledger line is
    this package's own file and already carries what the event cannot, so the count goes there and the
    event keeps the shape 9.4 states. The last assertion is the one that keeps the two in step: the
    record's fields are exactly the schema's, so a fifteenth field added here would fail here too.
    """
    table = _table()
    pair = rolling_pair(table, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    result = tester.run_family(
        [_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=1
    )
    assert result.permutations == permutations_for(result.family.n_screened)
    replicate = [row for row in ledger.rules() if row.get("stage") == "replicate"]
    assert len(replicate) == 1
    assert replicate[0]["permutations"] == result.permutations
    fit = [row for row in ledger.rules() if row.get("stage") == "fit"]
    assert fit and fit[0]["permutations"] is None, "the fit screen draws no shuffle"

    event_fields = set(result.replicate[0].to_dict())
    assert "permutations" not in event_fields
    schema = json.loads(
        (REPO / "src" / "pmx" / "schemas" / "journal.v2.json").read_text(encoding="utf-8")
    )
    declared = set(schema["$defs"]["rule_tested"]["properties"]) - {"type", "phase"}
    assert event_fields | {"generation"} == declared, (
        "the rule_tested record is 9.4's field list exactly, which journal.v2.json closes"
    )


# --------------------------------------------------------------------------------------------------
# The measurement table's own corners, the refusals, and the fold the null is drawn on
# --------------------------------------------------------------------------------------------------
# A second mutation pass over this package left these fourteen holes: each test below was written
# against a mutation the file survived, and each of those mutations is a contract sentence.


def test_the_null_is_drawn_on_the_replicate_fold_and_never_on_the_fit_fold(tmp_path: Path) -> None:
    """18.2 step 3 and ruling R238: the p-value is measured on the **replicate** fold.

    The two folds are given opposite planted effects here, so the one-sided null answers opposite
    things on them: on the months the rule was drawn from the matched mean is the highest it could be
    and luck almost never reaches it, and on the month it must replicate on the matched mean is the
    lowest it could be and luck reaches it every time. A tester that drew its shuffles on the fit fold
    would report the small p-value of the fold it already fitted, which is the whole reason 18.2 puts
    the null out of time.
    """
    table = _table(months=9, per_month=8, bars=12, steps=(120,) * 4 + (-120,) * 5)
    pair = rolling_pair(table, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(7), ledger=ledger)
    rule = _drift_rule(pair.registered_at_ms)
    result = tester.run_family([rule], template=_template(), pair=pair, n_candidates=1)
    assert result.family.n_screened == 1, "the rule must clear the fit screen to reach the null at all"
    assert result.fit[0].effect.lower > 0
    assert result.replicate[0].effect.upper < 0, "the replicate month carries the opposite effect"

    def _measured(ids: Sequence[str]) -> int:
        rows = scope_rows(table, rule, ids=ids, usual_bp=0)
        return rule_permutation_p_ppm(
            [row.y_bp for row in rows],
            [row.fired for row in rows],
            [row.block for row in rows],
            rng=RngTree(99),
            permutations=result.permutations,
        )

    on_the_fit_fold = _measured(pair.fit_ids)
    on_the_replicate_fold = _measured(pair.replicate_ids)
    assert on_the_fit_fold < 100_000 < 900_000 < on_the_replicate_fold, (
        "the two folds must answer differently, or this test cannot tell them apart"
    )
    assert result.replicate[0].p_value_ppm is not None
    assert result.replicate[0].p_value_ppm > 900_000
    assert result.replicate[0].passed is False


def test_a_volatility_claim_is_refused_when_its_usual_move_rests_on_too_few_rows(tmp_path: Path) -> None:
    """S2's own floor, which BUILD_STATE 9.6b leaves to this package.

    ``usual_bp`` is the median absolute move of every fit-fold row in the rule's scope, and a volatility
    claim measures the excess over it. A scope the fit fold does not cover has no median: over no rows it
    is zero, every absolute move becomes a positive excess, and the interval clears its lower bound on
    arithmetic instead of on evidence. In the first half below all three of 18.2's conditions hold -
    support, distinct markets and a positive lower bound - and the claim is still refused, so the floor
    is the only thing that can have refused it. The second half is the same claim on a scope the fit fold
    does cover, and it holds, so the floor refuses a missing baseline and not volatility itself.
    """
    table = _table()
    edges = table.split.month_edges_ms
    uncovered = RowTable(
        dataset_hash=table.dataset_hash,
        interval_min=table.interval_min,
        split=table.split,
        markets=tuple(
            MarketRows(
                meta=_meta(
                    id=rows.meta.id,
                    provider=rows.meta.provider,
                    resolved_at_ms=rows.meta.resolved_at_ms,
                    close_at_ms=rows.meta.close_at_ms,
                    created_at_ms=rows.meta.created_at_ms,
                    fold=rows.meta.fold,
                    resolution=rows.meta.resolution,
                    n_bars=rows.meta.n_bars,
                    tags=("m5",) if edges[4] <= rows.fold_key_ms < edges[5] else ("election",),
                ),
                bars=rows.bars,
                block=rows.block,
                fold_key_ms=rows.fold_key_ms,
            )
            for rows in table.markets
        ),
    )
    claim = RuleClaim(kind="volatility", direction=0, magnitude_bp=0, factor_ppm=1_500_000)
    condition = [Predicate(feature="ret_7b_bp", op="gt", value=-300)]
    pair = rolling_pair(uncovered, 4)
    rule = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=pair.registered_at_ms,
        scope=RuleScope(tags=("m5",)),
        condition=condition,
        claim=claim,
        horizon_bars=1,
    )
    tester = RuleTester(
        uncovered, rng=RngTree(5), ledger=RuleLedger(root=tmp_path / "thin", dataset_hash="a" * 64)
    )
    template = FamilyTemplate(
        scope_keys=("tags",),
        features=("ret_7b_bp",),
        claim_kind="volatility",
        horizon_bars=1,
        author_kind="miner",
    )
    family = tester.register_family(template, pair, n_candidates=1, n_screened=1)
    thin, _rows = tester.test_on_fold(
        rule, pair, stage="replicate", family_id=family.family_id, ids=pair.replicate_ids
    )
    assert thin.usual_bp == 0, "the fit fold carries no row of this scope, so there is no median"
    assert thin.support >= RULE_MIN_SUPPORT_DEFAULT
    assert thin.n_markets >= RULE_MIN_MARKETS
    assert thin.effect.lower > 0, "an excess over nothing is positive on every row"
    assert thin.passed is False, "and the floor refuses it anyway"

    covered_table = _table(months=9, per_month=8, bars=12, steps=(20,) * 4 + (200,) * 5)
    covered_pair = rolling_pair(covered_table, 4)
    covered_rule = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=covered_pair.registered_at_ms,
        scope=RuleScope(),
        condition=condition,
        claim=claim,
        horizon_bars=1,
    )
    covered_tester = RuleTester(
        covered_table, rng=RngTree(5), ledger=RuleLedger(root=tmp_path / "thick", dataset_hash="a" * 64)
    )
    covered_family = covered_tester.register_family(
        FamilyTemplate(
            scope_keys=(),
            features=("ret_7b_bp",),
            claim_kind="volatility",
            horizon_bars=1,
            author_kind="miner",
        ),
        covered_pair,
        n_candidates=1,
        n_screened=1,
    )
    thick, _more = covered_tester.test_on_fold(
        covered_rule,
        covered_pair,
        stage="replicate",
        family_id=covered_family.family_id,
        ids=covered_pair.replicate_ids,
    )
    assert thick.usual_bp == 20, "the fit months move by twenty bp, so that is the usual move"
    assert thick.effect.lower > 0 and thick.passed is True


def test_a_fold_pair_with_an_empty_side_is_refused(tmp_path: Path) -> None:
    """Ruling R277's neighbour: O1 raises ``FoldIntegrityError`` on an empty fold and the remedy is 7.4's
    fallback order, never a silently narrower test. Here the same condition is an ``InvalidConfigError``,
    because a pair with nothing on one side would screen on data and replicate on none of it, and report
    a rejection that means "there was no month" rather than "the rule did not hold".
    """
    table = _table()
    train_only = RowTable(
        dataset_hash=table.dataset_hash,
        interval_min=table.interval_min,
        split=table.split,
        markets=tuple(rows for rows in table.markets if rows.meta.fold == "train"),
    )
    assert train_only.markets, "the fixture must have a training fold, or this proves nothing"
    with pytest.raises(InvalidConfigError):
        headline_pair(train_only)
    validation_only = RowTable(
        dataset_hash=table.dataset_hash,
        interval_min=table.interval_min,
        split=table.split,
        markets=tuple(rows for rows in table.markets if rows.meta.fold == "validation"),
    )
    with pytest.raises(InvalidConfigError):
        headline_pair(validation_only)


def test_a_row_table_out_of_canonical_order_and_a_market_whose_bars_descend_are_refused() -> None:
    """Section 3 and 4.2: canonical order is what makes a ledger line and a hash reproducible.

    Both refusals are ``SchemaError`` at construction rather than a sort applied quietly, because a table
    that arrived out of order came from somewhere that disagrees with this one about the order, and
    sorting it would hide the disagreement instead of reporting it.
    """
    table = _table(months=1, per_month=2, bars=4)
    assert len(table.markets) > 1
    with pytest.raises(SchemaError):
        RowTable(
            dataset_hash=table.dataset_hash,
            interval_min=table.interval_min,
            split=table.split,
            markets=tuple(reversed(table.markets)),
        )
    bars = table.markets[0].bars
    assert len(bars) > 1
    with pytest.raises(SchemaError):
        MarketRows(meta=_meta(), bars=tuple(reversed(bars)), block="blk-1", fold_key_ms=0)


def test_a_drift_row_reads_the_claims_direction() -> None:
    """18.2's table: a drift row is ``direction * (price_{t+h} - price_t)``.

    The same defect ruling R280 fixed in the belief lives here in the measurement: drop the direction and
    a rule claiming the price falls is measured as though it claimed the price rises, so the sign the
    tester tests is the opposite of the sign the rule stated. The two rules below share a condition, so
    they fire on exactly the same rows and only the claim's direction can move a number.
    """
    table = _table(months=1, per_month=2, bars=8)
    ids = [rows.meta.id for rows in table.markets]
    condition = [Predicate(feature="ret_7b_bp", op="gt", value=300)]
    up = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=0,
        scope=RuleScope(),
        condition=condition,
        claim=RuleClaim(kind="drift", direction=1, magnitude_bp=120, factor_ppm=0),
        horizon_bars=1,
    )
    down = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=0,
        scope=RuleScope(),
        condition=condition,
        claim=RuleClaim(kind="drift", direction=-1, magnitude_bp=120, factor_ppm=0),
        horizon_bars=1,
    )
    assert up.rule_id != down.rule_id, "the direction is part of the statement and so of the id"
    rising = scope_rows(table, up, ids=ids, usual_bp=0)
    falling = scope_rows(table, down, ids=ids, usual_bp=0)
    assert rising and len(rising) == len(falling)
    assert any(row.fired and row.y_bp != 0 for row in rising), "a flat world would make the mirror vacuous"
    for left, right in zip(rising, falling, strict=True):
        assert (left.market_id, left.t_ms, left.fired) == (right.market_id, right.t_ms, right.fired)
        assert right.y_bp == -left.y_bp


def test_a_bias_row_on_a_continuous_kind_is_a_ratio_at_the_shortest_declared_horizon() -> None:
    """18.2's table: on a continuous kind a bias is ``direction * bp_ratio(price_{t+h} - price_t,
    price_t)`` with ``h`` the shortest declared horizon of 17.5.

    Two things are pinned at once, because a continuous kind is the only place either is visible. The
    horizon is the catalogue's and not the rule's: a bias rule's own ``horizon_bars`` is ``0`` by
    construction (there is no horizon to declare when the measurement is against a payout), so reading it
    here would measure a bar against itself and every row would be zero. And the quantity is a **ratio**
    in bp of the price, not a difference in the instrument's own scale, which is what lets one rule be
    tested on a market quoted in cents and on one quoted in dollars.
    """
    hour = MS_PER_HOUR
    resolved = 100 * hour
    closes = (5_000, 5_120, 5_360)
    bars = tuple(
        BarRow(
            t_ms=resolved - (len(closes) - position) * hour,
            close_bp=close,
            blocks={"tape": FeatureBlock(sensor="tape", values=(close,) + (0,) * 10)},
        )
        for position, close in enumerate(closes)
    )
    rows = MarketRows(
        meta=_meta(
            id="cx-1",
            kind="spot_crypto",
            resolved_at_ms=resolved,
            close_at_ms=resolved,
            created_at_ms=0,
            n_bars=len(closes),
        ),
        bars=bars,
        block="blk-cx-1",
        fold_key_ms=resolved,
    )
    table = RowTable(
        dataset_hash="c" * 64, interval_min=60, split=_table().split, markets=(rows,)
    )
    rule = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=0,
        scope=RuleScope(kinds=("spot_crypto",)),
        condition=[Predicate(feature="last_price_bp", op="gt", value=1)],
        claim=RuleClaim(kind="bias", direction=1, magnitude_bp=100, factor_ppm=0),
        horizon_bars=0,
    )
    assert default_horizons_bars(60)[0] == 1
    measured = scope_rows(table, rule, ids=["cx-1"], usual_bp=0)
    assert [row.y_bp for row in measured] == [bp_ratio(120, 5_000), bp_ratio(240, 5_120)]
    assert measured[0].y_bp == 240 and measured[1].y_bp == 469
    assert all(row.fired for row in measured)


def test_a_scope_matches_a_subset_of_tags_and_not_an_intersection() -> None:
    """18.2: a scope tuple is a conjunction, so two tags mean both tags and not either of them.

    An intersection would widen every multi-tag rule to the union of its tags the moment it was written
    down, which is a different statement from the one whose hash the id was taken over.
    """
    rule = make_rule(
        author_kind="miner",
        author_id="miner",
        born_at_ms=0,
        scope=RuleScope(tags=("election", "senate")),
        condition=[Predicate(feature="last_price_bp", op="gt", value=1)],
        claim=RuleClaim(kind="bias", direction=1, magnitude_bp=100, factor_ppm=0),
        horizon_bars=0,
    )
    blocks = {"tape": FeatureBlock(sensor="tape", values=(5_000,) + (0,) * 10)}
    assert rule.fires(blocks, _meta(tags=("election", "senate"))) is True
    assert rule.fires(blocks, _meta(tags=("election", "senate", "us"))) is True
    assert rule.fires(blocks, _meta(tags=("election",))) is False
    assert rule.fires(blocks, _meta(tags=("senate",))) is False
    assert rule.fires(blocks, _meta(tags=())) is False


def test_the_usual_move_median_rounds_a_tie_up() -> None:
    """Integers only (section 1): ``usual_bp`` is a median of absolute moves and an even count has none.

    The tie rounds up, away from zero, because a volatility claim measures the excess **over** the usual
    move: a baseline rounded down inflates every excess by half a unit, and half a unit in the direction
    of promoting is not a rounding choice, it is a bias.
    """
    assert _median([]) == 0
    assert _median([5]) == 5
    assert _median([10, 20, 30]) == 20
    assert _median([10, 30]) == 20
    assert _median([10, 31]) == 21, "twenty and a half rounds to twenty-one"
    assert _median([0, 1]) == 1
    assert _median([31, 10]) == 21, "the median sorts its own input"


def test_a_template_names_the_scope_keys_the_pass_fixed_and_no_others() -> None:
    """18.2: ``FamilyTemplate.scope_keys`` is the subset of the five whose values vary in the family.

    A template that named all five would put every family of every scope under one grammar, and the
    ``family_id`` of ruling R284 would stop telling a per-provider pass from a per-cohort one.
    """
    claim = RuleClaim(kind="drift", direction=1, magnitude_bp=120, factor_ppm=0)
    assert template_of(RuleScope(), ("ret_7b_bp",), claim, 1).scope_keys == ()
    assert template_of(RuleScope(providers=("kalshi",)), ("ret_7b_bp",), claim, 1).scope_keys == (
        "providers",
    )
    assert template_of(
        RuleScope(kinds=("binary",), providers=("kalshi",), cohorts=("co-kalshi-politics-a-b-c",)),
        ("ret_7b_bp", "bars_to_close"),
        claim,
        2,
    ) == FamilyTemplate(
        scope_keys=("kinds", "providers", "cohorts"),
        features=("bars_to_close", "ret_7b_bp"),
        claim_kind="drift",
        horizon_bars=2,
        author_kind="miner",
    )


def test_an_unknown_scope_key_off_a_payload_is_refused() -> None:
    """Ruling R236: the grammar is closed, so ``rule_from_dict`` is the door that closes it.

    A key nobody reads is worse than a key that fails: the rule would validate, take an id computed over
    the five keys the record knows, and claim to hold everywhere the sixth key meant to exclude.
    """
    payload = json.loads((CONTRACT / "rule.sample.json").read_text(encoding="utf-8"))
    scope = dict(payload["scope"])
    scope["regions"] = ["eu"]
    with pytest.raises(RuleRefusedError) as refused:
        rule_from_dict({**payload, "scope": scope})
    assert refused.value.context["keys"] == ["regions"]
    assert rule_from_dict(payload).scope == _sample_rule().scope, "the untouched payload still reads"


def test_a_family_cannot_screen_more_rules_than_it_enumerated(tmp_path: Path) -> None:
    """18.2 step 1: ``n_screened`` are the survivors of ``n_candidates``, so it can never exceed it.

    The pair is what the Benjamini-Hochberg bar is read against, and a family claiming to have screened
    more than it looked at would report an ``m`` smaller than the number of hypotheses behind it, which
    is the one direction that makes the bar too easy.
    """
    table = _table()
    pair = rolling_pair(table, 4)
    ledger = RuleLedger(root=tmp_path, dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(5), ledger=ledger)
    with pytest.raises(RuleRefusedError):
        tester.register_family(_template(), pair, n_candidates=1, n_screened=2)
    assert ledger.families() == (), "a refused family writes no line"
    accepted = tester.register_family(_template(), pair, n_candidates=2, n_screened=2)
    assert accepted.n_screened == accepted.n_candidates == 2
