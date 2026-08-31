"""The informational profile Latin square (FR-5.3.2, CONTRACTS section 7.19, A19).

FR-5.3.2 asks that, in a rated tournament, the information profiles be permuted
between the agents of a matchup "selon un carre latin sur les seeds du matchup:
chaque harness occupe chaque profil un nombre egal de fois". This module is that
permutation and the measurement of how well it succeeded.

Three facts make the measurement necessary rather than decorative, and they are
arithmetic, not opinion:

* :class:`~pxe.types.InfoProfileKind` has exactly **three** members;
* PRD section 5.7 allows **4 to 8** seats per match and sets the default seed
  count to **3**;
* a seat count that is not a multiple of the kind count cannot give every seat
  the same multiset of kinds, whatever the construction.

So exact balance is impossible on 5 or 7 seats, and :func:`verify_balance`
returns a :class:`BalanceReport` instead of a bare ``bool``: the orchestrator
proceeds unchanged and the report publishes the residual deviation
(CONTRACTS section 7.19, "what an equal number of times degrades to").

Determinism
-----------
Nothing here draws a random number. The square is the cyclic one, the expansion
is a modulo and the assignment is a rotation, so the profile a seat plays is a
pure function of ``(agent_ids, profile_kinds, seed_index)`` and the registered
``tournament.latin_square`` substream is deliberately not consumed: a shuffled
square would make the same seed produce a different information layout on a
different machine's iteration order, which is exactly what FR-5.1.4 forbids.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pxe.errors import InvalidConfigError
from pxe.types import InfoProfileKind, sorted_ids

__all__ = [
    "BalanceReport",
    "latin_square",
    "expand_profile_kinds",
    "assign_profiles",
    "verify_balance",
]


@dataclass(frozen=True, slots=True)
class BalanceReport:
    """How evenly the profiles were spread over the seeds of a matchup.

    Attributes:
        exact: True when every seat saw every kind exactly the same number of
            times, that is when the kind count divides both the seat count and
            the seed count. False is **not** an error (CONTRACTS section 7.19,
            rule 4): the permutation was still applied and the residual is
            published rather than hidden.
        counts: ``(agent_id, counts_per_kind)`` pairs, sorted by ``agent_id``.
            The inner tuple is aligned with the kinds actually present in the
            assignments, in :class:`~pxe.types.InfoProfileKind` declaration
            order, which is the order :func:`expand_profile_kinds` cycles.
        max_deviation: The largest distance, over every ``(agent, kind)`` pair,
            between the observed count and the admissible integer count. When
            the kind count divides the seed count there is exactly one
            admissible count, ``seeds / kinds``, and this is
            ``max |count - mean|`` as CONTRACTS section 7.19 spells it. When it
            does not, no integer count can equal the mean, so the admissible
            counts are ``floor(mean)`` and ``ceil(mean)`` and the deviation is
            measured from that interval; a report of ``0`` with ``exact=False``
            then means "as even as integers allow".
        seeds: Number of seed indices the assignments cover.
        seats: Number of seats per assignment.
    """

    exact: bool
    counts: tuple[tuple[str, tuple[int, ...]], ...]
    max_deviation: int
    seeds: int
    seats: int

    def __bool__(self) -> bool:
        """Return :attr:`exact`, so ``if report:`` reads as "balance is exact"."""
        return self.exact


def latin_square(n: int) -> tuple[tuple[int, ...], ...]:
    """Return the cyclic Latin square of order ``n``.

    Row ``i`` is ``(i, i + 1, ..., n - 1, 0, ..., i - 1)``. Every row and every
    column is a permutation of ``0..n-1``, which is the property FR-5.3.2 needs:
    read row ``k`` as "the rotation applied at seed index ``k``" and column ``j``
    as "the sequence of symbols seat ``j`` sees over ``n`` seeds".

    This is the only construction used here. A randomised or reduced square would
    give the same balance guarantee and a different, seed dependent layout, so it
    would buy nothing and cost reproducibility.

    Args:
        n: Order of the square, at least one.

    Returns:
        ``n`` rows of ``n`` symbols.

    Raises:
        InvalidConfigError: If ``n`` is below one.
    """
    if n < 1:
        raise InvalidConfigError("a Latin square has order at least one", n=n)
    return tuple(tuple((i + j) % n for j in range(n)) for i in range(n))


def expand_profile_kinds(kinds: Sequence[InfoProfileKind], n_seats: int) -> tuple[InfoProfileKind, ...]:
    """Cycle ``kinds`` in declaration order up to length ``n_seats``.

    The vector is ``tuple(kinds[i % len(kinds)] for i in range(n_seats))``, so for
    six seats and the three default kinds it is ``(GENERALIST, SPECIALIST,
    DELAYED, GENERALIST, SPECIALIST, DELAYED)``. Declaration order and not sorted
    order, so adding a fourth kind later changes the vector in one predictable
    place (CONTRACTS section 7.19, rule 1). This is byte for byte what
    :func:`pxe.info.profiles.default_profile_kinds` produces, and the two have to
    agree: this module rotates that vector across seeds and a differently ordered
    default would rotate over a different multiset than the report measures.

    Args:
        kinds: The kinds in declaration order, normally ``tuple(InfoProfileKind)``.
        n_seats: Number of seats to fill, at least one.

    Returns:
        The expanded vector, of length ``n_seats``.

    Raises:
        InvalidConfigError: If ``kinds`` is empty or ``n_seats`` is below one.
    """
    if not kinds:
        raise InvalidConfigError("at least one profile kind is needed")
    if n_seats < 1:
        raise InvalidConfigError("a match seats at least one agent", n_seats=n_seats)
    return tuple(kinds[i % len(kinds)] for i in range(n_seats))


def assign_profiles(
    *,
    agent_ids: Sequence[str],
    profile_kinds: Sequence[InfoProfileKind],
    seed_index: int,
) -> tuple[tuple[str, InfoProfileKind], ...]:
    """Assign one profile kind per seat for one seed of a matchup.

    The expanded kind vector is rotated left by ``seed_index % n`` and zipped with
    ``sorted_ids(agent_ids)``, so over ``n`` consecutive seed indices every seat
    sees the whole expanded vector exactly once. That is the Latin square property
    on seats, and it holds for every seat count in 4..8 and any number of kinds
    (CONTRACTS section 7.19, rule 2).

    Args:
        agent_ids: The seats of the matchup. Iterated through
            :func:`pxe.types.sorted_ids` (section 2.3), so the order the caller
            happened to build the sequence in cannot influence the layout.
        profile_kinds: The kinds to spread, in declaration order. Expanded to the
            seat count by :func:`expand_profile_kinds`.
        seed_index: Position of this seed inside the matchup's seed list,
            ``>= 0``. It is the row of the Latin square.

    Returns:
        ``(agent_id, kind)`` pairs, sorted by ``agent_id``.

    Raises:
        InvalidConfigError: If ``agent_ids`` is empty, holds a duplicate, holds
            ``MM`` or ``FEES`` (:func:`pxe.types.sorted_ids` refuses those), if
            ``profile_kinds`` is empty, or if ``seed_index`` is negative.
    """
    if seed_index < 0:
        raise InvalidConfigError("a seed index is never negative", seed_index=seed_index)
    seats = sorted_ids(agent_ids)
    if not seats:
        raise InvalidConfigError("a matchup seats at least one agent")
    if len(set(seats)) != len(seats):
        raise InvalidConfigError("duplicate seat in a profile assignment", agent_ids=list(seats))
    expanded = expand_profile_kinds(profile_kinds, len(seats))
    offset = seed_index % len(seats)
    rotated = expanded[offset:] + expanded[:offset]
    return tuple(zip(seats, rotated, strict=True))


def verify_balance(assignments: Sequence[Sequence[tuple[str, InfoProfileKind]]]) -> BalanceReport:
    """Measure how evenly a set of per seed assignments spread the profiles.

    FR-5.3.2. This returns a report and never a bare ``bool``: with some seat
    counts exact balance is arithmetically impossible and a ``False`` would read
    as a bug (CONTRACTS section 7.19). Nothing raises on an imperfect square, and
    the orchestrator does not skip or discard anything because of one.

    Args:
        assignments: One assignment per seed index, each being the
            ``(agent_id, kind)`` pairs :func:`assign_profiles` returned. Every
            assignment must cover the same seats.

    Returns:
        The :class:`BalanceReport`. An empty input yields
        ``exact=False, seeds=0, seats=0``: no seed was played, so nothing was
        balanced, and reporting vacuous truth here would let an empty schedule
        claim FR-5.3.2 compliance.

    Raises:
        InvalidConfigError: If two assignments cover different seats, or if one
            assignment names a seat twice.
    """
    if not assignments:
        return BalanceReport(exact=False, counts=(), max_deviation=0, seeds=0, seats=0)

    seats = sorted_ids([agent_id for agent_id, _kind in assignments[0]])
    if len(set(seats)) != len(seats):
        raise InvalidConfigError("duplicate seat in an assignment", agent_ids=list(seats))
    counts: dict[str, dict[InfoProfileKind, int]] = {seat: {} for seat in seats}
    seen_kinds: list[InfoProfileKind] = []
    for assignment in assignments:
        if sorted_ids([agent_id for agent_id, _kind in assignment]) != seats:
            raise InvalidConfigError("assignments cover different seats", agent_ids=list(seats))
        for agent_id, kind in assignment:
            if kind not in seen_kinds:
                seen_kinds.append(kind)
            counts[agent_id][kind] = counts[agent_id].get(kind, 0) + 1

    kinds = tuple(kind for kind in InfoProfileKind if kind in seen_kinds)
    n_seeds = len(assignments)
    n_kinds = len(kinds)
    quotient, remainder = divmod(n_seeds, n_kinds)
    low = quotient
    high = quotient if remainder == 0 else quotient + 1

    rows: list[tuple[str, tuple[int, ...]]] = []
    deviation = 0
    exact = remainder == 0
    for seat in seats:
        row = tuple(counts[seat].get(kind, 0) for kind in kinds)
        rows.append((seat, row))
        for value in row:
            deviation = max(deviation, low - value, value - high)
            if value != quotient:
                exact = False

    return BalanceReport(
        exact=exact,
        counts=tuple(rows),
        max_deviation=deviation,
        seeds=n_seeds,
        seats=len(seats),
    )
