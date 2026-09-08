"""D7: the RNG tree and the journal, the two ports Exchange paid for and pmx inherits.

What these tests are for, in the order the contract states the guarantees:

* **The tree is the only source of randomness and it is reproducible** (CONTRACTS_V2 6.1, 6.4). Two
  trees built from one seed draw the same values from every registered substream, a name that is not
  in the registry is refused, and every public helper consumes ``getrandbits`` and nothing else, which
  is what keeps a draw identical between glibc, msvcrt and macOS. A handful of golden integers are
  pinned so that a change to the pinned float primitives fails here rather than silently moving every
  journal hash in the product.
* **The journal's bytes are the artefact** (4.2, 4.3, 9.1). The file is LF and UTF-8 whatever the
  platform, its SHA-256 is the same read from events, from lines or from the file's own bytes, and the
  contract's own fixtures (``tests/fixtures/contract/journal.*.jsonl``, written by C0 before this code
  existed) re-serialise byte for byte through this encoder. That last one is the test that would catch
  a canonical-serialisation drift between two packages.
* **The catalogue is the schema** (9.2, 9.4). Every event of section 9 has a class here, every class's
  payload field set is exactly the ``required`` list of ``journal.v2.json``, and every class's legal
  phases are exactly the phase the schema pins. A new event cannot be added to one side only.
* **What may never enter a journal is refused at the emitting call site** (4.4): a float, a wall clock,
  a duration, a provider cost, a token or retry count, an LLM rationale, a set. Not at the next flush,
  not at read time, and not only for a file-backed journal.

Everything here is offline and deterministic: no network, no clock, no ``random`` module state.
"""

from __future__ import annotations

import importlib
import json
import math
import random
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Any

import pytest

from pmx import rng as rngmod
from pmx.data.schema import SCHEMA_DIR
from pmx.errors import JournalError, NonCanonicalValueError, SchemaError, UnknownSubstreamError
from pmx.journal import (
    _BAR_PHASES,
    EVENT_CLASSES,
    EVENT_TYPES,
    FORBIDDEN_PAYLOAD_FIELDS,
    JOURNAL_ENCODING,
    JOURNAL_NEWLINE,
    ActionReceived,
    ActionRejected,
    AgentRuined,
    BarClosed,
    BarOpened,
    CandidateScored,
    EquityMarked,
    EvolutionEnded,
    EvolutionStarted,
    FeeCharged,
    Filled,
    ForecastRecorded,
    GenerationClosed,
    GenerationStarted,
    HiveWritten,
    Journal,
    JournalEvent,
    MarketListed,
    MarketPriced,
    MemoryWritten,
    ObservationBuilt,
    OrderExpired,
    OrderPlaced,
    OrderRejected,
    ReplyReceived,
    ResearchSpent,
    RunEnded,
    RunStarted,
    SealedTestOpened,
    Settled,
    SettlementApplied,
    _forbidden_reason,
    canonical_json,
    canonical_sha256,
    event_from_line,
    event_to_line,
    filter_events,
    iter_bars,
    iter_journal,
    journal_hash,
    journal_hash_from_lines,
    journal_hash_of_file,
    payload_field_names,
    read_journal,
    validate_event_dict,
    verify_journal,
    write_journal,
)
from pmx.rng import (
    RNG_ALGORITHM_VERSION,
    SEED_SPACE,
    SUBSTREAM_PREFIXES,
    SUBSTREAMS,
    RngTree,
    bernoulli,
    beta,
    choice,
    choices_weighted,
    derive_seed,
    is_registered_substream,
    lognormal,
    normal,
    ordered,
    randint,
    random_open_unit,
    random_unit,
    sample_without_replacement,
    shuffle_seeded,
    stable_key,
    uniform,
)
from pmx.types import PHASE_ORDER

REPO = Path(__file__).resolve().parent.parent
CONTRACT_FIXTURES = REPO / "tests" / "fixtures" / "contract"

RUN_ID = "r-f60463ae-7-f119e64e"
EVO_RUN_ID = "e-f60463ae-7-f119e64e"
MARKET_ID = "demo-brexit-2016"
AGENT_ID = "contrarian"
HASH_A = "a" * 64
HASH_B = "b" * 64
T0_MS = 1_466_640_000_000
T1_MS = 1_466_726_400_000

# Golden values. They pin the pinned algorithms of section 6.1: a change to ``_log``, ``_exp``,
# ``_norm_ppf``, ``_randbelow`` or the Fisher-Yates loop fails here, loudly, instead of moving every
# journal hash in the product while looking like a determinism bug somewhere else. Recomputing one is a
# deliberate act that comes with a bump of ``RNG_ALGORITHM_VERSION``.
GOLDEN_DERIVE_SEED_HEX = "d6aecc77699f1998ce1ebce569f77050caf4b59c4d038663fa284714973fdcca"
GOLDEN_GETRANDBITS = [3_330_534_848, 145_760_158, 3_422_264_144, 1_660_148_552]
GOLDEN_SHUFFLE = [4, 1, 2, 7, 3, 6, 5, 0]
GOLDEN_UNIT_MILLI = 725
GOLDEN_NORMAL_MILLI = 597
GOLDEN_BETA_MILLI = 307
#: ``sha256(canonical_json({"agent_id": "contrarian", "prob_ppm": 550000}))``.
GOLDEN_PAYLOAD_SHA256 = "86a5637009e03a59f7d1c5fdf0e0efcb079252fb160f339747ce72c9fe333b45"

GENOME: dict[str, Any] = {
    "family": "follower",
    "genes": {"edge_min_bp": 0, "shrink_permille": 1000},
    "inner": None,
    "members": [],
    "prompt": None,
}


# ==================================================================================================
# pmx.rng: the registry
# ==================================================================================================
def test_the_registry_is_exactly_the_one_of_contract_6_3() -> None:
    """The registry is contract, not a suggestion: a draw that is not listed here does not exist."""
    assert frozenset(
        {
            "stats.bootstrap",
            "stats.permutation",
            "evolution.parents",
            "evolution.mutation",
            "evolution.crossover",
            "evolution.immigrants",
            "evolution.novelty",
            "evolution.prompt_mutation",
            "dataset.subsample",
            "contamination.paraphrases",
            "test.scratch",
        }
    ) == SUBSTREAMS
    assert frozenset({"agent", "test"}) == SUBSTREAM_PREFIXES
    assert RNG_ALGORITHM_VERSION == "1.0.0"
    assert SEED_SPACE == 2**63


def test_the_runner_has_no_substream() -> None:
    """Section 6.2: the runner consumes no randomness, so no ``runner.*`` name may be registered."""
    assert [name for name in SUBSTREAMS if name.startswith("runner")] == []
    assert "runner" not in SUBSTREAM_PREFIXES
    assert not is_registered_substream("runner.bar_shuffle.7")


def test_parametric_families_need_a_non_empty_suffix() -> None:
    assert is_registered_substream("agent.market_follower")
    assert is_registered_substream("test.anything")
    assert not is_registered_substream("agent")
    assert not is_registered_substream("agent.")
    assert not is_registered_substream("agentx.foo")


@pytest.mark.parametrize("name", ["", "world.markets", "mm.tiebreak", "evolution", "stats.bootstrapx"])
def test_an_unregistered_substream_is_refused_by_every_accessor(name: str) -> None:
    tree = RngTree(7)
    for accessor in (tree.substream, tree.fresh_substream, tree.seed_for):
        with pytest.raises(UnknownSubstreamError):
            accessor(name)


