"""The FR-5.3.2 profile Latin square: rotation, coverage and honest degradation.

CONTRACTS section 7.19 names five tests here and each one pins a different half
of the same claim:

* the exact case (6 seats, 3 kinds, 6 seeds) really is exact;
* the PRD defaults (6 seats, 3 seeds) are exact too, so the shipped
  configuration is not the degraded one;
* five seats degrade **gracefully**: ``exact is False``, ``max_deviation == 1``
  and nothing raises, because FR-5.3.2's "an equal number of times" is
  arithmetically impossible there and a raise would fail a configuration the PRD
  itself allows;
* the rotation covers every seat over ``n`` seeds, which is the Latin square
  property the whole construction rests on;
* a seed count below three is refused, because T3.3 and AC-P3 make three the
  floor.
"""

from __future__ import annotations

import pytest

from pxe.agents.base import BASELINES
from pxe.errors import InvalidConfigError
from pxe.info.profiles import default_profile_kinds
from pxe.tournament.latin_square import (
    BalanceReport,
    assign_profiles,
    expand_profile_kinds,
    latin_square,
    verify_balance,
)
from pxe.tournament.orchestrator import background_harness
from pxe.types import (
    GatewayConfig,
    InfoProfileKind,
    MatchConfig,
    TournamentConfig,
    TournamentFormat,
    make_agent_id,
)

KINDS = tuple(InfoProfileKind)


def seats(n: int) -> tuple[str, ...]:
    """Return ``n`` canonical seat ids, ``A1``..``An``."""
    return tuple(make_agent_id(index + 1) for index in range(n))


def schedule(n_seats: int, n_seeds: int) -> tuple[tuple[tuple[str, InfoProfileKind], ...], ...]:
    """Return the assignments of ``n_seeds`` consecutive seed indices."""
    agent_ids = seats(n_seats)
    return tuple(
        assign_profiles(agent_ids=agent_ids, profile_kinds=KINDS, seed_index=index) for index in range(n_seeds)
    )


# ---------------------------------------------------------------------------
# The cyclic square itself
# ---------------------------------------------------------------------------
def test_latin_square_rows_and_columns_are_permutations() -> None:
    """Every row and every column of the cyclic square is a permutation."""
    square = latin_square(6)
    assert square, "the square is empty"
    assert len(square) == 6
    expected = set(range(6))
    for row in square:
        assert set(row) == expected
    for column_index in range(6):
        assert {row[column_index] for row in square} == expected


def test_latin_square_is_the_cyclic_one_and_deterministic() -> None:
    """Row ``i`` is ``(i, i+1, ..., n-1, 0, ..., i-1)`` and two calls agree."""
    assert latin_square(4)[0] == (0, 1, 2, 3)
    assert latin_square(4)[2] == (2, 3, 0, 1)
    assert latin_square(5) == latin_square(5)


def test_latin_square_refuses_order_zero() -> None:
    """Order zero is not a square, it is a caller bug."""
    with pytest.raises(InvalidConfigError):
        latin_square(0)


# ---------------------------------------------------------------------------
# Expansion
# ---------------------------------------------------------------------------
def test_expansion_cycles_in_declaration_order() -> None:
    """Six seats and the three default kinds give G, S, D, G, S, D."""
    expanded = expand_profile_kinds(KINDS, 6)
    assert expanded == (
        InfoProfileKind.GENERALIST,
        InfoProfileKind.SPECIALIST,
        InfoProfileKind.DELAYED,
        InfoProfileKind.GENERALIST,
        InfoProfileKind.SPECIALIST,
        InfoProfileKind.DELAYED,
    )


def test_expansion_agrees_with_the_info_engine_default() -> None:
    """A19 and A04 must produce the same vector (CONTRACTS section 7.19 rule 1).

    ``default_profile_kinds`` is what a standalone match uses and
    ``expand_profile_kinds`` is what a tournament rotates. A different order in
    either would make the rotation cover a different multiset than the one the
    report measures, and no other test compares them.
    """
    for n_seats in range(4, 9):
        assert expand_profile_kinds(KINDS, n_seats) == default_profile_kinds(n_seats)


def test_expansion_refuses_an_empty_kind_list() -> None:
    """No kinds means no assignment; that is a configuration bug."""
    with pytest.raises(InvalidConfigError):
        expand_profile_kinds((), 6)


# ---------------------------------------------------------------------------
# Rotation and coverage
# ---------------------------------------------------------------------------
def test_rotation_covers_every_seat_over_n_seeds() -> None:
    """Over ``n`` seed indices every seat sees the whole expanded vector once."""
    n_seats = 6
    expanded = expand_profile_kinds(KINDS, n_seats)
    assignments = schedule(n_seats, n_seats)
    assert len(assignments) == n_seats
    for agent_id in seats(n_seats):
        seen = [dict(assignment)[agent_id] for assignment in assignments]
        assert sorted(seen) == sorted(expanded), f"{agent_id} did not see the whole vector"


