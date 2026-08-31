"""The tournament orchestrator, the three pairing formats and AC-P3.

The headline claims of T3.1 and AC-P3 are behavioural, so they are tested
behaviourally and not by inspection:

* **100 matches chained with no human intervention**
  (``test_nightly_plan_and_budget``, the O3 and AC-P3 row of section 11): the AC-P3 population
  of eight harnesses, four seeds per matchup, 112 real matches, the Latin square
  applied, the wall clock and the orchestrator's heap peak measured. The figures
  on the development machine: 57.1 s on four worker processes, 103.9 s
  sequentially, 5 MiB of orchestrator heap and 219 MiB of peak committed memory
  over the whole process tree.
* **Resume after a crash without double counting**
  (``test_crash_recovery_matches_an_uninterrupted_run``): the orchestrator is
  started in a **real subprocess**, killed mid tournament, restarted, and the
  match count, the journal hashes and the ratings are asserted equal to an
  uninterrupted run of the same configuration.
* **At least three seeds per matchup** (``test_min_three_seeds``)
  and the informational Latin square over those seeds
  (``test_plan_applies_the_latin_square``), which is FR-5.3.2.
* **The background population** (``test_background_population_joins_the_ranking``):
  the four rated scripted baselines are seated and rated, and the reference
  market maker plays every match while staying out of the ranking (FR-5.8.5).

Every test that reads a match first asserts that its journal is non empty and
holds the event under test (CONTRACTS section 10, anti-vacuous rule).
"""

from __future__ import annotations

import itertools
import os
import subprocess
import sys
import time
import tracemalloc
from collections import Counter
from pathlib import Path

import pytest

from pxe.errors import InvalidConfigError, TournamentError
from pxe.events import MatchEnded, MMQuoted, TradeExecuted
from pxe.journal import read_journal
from pxe.rng import RngTree
from pxe.store.db import Store
from pxe.store.files import artefact_paths
from pxe.tournament.elites import DEFAULT_ELITE_AXES, DEFAULT_ELITE_BINS
from pxe.tournament.latin_square import verify_balance
from pxe.tournament.orchestrator import (
    BACKGROUND_BASELINES,
    TournamentOrchestrator,
    background_harness,
    load_tournament_config,
)
from pxe.tournament.ratings import DEFAULT_MU, DEFAULT_SIGMA
from pxe.tournament.scheduling import (
    exhibition_pairings,
    format_pairings,
    round_robin_pairings,
    swiss_pairings,
)
from pxe.types import (
    FEES_ACCOUNT_ID,
    MM_ACCOUNT_ID,
    RE_MATCH_ID,
    GatewayConfig,
    HarnessConfig,
    MatchConfig,
    RatingRecord,
    TournamentConfig,
    TournamentFormat,
    harness_key,
)

#: A cheap but real match: the smallest legal horizon, four seats, two markets.
SMALL_DEFAULTS = MatchConfig(ticks_total=24, n_agents=4, n_markets=2)

#: The AC-P3 wall clock budget for 112 scripted matches on four workers. The
#: measured figures on the development machine are 57.1 s on four workers and
#: 103.9 s sequentially; the budget is an order of magnitude above that because
#: this test asserts "it finishes unattended", not "it is fast", and a loaded CI
#: runner sharing four cores with the rest of the suite is the normal case.
AC_P3_BUDGET_S = 600.0

#: The AC-P3 heap budget for the orchestrator **process**, in bytes. It measures
#: the one thing chaining a hundred matches can get wrong in this process: keeping
#: every journal, projection and metric alive instead of writing them out and
#: dropping them. The measured peak on the development machine is 5 MiB over 112
#: matches and it does not grow with the match count; the budget is 512 MiB
#: because this asserts "nothing accumulates", not a byte count. Worker processes
#: are outside :mod:`tracemalloc` by construction, and they are measured out of
#: band: 219 MiB of peak committed memory for the whole tree of five processes.
AC_P3_HEAP_BUDGET_BYTES = 512 * 1024 * 1024


def rated(keys: list[str], mus: list[float]) -> tuple[RatingRecord, ...]:
    """Build a synthetic leaderboard, strongest first in the given order."""
    return tuple(
        RatingRecord(harness_key=key, mu=mu, sigma=DEFAULT_SIGMA, matches=1) for key, mu in zip(keys, mus, strict=True)
    )


def keys_of(n: int) -> list[str]:
    """Return ``n`` distinct, sortable harness keys."""
    return [f"h{index:02d}@1.0.0+0000000{index}" for index in range(n)]