# ==================================================================================================
# pmx.rng: determinism
# ==================================================================================================
def test_two_trees_of_the_same_seed_draw_the_same_values_from_every_substream() -> None:
    """The done-when of D7: same seed, same substream draws, for every registered name."""
    names = sorted(SUBSTREAMS) + ["agent.market_follower", "agent.contrarian", "test.scratch.7"]
    left = {name: [RngTree(2026).substream(name).getrandbits(64) for _ in range(4)] for name in names}
    right = {name: [RngTree(2026).substream(name).getrandbits(64) for _ in range(4)] for name in names}
    assert left == right
    # ... and two different names never share a stream.
    first_draws = {name: values[0] for name, values in left.items()}
    assert len(set(first_draws.values())) == len(names)


def test_a_substream_is_cached_and_keeps_advancing() -> None:
    tree = RngTree(11)
    first = tree.substream("stats.bootstrap")
    assert tree.substream("stats.bootstrap") is first
    walked = [first.getrandbits(32) for _ in range(3)]
    assert walked[0] != walked[1] or walked[1] != walked[2]
    fresh = tree.fresh_substream("stats.bootstrap")
    assert fresh is not first
    assert fresh.getrandbits(32) == RngTree(11).substream("stats.bootstrap").getrandbits(32)


def test_child_trees_are_isolated_and_qualify_the_name() -> None:
    tree = RngTree(99)
    child = tree.child("stats")
    assert child.root_seed == tree.root_seed
    assert child.namespace == "stats"
    assert child.seed_for("stats.bootstrap") == derive_seed(99, "stats/stats.bootstrap")
    assert child.seed_for("stats.bootstrap") != tree.seed_for("stats.bootstrap")
    grandchild = child.child("permutation")
    assert grandchild.seed_for("test.scratch") == derive_seed(99, "stats/permutation/test.scratch")


def test_derive_seed_is_stable_namespaced_and_bounded() -> None:
    assert derive_seed(7, "stats.bootstrap") == derive_seed(7, "stats.bootstrap")
    assert derive_seed(7, "stats.bootstrap") != derive_seed(8, "stats.bootstrap")
    assert derive_seed(7, "stats.bootstrap") != derive_seed(7, "stats.permutation")
    assert 0 <= derive_seed(7, "stats.bootstrap") < 2**256
    # A golden digest: the derivation is blake2b(uint64_be(seed) || 0x1f || utf8(name)) and moving it
    # would move every draw in the product.
    assert format(derive_seed(7, "stats.bootstrap"), "064x") == GOLDEN_DERIVE_SEED_HEX


@pytest.mark.parametrize("bad", [-1, 2**64, 2**70])
def test_a_seed_outside_the_unsigned_64_bit_range_is_refused(bad: int) -> None:
    with pytest.raises(ValueError, match="unsigned 64 bit"):
        RngTree(bad)
    with pytest.raises(ValueError, match="unsigned 64 bit"):
        derive_seed(bad, "test.scratch")


def test_the_evolution_seed_recipe_of_section_6_2() -> None:
    """``run_seed_g = derive_seed(seed, f"generation/{g}") % SEED_SPACE``: reproducible and storable."""
    seeds = [derive_seed(4242, f"generation/{g}") % SEED_SPACE for g in range(5)]
    assert seeds == [derive_seed(4242, f"generation/{g}") % SEED_SPACE for g in range(5)]
    assert all(0 <= seed < 2**63 for seed in seeds)
    assert len(set(seeds)) == 5


def test_golden_draws_pin_the_algorithms() -> None:
    """If a pinned primitive moves, this fails here instead of moving a journal hash silently."""
    tree = RngTree(7)
    assert [tree.substream("evolution.mutation").getrandbits(32) for _ in range(4)] == GOLDEN_GETRANDBITS
    assert shuffle_seeded(RngTree(7).substream("evolution.parents"), tuple(range(8))) == GOLDEN_SHUFFLE
    assert _milli(random_unit(RngTree(7).substream("test.scratch"))) == GOLDEN_UNIT_MILLI
    assert _milli(normal(RngTree(7).substream("test.scratch"))) == GOLDEN_NORMAL_MILLI
    assert _milli(beta(RngTree(7).substream("test.scratch"), 2.0, 5.0)) == GOLDEN_BETA_MILLI


def _milli(value: float) -> int:
    """Quantise a draw the way every consumer does, without the banker's rounding of ``round``."""
    return math.floor(value * 1000 + 0.5)