def test_assignment_is_sorted_by_agent_id_and_rotation_wraps() -> None:
    """The result is in canonical seat order and ``seed_index`` wraps modulo n."""
    assignment = assign_profiles(agent_ids=("A3", "A1", "A2", "A4"), profile_kinds=KINDS, seed_index=0)
    assert [agent_id for agent_id, _kind in assignment] == ["A1", "A2", "A3", "A4"]
    assert assign_profiles(agent_ids=seats(4), profile_kinds=KINDS, seed_index=4) == assignment


def test_assignment_refuses_a_negative_seed_index_and_a_reserved_account() -> None:
    """A seed index is never negative and ``MM`` is never a rated seat."""
    with pytest.raises(InvalidConfigError):
        assign_profiles(agent_ids=seats(4), profile_kinds=KINDS, seed_index=-1)
    with pytest.raises(InvalidConfigError):
        assign_profiles(agent_ids=("A1", "MM"), profile_kinds=KINDS, seed_index=0)


# ---------------------------------------------------------------------------
# Balance
# ---------------------------------------------------------------------------
def test_each_harness_gets_each_profile_equally() -> None:
    """The exact case of CONTRACTS section 7.19: 6 seats, 3 kinds, 6 seeds."""
    report = verify_balance(schedule(6, 6))
    assert report.seeds == 6
    assert report.seats == 6
    assert report.counts, "the report counted nothing"
    assert report.exact is True
    assert bool(report) is True
    assert report.max_deviation == 0
    for _agent_id, counts in report.counts:
        assert counts == (2, 2, 2)


def test_balance_is_exact_with_prd_defaults() -> None:
    """6 seats and 3 seeds (PRD section 5.7) are exact: three kinds divide both."""
    report = verify_balance(schedule(6, 3))
    assert report.counts, "the report counted nothing"
    assert report.exact is True
    assert report.max_deviation == 0
    for _agent_id, counts in report.counts:
        assert counts == (1, 1, 1)


def test_balance_degrades_gracefully_on_five_seats() -> None:
    """Five seats cannot be balanced, and that is measured, not raised."""
    report = verify_balance(schedule(5, 3))
    assert report.counts, "the report counted nothing"
    assert report.exact is False
    assert bool(report) is False
    assert report.max_deviation == 1
    assert report.seats == 5
    assert report.seeds == 3


def test_seven_seats_are_never_exact_whatever_the_seed_count() -> None:
    """Rule 3 wins over rule 6's advice when the seat count is the problem.

    CONTRACTS section 7.19 rule 3 makes balance exact only when the kind count
    divides **both** the seat count and the seed count, and rule 6 then advises
    "use a seed count that is a multiple of both ``agents_per_match`` and
    ``len(kinds)``". On seven seats no seed count can help: the expanded vector
    itself is ``(G, S, D, G, S, D, G)``, so every seat that sees the whole vector
    sees one extra generalist. 21 seeds is a multiple of both 7 and 3 and the
    report is still, correctly, not exact. Rule 6's advice is therefore only
    sufficient when three already divides the seat count; see CONTRACT ISSUES.
    """
    report = verify_balance(schedule(7, 21))
    assert report.exact is False
    assert report.max_deviation == 2
    for _agent_id, counts in report.counts:
        assert counts == (9, 6, 6)


def test_empty_schedule_is_not_a_balanced_one() -> None:
    """An empty schedule reports ``exact=False`` rather than vacuous truth."""
    report = verify_balance(())
    assert isinstance(report, BalanceReport)
    assert report.exact is False
    assert report.seeds == 0
    assert report.counts == ()


def test_balance_refuses_assignments_over_different_seats() -> None:
    """Two rounds over different tables are not one schedule."""
    first = assign_profiles(agent_ids=seats(4), profile_kinds=KINDS, seed_index=0)
    second = assign_profiles(agent_ids=seats(5), profile_kinds=KINDS, seed_index=1)
    with pytest.raises(InvalidConfigError):
        verify_balance((first, second))


# ---------------------------------------------------------------------------
# The seed count floor (T3.3, AC-P3)
# ---------------------------------------------------------------------------
def test_seed_count_below_three_raises(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Fewer than three seeds per matchup is refused (PRD section 5.7, T3.3).

    CONTRACTS section 7.19 rule 5 puts this check in
    ``TournamentConfig.__post_init__``, and that is now where it lives, so an
    under-seeded tournament cannot be constructed, let alone run. The three seed
    control below is what stops this test from passing on a dataclass that
    refuses everything.
    """
    from pxe.store.db import Store
    from pxe.tournament.orchestrator import TournamentOrchestrator

    def build(seeds: tuple[int, ...]) -> TournamentConfig:
        return TournamentConfig(
            tournament_id="T-floor-0001",
            format=TournamentFormat.ROUND_ROBIN,
            harnesses=tuple(background_harness(name) for name in BASELINES[:4]),
            template_ids=("election",),
            seeds=seeds,
            agents_per_match=4,
            rounds=1,
            gateway=GatewayConfig(),
            match_defaults=MatchConfig(ticks_total=24, n_agents=4, n_markets=2),
        )

    with pytest.raises(InvalidConfigError):
        build((1, 2))
    legal = build((1, 2, 3))
    runs_dir = tmp_path_factory.mktemp("floor")
    with Store(runs_dir=runs_dir) as store:
        assert TournamentOrchestrator(config=legal, store=store).plan()