def scripted_population(names: tuple[str, ...], *, extra_versions: tuple[str, ...] = ()) -> tuple[HarnessConfig, ...]:
    """Return one scripted harness per baseline name, plus extra versions.

    A second version of the same baseline is a legitimate distinct harness: same
    behaviour, different key, which is exactly what CONTRACTS section 2.2 says a
    version bump means. It is how a population of eight is built out of six
    baselines without inventing a seventh policy.
    """
    harnesses = [background_harness(name) for name in names]
    harnesses.extend(HarnessConfig(harness_id=name, version="2.0.0", kind="scripted") for name in extra_versions)
    return tuple(harnesses)


def config_for(
    *,
    tournament_id: str,
    harnesses: tuple[HarnessConfig, ...],
    seeds: tuple[int, ...] = (11, 22, 33),
    agents_per_match: int = 4,
    fmt: TournamentFormat = TournamentFormat.ROUND_ROBIN,
    template_ids: tuple[str, ...] = ("election",),
    rounds: int = 1,
    background: tuple[str, ...] = (),
    max_cost_usd: float = 0.0,
) -> TournamentConfig:
    """Build a small but real tournament configuration."""
    from dataclasses import replace

    return TournamentConfig(
        tournament_id=tournament_id,
        format=fmt,
        harnesses=harnesses,
        template_ids=template_ids,
        seeds=seeds,
        agents_per_match=agents_per_match,
        rounds=rounds,
        gateway=GatewayConfig(),
        match_defaults=replace(SMALL_DEFAULTS, n_agents=agents_per_match),
        background_baselines=background,
        max_cost_usd=max_cost_usd,
    )


def crash_config() -> TournamentConfig:
    """The configuration of the crash recovery test.

    It is a module level function because the driver script the test kills
    imports it, so the interrupted run and the uninterrupted reference run are
    provably the same tournament rather than two copies of one literal.
    """
    return config_for(
        tournament_id="T-crash-0001",
        harnesses=scripted_population(("fundamentalist", "momentum", "noise", "zero_intelligence", "bayesian")),
        seeds=(101, 202, 303),
        agents_per_match=4,
    )


def assert_real_match(runs_dir: Path, match_id: str) -> None:
    """Assert that one match really happened before anything is claimed about it."""
    events = read_journal(artefact_paths(runs_dir, match_id)["journal"])
    assert events, f"{match_id} produced an empty journal"
    assert [event for event in events if isinstance(event, MatchEnded)], f"{match_id} never ended"
    assert [event for event in events if isinstance(event, MMQuoted)], f"{match_id} has no market maker quote"
    assert [event for event in events if isinstance(event, TradeExecuted)], f"{match_id} traded nothing"


# ---------------------------------------------------------------------------
# Round robin
# ---------------------------------------------------------------------------
def test_round_robin_covers_every_matchup() -> None:
    """Every combination appears exactly once and two calls are byte identical."""
    keys = keys_of(6)
    groups = round_robin_pairings(harness_keys=keys, agents_per_match=4)
    assert groups, "no group was produced"
    assert len(groups) == 15
    assert len(set(groups)) == len(groups)
    assert {frozenset(group) for group in groups} == {
        frozenset(combination) for combination in itertools.combinations(keys, 4)
    }
    assert groups == round_robin_pairings(harness_keys=list(reversed(keys)), agents_per_match=4)
    for group in groups:
        assert list(group) == sorted(group), "a group is not in seat order"


def test_round_robin_refuses_an_impossible_population() -> None:
    """A population smaller than one match, a duplicate key, a table of one."""
    with pytest.raises(InvalidConfigError):
        round_robin_pairings(harness_keys=keys_of(3), agents_per_match=4)
    with pytest.raises(InvalidConfigError):
        round_robin_pairings(harness_keys=["a", "a", "b", "c"], agents_per_match=4)
    with pytest.raises(InvalidConfigError):
        round_robin_pairings(harness_keys=keys_of(4), agents_per_match=1)


# ---------------------------------------------------------------------------
# Swiss
# ---------------------------------------------------------------------------
def test_swiss_pairs_by_standing_without_rematch() -> None:
    """Round one seats the top of the table together; round two never repeats it."""
    keys = keys_of(8)
    standings = rated(keys, [30.0 - index for index in range(8)])
    rng = RngTree(4242, namespace="tournament")
    first = swiss_pairings(
        standings=standings,
        agents_per_match=4,
        played=(),
        rng=rng.fresh_substream("tournament.pairing"),
    )
    assert first, "no group was produced"
    assert len(first) == 2
    assert keys[0] in first[0] and keys[1] in first[0], "the two strongest did not meet"
    played = [frozenset(group) for group in first]
    second = swiss_pairings(
        standings=standings,
        agents_per_match=4,
        played=played,
        rng=rng.fresh_substream("tournament.pairing"),
    )
    assert second, "the second round produced no group"
    for group in second:
        assert frozenset(group) not in played, "a group was replayed"
    for round_groups in (first, second):
        seated = [key for group in round_groups for key in group]
        assert len(seated) == len(set(seated)), "a harness was seated twice in one round"