# ==================================================================================================
# pmx.rng: only getrandbits, and the helpers' contracts
# ==================================================================================================
class _OnlyGetrandbits(random.Random):
    """A generator that fails the test if anything but ``getrandbits`` is consumed (section 6.1)."""

    def __init__(self, seed: int) -> None:
        super().__init__(seed)
        self.calls = 0

    def getrandbits(self, k: int) -> int:
        self.calls += 1
        return super().getrandbits(k)

    def random(self) -> float:
        raise AssertionError("random() reaches libm and is banned in pmx.rng")

    def shuffle(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("shuffle() is an implementation detail and is banned in pmx.rng")

    def choice(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("choice() is an implementation detail and is banned in pmx.rng")

    def randrange(self, *args: Any, **kwargs: Any) -> int:
        raise AssertionError("randrange() is an implementation detail and is banned in pmx.rng")

    def randint(self, *args: Any, **kwargs: Any) -> int:
        raise AssertionError("randint() is an implementation detail and is banned in pmx.rng")

    def gauss(self, *args: Any, **kwargs: Any) -> float:
        raise AssertionError("gauss() reaches libm and caches a spare value; banned in pmx.rng")

    def betavariate(self, *args: Any, **kwargs: Any) -> float:
        raise AssertionError("betavariate() reaches libm and is banned in pmx.rng")

    def gammavariate(self, *args: Any, **kwargs: Any) -> float:
        raise AssertionError("gammavariate() reaches libm and is banned in pmx.rng")

    def uniform(self, *args: Any, **kwargs: Any) -> float:
        raise AssertionError("uniform() of the standard library is banned in pmx.rng")

    def sample(self, *args: Any, **kwargs: Any) -> list[Any]:
        raise AssertionError("sample() is an implementation detail and is banned in pmx.rng")


def test_every_public_helper_consumes_getrandbits_and_nothing_else() -> None:
    spy = _OnlyGetrandbits(3)
    items = ("a", "b", "c", "d")
    assert len(shuffle_seeded(spy, items)) == 4
    assert choice(spy, items) in items
    assert len(choices_weighted(spy, items, (1.0, 2.0, 3.0, 4.0), k=3)) == 3
    assert len(sample_without_replacement(spy, items, 2)) == 2
    assert 0.0 <= random_unit(spy) < 1.0
    assert 0.0 < random_open_unit(spy) < 1.0
    assert isinstance(normal(spy, 0.0, 1.0), float)
    assert lognormal(spy, 0.0, 1.0) > 0.0
    assert isinstance(bernoulli(spy, 0.5), bool)
    assert 3 <= randint(spy, 3, 9) <= 9
    assert 1.0 <= uniform(spy, 1.0, 2.0) < 2.0
    assert 0.0 <= beta(spy, 2.0, 3.0) <= 1.0
    assert spy.calls > 0


def test_shuffle_is_a_permutation_that_never_mutates_its_input() -> None:
    items = tuple(range(16))
    shuffled = shuffle_seeded(RngTree(5).substream("test.scratch"), items)
    assert sorted(shuffled) == list(items)
    assert items == tuple(range(16))
    assert shuffled != list(items)  # 16! makes the identity permutation a non event


def test_weighted_draws_follow_the_weights_and_refuse_bad_input() -> None:
    rng = RngTree(5).substream("test.scratch")
    drawn = choices_weighted(rng, ("rare", "common"), (1.0, 999.0), k=200)
    assert drawn.count("common") > drawn.count("rare")
    with pytest.raises(ValueError, match="same length"):
        choices_weighted(rng, ("a", "b"), (1.0,))
    with pytest.raises(ValueError, match="non negative"):
        choices_weighted(rng, ("a", "b"), (1.0, -1.0))
    with pytest.raises(ValueError, match="non negative"):
        choices_weighted(rng, ("a", "b"), (0.0, 0.0))


def test_the_small_helpers_hold_their_edges() -> None:
    rng = RngTree(5).substream("test.scratch")
    assert sorted(sample_without_replacement(rng, ("a", "b"), 9)) == ["a", "b"]
    assert sample_without_replacement(rng, ("a", "b"), -3) == []
    with pytest.raises(IndexError):
        choice(rng, ())
    with pytest.raises(ValueError, match="empty range"):
        randint(rng, 9, 3)
    with pytest.raises(ValueError, match=r"p must be in \[0, 1\]"):
        bernoulli(rng, 1.5)
    with pytest.raises(ValueError, match="sigma"):
        normal(rng, 0.0, -1.0)
    with pytest.raises(ValueError, match="strictly positive"):
        beta(rng, 0.0, 1.0)
    assert stable_key("p017", 3) == "p017.3"
    assert ordered({"b", "a", "c"}) == ["a", "b", "c"]
    assert randint(rng, 4, 4) == 4


def test_the_pinned_log_and_exp_agree_with_libm_to_a_dozen_digits() -> None:
    """They are reimplemented for reproducibility, not for a different answer."""
    for x in (1e-8, 0.25, 0.5, 1.0, 1.5, 2.0, 10.0, 1e8):
        assert rngmod._log(x) == pytest.approx(math.log(x), rel=1e-12, abs=1e-12)
    for x in (-20.0, -1.0, 0.0, 1.0, 5.0, 20.0):
        assert rngmod._exp(x) == pytest.approx(math.exp(x), rel=1e-12)
    for p in (0.001, 0.02, 0.25, 0.5, 0.75, 0.98, 0.999):
        assert rngmod._norm_ppf(p) == pytest.approx(-rngmod._norm_ppf(1.0 - p), rel=1e-9, abs=1e-9)
    with pytest.raises(ValueError, match="log domain"):
        rngmod._log(0.0)
    with pytest.raises(ValueError, match="exp domain"):
        rngmod._exp(math.inf)
    with pytest.raises(ValueError, match=r"p in \(0, 1\)"):
        rngmod._norm_ppf(0.0)


def test_bernoulli_and_normal_are_distributions_not_constants() -> None:
    rng = RngTree(17).substream("test.scratch")
    flips = [bernoulli(rng, 0.5) for _ in range(400)]
    assert 150 < sum(flips) < 250
    draws = [normal(rng, 0.0, 1.0) for _ in range(400)]
    mean_milli = _milli(sum(draws) / 400)
    assert abs(mean_milli) < 150
    assert max(draws) > 1.0 > min(draws)


# ==================================================================================================
# pmx.journal: canonical_json (section 4.1)
# ==================================================================================================
class _Colour(StrEnum):
    RED = "red"


class _Size(IntEnum):
    ONE = 1


@dataclass(frozen=True, slots=True)
class _NotSerialisable:
    value: int


def test_canonical_json_sorts_keys_drops_whitespace_and_keeps_utf8() -> None:
    payload = {"b": 1, "a": {"z": [1, 2, (3, 4)], "y": None}, "A": True}
    assert canonical_json(payload) == '{"A":true,"a":{"y":null,"z":[1,2,[3,4]]},"b":1}'
    assert canonical_json({"note": "resolué"}) == '{"note":"resolué"}'
    assert JOURNAL_NEWLINE not in canonical_json(payload)
    assert canonical_json((1, "two", None)) == '[1,"two",null]'
    assert canonical_json(_Colour.RED) == '"red"'


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"p": 0.5}, "floats are forbidden"),
        ({"p": [1, 2.0]}, "floats are forbidden"),
        ({"p": float("nan")}, "floats are forbidden"),
        ({"ids": {"a", "b"}}, "sets have no stable order"),
        ({"blob": b"01"}, "bytes have no canonical"),
        ({"size": _Size.ONE}, "str-subclass Enum"),
        ({"row": _NotSerialisable(1)}, "unsupported type"),
        ({1: "one"}, "object keys must be strings"),
        ({"nested": {"deep": {"cost": 1.25}}}, "floats are forbidden"),
    ],
)
def test_canonical_json_refuses_what_a_journal_may_not_carry(payload: object, match: str) -> None:
    with pytest.raises(NonCanonicalValueError, match=match):
        canonical_json(payload)


def test_the_error_names_the_path_of_the_offending_value() -> None:
    with pytest.raises(NonCanonicalValueError) as caught:
        canonical_json({"agents": [{"pnl": 1}, {"pnl": 2.5}]})
    assert caught.value.context["path"] == "$.agents[1].pnl"


def test_canonical_sha256_is_the_hash_of_the_canonical_bytes() -> None:
    payload = {"agent_id": AGENT_ID, "prob_ppm": 550_000}
    assert canonical_sha256(payload) == GOLDEN_PAYLOAD_SHA256
    assert canonical_sha256(payload) == canonical_sha256({"prob_ppm": 550_000, "agent_id": AGENT_ID})
    assert len(canonical_sha256(payload)) == 64


# ==================================================================================================
# pmx.journal: the catalogue against the schema (sections 9.2 and 9.4)
# ==================================================================================================
def _journal_schema() -> Mapping[str, Any]:
    loaded: Mapping[str, Any] = json.loads((SCHEMA_DIR / "journal.v2.json").read_text(encoding=JOURNAL_ENCODING))
    return loaded


def _schema_event_names() -> tuple[str, ...]:
    schema = _journal_schema()
    refs = [str(entry["$ref"]).rsplit("/", 1)[-1] for entry in schema["oneOf"]]
    return tuple(refs)


def test_every_event_of_the_schema_has_a_class_and_the_reverse() -> None:
    assert set(EVENT_TYPES) == set(_schema_event_names())
    assert len(EVENT_TYPES) == len(set(EVENT_TYPES)) == 29
    assert tuple(EVENT_CLASSES) == EVENT_TYPES


@pytest.mark.parametrize("event_type", _schema_event_names())
def test_a_class_payload_is_exactly_its_schema_entry(event_type: str) -> None:
    """The catalogue cannot drift from the schema: same fields, same phases, same bar_ms rule."""
    entry = _journal_schema()["$defs"][event_type]
    event_cls = EVENT_CLASSES[event_type]
    assert sorted(payload_field_names(event_cls)) == sorted(entry["required"])
    phase_spec = entry["properties"]["phase"]
    expected_phases = (phase_spec["const"],) if "const" in phase_spec else tuple(phase_spec["enum"])
    assert expected_phases == event_cls.PHASES
    assert set(event_cls.PHASES) <= set(PHASE_ORDER)


def test_the_phase_order_is_the_one_of_ruling_r46() -> None:
    assert PHASE_ORDER == (
        "pre",
        "open",
        "observe",
        "decide",
        "execute",
        "settle",
        "learn",
        "hive",
        "close",
        "generation",
        "post",
    )
    assert PHASE_ORDER[1:9] == _BAR_PHASES
    assert "generation" not in _BAR_PHASES


