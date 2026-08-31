"""The three tournament pairing formats (PRD section 8, T3.1, CONTRACTS 7.19, A19).

All three functions return a tuple of **seat groups**. A group is a tuple of
harness keys and the position inside the group **is** the seat: ``group[0]`` sits
at ``A1``. Groups come back in the order they must be played. Nothing here reads
a clock and only Swiss touches an RNG, for one purpose (breaking a tie between
two equally unplayed candidate groups).

Why a dispatcher exists
-----------------------
:func:`format_pairings` is the one entry point
:meth:`pxe.tournament.orchestrator.TournamentOrchestrator.plan_round` calls, so
the orchestrator holds no ``if format ==`` chain of its own and a fourth format
is one function plus one dispatch row rather than an edit in two modules.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Sequence

from pxe.errors import InvalidConfigError
from pxe.rng import choice
from pxe.types import RatingRecord, TournamentFormat

__all__ = [
    "round_robin_pairings",
    "swiss_pairings",
    "exhibition_pairings",
    "format_pairings",
]


def _distinct(keys: Sequence[str], *, what: str) -> tuple[str, ...]:
    """Return ``keys`` unchanged, refusing an empty entry or a duplicate.

    A duplicated harness key is never a benign input: round robin would emit the
    same group twice, Swiss would seat one brain against itself and the ratings
    would fold one match into one harness twice.

    Args:
        keys: The population.
        what: Name of the argument, used in the error.

    Returns:
        The keys as a tuple.

    Raises:
        InvalidConfigError: If a key is empty or appears twice.
    """
    result = tuple(keys)
    if any(not key for key in result):
        raise InvalidConfigError(f"{what} holds an empty harness key")
    if len(set(result)) != len(result):
        raise InvalidConfigError(f"{what} holds a duplicate harness key", keys=list(result))
    return result


def round_robin_pairings(*, harness_keys: Sequence[str], agents_per_match: int) -> tuple[tuple[str, ...], ...]:
    """Every combination of ``agents_per_match`` distinct harness keys, once.

    ``itertools.combinations`` over a lexicographically sorted input is itself
    lexicographically ordered and deterministic, which is why it is named in
    CONTRACTS section 7.19 rather than described: two calls are byte identical and
    the schedule does not depend on the order the caller listed the population in.

    Seat assignment inside a group is that sorted order. Seat *fairness* is not
    this function's job: it belongs to the Latin square (FR-5.3.2) and to the P3
    fairness shuffle (FR-5.1.5).

    Args:
        harness_keys: The population, distinct.
        agents_per_match: Seats per match, at least two.

    Returns:
        ``C(len(harness_keys), agents_per_match)`` groups, lexicographically
        ordered.

    Raises:
        InvalidConfigError: If ``agents_per_match`` is below two, if the
            population is smaller than one match, or if a key is empty or
            duplicated.
    """
    keys = _distinct(harness_keys, what="round robin population")
    if agents_per_match < 2:
        raise InvalidConfigError("a match seats at least two harnesses", agents_per_match=agents_per_match)
    if len(keys) < agents_per_match:
        raise InvalidConfigError(
            "the population is smaller than one match",
            n_harnesses=len(keys),
            agents_per_match=agents_per_match,
        )
    return tuple(itertools.combinations(tuple(sorted(keys)), agents_per_match))


def _standings_order(standings: Sequence[RatingRecord]) -> tuple[str, ...]:
    """Return the harness keys strongest first (CONTRACTS 7.19, Swiss step 1).

    The key is ``(-mu, sigma, harness_key)``: strongest first, then the more
    uncertain of two equal means (it gains the most information from a match),
    then the key itself so the order never depends on the caller's input order.

    Args:
        standings: The current leaderboard, one record per harness.

    Returns:
        The keys in pairing order.

    Raises:
        InvalidConfigError: If a record's key is empty or appears twice.
    """
    _distinct([record.harness_key for record in standings], what="standings")
    ordered = sorted(standings, key=lambda record: (-record.mu, record.sigma, record.harness_key))
    return tuple(record.harness_key for record in ordered)


def _meetings(played: Sequence[frozenset[str]], group: frozenset[str]) -> int:
    """Return how many times this exact group has already played.

    Args:
        played: Every group played so far, one entry per group per round.
        group: The candidate group.

    Returns:
        The number of prior meetings.
    """
    return sum(1 for previous in played if previous == group)


def _bye_keys(ordered: Sequence[str], *, agents_per_match: int, round_index: int) -> frozenset[str]:
    """Return the keys that sit out this round (CONTRACTS 7.19, Swiss step 4).

    When the population is not a multiple of ``agents_per_match`` a tail of fewer
    than ``agents_per_match`` keys cannot be seated. It receives a bye: it plays
    no match this round and its sigma is untouched. Byes rotate, round ``r``
    taking its tail from the standings rotated left by ``r * remainder``.

    Args:
        ordered: The standings order.
        agents_per_match: Seats per match.
        round_index: The round, ``0`` based.

    Returns:
        The keys on a bye, possibly empty.
    """
    n = len(ordered)
    remainder = n % agents_per_match
    if remainder == 0 or n == 0:
        return frozenset()
    offset = (round_index * remainder) % n
    rotated = tuple(ordered[(offset + j) % n] for j in range(n))
    return frozenset(rotated[n - remainder :])


def _round_index_of(played: Sequence[frozenset[str]], *, groups_per_round: int) -> int:
    """Infer the round about to be paired from the groups already played.

    ``swiss_pairings`` has no ``round_index`` parameter in CONTRACTS section 7.19
    and needs one for the bye rotation of step 4, so it is derived from the
    history the signature does carry. A Swiss round always seats
    ``(n - n % agents_per_match) / agents_per_match`` groups, so the count is
    exact. See CONTRACT ISSUES.

    Args:
        played: Every group played so far in this tournament, in round order.
        groups_per_round: Groups one round seats, at least one.

    Returns:
        The ``0`` based index of the round to pair.
    """
    return len(played) // groups_per_round


def swiss_pairings(
    *,
    standings: Sequence[RatingRecord],
    agents_per_match: int,
    played: Sequence[frozenset[str]],
    rng: random.Random,
) -> tuple[tuple[str, ...], ...]:
    """Pair one Swiss round from the standings (CONTRACTS 7.19, Swiss steps 1..5).

    One round at a time, which is the entire reason
    :meth:`pxe.tournament.orchestrator.TournamentOrchestrator.plan_round` exists:
    the pairing of round ``r`` depends on the ratings after round ``r - 1``.

    The algorithm walks the standings from the top and greedily completes the head
    with the next ``agents_per_match - 1`` still unpaired keys whose resulting
    group has never been played. When no unplayed group can be formed from the
    current head it relaxes to the candidate group with the **fewest** prior
    meetings, which covers both relaxation steps of CONTRACTS section 7.19 (allow
    one repeat, then allow any repeat) in one expression: a group met once is
    strictly preferred to a group met twice. A player is never left unpaired and a
    group is never silently shortened.

    Args:
        standings: The current leaderboard. Every harness that should play this
            round must appear, including one entering at the prior: an absent key
            is simply not seated.
        agents_per_match: Seats per match, at least two.
        played: Every group played so far in this tournament, in round order. It
            is both the rematch filter and, through its length, the source of the
            round index used by the bye rotation.
        rng: ``tournament_rng.fresh_substream("tournament.pairing")``. Used for
            exactly one thing: breaking a tie between two candidate groups with
            the same fewest prior meetings. ``fresh_substream`` and not
            ``substream``, so round ``r`` does not depend on how many draws round
            ``r - 1`` consumed.

    Returns:
        The groups of this round, strongest head first. Empty when the population
        cannot seat a single match.

    Raises:
        InvalidConfigError: If ``agents_per_match`` is below two, or if the
            standings hold an empty or duplicated harness key.
    """
    if agents_per_match < 2:
        raise InvalidConfigError("a match seats at least two harnesses", agents_per_match=agents_per_match)
    ordered = _standings_order(standings)
    groups_per_round = (len(ordered) - len(ordered) % agents_per_match) // agents_per_match
    if groups_per_round == 0:
        return ()
    round_index = _round_index_of(played, groups_per_round=groups_per_round)
    on_bye = _bye_keys(ordered, agents_per_match=agents_per_match, round_index=round_index)
    pool = [key for key in ordered if key not in on_bye]

    groups: list[tuple[str, ...]] = []
    unpaired = list(pool)
    while len(unpaired) >= agents_per_match:
        head = unpaired[0]
        rest = unpaired[1:]
        best: tuple[str, ...] | None = None
        tied: list[tuple[str, ...]] = []
        best_meetings = -1
        for combination in itertools.combinations(rest, agents_per_match - 1):
            candidate = (head, *combination)
            meetings = _meetings(played, frozenset(candidate))
            if meetings == 0:
                best = candidate
                tied = []
                break
            if best_meetings < 0 or meetings < best_meetings:
                best_meetings = meetings
                tied = [candidate]
            elif meetings == best_meetings:
                tied.append(candidate)
        if best is None:
            if not tied:
                break
            best = tied[0] if len(tied) == 1 else choice(rng, tied)
        groups.append(best)
        seated = set(best)
        unpaired = [key for key in unpaired if key not in seated]
    return tuple(groups)


def exhibition_pairings(
    *,
    harness_keys: Sequence[str],
    challengers: Sequence[str],
    agents_per_match: int = 0,
) -> tuple[tuple[str, ...], ...]:
    """One match per challenger against a fixed field (CONTRACTS 7.19).

    The challenger is always seat ``A1``, which makes an exhibition report
    readable without a legend. ``harness_keys`` keeps the order the caller gave
    (normally the Hall of Fame or the background baselines): this function never
    re-sorts it, because "the field" is a curated list and sorting it would
    silently change who plays.

    Exhibition matches are **not rated**:
    :meth:`pxe.tournament.orchestrator.TournamentOrchestrator.run` skips
    :meth:`pxe.tournament.ratings.RatingService.update` for this format, so a
    novelty match cannot move a leaderboard.

    Args:
        harness_keys: The field, in the order it should be seated.
        challengers: One match per entry, in order.
        agents_per_match: Seats per match. ``0``, the default, means "the whole
            field": CONTRACTS section 7.19 gives this function no
            ``agents_per_match`` parameter and then truncates the field to
            ``agents_per_match - 1`` in its own body, so the argument is added
            keyword-only with a default that preserves the contracted call. See
            CONTRACT ISSUES.

    Returns:
        One group per challenger, challenger first.

    Raises:
        InvalidConfigError: If ``agents_per_match`` is negative or exactly one, if
            a challenger is empty, or if the field is empty while a challenger
            needs one.
    """
    if agents_per_match == 1 or agents_per_match < 0:
        raise InvalidConfigError("a match seats at least two harnesses", agents_per_match=agents_per_match)
    field = _distinct(harness_keys, what="exhibition field")
    entrants = _distinct(challengers, what="exhibition challengers")
    groups: list[tuple[str, ...]] = []
    for entrant in entrants:
        others = tuple(key for key in field if key != entrant)
        if agents_per_match:
            others = others[: agents_per_match - 1]
        if not others:
            raise InvalidConfigError("an exhibition needs a field to play against", challenger=entrant)
        groups.append((entrant, *others))
    return tuple(groups)


def format_pairings(
    format: TournamentFormat,
    *,
    harness_keys: Sequence[str],
    agents_per_match: int,
    standings: Sequence[RatingRecord],
    played: Sequence[frozenset[str]],
    challengers: Sequence[str],
    rng: random.Random,
) -> tuple[tuple[str, ...], ...]:
    """Dispatch to the pairing function of one format.

    This is the one dispatcher
    :meth:`pxe.tournament.orchestrator.TournamentOrchestrator.plan_round` calls,
    so the orchestrator holds no ``if format ==`` chain of its own. Every argument
    is passed by every caller and each format ignores what it does not need,
    which is what keeps the call site free of conditionals.

    Args:
        format: The tournament format.
        harness_keys: The population for round robin, the field for an exhibition,
            ignored by Swiss (which reads ``standings``).
        agents_per_match: Seats per match.
        standings: The current leaderboard, used by Swiss only.
        played: Groups already played, used by Swiss only.
        challengers: Used by the exhibition format only.
        rng: Used by Swiss only.

    Returns:
        The groups to play, in playing order.

    Raises:
        InvalidConfigError: If the format is unknown, or on any argument error the
            selected function raises.
    """
    if format is TournamentFormat.ROUND_ROBIN:
        return round_robin_pairings(harness_keys=harness_keys, agents_per_match=agents_per_match)
    if format is TournamentFormat.SWISS:
        return swiss_pairings(
            standings=standings,
            agents_per_match=agents_per_match,
            played=played,
            rng=rng,
        )
    if format is TournamentFormat.EXHIBITION:
        return exhibition_pairings(
            harness_keys=harness_keys,
            challengers=challengers,
            agents_per_match=agents_per_match,
        )
    raise InvalidConfigError("unknown tournament format", format=str(format))