def test_swiss_byes_rotate() -> None:
    """With a tail that divides the population, every key sits out exactly once.

    Eight harnesses at three seats leave a tail of two, so a round seats six and
    two sit out. Over ``8 / 2 == 4`` rounds every key has had exactly one bye and
    none has had two, which is the rotation CONTRACTS section 7.19 step 4 asks
    for.
    """
    keys = keys_of(8)
    standings = rated(keys, [30.0 - index for index in range(8)])
    rng = RngTree(99, namespace="tournament")
    played: list[frozenset[str]] = []
    byes: Counter[str] = Counter()
    for _round_index in range(4):
        groups = swiss_pairings(
            standings=standings,
            agents_per_match=3,
            played=played,
            rng=rng.fresh_substream("tournament.pairing"),
        )
        assert len(groups) == 2, "a round did not seat the whole population minus its tail"
        seated = {key for group in groups for key in group}
        byes.update(key for key in keys if key not in seated)
        played.extend(frozenset(group) for group in groups)
    assert sum(byes.values()) == 8
    assert set(byes) == set(keys), "a key never sat out"
    assert max(byes.values()) == 1, "a key sat out twice before every key had once"


def test_swiss_returns_nothing_when_no_match_can_be_seated() -> None:
    """Three harnesses cannot seat a table of four; that is empty, not an error."""
    standings = rated(keys_of(3), [30.0, 20.0, 10.0])
    rng = RngTree(1, namespace="tournament")
    assert (
        swiss_pairings(
            standings=standings,
            agents_per_match=4,
            played=(),
            rng=rng.fresh_substream("tournament.pairing"),
        )
        == ()
    )


# ---------------------------------------------------------------------------
# Exhibition
# ---------------------------------------------------------------------------
def test_exhibition_puts_the_challenger_in_seat_one() -> None:
    """The challenger is always ``A1`` and the field keeps the caller's order."""
    field = ["z-field", "a-field", "m-field"]
    groups = exhibition_pairings(harness_keys=field, challengers=["chal-1", "chal-2"])
    assert groups, "no group was produced"
    assert len(groups) == 2
    for group, challenger in zip(groups, ("chal-1", "chal-2"), strict=True):
        assert group[0] == challenger
        assert list(group[1:]) == field, "the field was re-sorted"
    truncated = exhibition_pairings(harness_keys=field, challengers=["chal-1"], agents_per_match=3)
    assert truncated == (("chal-1", "z-field", "a-field"),)


def test_exhibition_refuses_an_empty_field() -> None:
    """A challenger with nobody to play is a configuration error."""
    with pytest.raises(InvalidConfigError):
        exhibition_pairings(harness_keys=["only"], challengers=["only"])


def test_format_pairings_dispatches_every_format() -> None:
    """The dispatcher agrees with each function and refuses nothing valid."""
    keys = keys_of(6)
    standings = rated(keys, [30.0 - index for index in range(6)])
    rng = RngTree(7, namespace="tournament")
    common = {
        "harness_keys": keys,
        "agents_per_match": 4,
        "standings": standings,
        "played": (),
        "challengers": keys[:1],
    }
    assert format_pairings(
        TournamentFormat.ROUND_ROBIN, rng=rng.fresh_substream("tournament.pairing"), **common
    ) == round_robin_pairings(harness_keys=keys, agents_per_match=4)
    swiss = format_pairings(TournamentFormat.SWISS, rng=rng.fresh_substream("tournament.pairing"), **common)
    assert len(swiss) == 1
    exhibition = format_pairings(TournamentFormat.EXHIBITION, rng=rng.fresh_substream("tournament.pairing"), **common)
    assert exhibition[0][0] == keys[0]
    assert len(exhibition[0]) == 4


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------
def test_min_three_seeds(tmp_path: Path) -> None:
    """T3.3: every matchup is played on every seed, and there are at least three."""
    config = config_for(tournament_id="T-seeds-0001", harnesses=scripted_population((*BACKGROUND_BASELINES, "mute")))
    with Store(runs_dir=tmp_path) as store:
        orchestrator = TournamentOrchestrator(config=config, store=store)
        tasks = orchestrator.plan()
    assert tasks, "the plan is empty"
    assert len(config.seeds) >= 3
    per_matchup: Counter[frozenset[str]] = Counter(frozenset(task.harness_keys) for task in tasks)
    assert per_matchup, "no matchup was planned"
    for matchup, count in per_matchup.items():
        assert count == len(config.seeds) * len(config.template_ids), f"{matchup} was not played on every seed"
    assert {task.seed for task in tasks} == set(config.seeds)
    assert len({task.match_id for task in tasks}) == len(tasks), "two tasks share a match id"
    assert len({task.task_id for task in tasks}) == len(tasks), "two tasks share a task id"
    for task in tasks:
        assert task.task_id.startswith(f"{config.tournament_id}#"), "the store cannot recover the tournament id"
        assert RE_MATCH_ID.match(task.match_id), f"{task.match_id} is not a legal match id (section 2.2)"