def test_the_constants_two_packages_both_declare_agree() -> None:
    """``JOURNAL_ENCODING``, ``SEED_SPACE`` and the RNG version also live in ``pmx.types``.

    Section 14 gives the first two to D7 and the third is re-exported from here on purpose; while a
    second declaration exists, a drift between them would be silent, so it is pinned rather than
    trusted. The ``getattr`` default is what keeps this honest if the gate removes the duplicate."""
    import pmx.types as types_module

    assert getattr(types_module, "JOURNAL_ENCODING", JOURNAL_ENCODING) == JOURNAL_ENCODING
    assert getattr(types_module, "SEED_SPACE", SEED_SPACE) == SEED_SPACE
    assert getattr(types_module, "RNG_ALGORITHM_VERSION", RNG_ALGORITHM_VERSION) == RNG_ALGORITHM_VERSION


def test_no_legal_field_name_collides_with_the_forbidden_list() -> None:
    """The ban of section 4.4 must never refuse a field the catalogue itself declares."""
    for event_cls in EVENT_CLASSES.values():
        for name in payload_field_names(event_cls):
            assert _forbidden_reason(name) is None, (event_cls.TYPE, name)
    assert "rationale" in FORBIDDEN_PAYLOAD_FIELDS


# ==================================================================================================
# pmx.journal: a complete journal of every event type
# ==================================================================================================
def _backtest_payloads() -> tuple[tuple[type[JournalEvent], int, str | None, dict[str, Any]], ...]:
    """One legal event of every backtest type, in the phase order of one bar (section 8.2)."""
    intent: dict[str, Any] = {
        "market_id": MARKET_ID,
        "prob_ppm": 480_000,
        "kind": "target",
        "target_position": 12,
        "side": None,
        "price_bp": None,
        "size": None,
        "ttl_bars": None,
    }
    roster_entry: dict[str, Any] = {
        "agent_id": AGENT_ID,
        "family": "follower",
        "kind": "scripted",
        "genome_hash": HASH_B,
        "genome": GENOME,
        "model": None,
        "knowledge_cutoff_ms": None,
    }
    return (
        (
            RunStarted,
            0,
            None,
            {
                "seed": 7,
                "engine_version": "2.0.0",
                "contract_version": "2.0",
                "rng_algorithm_version": RNG_ALGORITHM_VERSION,
                "dataset_name": "demo_v1",
                "dataset_hash": HASH_A,
                "interval_min": 1440,
                "t0_ms": T0_MS,
                "t1_ms": T1_MS,
                "market_ids": (MARKET_ID,),
                "config": {"seed": 7, "fold": "all"},
                "config_hash": HASH_B,
                "folds": {"train_end_ms": T0_MS, "validation_end_ms": T1_MS},
                "memory_from_run_id": None,
                "memory_hash": None,
                "memory_from_run_t1_ms": None,
                "contamination_hash": None,
                "roster": (roster_entry,),
            },
        ),
        (
            SealedTestOpened,
            0,
            None,
            {
                "claim_id": "c-f60463ae-demo-0123456789abcdef",
                "dataset_hash": HASH_A,
                "genome_hash": HASH_B,
                "provider": "demo",
                "n_markets": 1,
                "market_ids": (MARKET_ID,),
            },
        ),
        (
            BarOpened,
            T0_MS,
            None,
            {
                "open_market_ids": (MARKET_ID,),
                "tradable_market_ids": (MARKET_ID,),
                "settling_market_ids": (MARKET_ID,),
                "listed_market_ids": (MARKET_ID,),
            },
        ),
        (
            MarketListed,
            T0_MS,
            None,
            {
                "market_id": MARKET_ID,
                "provider": "demo",
                "category": "politics",
                "tags": (),
                "event_key": None,
                "created_at_ms": 1_454_284_800_000,
                "close_at_ms": T1_MS,
                "interval_min": 1440,
                "fee_schedule_id": "demo-zero",
                "hardness_tags": ("upset",),
                "fold": "train",
            },
        ),
        (
            MarketPriced,
            T0_MS,
            None,
            {
                "market_id": MARKET_ID,
                "close_bp": 2_500,
                "last_close_bp": 2_600,
                "vwap_bp": 2_550,
                "volume_milli": 0,
            },
        ),
        (
            OrderExpired,
            T0_MS,
            "open",
            {
                "order_id": "o-00000001",
                "agent_id": AGENT_ID,
                "market_id": MARKET_ID,
                "remaining_size": 3,
                "released_cents": 900,
                "reason": "ttl",
            },
        ),
        (
            ObservationBuilt,
            T0_MS,
            None,
            {
                "agent_id": AGENT_ID,
                "n_markets": 1,
                "n_news": 4,
                "n_hive": 0,
                "n_bars_max": 90,
                "research_remaining": 10,
                "bytes": 4_096,
                "obs_sha256": HASH_A,
            },
        ),
        (
            ReplyReceived,
            T0_MS,
            None,
            {"agent_id": AGENT_ID, "source": "llm", "error": None, "schema_valid": True, "n_lessons": 1},
        ),
        (
            ActionReceived,
            T0_MS,
            None,
            {
                "agent_id": AGENT_ID,
                "source": "scripted",
                "intents": (intent,),
                "research": {"kind": "news", "market_id": MARKET_ID},
                "notes": "held the line",
                "n_lessons": 0,
                "n_rejected": 1,
            },
        ),
        (
            ActionRejected,
            T0_MS,
            None,
            {
                "agent_id": AGENT_ID,
                "market_id": MARKET_ID,
                "scope": "market",
                "item_index": 1,
                "reason": "duplicate",
                "detail": "second action on one market in one bar",
            },
        ),
        (
            ForecastRecorded,
            T0_MS,
            None,
            {"agent_id": AGENT_ID, "market_id": MARKET_ID, "prob_ppm": 480_000, "carried": False},
        ),
        (
            ResearchSpent,
            T0_MS,
            None,
            {
                "agent_id": AGENT_ID,
                "kind": "news",
                "market_id": MARKET_ID,
                "units": 1,
                "remaining": 9,
                "granted": True,
            },
        ),
        (
            MemoryWritten,
            T0_MS,
            "decide",
            {
                "agent_id": AGENT_ID,
                "kind": "lesson",
                "key": "lesson/0001",
                "payload": {"text": "fade the tape late"},
                "bytes_after": 512,
            },
        ),
        (
            OrderPlaced,
            T0_MS,
            None,
            {
                "order_id": "o-00000002",
                "agent_id": AGENT_ID,
                "market_id": MARKET_ID,
                "kind": "market",
                "side": "buy",
                "price_bp": None,
                "size": 12,
                "ttl_bars": None,
                "expires_at_ms": None,
                "reserved_cents": 3_060,
                "origin": "target",
            },
        ),
        (
            OrderRejected,
            T0_MS,
            None,
            {
                "agent_id": AGENT_ID,
                "market_id": MARKET_ID,
                "item_index": 0,
                "reason": "not_tradable",
                "detail": "the settling bar never fills",
            },
        ),
        (
            Filled,
            T0_MS,
            None,
            {
                "order_id": "o-00000002",
                "agent_id": AGENT_ID,
                "market_id": MARKET_ID,
                "side": "buy",
                "kind": "market",
                "requested_size": 12,
                "filled_size": 12,
                "unfilled_size": 0,
                "unfilled_reason": "none",
                "base_price_bp": 2_550,
                "slippage_bp": 3,
                "fill_price_bp": 2_553,
                "price_source": "vwap",
                "close_size": 0,
                "open_size": 12,
                "cash_delta_cents": -3_064,
                "released_cents": 3_060,
                "position_before": 0,
                "position_after": 12,
                "avg_cost_bp_after": 2_553,
            },
        ),
        (
            FeeCharged,
            T0_MS,
            None,
            {
                "order_id": "o-00000002",
                "agent_id": AGENT_ID,
                "market_id": MARKET_ID,
                "fee_cents": 0,
                "schedule_id": "demo-zero",
                "role": "taker",
            },
        ),
        (
            Settled,
            T0_MS,
            None,
            {
                "market_id": MARKET_ID,
                "outcome": 1,
                "payout_bp": 10_000,
                "resolved_at_ms": T0_MS + 3_600_000,
                "n_bars": 2,
                "market_brier_tw_micro": 562_500,
                "life_mean_price_bp": 2_550,
            },
        ),
        (
            SettlementApplied,
            T0_MS,
            None,
            {
                "agent_id": AGENT_ID,
                "market_id": MARKET_ID,
                "position": 12,
                "cash_delta_cents": 1_200,
                "cash_after_cents": 98_136,
                "realised_pnl_cents": -1_864,
                "agent_brier_tw_micro": 270_400,
                "n_forecast_bars": 2,
            },
        ),
        (
            MemoryWritten,
            T0_MS,
            "learn",
            {
                "agent_id": AGENT_ID,
                "kind": "calibration",
                "key": "calibration/decile/4",
                "payload": {"n": 1, "hits": 1},
                "bytes_after": 640,
            },
        ),
        (
            HiveWritten,
            T0_MS,
            None,
            {
                "entry_id": "h-00000001",
                "kind": "forecast",
                "author_id": AGENT_ID,
                "market_id": MARKET_ID,
                "visible_from_ms": T1_MS,
                "payload": {"prob_ppm": 480_000},
            },
        ),
        (
            EquityMarked,
            T0_MS,
            None,
            {
                "agent_id": AGENT_ID,
                "cash_cents": 96_936,
                "reserved_cents": 0,
                "positions_value_cents": 3_060,
                "equity_cents": 99_996,
                "fees_paid_cents": 0,
                "peak_equity_cents": 100_000,
                "drawdown_bp": -4,
                "n_open_positions": 1,
                "n_open_orders": 0,
            },
        ),
        (
            AgentRuined,
            T0_MS,
            None,
            {"agent_id": AGENT_ID, "equity_cents": 0, "cancelled_order_ids": ("o-00000002",)},
        ),
        (BarClosed, T0_MS, None, {"n_events": 21}),
        (
            RunEnded,
            T1_MS,
            None,
            {
                "reason": "completed",
                "final_bar_ms": T0_MS,
                "n_bars": 1,
                "event_count": 25,
                "ruined_agent_ids": (AGENT_ID,),
            },
        ),
    )


