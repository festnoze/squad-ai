"""TrueSkill ratings and bootstrap confidence intervals (PRD 7.3, CONTRACTS 7.19, A20).

PRD section 7.3 asks for three things and this module is all three:

* **TrueSkill updated on the PnL ranking of every match.** The ranking is
  :class:`~pxe.types.MatchRanking`, that is exactly what the runner journalled
  inside ``MatchEnded.rankings``, so a rating is a projection of the journal and
  never of engine state.
* **mu and sigma tracked per harness version.** The rated identity is the
  *harness key* ``<harness_id>@<version>+<config_hash[:8]>`` produced by
  :func:`pxe.types.harness_key` (section 2.2, decision 24), never the seat id:
  two prompts shipped under one ``version`` tag are two ratings, and the same
  harness sitting at ``A1`` in one match and ``A5`` in the next keeps one.
* **The reference market maker is never rated (FR-5.8.5).** ``MM`` and ``FEES``
  are filtered out of ``harness_of`` before anything else happens, which is also
  what keeps :func:`pxe.types.sorted_ids` usable on the remaining keys: that
  helper *raises* on the two reserved accounts by design (section 2.3).

Floats live here on purpose
---------------------------
``mu``, ``sigma`` and a bootstrap bound are floats, which section 2.1 allows for
"statistical helpers in metrics/ratings/integrity that never write into a
journal". Nothing in this module is journalled and nothing in it enters a
journal hash; a rating reaches disk through
:meth:`pxe.store.db.Store.save_ratings` and through nothing else.

Determinism
-----------
No clock, no network, no builtin ``hash()``. The only randomness is the
``random.Random`` the caller hands to :func:`bootstrap_ci`, which must come from
a registered substream (``metrics.bootstrap``), and every draw goes through
:func:`pxe.rng.randint` so the resampling is bit identical on every platform.
Every iteration that produces output is over a sorted sequence: harness keys sort
lexicographically (the spelling
:func:`pxe.tournament.scheduling.round_robin_pairings` uses for the same values),
seat ids sort through :func:`pxe.types.sorted_ids`.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from statistics import fmean
from typing import Any

import trueskill

from pxe.errors import InvalidConfigError
from pxe.rng import randint
from pxe.types import (
    FEES_ACCOUNT_ID,
    MM_ACCOUNT_ID,
    MatchRanking,
    RatingRecord,
    sorted_ids,
)

__all__ = [
    "UNRATED_ACCOUNT_IDS",
    "DEFAULT_MU",
    "DEFAULT_SIGMA",
    "DEFAULT_BETA",
    "DEFAULT_TAU",
    "RatingService",
    "bootstrap_ci",
]

#: The two accounts that are never rated (FR-5.8.5). The market maker is a
#: neutral liquidity provider whose PnL is the published cost of liquidity, and
#: ``FEES`` is a vault, not a player. Both are dropped from ``harness_of`` before
#: any ordering happens, because :func:`pxe.types.sorted_ids` raises on them.
UNRATED_ACCOUNT_IDS: frozenset[str] = frozenset({MM_ACCOUNT_ID, FEES_ACCOUNT_ID})

#: The TrueSkill prior of an unrated harness. These are the four defaults of
#: :class:`RatingService`, published as constants so a test and a report do not
#: each re-spell them.
DEFAULT_MU: float = 25.0
DEFAULT_SIGMA: float = 8.333
DEFAULT_BETA: float = 4.167
DEFAULT_TAU: float = 0.083

#: Minimum number of distinct harnesses a match must field for its ranking to
#: carry information. A one player ranking has nothing to compare against, so it
#: is a no op rather than an error: an exhibition field reduced to a single
#: harness is a caller decision, not a bug.
_MIN_RATED_GROUPS = 2


class RatingService:
    """TrueSkill leaderboard over harness keys (PRD 7.3, T3.2).

    One instance holds the ratings of one population, normally one tournament.
    It is a pure in memory service: persistence is
    :meth:`pxe.store.db.Store.save_ratings`, and the service never touches a
    file, a clock or a database.

    Ties are supported. :class:`~pxe.types.MatchRanking` lets two seats share the
    lowest rank (finalisation step 18), and equal ranks are handed to TrueSkill
    as a draw, which is the meaning the algorithm already gives them.

    A harness holding **several seats of one match** is rated once, at the best
    (numerically lowest) rank of its seats. That case only arises when a caller
    seats one harness twice; rating it twice from a single match would let a
    population double count its own result.
    """

    __slots__ = ("_env", "_prior_mu", "_prior_sigma", "_records")

    def __init__(
        self,
        *,
        mu: float = DEFAULT_MU,
        sigma: float = DEFAULT_SIGMA,
        beta: float = DEFAULT_BETA,
        tau: float = DEFAULT_TAU,
        draw_probability: float = 0.0,
    ) -> None:
        """Build the service with a TrueSkill environment.

        Args:
            mu: Prior mean skill of an unrated harness.
            sigma: Prior standard deviation of an unrated harness.
            beta: Skill distance covering one standard deviation of match
                outcome noise.
            tau: Per match additive dynamics, which keeps sigma from collapsing
                to zero and lets a harness that changed behaviour be re-learned.
            draw_probability: Probability the algorithm assigns to a draw. The
                default is ``0.0``, which section 7.19 fixes: a PnL ranking in
                cents is a total order in all but exact ties, and an inflated
                draw prior would flatten the leaderboard. Note the consequence,
                because it surprises: under a zero draw prior an **exact** tie
                is an outcome the model calls impossible, so it *raises* sigma
                (8.333 to 9.588 on a two player tie at the prior) instead of
                lowering it. Two mute seats both finishing at zero PnL is a
                reachable tie, so a population where ties are routine should
                pass a small draw probability rather than rely on the default.
                This is reported as a contract gap rather than silently
                overridden here.

        Raises:
            InvalidConfigError: If ``sigma`` or ``beta`` is not strictly
                positive, if ``tau`` is negative, or if ``draw_probability`` is
                outside ``[0, 1)``.
        """
        if sigma <= 0.0:
            raise InvalidConfigError("sigma must be strictly positive", sigma=sigma)
        if beta <= 0.0:
            raise InvalidConfigError("beta must be strictly positive", beta=beta)
        if tau < 0.0:
            raise InvalidConfigError("tau must be non negative", tau=tau)
        if not 0.0 <= draw_probability < 1.0:
            raise InvalidConfigError("draw_probability must be in [0, 1)", draw_probability=draw_probability)
        self._env: Any = trueskill.TrueSkill(
            mu=float(mu),
            sigma=float(sigma),
            beta=float(beta),
            tau=float(tau),
            draw_probability=float(draw_probability),
        )
        self._prior_mu = float(mu)
        self._prior_sigma = float(sigma)
        self._records: dict[str, RatingRecord] = {}

    def update(self, ranking: Sequence[MatchRanking], *, harness_of: Mapping[str, str]) -> tuple[RatingRecord, ...]:
        """Fold one match ranking into the leaderboard.

        ``MM`` and ``FEES`` are never rated (FR-5.8.5); a seat absent from
        ``harness_of`` is not rated either, which is how a background baseline
        can play without being ranked. ``harness_of`` is iterated only through
        :func:`pxe.types.sorted_ids` (section 2.3), so a caller that built the
        mapping in a different order gets the same leaderboard.

        Args:
            ranking: The final ranking of a finished match, that is
                ``MatchEnded.rankings``. Only ``agent_id`` and ``rank`` are read:
                the PnL is already encoded in the rank (finalisation step 18).
            harness_of: Seat id to harness key, for the seats of that match.

        Returns:
            The updated records, one per rated harness of this match, ordered by
            harness key. Empty when fewer than two distinct harnesses played,
            in which case no rating moved.

        Raises:
            InvalidConfigError: If a rated seat maps to an empty harness key, or
                if ``ranking`` names a seat twice.
        """
        rated_seats = sorted_ids(tuple(seat for seat in harness_of if seat not in UNRATED_ACCOUNT_IDS))
        best_rank: dict[str, int] = {}
        seen: set[str] = set()
        for row in ranking:
            if row.agent_id in seen:
                raise InvalidConfigError("a ranking names a seat twice", agent_id=row.agent_id)
            seen.add(row.agent_id)
        for seat in rated_seats:
            key = harness_of[seat]
            if not key:
                raise InvalidConfigError("a rated seat maps to an empty harness key", agent_id=seat)
            rank = _rank_of(ranking, seat)
            if rank is None:
                continue
            current = best_rank.get(key)
            if current is None or rank < current:
                best_rank[key] = rank
        keys = tuple(sorted(best_rank))
        if len(keys) < _MIN_RATED_GROUPS:
            return ()
        groups = [(self._env.create_rating(mu=self.rating(key).mu, sigma=self.rating(key).sigma),) for key in keys]
        ranks = [best_rank[key] for key in keys]
        rated = self._env.rate(groups, ranks=ranks)
        updated: list[RatingRecord] = []
        for key, group in zip(keys, rated, strict=True):
            record = RatingRecord(
                harness_key=key,
                mu=float(group[0].mu),
                sigma=float(group[0].sigma),
                matches=self.rating(key).matches + 1,
            )
            self._records[key] = record
            updated.append(record)
        return tuple(updated)

    def rating(self, harness_key: str) -> RatingRecord:
        """Return the current rating of one harness.

        An unknown key returns the **prior** (``mu``, ``sigma``, ``matches=0``)
        rather than raising: in TrueSkill an unrated player is not an error, it is
        a player at the prior, and Swiss pairing (section 7.19) needs a standing
        for a harness entering the population at round one.

        Args:
            harness_key: The key produced by :func:`pxe.types.harness_key`.

        Returns:
            The stored record, or the prior when this harness never played.
        """
        stored = self._records.get(harness_key)
        if stored is not None:
            return stored
        return RatingRecord(harness_key=harness_key, mu=self._prior_mu, sigma=self._prior_sigma, matches=0)

    def leaderboard(self) -> tuple[RatingRecord, ...]:
        """Return every rated harness, best first.

        The order is ``(-mu, sigma, harness_key)``: strongest first, then the
        more certain of two equal means, then the key so the result never depends
        on insertion order.

        Returns:
            One record per harness that played at least one rated match.
        """
        return tuple(sorted(self._records.values(), key=lambda record: (-record.mu, record.sigma, record.harness_key)))


def _rank_of(ranking: Sequence[MatchRanking], agent_id: str) -> int | None:
    """Return the rank of one seat in a ranking, or ``None`` when it is absent.

    Args:
        ranking: The match ranking.
        agent_id: The seat to look for.

    Returns:
        The 1 based rank, or ``None``.
    """
    for row in ranking:
        if row.agent_id == agent_id:
            return row.rank
    return None


def bootstrap_ci(
    values: Sequence[float],
    *,
    n_resamples: int = 2000,
    alpha: float = 0.05,
    rng: random.Random,
) -> tuple[float, float]:
    """Return a percentile bootstrap confidence interval of the mean (PRD 7.3, T3.3).

    PRD section 7.3 requires every report to publish confidence intervals over
    the ``>= 3`` seeds a matchup is played on. The interval is the
    ``[alpha/2, 1 - alpha/2]`` percentile pair of the resampled means, taken by
    the nearest rank rule on the sorted resamples, which needs no interpolation
    and therefore no tie breaking convention.

    The resampling is fully determined by ``rng``: indices come from
    :func:`pxe.rng.randint`, which is built on ``getrandbits`` alone, so two
    machines given the same substream return the same bounds
    (``test_ratings.py::test_bootstrap_ci_is_seeded_and_stable``).

    Args:
        values: The observations, normally one per seed of a matchup. A single
            observation is legal and yields a degenerate interval.
        n_resamples: Number of bootstrap resamples.
        alpha: Total tail mass, so ``0.05`` gives a 95 % interval.
        rng: Generator from a registered substream, normally
            ``tournament_rng.fresh_substream("metrics.bootstrap")``.

    Returns:
        The ``(low, high)`` bounds of the interval, ``low <= high``.

    Raises:
        InvalidConfigError: If ``values`` is empty, ``n_resamples`` is below one,
            or ``alpha`` is outside ``(0, 1)``.
    """
    if not values:
        raise InvalidConfigError("bootstrap needs at least one observation", n=len(values))
    if n_resamples < 1:
        raise InvalidConfigError("n_resamples must be at least one", n_resamples=n_resamples)
    if not 0.0 < alpha < 1.0:
        raise InvalidConfigError("alpha must be in (0, 1)", alpha=alpha)
    sample = [float(value) for value in values]
    size = len(sample)
    means = [fmean(sample[randint(rng, 0, size - 1)] for _ in range(size)) for _ in range(n_resamples)]
    means.sort()
    low = means[_nearest_rank(n_resamples, alpha / 2.0)]
    high = means[_nearest_rank(n_resamples, 1.0 - alpha / 2.0)]
    return (low, high)


def _nearest_rank(count: int, quantile: float) -> int:
    """Return the 0 based index of a quantile under the nearest rank rule.

    Args:
        count: Number of sorted observations, at least one.
        quantile: Quantile in ``(0, 1)``.

    Returns:
        An index in ``0..count - 1``.
    """
    rank = int(quantile * count)
    if quantile * count > float(rank):
        rank += 1
    return min(count - 1, max(0, rank - 1))