def test_more_matchups_than_a_run_index_can_express_raises(tmp_path: Path) -> None:
    """A match id ends in two digits, so 210 matchups on one seed is refused.

    Ten harnesses at four seats is C(10, 4) = 210 matchups, and the run index of
    a match id has two digits (section 2.2). Silently wrapping or widening it
    would produce ids no other module can parse, so planning raises instead.
    """
    config = config_for(
        tournament_id="T-wide-0001",
        harnesses=tuple(
            HarnessConfig(harness_id="mute", version=f"{index}.0.0", kind="scripted") for index in range(10)
        ),
    )
    with Store(runs_dir=tmp_path) as store:
        orchestrator = TournamentOrchestrator(config=config, store=store)
        with pytest.raises(InvalidConfigError):
            orchestrator.plan()


def test_plan_applies_the_latin_square(tmp_path: Path) -> None:
    """FR-5.3.2: the profiles rotate over the seeds of a matchup."""
    config = config_for(
        tournament_id="T-square-0001",
        harnesses=scripted_population(("fundamentalist", "momentum", "noise", "zero_intelligence", "bayesian", "mute")),
        agents_per_match=6,
        seeds=(11, 22, 33),
    )
    with Store(runs_dir=tmp_path) as store:
        orchestrator = TournamentOrchestrator(config=config, store=store)
        tasks = orchestrator.plan()
        balance = orchestrator.profile_balance
    assert tasks, "the plan is empty"
    matchup = frozenset(tasks[0].harness_keys)
    by_seed = {task.seed: task.profile_assignment for task in tasks if frozenset(task.harness_keys) == matchup}
    assert len(by_seed) == len(config.seeds)
    assignments = [by_seed[seed] for seed in config.seeds]
    assert len(set(assignments)) == len(assignments), "the profiles did not rotate"
    report = verify_balance(assignments)
    assert report.exact is True, f"six seats and three seeds must balance exactly, got {report}"
    assert balance.exact is True
    assert balance.seats == 6


def test_plan_is_deterministic(tmp_path: Path) -> None:
    """Two orchestrators over the same configuration plan the same tournament."""
    config = config_for(tournament_id="T-det-0001", harnesses=scripted_population((*BACKGROUND_BASELINES, "mute")))
    with Store(runs_dir=tmp_path / "a") as first, Store(runs_dir=tmp_path / "b") as second:
        left = TournamentOrchestrator(config=config, store=first).plan()
        right = TournamentOrchestrator(config=config, store=second).plan()
    assert left, "the plan is empty"
    assert left == right


def test_swiss_cannot_be_planned_up_front(tmp_path: Path) -> None:
    """``plan()`` refuses Swiss, whose pairing depends on the standings."""
    config = config_for(
        tournament_id="T-swiss-0001",
        harnesses=scripted_population((*BACKGROUND_BASELINES, "mute", "bayesian")),
        fmt=TournamentFormat.SWISS,
        rounds=2,
    )
    with Store(runs_dir=tmp_path) as store:
        orchestrator = TournamentOrchestrator(config=config, store=store)
        with pytest.raises(TournamentError):
            orchestrator.plan()
        first = orchestrator.plan_round(0, ())
        assert first, "round zero planned nothing"
        heads = sorted({task.harness_keys[0] for task in first})
        standings = rated(heads, [30.0] * len(heads))
        second = orchestrator.plan_round(1, standings)
        assert second, "round one planned nothing"
        assert {frozenset(task.harness_keys) for task in second} != {frozenset(task.harness_keys) for task in first}, (
            "round one repeated round zero"
        )