def _evolution_payloads() -> tuple[tuple[type[JournalEvent], int, str | None, dict[str, Any]], ...]:
    """One legal event of every evolution type (section 9.4), all at ``bar_ms = 0``."""
    return (
        (
            EvolutionStarted,
            0,
            None,
            {
                "seed": 7,
                "engine_version": "2.0.0",
                "contract_version": "2.0",
                "dataset_hash": HASH_A,
                "config": {"population_size": 48},
                "config_hash": HASH_B,
                "population_size": 48,
                "max_generations": 30,
                "folds": {
                    "train_end_ms": T0_MS,
                    "validation_end_ms": T1_MS,
                    "n_train": 10,
                    "n_validation": 3,
                    "n_sealed": 2,
                },
                "initial_population": (
                    {"agent_id": "p000-3fa9c2e1", "family": "follower", "genome_hash": HASH_B, "genome": GENOME},
                ),
            },
        ),
        (
            GenerationStarted,
            0,
            None,
            {
                "generation": 0,
                "run_seed": 12_345,
                "train_run_id": RUN_ID,
                "validation_run_id": "r-f60463ae-7-aaaaaaaa",
                "population": ("p000-3fa9c2e1",),
            },
        ),
        (
            CandidateScored,
            0,
            None,
            {
                "generation": 0,
                "agent_id": "p000-3fa9c2e1",
                "genome_hash": HASH_B,
                "fold": "train",
                "n_markets": 10,
                "skill_point_micro": 42_000,
                "skill_lb_micro": 11_000,
                "pnl_point_cents": 5_000,
                "pnl_lb_cents": -1_000,
                "brier_tw_micro": 180_000,
                "ruined": False,
                "research_units_spent": 4,
                "descriptors": {
                    "turnover_ppm": 120_000,
                    "contrarian_bp": -250,
                    "abstention_ppm": 300_000,
                    "holding_horizon_bars": 3,
                    "category_coverage_ppm": 250_000,
                },
            },
        ),
        (
            GenerationClosed,
            0,
            None,
            {
                "generation": 0,
                "ranked": (
                    {
                        "agent_id": "p000-3fa9c2e1",
                        "genome_hash": HASH_B,
                        "skill_lb_micro": 11_000,
                        "pnl_lb_cents": -1_000,
                        "rank": 1,
                    },
                ),
                "culled": (),
                "elites": ("p000-3fa9c2e1",),
                "children": (
                    {
                        "agent_id": "p001-4fb9c2e1",
                        "genome_hash": HASH_A,
                        "genome": GENOME,
                        "op": "mutation",
                        "parents": ["p000-3fa9c2e1"],
                    },
                ),
                "archive": (
                    {
                        "cell_key": "t1-c2-a0",
                        "agent_id": "p000-3fa9c2e1",
                        "genome_hash": HASH_B,
                        "skill_lb_micro": 11_000,
                    },
                ),
                "archive_filled": 1,
                "archive_cells": 48,
                "hall_of_fame": (
                    {
                        "family": "follower",
                        "genome_hash": HASH_B,
                        "skill_lb_micro": 11_000,
                        "genome": GENOME,
                        "run_id": RUN_ID,
                    },
                ),
                "candidates_evaluated_cum": 0,
                "best_validation_lb_micro": 0,
                "patience_left": 6,
                "research_budget_next": {"p000-3fa9c2e1": 10},
            },
        ),
        (
            EvolutionEnded,
            0,
            None,
            {
                "reason": "patience",
                "generations_run": 1,
                "candidates_evaluated_cum": 1,
                "champion": {
                    "agent_id": "p000-3fa9c2e1",
                    "genome_hash": HASH_B,
                    "genome": GENOME,
                    "validation_skill_lb_micro": 11_000,
                },
            },
        ),
    )


def _build(
    run_id: str,
    rows: Sequence[tuple[type[JournalEvent], int, str | None, dict[str, Any]]],
    path: Path | None = None,
    *,
    validate: bool = False,
) -> Journal:
    journal = Journal(run_id, path, validate=validate)
    for event_cls, bar_ms, phase, payload in rows:
        journal.emit(event_cls, bar_ms=bar_ms, phase=phase, **payload)
    return journal


@pytest.fixture
def backtest_journal() -> Iterator[Journal]:
    journal = _build(RUN_ID, _backtest_payloads())
    yield journal
    journal.close()


def test_a_journal_of_every_backtest_event_validates_and_verifies(backtest_journal: Journal) -> None:
    events = backtest_journal.events
    assert len(events) == 25
    assert {event.TYPE for event in events} == {cls.TYPE for cls, _, _, _ in _backtest_payloads()}
    assert [event.seq for event in events] == list(range(1, 26))
    verify_journal(events)
    for event in events:
        validate_event_dict(event.to_dict())


def test_a_journal_of_every_evolution_event_validates_and_verifies() -> None:
    journal = _build(EVO_RUN_ID, _evolution_payloads())
    events = journal.events
    assert len(events) == 5
    assert [event.bar_ms for event in events] == [0, 0, 0, 0, 0]
    assert [event.phase for event in events] == ["pre", "generation", "generation", "generation", "post"]
    verify_journal(events)
    for event in events:
        validate_event_dict(event.to_dict())


