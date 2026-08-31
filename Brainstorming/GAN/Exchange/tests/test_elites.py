"""A20 acceptance tests for the MAP-Elites archive and the two Halls of Fame.

Covers T5.2 (``test_grid_is_configurable``,
``test_elite_is_the_best_mu_of_the_cell``), T3.4
(``test_frozen_harness_replays_identically``) and T5.3 (``test_failure_hof``).

The anti vacuous rule (CONTRACTS section 10) is applied at the top of the file
and not per test: every style vector offered to an archive here comes from
``compute_descriptors`` over a **real** ``MatchProjection`` folded from a frozen
golden journal, and ``golden_descriptors`` refuses an empty journal, an empty set
of projection rows and an empty descriptor list before any cell is filled. An
archive fed six neutral constants would satisfy every type annotation and every
"the best mu wins" assertion while proving nothing about the axes.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from pxe.errors import InvalidConfigError
from pxe.events import Event
from pxe.journal import read_journal
from pxe.metrics.behavioral import (
    DESCRIPTOR_NAMES,
    BehavioralDescriptors,
    compute_descriptors,
)
from pxe.metrics.projection import MatchProjection, project
from pxe.tournament.elites import AXIS_MAX, MAX_AXES, MIN_AXES, EliteArchive, EliteCell
from pxe.tournament.halloffame import FailureHallOfFame, HallOfFame
from pxe.types import HarnessConfig, RatingRecord, harness_key
from tests.test_match_runner import GOLDEN_DIR, REFERENCE, WIDE, Recipe

#: The two axes used by most tests here. They are the two the six baselines
#: actually spread over on the reference match, so a two cell archive is
#: reachable rather than hypothetical.
TWO_AXES = ("maker_ratio_ppm", "holding_horizon_milli")


# ---------------------------------------------------------------------------
# Real descriptors, from a real journal
# ---------------------------------------------------------------------------
def golden_events(recipe: Recipe) -> tuple[Event, ...]:
    """Read one frozen golden journal and refuse an empty one."""
    path = GOLDEN_DIR / f"{recipe.name}.journal.jsonl"
    assert path.exists(), f"missing golden journal for {recipe.name}"
    events = read_journal(path)
    assert events, "the golden journal read back empty, so every cell below would be vacuous"
    return events


def golden_projection(recipe: Recipe) -> MatchProjection:
    """Project one golden journal and refuse a projection of empty tuples."""
    projection = project(golden_events(recipe))
    assert projection.agent_ids, "no ranked seat in the projection"
    assert projection.trades, "no trade row: maker_ratio_ppm would be the neutral constant for everybody"
    assert projection.orders, "no order row: the reserved reconstruction would be vacuous"
    return projection


def golden_descriptors(recipe: Recipe) -> tuple[BehavioralDescriptors, ...]:
    """Compute the six descriptors of every seat of one golden match."""
    rows = compute_descriptors(golden_projection(recipe))
    assert rows, "compute_descriptors returned nothing"
    assert len(rows) == len(recipe.baselines), "one style vector per ranked seat"
    return rows


#: The reference population: six baselines, six real style vectors.
REFERENCE_STYLES: tuple[BehavioralDescriptors, ...] = golden_descriptors(REFERENCE)


def key_of(name: str, *, version: str = "1.0.0", prompt: str = "") -> str:
    """Harness key of a scripted harness, through the one producer (section 2.2)."""
    return harness_key(HarnessConfig(harness_id=name, version=version, kind="scripted", system_prompt=prompt))


# ---------------------------------------------------------------------------
# T5.2: the grid
# ---------------------------------------------------------------------------
def test_grid_is_configurable() -> None:
    """PRD section 8: a 2 or 3 dimensional grid, with a configurable bin count."""
    assert REFERENCE_STYLES, "no real style vector to bin"
    assert set(TWO_AXES) <= set(DESCRIPTOR_NAMES)

    two = EliteArchive(axes=TWO_AXES, bins=(4, 4))
    three = EliteArchive(axes=("maker_ratio_ppm", "leverage_ppm", "herfindahl_ppm"), bins=(2, 3, 5))
    for style in REFERENCE_STYLES:
        assert len(two.coords_for(style)) == 2
        coords = three.coords_for(style)
        assert len(coords) == 3
        for value, count in zip(coords, (2, 3, 5), strict=True):
            assert 0 <= value < count, "a coordinate escaped its axis"

    coarse = EliteArchive(axes=TWO_AXES, bins=(1, 1))
    assert {coarse.coords_for(style) for style in REFERENCE_STYLES} == {(0, 0)}, "a one bin axis has one cell"

    fine = EliteArchive(axes=TWO_AXES, bins=(1_000, 1_000))
    assert len({fine.coords_for(style) for style in REFERENCE_STYLES}) >= 2, "a fine grid must separate two seats"


def test_the_grid_refuses_a_shape_it_cannot_bin() -> None:
    """Every rejected shape is a configuration error, never a silent default."""
    assert (MIN_AXES, MAX_AXES) == (2, 3)
    with pytest.raises(InvalidConfigError):
        EliteArchive(axes=("maker_ratio_ppm",), bins=(4,))
    with pytest.raises(InvalidConfigError):
        EliteArchive(axes=(*DESCRIPTOR_NAMES[:4],), bins=(2, 2, 2, 2))
    with pytest.raises(InvalidConfigError):
        EliteArchive(axes=TWO_AXES, bins=(4,))
    with pytest.raises(InvalidConfigError):
        EliteArchive(axes=("maker_ratio_ppm", "not_a_descriptor"), bins=(4, 4))
    with pytest.raises(InvalidConfigError):
        EliteArchive(axes=("maker_ratio_ppm", "maker_ratio_ppm"), bins=(4, 4))
    with pytest.raises(InvalidConfigError):
        EliteArchive(axes=TWO_AXES, bins=(4, 0))


def test_every_axis_has_a_declared_bound_and_the_extremes_are_reachable() -> None:
    """A ratio axis is bounded by PPM_ONE, a duration axis by the longest match."""
    assert set(AXIS_MAX) == set(DESCRIPTOR_NAMES), "an axis without a bound cannot be binned"
    archive = EliteArchive(axes=TWO_AXES, bins=(4, 4))
    floor = replace(REFERENCE_STYLES[0], maker_ratio_ppm=0, holding_horizon_milli=0)
    ceiling = replace(
        REFERENCE_STYLES[0],
        maker_ratio_ppm=AXIS_MAX["maker_ratio_ppm"],
        holding_horizon_milli=AXIS_MAX["holding_horizon_milli"],
    )
    beyond = replace(REFERENCE_STYLES[0], maker_ratio_ppm=10 * AXIS_MAX["maker_ratio_ppm"])
    assert archive.coords_for(floor) == (0, 0)
    assert archive.coords_for(ceiling) == (3, 3)
    assert archive.coords_for(beyond)[0] == 3, "a value above its bound clamps into the top bin"


def test_elite_is_the_best_mu_of_the_cell() -> None:
    """The occupant of a cell is the best mu with that style (PRD section 8)."""
    style = REFERENCE_STYLES[0]
    archive = EliteArchive(axes=TWO_AXES, bins=(4, 4))
    coords = archive.coords_for(style)

    assert archive.offer(harness_key=key_of("weak"), mu=20.0, descriptors=style) is True
    assert archive.offer(harness_key=key_of("strong"), mu=31.5, descriptors=style) is True
    assert archive.offer(harness_key=key_of("middling"), mu=25.0, descriptors=style) is False
    assert archive.offer(harness_key=key_of("tied"), mu=31.5, descriptors=style) is False, (
        "an equal mu must not displace the incumbent, or the archive depends on offer order"
    )

    cells = archive.cells()
    assert len(cells) == 1, "one style, one cell"
    assert cells[0] == EliteCell(
        coords=coords,
        harness_key=key_of("strong"),
        mu=31.5,
        descriptors=(style.maker_ratio_ppm, style.holding_horizon_milli),
    )


def test_a_different_style_takes_a_different_cell() -> None:
    """Two styles far apart on one axis never compete for the same slot."""
    archive = EliteArchive(axes=TWO_AXES, bins=(4, 4))
    passive = replace(REFERENCE_STYLES[0], maker_ratio_ppm=990_000, holding_horizon_milli=0)
    aggressive = replace(REFERENCE_STYLES[0], maker_ratio_ppm=0, holding_horizon_milli=0)
    assert archive.offer(harness_key=key_of("passive"), mu=22.0, descriptors=passive) is True
    assert archive.offer(harness_key=key_of("aggressive"), mu=21.0, descriptors=aggressive) is True
    cells = archive.cells()
    assert len(cells) == 2, "the archive collapsed two styles into one cell"
    assert {cell.harness_key for cell in cells} == {key_of("passive"), key_of("aggressive")}
    assert cells[0].coords < cells[1].coords, "cells() is ordered by coordinates"


def test_the_archive_is_fed_from_the_journal_and_keeps_the_real_descriptors() -> None:
    """A cell's descriptors are the seat's own values, so a report can place it."""
    archive = EliteArchive(axes=TWO_AXES, bins=(8, 8))
    for index, style in enumerate(REFERENCE_STYLES):
        archive.offer(harness_key=key_of(f"seat-{index}"), mu=20.0 + float(index), descriptors=style)
    cells = archive.cells()
    assert cells, "no cell was filled from a real projection"
    real = {(style.maker_ratio_ppm, style.holding_horizon_milli) for style in REFERENCE_STYLES}
    for cell in cells:
        assert len(cell.descriptors) == 2
        assert cell.descriptors in real, "a cell invented a descriptor value"
        assert cell.coords == archive.coords_for(
            replace(
                REFERENCE_STYLES[0],
                maker_ratio_ppm=cell.descriptors[0],
                holding_horizon_milli=cell.descriptors[1],
            )
        )


def test_the_archive_does_not_depend_on_the_order_of_the_offers() -> None:
    """Two archives fed the same population in opposite orders publish one grid."""
    population = [(key_of(f"seat-{index}"), 20.0 + float(index), style) for index, style in enumerate(REFERENCE_STYLES)]
    forward = EliteArchive(axes=TWO_AXES, bins=(6, 6))
    backward = EliteArchive(axes=TWO_AXES, bins=(6, 6))
    for key, mu, style in population:
        forward.offer(harness_key=key, mu=mu, descriptors=style)
    for key, mu, style in reversed(population):
        backward.offer(harness_key=key, mu=mu, descriptors=style)
    assert forward.cells() == backward.cells()
    assert forward.cells(), "both archives are empty, so the claim is vacuous"


def test_an_empty_archive_publishes_nothing_and_a_candidate_needs_a_key() -> None:
    """The empty grid is empty, and an anonymous candidate is refused."""
    archive = EliteArchive(axes=TWO_AXES, bins=(3, 3))
    assert archive.cells() == ()
    with pytest.raises(InvalidConfigError):
        archive.offer(harness_key="", mu=25.0, descriptors=REFERENCE_STYLES[0])


def test_two_golden_matches_land_in_the_same_grid() -> None:
    """The archive is a projection, so a second journal simply adds candidates."""
    archive = EliteArchive(axes=TWO_AXES, bins=(6, 6))
    for recipe in (REFERENCE, WIDE):
        styles = golden_descriptors(recipe)
        for index, style in enumerate(styles):
            archive.offer(harness_key=key_of(f"{recipe.name}-{index}"), mu=25.0, descriptors=style)
    assert len(archive.cells()) >= 2


# ---------------------------------------------------------------------------
# T3.4: the Hall of Fame of frozen harness versions
# ---------------------------------------------------------------------------
def test_frozen_harness_replays_identically() -> None:
    """A frozen member carries the config+prompt hash that makes it replayable."""
    harness = HarnessConfig(
        harness_id="champion",
        version="2.1.0",
        kind="llm",
        model="claude-sonnet-5",
        system_prompt="you are a market maker taker",
        params=(("temperature", "0.2"),),
    )
    assert harness.config_hash, "HarnessConfig.__post_init__ must fill the hash"
    hall = HallOfFame()
    key = hall.freeze(harness, RatingRecord(harness_key=harness.key, mu=30.0, sigma=2.0, matches=40))

    assert key == harness.key == harness_key(harness)
    members = hall.members()
    assert len(members) == 1
    frozen = members[0]
    assert frozen == harness, "a frozen version must be the very config that was handed over"
    assert harness_key(frozen) == key
    assert frozen.config_hash == harness.config_hash
    rebuilt = HarnessConfig(
        harness_id=frozen.harness_id,
        version=frozen.version,
        kind=frozen.kind,
        model=frozen.model,
        system_prompt=frozen.system_prompt,
        params=frozen.params,
    )
    assert rebuilt.config_hash == harness.config_hash, "the hash is not reproducible from the frozen fields"
    assert harness_key(rebuilt) == key


def test_two_prompts_under_one_version_are_two_slots() -> None:
    """Decision 24: without the config hash they would share one Hall of Fame slot."""
    first = HarnessConfig(harness_id="champion", version="2.1.0", kind="llm", system_prompt="prompt A")
    second = HarnessConfig(harness_id="champion", version="2.1.0", kind="llm", system_prompt="prompt B")
    assert first.key != second.key
    hall = HallOfFame()
    hall.freeze(first, RatingRecord(harness_key=first.key, mu=28.0, sigma=3.0, matches=10))
    hall.freeze(second, RatingRecord(harness_key=second.key, mu=29.0, sigma=3.0, matches=10))
    assert len(hall.members()) == 2
    assert hall.members()[0] == second, "members() is best mu first"


def test_refreezing_a_version_keeps_one_slot_and_refreshes_its_rating() -> None:
    """A version is frozen once, whatever its rating does afterwards."""
    harness = HarnessConfig(harness_id="champion", version="1.0.0", kind="scripted")
    other = HarnessConfig(harness_id="rival", version="1.0.0", kind="scripted")
    hall = HallOfFame()
    hall.freeze(harness, RatingRecord(harness_key=harness.key, mu=26.0, sigma=3.0, matches=5))
    hall.freeze(other, RatingRecord(harness_key=other.key, mu=27.0, sigma=3.0, matches=5))
    assert hall.members() == (other, harness)
    hall.freeze(harness, RatingRecord(harness_key=harness.key, mu=33.0, sigma=1.5, matches=50))
    assert len(hall.members()) == 2
    assert hall.members() == (harness, other), "the refreshed rating did not reorder the hall"


def test_the_hall_of_fame_is_bounded_and_evicts_the_weakest() -> None:
    """Capacity is enforced on insertion, and a weaker offer does not enter."""
    hall = HallOfFame(capacity=2)
    strong = [HarnessConfig(harness_id=f"h{index}", version="1.0.0", kind="scripted") for index in range(3)]
    for index, harness in enumerate(strong):
        hall.freeze(harness, RatingRecord(harness_key=harness.key, mu=30.0 - float(index), sigma=2.0, matches=9))
    assert hall.members() == (strong[0], strong[1]), "the weakest of three did not get evicted"
    newcomer = HarnessConfig(harness_id="weakling", version="1.0.0", kind="scripted")
    hall.freeze(newcomer, RatingRecord(harness_key=newcomer.key, mu=1.0, sigma=2.0, matches=9))
    assert newcomer not in hall.members(), "an offer weaker than every member must not enter"
    assert len(hall.members()) == 2


def test_the_hall_of_fame_refuses_a_foreign_rating_and_a_zero_capacity() -> None:
    """A rating that belongs to another version would order the hall by the wrong number."""
    harness = HarnessConfig(harness_id="champion", version="1.0.0", kind="scripted")
    hall = HallOfFame()
    with pytest.raises(InvalidConfigError):
        hall.freeze(harness, RatingRecord(harness_key="somebody-else@1.0.0+00000000", mu=30.0, sigma=2.0, matches=9))
    with pytest.raises(InvalidConfigError):
        HallOfFame(capacity=0)


# ---------------------------------------------------------------------------
# T5.3: the Failure Hall of Fame
# ---------------------------------------------------------------------------
def test_failure_hof() -> None:
    """The worst (scenario, seed) pairs of a harness, worst first (PRD section 8)."""
    champion = key_of("champion")
    rival = key_of("rival")
    failures = FailureHallOfFame()
    failures.record(template_id="election", seed=11, harness_key=champion, deficit_cents=5_000)
    failures.record(template_id="harvest", seed=22, harness_key=champion, deficit_cents=90_000)
    failures.record(template_id="league", seed=33, harness_key=champion, deficit_cents=40_000)
    failures.record(template_id="election", seed=44, harness_key=rival, deficit_cents=1_000_000)

    worst = failures.worst(champion)
    assert worst == (("harvest", 22), ("league", 33), ("election", 11))
    assert failures.worst(champion, limit=2) == (("harvest", 22), ("league", 33))
    assert failures.worst(rival) == (("election", 44),), "one harness's failures leaked into another's"
    assert failures.worst(key_of("never-played")) == (), "an unknown harness is not an error"

    failures.record(template_id="election", seed=11, harness_key=champion, deficit_cents=99_999_999)
    assert failures.worst(champion)[0] == ("election", 11), "re-recording a pair must keep the worst deficit"
    assert len(failures.worst(champion)) == 3, "a re-recorded pair must not be duplicated"


def test_the_failure_hall_of_fame_is_bounded_per_harness() -> None:
    """Capacity is per harness key, so one collapsing harness evicts nobody else."""
    champion = key_of("champion")
    rival = key_of("rival")
    failures = FailureHallOfFame(capacity=3)
    for seed in range(10):
        failures.record(template_id="election", seed=seed, harness_key=champion, deficit_cents=seed * 100)
    failures.record(template_id="election", seed=99, harness_key=rival, deficit_cents=1)
    kept = failures.worst(champion, limit=100)
    assert len(kept) == 3
    assert kept == (("election", 9), ("election", 8), ("election", 7))
    assert failures.worst(rival) == (("election", 99),)


def test_the_failure_hall_of_fame_refuses_what_it_cannot_replay() -> None:
    """A pair that cannot be replayed (no template, no key, illegal seed) is refused."""
    failures = FailureHallOfFame()
    with pytest.raises(InvalidConfigError):
        failures.record(template_id="", seed=1, harness_key=key_of("h"), deficit_cents=1)
    with pytest.raises(InvalidConfigError):
        failures.record(template_id="election", seed=1, harness_key="", deficit_cents=1)
    with pytest.raises(InvalidConfigError):
        failures.record(template_id="election", seed=-1, harness_key=key_of("h"), deficit_cents=1)
    with pytest.raises(InvalidConfigError):
        failures.record(template_id="election", seed=2**64, harness_key=key_of("h"), deficit_cents=1)
    with pytest.raises(InvalidConfigError):
        failures.worst(key_of("h"), limit=-1)
    with pytest.raises(InvalidConfigError):
        FailureHallOfFame(capacity=0)