def test_the_config_refuses_its_own_two_invariants() -> None:
    """CONTRACTS section 7.19 rule 5: the two config-local checks raise in ``__post_init__``.

    ``agents_per_match`` lives on the tournament and not on ``MatchConfig``, so a
    nine seat table is expressible and has to be refused; three seeds per matchup
    is the T3.3 floor. Both are properties of the dataclass alone, so neither
    needs a store, and an invalid tournament cannot be constructed at all.
    """
    harnesses = scripted_population((*BACKGROUND_BASELINES, "mute"))
    assert config_for(tournament_id="T-good-0001", harnesses=harnesses).agents_per_match == 4, (
        "the legal control must build, or the refusals below prove nothing"
    )
    with pytest.raises(InvalidConfigError):
        config_for(tournament_id="T-bad-0001", harnesses=harnesses, agents_per_match=9)
    with pytest.raises(InvalidConfigError):
        config_for(tournament_id="T-bad-0001b", harnesses=harnesses, agents_per_match=3)
    with pytest.raises(InvalidConfigError):
        config_for(tournament_id="T-bad-0001c", harnesses=harnesses, seeds=(11, 22))


def test_orchestrator_refuses_an_invalid_configuration(tmp_path: Path) -> None:
    """CONTRACTS section 7.19 rule 5, the checks that need the assembled population.

    ``harnesses`` holds the competitors only and the seats are filled by the
    competitors plus ``background_baselines``, so "the population is smaller
    than one match" is knowable here and nowhere else.
    """
    harnesses = scripted_population((*BACKGROUND_BASELINES, "mute"))
    with Store(runs_dir=tmp_path) as store:
        assert TournamentOrchestrator(config=config_for(tournament_id="T-ok-0001", harnesses=harnesses), store=store)
        for bad in (
            config_for(tournament_id="T-bad-0002", harnesses=harnesses[:2], agents_per_match=4),
            config_for(tournament_id="T-bad-0003", harnesses=harnesses, seeds=(1, 1, 1)),
            config_for(tournament_id="T-bad-0004", harnesses=harnesses, template_ids=()),
            config_for(tournament_id="has#hash", harnesses=harnesses),
            config_for(tournament_id="T-" + "x" * 40, harnesses=harnesses),
        ):
            with pytest.raises(InvalidConfigError):
                TournamentOrchestrator(config=bad, store=store)


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------
def test_a_round_robin_runs_and_persists_every_projection(tmp_path: Path) -> None:
    """One small tournament, end to end: journals, metrics, database, ratings."""
    config = config_for(
        tournament_id="T-run-0001",
        harnesses=scripted_population(("bayesian", "mute")),
        background=("fundamentalist", "momentum"),
    )
    with Store(runs_dir=tmp_path) as store:
        orchestrator = TournamentOrchestrator(config=config, store=store)
        result = orchestrator.run(max_workers=1)
        assert result.match_results, "the tournament played nothing"
        assert len(result.match_results) == 3, "one matchup on three seeds is three matches"
        for match in result.match_results:
            assert_real_match(tmp_path, match.match_id)
            assert store.has_match(match.match_id)
            assert artefact_paths(tmp_path, match.match_id)["metrics"].exists()
            metrics = store.load_metrics(match.match_id)
            assert metrics.performance, "no performance block was stored"
            projection = store.load_projection(match.match_id)
            assert projection.trades, "the stored projection holds no trade"
        assert store.pending_tasks(config.tournament_id) == (), "a task stayed pending"
        assert result.ratings, "nothing was rated"
        assert store.load_ratings(config.tournament_id) == result.ratings
        assert result.total_cost_usd == 0.0
        rows = store.list_matches(limit=100)
        assert len(rows) == 3


def test_a_real_tournament_fills_the_map_elites_archive(tmp_path: Path) -> None:
    """T5.2: ``elite_cell`` is written by the orchestrator, not by a fixture.

    Section 7.20's writer table names the orchestrator as the caller of
    ``save_elites`` "at end of tournament". Before this landed the archive was
    only ever populated by hand in a test, so ``GET /api/tournaments/{id}``
    served a grid no run had ever produced.
    """
    config = config_for(
        tournament_id="T-elites-0001",
        harnesses=scripted_population(("bayesian", "mute")),
        background=("fundamentalist", "momentum"),
    )
    with Store(runs_dir=tmp_path) as store:
        result = TournamentOrchestrator(config=config, store=store).run(max_workers=1)
        assert result.match_results, "the tournament played nothing, so the archive would be empty for free"
        cells = store.load_elites(config.tournament_id)
        assert cells, "no elite cell was persisted"
        rated = {record.harness_key for record in result.ratings}
        assert {cell.harness_key for cell in cells} <= rated, "an unrated key reached the archive"
        assert len({cell.coords for cell in cells}) == len(cells), "a cell was stored twice"
        for cell in cells:
            assert len(cell.coords) == len(DEFAULT_ELITE_AXES)
            assert len(cell.descriptors) == len(DEFAULT_ELITE_AXES)
            assert all(0 <= axis < count for axis, count in zip(cell.coords, DEFAULT_ELITE_BINS, strict=True))
            # mu is the rating "at the time it was offered" (section 7.19), that
            # is after the match that produced the style, so it is a real
            # TrueSkill mean and not the 25.0 prior of a key that never played.
            assert cell.mu > 0.0
        assert any(cell.mu != DEFAULT_MU for cell in cells), "every cell still carries the untouched prior"