def test_every_event_round_trips_through_its_line(backtest_journal: Journal) -> None:
    for event in backtest_journal.events + _build(EVO_RUN_ID, _evolution_payloads()).events:
        line = event_to_line(event)
        assert line.endswith(JOURNAL_NEWLINE)
        assert "\r" not in line
        back = event_from_line(line)
        assert back == event
        assert type(back) is type(event)
        assert back.to_dict() == event.to_dict()


def test_a_line_carries_the_five_envelope_fields_and_nothing_invented() -> None:
    journal = _build(RUN_ID, _backtest_payloads()[:1])
    payload = json.loads(event_to_line(journal.events[0]))
    assert payload["seq"] == 1
    assert payload["type"] == "run_started"
    assert payload["run_id"] == RUN_ID
    assert payload["bar_ms"] == 0
    assert payload["phase"] == "pre"
    assert set(payload) == {"seq", "type", "run_id", "bar_ms", "phase", *payload_field_names(RunStarted)}


# ==================================================================================================
# pmx.journal: the bytes and the hash (sections 4.2 and 4.3)
# ==================================================================================================
def test_the_file_is_lf_and_utf8_and_its_bytes_hash_to_the_journal_hash(tmp_path: Path) -> None:
    """The Windows trap, pinned: the default text mode would write CRLF and break every comparison."""
    path = tmp_path / "runs" / RUN_ID / "journal.jsonl"
    journal = _build(RUN_ID, _backtest_payloads(), path)
    journal.close()
    raw = path.read_bytes()
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    assert raw.decode("utf-8").count("\n") == 25
    assert journal_hash_of_file(path) == journal.hash()
    assert journal_hash(journal.events) == journal.hash()
    with open(path, encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        assert journal_hash_from_lines(handle) == journal.hash()
    assert journal_hash_from_lines(line for line in raw.decode("utf-8").splitlines()) == journal.hash()


def test_a_journal_with_no_path_hashes_like_the_file_it_did_not_write(tmp_path: Path) -> None:
    in_memory = _build(RUN_ID, _backtest_payloads())
    path = tmp_path / "journal.jsonl"
    assert write_journal(path, in_memory.events) == in_memory.hash()
    assert journal_hash_of_file(path) == in_memory.hash()
    assert read_journal(path) == in_memory.events


def test_non_ascii_text_is_written_as_utf8_without_a_bom(tmp_path: Path) -> None:
    """``ensure_ascii=False`` keeps a headline readable; the encoding is what makes the bytes stable."""
    rows = list(_backtest_payloads())
    cls, bar_ms, phase, payload = rows[8]
    assert cls is ActionReceived
    rows[8] = (cls, bar_ms, phase, {**payload, "notes": "resolué: 50 %"})
    path = tmp_path / "journal.jsonl"
    journal = _build(RUN_ID, rows, path)
    journal.close()
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "resolué".encode() in raw
    assert journal_hash_of_file(path) == journal.hash()
    events = read_journal(path)
    reread = events[8]
    assert isinstance(reread, ActionReceived)
    assert reread.notes == "resolué: 50 %"


def test_a_crlf_journal_is_refused_rather_than_normalised(tmp_path: Path) -> None:
    good = tmp_path / "good.jsonl"
    write_journal(good, _build(RUN_ID, _backtest_payloads()).events)
    crlf = tmp_path / "crlf.jsonl"
    crlf.write_bytes(good.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(NonCanonicalValueError, match="carriage return"):
        read_journal(crlf)
    with pytest.raises(NonCanonicalValueError, match="carriage return"):
        journal_hash_of_file(crlf)
    with pytest.raises(NonCanonicalValueError, match="carriage return"):
        journal_hash_from_lines(["{}\r"])


def test_the_hash_moves_with_a_single_field(tmp_path: Path) -> None:
    """A hash that did not move on a changed payload would make AC-3 decorative."""
    rows = list(_backtest_payloads())
    base = _build(RUN_ID, rows).hash()
    cls, bar_ms, phase, payload = rows[10]
    assert cls is ForecastRecorded
    moved = dict(payload)
    moved["prob_ppm"] = 480_001
    rows[10] = (cls, bar_ms, phase, moved)
    assert _build(RUN_ID, rows).hash() != base


# ==================================================================================================
# pmx.journal: the contract's own fixtures re-serialise byte for byte
# ==================================================================================================
@pytest.mark.parametrize("name", ["journal.backtest.jsonl", "journal.evolution.jsonl"])
def test_the_contract_fixtures_read_verify_and_re_serialise_identically(name: str, tmp_path: Path) -> None:
    """C0 wrote these bytes before this encoder existed; they must round-trip through it exactly."""
    fixture = CONTRACT_FIXTURES / name
    events = read_journal(fixture)
    assert events
    verify_journal(events)
    rewritten = tmp_path / name
    assert write_journal(rewritten, events) == journal_hash_of_file(fixture)
    assert rewritten.read_bytes() == fixture.read_bytes()


def test_the_backtest_fixture_is_the_run_the_contract_describes() -> None:
    events = read_journal(CONTRACT_FIXTURES / "journal.backtest.jsonl")
    started = events[0]
    ended = events[-1]
    assert isinstance(started, RunStarted)
    assert isinstance(ended, RunEnded)
    assert started.bar_ms == 0
    assert ended.bar_ms == started.t1_ms
    assert ended.event_count == len(events)
    bars = [bar_ms for bar_ms, _ in iter_bars(events)]
    assert bars == sorted(bars) == [0, 1_466_640_000_000, 1_466_726_400_000, started.t1_ms]
    settling: set[str] = set()
    for settled in filter_events(events, Settled):
        assert isinstance(settled, Settled)
        settling.add(settled.market_id)
    assert settling == {MARKET_ID}
    for fill in filter_events(events, Filled):
        assert fill.bar_ms != 1_466_726_400_000, "section 5.3: the settling bar never fills"


def test_the_evolution_fixture_carries_no_bar_event() -> None:
    events = read_journal(CONTRACT_FIXTURES / "journal.evolution.jsonl")
    assert isinstance(events[0], EvolutionStarted)
    assert isinstance(events[-1], EvolutionEnded)
    assert {event.bar_ms for event in events} == {0}
    assert {event.phase for event in events} <= {"pre", "generation", "post"}
    assert not [event for event in events if event.phase in _BAR_PHASES]


# ==================================================================================================
# pmx.journal: what is refused at write time (section 4.4)
# ==================================================================================================
@pytest.mark.parametrize(
    "field",
    ["latency_ms", "cost_usd", "tokens_in", "rationale", "wall_clock_ms", "retries", "attempts", "duration_ms"],
)
def test_a_wall_clock_a_cost_or_a_token_count_is_refused_by_name(field: str) -> None:
    journal = _build(RUN_ID, _backtest_payloads()[:1])
    payload = dict(_backtest_payloads()[10][3])
    payload[field] = 12
    with pytest.raises(JournalError, match="llm_trace.jsonl"):
        journal.emit(ForecastRecorded, bar_ms=T0_MS, **payload)
    assert journal.next_seq == 2


def test_a_float_in_a_payload_fails_at_the_emitting_call_site_and_appends_nothing(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    journal = _build(RUN_ID, _backtest_payloads()[:1], path)
    with pytest.raises(NonCanonicalValueError, match="floats are forbidden"):
        journal.emit(
            EquityMarked,
            bar_ms=T0_MS,
            agent_id=AGENT_ID,
            cash_cents=100_000.0,
            reserved_cents=0,
            positions_value_cents=0,
            equity_cents=100_000,
            fees_paid_cents=0,
            peak_equity_cents=100_000,
            drawdown_bp=0,
            n_open_positions=0,
            n_open_orders=0,
        )
    assert journal.next_seq == 2
    assert len(journal.events) == 1
    journal.close()
    assert len(path.read_text(encoding=JOURNAL_ENCODING).splitlines()) == 1


def test_an_unknown_or_missing_field_is_refused_with_its_name() -> None:
    journal = _build(RUN_ID, _backtest_payloads()[:1])
    with pytest.raises(JournalError, match="not in this event's catalogue entry"):
        journal.emit(BarClosed, bar_ms=T0_MS, n_events=3, n_orders=1)
    with pytest.raises(JournalError, match="missing a field"):
        journal.emit(ForecastRecorded, bar_ms=T0_MS, agent_id=AGENT_ID, market_id=MARKET_ID, prob_ppm=1)
    assert journal.next_seq == 2


def test_a_set_in_a_payload_is_refused() -> None:
    journal = _build(RUN_ID, _backtest_payloads()[:1])
    with pytest.raises(NonCanonicalValueError, match="sets have no stable order"):
        journal.emit(
            BarOpened,
            bar_ms=T0_MS,
            open_market_ids={MARKET_ID},
            tradable_market_ids=(),
            settling_market_ids=(),
            listed_market_ids=(),
        )


# ==================================================================================================
# pmx.journal: the envelope and the ordering (section 9.1)
# ==================================================================================================
def test_seq_is_assigned_by_the_journal_and_by_nothing_else() -> None:
    journal = _build(RUN_ID, _backtest_payloads()[:3])
    assert journal.next_seq == 4
    with pytest.raises(JournalError, match="increase by exactly 1"):
        journal.append(BarClosed(seq=9, run_id=RUN_ID, bar_ms=T0_MS, phase="close", n_events=3))
    with pytest.raises(JournalError, match="another run"):
        journal.append(BarClosed(seq=4, run_id="r-deadbeef-1-deadbeef", bar_ms=T0_MS, phase="close", n_events=3))


def test_seq_one_is_run_started_or_evolution_started() -> None:
    journal = Journal(RUN_ID)
    with pytest.raises(JournalError, match="seq 1 is run_started or evolution_started"):
        journal.emit(BarClosed, bar_ms=T0_MS, n_events=1)
    assert journal.next_seq == 1


def test_nothing_follows_the_terminal_event() -> None:
    journal = _build(RUN_ID, _backtest_payloads())
    with pytest.raises(JournalError, match="terminal event is the last event"):
        journal.emit(BarClosed, bar_ms=T1_MS, n_events=1)


def test_a_journal_never_mixes_a_backtest_with_an_evolution() -> None:
    journal = _build(RUN_ID, _backtest_payloads()[:2])
    with pytest.raises(JournalError, match="never mixes"):
        journal.emit(
            GenerationStarted,
            bar_ms=0,
            generation=0,
            run_seed=1,
            train_run_id=RUN_ID,
            validation_run_id=RUN_ID,
            population=(),
        )


def test_bar_ms_never_decreases_and_a_phase_never_goes_backwards() -> None:
    journal = _build(RUN_ID, _backtest_payloads()[:5])
    with pytest.raises(JournalError, match="never decrease"):
        journal.emit(BarClosed, bar_ms=T0_MS - 86_400_000, n_events=1)
    journal.emit(BarClosed, bar_ms=T0_MS, n_events=6)
    with pytest.raises(JournalError, match="never go backwards inside one bar"):
        journal.emit(
            MarketPriced,
            bar_ms=T0_MS,
            market_id=MARKET_ID,
            close_bp=1,
            last_close_bp=1,
            vwap_bp=1,
            volume_milli=0,
        )


def test_the_events_that_carry_bar_ms_zero_carry_nothing_else() -> None:
    journal = Journal(RUN_ID)
    payload = dict(_backtest_payloads()[0][3])
    with pytest.raises(JournalError, match="bar_ms 0"):
        journal.emit(RunStarted, bar_ms=T0_MS, **payload)
    assert RunStarted.BAR_MS_ZERO and SealedTestOpened.BAR_MS_ZERO
    evolution = _evolution_payloads()
    assert len(evolution) == 5, "the whole evolution catalogue of section 9.4"
    assert all(cls.BAR_MS_ZERO for cls, _, _, _ in evolution)
    assert not BarOpened.BAR_MS_ZERO


def test_a_phase_must_be_legal_for_its_event_and_ambiguity_is_refused() -> None:
    journal = _build(RUN_ID, _backtest_payloads()[:2])
    with pytest.raises(JournalError, match="several legal phases"):
        journal.emit(
            OrderExpired,
            bar_ms=T0_MS,
            order_id="o-00000001",
            agent_id=AGENT_ID,
            market_id=MARKET_ID,
            remaining_size=1,
            released_cents=1,
            reason="ttl",
        )
    with pytest.raises(JournalError, match="not legal for this event type"):
        journal.emit(BarClosed, bar_ms=T0_MS, phase="decide", n_events=1)
    expired = journal.emit(
        OrderExpired,
        bar_ms=T0_MS,
        phase="settle",
        order_id="o-00000001",
        agent_id=AGENT_ID,
        market_id=MARKET_ID,
        remaining_size=1,
        released_cents=1,
        reason="settled",
    )
    assert expired.phase == "settle"


def test_a_closed_journal_refuses_an_append_and_a_zero_buffer_is_refused(tmp_path: Path) -> None:
    with pytest.raises(JournalError, match="buffer_size"):
        Journal(RUN_ID, buffer_size=0)
    path = tmp_path / "journal.jsonl"
    with Journal(RUN_ID, path, buffer_size=1) as journal:
        journal.emit(RunStarted, bar_ms=0, **dict(_backtest_payloads()[0][3]))
    assert journal.closed
    with pytest.raises(JournalError, match="journal is closed"):
        journal.emit(BarClosed, bar_ms=T0_MS, n_events=1)
    journal.close()  # idempotent
    assert path.read_bytes().count(b"\n") == 1


def test_the_repr_names_the_run_and_never_an_address() -> None:
    journal = _build(RUN_ID, _backtest_payloads()[:1])
    assert repr(journal) == f"Journal(run_id={RUN_ID!r}, events=1, path=None)"
    assert "0x" not in repr(journal)


# ==================================================================================================
# pmx.journal: verify_journal on broken journals
# ==================================================================================================
def _events(rows: Sequence[tuple[type[JournalEvent], int, str | None, dict[str, Any]]]) -> list[JournalEvent]:
    return list(_build(RUN_ID, rows).events)


def _renumbered(events: Sequence[JournalEvent]) -> list[JournalEvent]:
    """Reassign a dense ``seq``, so a test of another rule is not caught by the ``seq`` rule first."""
    return [replace(event, seq=index + 1) for index, event in enumerate(events)]


def test_verify_journal_rejects_an_empty_journal() -> None:
    with pytest.raises(JournalError, match="journal is empty"):
        verify_journal(())


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda events: _renumbered(events[1:]), "seq 1 is run_started"),
        (lambda events: events[:-2] + [events[-1]], "increase by exactly 1"),
        (lambda events: [*events[:5], *events[6:]], "increase by exactly 1"),
        (lambda events: [events[3], *events[1:]], "seq 1 is run_started"),
    ],
)
def test_verify_journal_rejects_a_broken_sequence(
    mutate: Callable[[list[JournalEvent]], list[JournalEvent]], match: str
) -> None:
    with pytest.raises(JournalError, match=match):
        verify_journal(mutate(_events(_backtest_payloads())))


def test_verify_journal_rejects_a_terminal_event_that_is_not_last() -> None:
    events = _events(_backtest_payloads())
    trailing = replace(events[-2], bar_ms=T1_MS + 86_400_000, seq=len(events) + 1)
    with pytest.raises(JournalError, match="terminal event is the last event"):
        verify_journal([*events, trailing])


def test_verify_journal_rejects_a_foreign_run_id_and_a_decreasing_bar() -> None:
    events = _events(_backtest_payloads())
    foreign = BarClosed(seq=events[3].seq, run_id="r-deadbeef-1-deadbeef", bar_ms=T0_MS, phase="close", n_events=1)
    with pytest.raises(JournalError, match="mixes two run ids"):
        verify_journal([*events[:3], foreign, *events[4:]])
    late = BarOpened(
        seq=4,
        run_id=RUN_ID,
        bar_ms=T0_MS - 1,
        phase="open",
        open_market_ids=(),
        tradable_market_ids=(),
        settling_market_ids=(),
        listed_market_ids=(),
    )
    with pytest.raises(JournalError, match="never decrease"):
        verify_journal([*events[:3], late])


def test_verify_journal_rejects_generation_mixed_with_the_bar_phases() -> None:
    backtest = _events(_backtest_payloads())
    evolution = list(_build(EVO_RUN_ID, _evolution_payloads()).events)
    mixed = [
        backtest[0],
        GenerationStarted(
            seq=2,
            run_id=RUN_ID,
            bar_ms=0,
            phase="generation",
            generation=0,
            run_seed=1,
            train_run_id=RUN_ID,
            validation_run_id=RUN_ID,
            population=(),
        ),
        *backtest[2:],
    ]
    with pytest.raises(JournalError, match="never mixes"):
        verify_journal(mixed)
    assert {event.JOURNAL_KIND for event in evolution} == {"evolution"}
    assert {event.JOURNAL_KIND for event in backtest} == {"backtest"}