def test_background_population_joins_the_ranking(tmp_path: Path) -> None:
    """PRD section 8: the four scripted baselines are rated floors; the MM is not.

    The reference market maker plays every match (it quotes on every open market)
    and is never a rated seat, which FR-5.8.5 requires and which is structural
    here: it has no harness and never appears in ``harness_of``.
    """
    config = config_for(
        tournament_id="T-floors-0001",
        harnesses=scripted_population(("mute",)),
        background=BACKGROUND_BASELINES,
    )
    with Store(runs_dir=tmp_path) as store:
        orchestrator = TournamentOrchestrator(config=config, store=store)
        assert len(orchestrator.population) == 5
        result = orchestrator.run(max_workers=1)
        assert result.match_results, "the tournament played nothing"
        rated_keys = {record.harness_key for record in result.ratings}
        for name in BACKGROUND_BASELINES:
            assert harness_key(background_harness(name)) in rated_keys, f"{name} is not a rated floor"
        assert MM_ACCOUNT_ID not in rated_keys
        assert FEES_ACCOUNT_ID not in rated_keys
        for record in result.ratings:
            assert record.matches >= 1
            assert record.sigma < DEFAULT_SIGMA, "sigma did not shrink for a rated harness"
        assert any(match.mm_pnl_cents != 0 for match in result.match_results), "the market maker never traded"
        for match in result.match_results:
            assert all(row.agent_id != MM_ACCOUNT_ID for row in match.rankings), "the MM is in a ranking"


def test_exhibition_does_not_move_ratings(tmp_path: Path) -> None:
    """A novelty match against a curated field cannot move a leaderboard."""
    config = config_for(
        tournament_id="T-exhib-0001",
        harnesses=scripted_population(("mute",)),
        background=BACKGROUND_BASELINES,
        fmt=TournamentFormat.EXHIBITION,
    )
    with Store(runs_dir=tmp_path) as store:
        orchestrator = TournamentOrchestrator(config=config, store=store)
        result = orchestrator.run(max_workers=1)
        assert result.match_results, "the exhibition played nothing"
        for match in result.match_results:
            assert_real_match(tmp_path, match.match_id)
        seat_one = read_journal(artefact_paths(tmp_path, result.match_results[0].match_id)["journal"])[0].agents[0]
        assert seat_one["agent_id"] == "A1"
        assert seat_one["harness_id"] == "mute", "the challenger is not seat A1"
        assert result.ratings == (), "an exhibition moved the ratings"
        assert store.load_ratings(config.tournament_id) == ()


def test_resume_never_double_counts(tmp_path: Path) -> None:
    """The idempotent resume of T3.1, without a crash: nothing is played twice."""
    config = config_for(
        tournament_id="T-idem-0001",
        harnesses=scripted_population(("bayesian", "mute", "noise")),
        background=("fundamentalist",),
    )
    with Store(runs_dir=tmp_path) as store:
        orchestrator = TournamentOrchestrator(config=config, store=store)
        first = orchestrator.run(max_workers=1)
        assert first.match_results, "the tournament played nothing"
        stamps = {
            match.match_id: artefact_paths(tmp_path, match.match_id)["journal"].stat().st_mtime_ns
            for match in first.match_results
        }
        second = orchestrator.resume()
    assert len(second.match_results) == len(first.match_results)
    assert [match.journal_hash for match in second.match_results] == [
        match.journal_hash for match in first.match_results
    ]
    assert second.ratings == first.ratings, "the resumed ratings differ"
    for match_id, stamp in stamps.items():
        assert artefact_paths(tmp_path, match_id)["journal"].stat().st_mtime_ns == stamp, (
            f"{match_id} was rewritten, so it was replayed"
        )