def test_verify_journal_rejects_a_phase_going_backwards_and_a_wrong_run_ended_bar() -> None:
    events = _events(_backtest_payloads())
    backwards = MarketPriced(
        seq=len(events),
        run_id=RUN_ID,
        bar_ms=T0_MS,
        phase="open",
        market_id=MARKET_ID,
        close_bp=1,
        last_close_bp=1,
        vwap_bp=1,
        volume_milli=0,
    )
    with pytest.raises(JournalError, match="never go backwards inside one bar"):
        verify_journal([*events[:-1], backwards])
    ended = events[-1]
    assert isinstance(ended, RunEnded)
    moved = RunEnded(
        seq=ended.seq,
        run_id=ended.run_id,
        bar_ms=T1_MS + 86_400_000,
        phase="post",
        reason=ended.reason,
        final_bar_ms=ended.final_bar_ms,
        n_bars=ended.n_bars,
        event_count=ended.event_count,
        ruined_agent_ids=ended.ruined_agent_ids,
    )
    with pytest.raises(JournalError, match="bar_ms t1_ms"):
        verify_journal([*events[:-1], moved])


def test_verify_journal_accepts_a_run_still_in_flight() -> None:
    """A journal read halfway through a run has no terminal event and is still valid."""
    verify_journal(_events(_backtest_payloads())[:-1])


# ==================================================================================================
# pmx.journal: reading, validating, grouping
# ==================================================================================================
def test_the_replay_iterator_validates_every_event_against_the_schema(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    events = _build(RUN_ID, _backtest_payloads()).events
    write_journal(path, events)
    assert tuple(iter_journal(path)) == events
    lines = path.read_text(encoding=JOURNAL_ENCODING).splitlines()
    poisoned = json.loads(lines[10])
    assert poisoned["type"] == "forecast_recorded"
    poisoned["prob_ppm"] = 2_000_000  # ppm has a ceiling of 1 000 000
    lines[10] = canonical_json(poisoned)
    path.write_text(JOURNAL_NEWLINE.join(lines) + JOURNAL_NEWLINE, encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE)
    with pytest.raises(SchemaError, match="fails its JSON schema"):
        read_journal(path)
    assert len(tuple(iter_journal(path, validate=False))) == 25


def test_a_journal_can_validate_at_append_time() -> None:
    journal = _build(RUN_ID, _backtest_payloads()[:1], validate=True)
    journal.emit(ForecastRecorded, bar_ms=T0_MS, agent_id=AGENT_ID, market_id=MARKET_ID, prob_ppm=1, carried=False)
    with pytest.raises(SchemaError, match="fails its JSON schema"):
        journal.emit(
            ForecastRecorded,
            bar_ms=T0_MS,
            agent_id=AGENT_ID,
            market_id=MARKET_ID,
            prob_ppm=2_000_000,
            carried=False,
        )
    assert journal.next_seq == 3


def test_an_unknown_event_type_and_a_broken_line_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    path.write_text(
        canonical_json({"seq": 1, "type": "not_an_event", "run_id": RUN_ID, "bar_ms": 0, "phase": "pre"})
        + JOURNAL_NEWLINE,
        encoding=JOURNAL_ENCODING,
        newline=JOURNAL_NEWLINE,
    )
    with pytest.raises(SchemaError, match="fails its JSON schema"):
        read_journal(path)
    with pytest.raises(JournalError, match="unknown event type"):
        read_journal(path, validate=False)
    with pytest.raises(JournalError, match="no string 'type' field"):
        event_from_line('{"seq":1}')
    with pytest.raises(JournalError, match="not a JSON object"):
        event_from_line("[]")
    truncated = {"seq": 1, "type": "bar_closed", "run_id": RUN_ID, "bar_ms": 0, "phase": "close"}
    with pytest.raises(JournalError, match="missing a field"):
        event_from_line(canonical_json(truncated))


def test_a_blank_line_is_skipped_not_parsed(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    events = _build(RUN_ID, _backtest_payloads()[:2]).events
    write_journal(path, events)
    with open(path, "a", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        handle.write(JOURNAL_NEWLINE)
    assert read_journal(path) == events


def test_iter_bars_groups_once_per_bar_and_keeps_the_order_inside(backtest_journal: Journal) -> None:
    grouped = list(iter_bars(backtest_journal.events))
    assert [bar_ms for bar_ms, _ in grouped] == [0, T0_MS, T1_MS]
    assert [len(events) for _, events in grouped] == [2, 22, 1]
    bar_events = grouped[1][1]
    assert [event.seq for event in bar_events] == sorted(event.seq for event in bar_events)
    assert sum(len(events) for _, events in grouped) == len(backtest_journal.events)


def test_filter_events_keeps_journal_order_and_nothing_by_default(backtest_journal: Journal) -> None:
    events = backtest_journal.events
    assert filter_events(events) == ()
    memories = filter_events(events, MemoryWritten)
    assert [event.phase for event in memories] == ["decide", "learn"]
    two_kinds = filter_events(events, ForecastRecorded, Filled)
    assert [event.TYPE for event in two_kinds] == ["forecast_recorded", "filled"]
    assert [event.seq for event in two_kinds] == sorted(event.seq for event in two_kinds)


# ==================================================================================================
# pmx.journal: one module, one spelling for the event classes (ruling R90)
# ==================================================================================================
def test_the_event_classes_live_in_pmx_journal_and_nowhere_else() -> None:
    """Ruling R90: section 14's ``pmx.journal.events.*`` is amended to ``pmx.journal.*``.

    The wave shipped a ``sys.modules`` alias so that both spellings imported at run time, which a type
    checker could not follow: annotated code in E5 and O2 would have had to import from one module and
    read the contract's other one. There is now exactly one importable spelling, and this test fails if
    the alias ever comes back.
    """
    journal_module = importlib.import_module("pmx.journal")
    assert journal_module.Filled is Filled
    assert set(journal_module.__all__) >= {cls.__name__ for cls in EVENT_CLASSES.values()}
    assert "pmx.journal.events" not in sys.modules
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("pmx.journal.events")
    assert not hasattr(journal_module, "events")