def test_cost_ceiling_stops_the_tournament(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-P3: the run stops rather than overspending the configured ceiling.

    A scripted tournament costs nothing, so the ceiling can only be reached by
    reporting a cost. The provider cost of a match comes from
    ``Store.load_costs_usd`` (the journal may not carry a cost, section 3.5), so
    that reader and the "is any harness an LLM" predicate are the two things
    patched here; the stopping logic itself is the real one.
    """
    config = config_for(
        tournament_id="T-cost-0001",
        harnesses=scripted_population(("bayesian", "mute", "noise")),
        background=("fundamentalist",),
        max_cost_usd=1.0,
    )
    monkeypatch.setattr(TournamentOrchestrator, "_has_llm", lambda self: True)
    monkeypatch.setattr(Store, "load_costs_usd", lambda self, tournament_id: (("spender", 2.5),))
    with Store(runs_dir=tmp_path) as store:
        orchestrator = TournamentOrchestrator(config=config, store=store)
        planned = orchestrator.plan()
        assert len(planned) > 1, "the ceiling test needs more than one match to stop before"
        result = orchestrator.run(max_workers=1)
        assert len(result.match_results) == 1, "the run did not stop at the ceiling"
        assert result.total_cost_usd == 2.5
        assert len(store.pending_tasks(config.tournament_id)) == len(planned) - 1


# ---------------------------------------------------------------------------
# AC-P3 and crash recovery
# ---------------------------------------------------------------------------
@pytest.mark.e2e
@pytest.mark.slow
def test_nightly_plan_and_budget(tmp_path: Path) -> None:
    """AC-P3: eight harnesses, 112 matches, four seeds per matchup, unattended.

    The population is the AC-P3 one (eight harnesses), the table is six seats,
    every matchup is played on four seeds and the informational Latin square is
    applied to each of them. Nothing in this test answers a prompt, retries a
    failure or touches a file by hand: ``run`` is called once.
    """
    config = config_for(
        tournament_id="T-acp3-0001",
        harnesses=scripted_population(
            ("fundamentalist", "momentum", "noise", "zero_intelligence", "bayesian", "mute"),
            extra_versions=("momentum", "bayesian"),
        ),
        seeds=(1101, 2202, 3303, 4404),
        agents_per_match=6,
        max_cost_usd=10.0,
    )
    assert len(config.harnesses) == 8
    assert len(config.seeds) >= 3
    with Store(runs_dir=tmp_path) as store:
        orchestrator = TournamentOrchestrator(config=config, store=store)
        planned = orchestrator.plan()
        assert len(planned) >= 100, f"AC-P3 needs at least 100 matches, planned {len(planned)}"
        tracemalloc.start()
        started = time.perf_counter()
        result = orchestrator.run(max_workers=4)
        elapsed = time.perf_counter() - started
        _current, peak_heap = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert len(result.match_results) == len(planned), "a match went missing"
        assert len(result.match_results) >= 100
        assert elapsed < AC_P3_BUDGET_S, f"112 scripted matches took {elapsed:.1f}s"
        # Nothing accumulates across the chain: the orchestrator writes each
        # match out and drops it, so the heap peak is flat in the match count.
        assert peak_heap < AC_P3_HEAP_BUDGET_BYTES, f"the orchestrator heap peaked at {peak_heap / 1048576:.0f} MiB"
        # The matches are real, not empty shells, and every one of them settled.
        assert_real_match(tmp_path, result.match_results[0].match_id)
        assert_real_match(tmp_path, result.match_results[-1].match_id)
        assert len({match.match_id for match in result.match_results}) == len(result.match_results)
        assert all(match.event_count > 0 for match in result.match_results)
        # The Latin square was applied to the seeds of every matchup, and its
        # residual deviation is measured rather than hidden (section 7.19 rule 4).
        assert orchestrator.profile_balance.seats == 6
        assert orchestrator.profile_balance.max_deviation <= 1
        # Every harness of the population is on the leaderboard, the cost stayed
        # under the ceiling, and no task is left pending.
        assert {record.harness_key for record in result.ratings} == {
            harness_key(harness) for harness in config.harnesses
        }
        assert result.total_cost_usd <= config.max_cost_usd
        assert store.pending_tasks(config.tournament_id) == ()
        assert len(store.list_matches(tournament_id=config.tournament_id, limit=500)) == len(planned)


#: The driver the crash recovery test kills. It imports the very configuration
#: the test uses, so the interrupted tournament and the reference one cannot
#: drift apart, and it runs sequentially so that terminating it terminates
#: everything that was playing.
CRASH_DRIVER = """
import sys
from pathlib import Path

from pxe.store.db import Store
from pxe.tournament.orchestrator import TournamentOrchestrator
from tests.test_tournament import crash_config

with Store(runs_dir=Path(sys.argv[1])) as store:
    TournamentOrchestrator(config=crash_config(), store=store).run(max_workers=1)
"""


def finished_matches(runs_dir: Path) -> int:
    """Count matches whose artefacts are complete, from outside the process.

    ``meta.json`` is written after ``MatchEnded`` (CONTRACTS section 4.6, step
    19), so counting those files is a signal a killed process cannot fake and
    that needs no cooperation from the orchestrator.
    """
    return len(list(runs_dir.glob("m-*/meta.json")))


@pytest.mark.e2e
@pytest.mark.slow
def test_crash_recovery_matches_an_uninterrupted_run(tmp_path: Path, repo_root: Path) -> None:
    """T3.1: kill the orchestrator for real, restart it, get the same tournament.

    A subprocess plays the tournament and is **terminated** (a real kill, not an
    exception) once a few matches are on disk. A new orchestrator then resumes
    the same store, and the match count, every journal hash and the whole
    leaderboard are asserted equal to an uninterrupted run of the same
    configuration in a different directory.
    """
    config = crash_config()
    reference_dir = tmp_path / "reference"
    crash_dir = tmp_path / "crashed"
    reference_dir.mkdir()
    crash_dir.mkdir()

    with Store(runs_dir=reference_dir) as store:
        reference = TournamentOrchestrator(config=config, store=store).run(max_workers=4)
    assert reference.match_results, "the reference tournament played nothing"
    assert len(reference.match_results) == 15, "five matchups on three seeds is fifteen matches"
    assert_real_match(reference_dir, reference.match_results[0].match_id)

    driver = tmp_path / "driver.py"
    driver.write_text(CRASH_DRIVER, encoding="utf-8", newline="\n")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(repo_root), str(repo_root / "src")])
    env["PYTHONHASHSEED"] = "0"
    process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(driver), str(crash_dir)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 120.0
        while finished_matches(crash_dir) < 3:
            assert process.poll() is None, "the driver exited before the tournament could be interrupted"
            assert time.monotonic() < deadline, "the driver never finished a match"
            time.sleep(0.05)
        killed_after = finished_matches(crash_dir)
        process.terminate()
        process.wait(timeout=60)
    finally:
        if process.poll() is None:  # pragma: no cover - only on a hung driver
            process.kill()
            process.wait(timeout=60)
    assert 3 <= killed_after < 15, f"the kill was not mid tournament ({killed_after} matches done)"

    with Store(runs_dir=crash_dir) as store:
        before = len(store.list_matches(limit=500))
        assert before < 15, "the interrupted run mirrored the whole tournament"
        resumed = TournamentOrchestrator(config=config, store=store).resume()
        assert len(store.list_matches(limit=500)) == 15, "resume did not finish the tournament"

    assert len(resumed.match_results) == len(reference.match_results), "the resumed match count differs"
    assert [match.match_id for match in resumed.match_results] == [match.match_id for match in reference.match_results]
    assert [match.journal_hash for match in resumed.match_results] == [
        match.journal_hash for match in reference.match_results
    ], "a resumed match replayed differently"
    assert resumed.ratings == reference.ratings, "the resumed ratings differ from the uninterrupted ones"
    assert len({match.match_id for match in resumed.match_results}) == 15, "a match was counted twice"


# ---------------------------------------------------------------------------
# The shipped presets
# ---------------------------------------------------------------------------
def test_shipped_presets_parse_and_are_runnable(repo_root: Path, tmp_path: Path) -> None:
    """Every ``configs/*.toml`` this package owns parses and passes validation."""
    presets = sorted((repo_root / "configs").glob("*.toml"))
    assert presets, "no tournament preset is shipped"
    for index, preset in enumerate(presets):
        config = load_tournament_config(preset)
        assert config.tournament_id
        assert len(config.seeds) >= 3
        assert 4 <= config.agents_per_match <= 8
        with Store(runs_dir=tmp_path / f"preset{index}") as store:
            orchestrator = TournamentOrchestrator(config=config, store=store)
            assert orchestrator.population
            if config.format is not TournamentFormat.SWISS:
                assert orchestrator.plan(), f"{preset.name} plans nothing"
            else:
                assert orchestrator.plan_round(0, ()), f"{preset.name} plans nothing"


def test_load_tournament_config_refuses_an_unknown_key(tmp_path: Path) -> None:
    """A typo in a preset is an error, never a silently ignored line."""
    path = tmp_path / "bad.toml"
    path.write_text(
        "\n".join(
            [
                'tournament_id = "T-bad-0001"',
                'format = "round_robin"',
                'template_ids = ["election"]',
                "seeds = [1, 2, 3]",
                "agents_per_match = 4",
                "[match_defaults]",
                "ticks_totl = 24",
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(InvalidConfigError):
        load_tournament_config(path)
