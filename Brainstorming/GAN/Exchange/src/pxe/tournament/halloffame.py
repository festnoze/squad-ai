"""The two Halls of Fame: frozen harness versions and worst (scenario, seed) pairs.

PRD section 8 names two of them and they are two different things:

* **Hall of Fame** - "versions de harness gelees (config + prompt hashes),
  reinjectees comme adversaires". A frozen member is a whole
  :class:`~pxe.types.HarnessConfig`, identified by its
  :func:`pxe.types.harness_key`, whose ``config_hash`` already covers the system
  prompt and every parameter (section 2.2, decision 24). Freezing therefore
  stores enough to replay the version identically, which is the whole point of
  T3.4: re-injecting a champion as an adversary is only meaningful if the
  adversary is *the same* champion.
* **Failure Hall of Fame** - "couples (scenario, seed) ou le champion courant
  sous-performe le plus; rejoues a chaque iteration". A member is a
  ``(template_id, seed)`` pair plus the deficit that earned it its place, kept
  per harness key so one weak harness cannot evict another's failures.

Both are bounded and both are pure: no clock, no file, no store. Persistence of
a frozen version is :meth:`pxe.store.db.Store.save_harness_version` (section
7.20 names ``HallOfFame.freeze`` as one of its two call sites); the failure list
is consumed by ``pxe.evolve.failures.collect_failures`` (section 7.23).
"""

from __future__ import annotations

from pxe.errors import InvalidConfigError
from pxe.types import SEED_SPACE, HarnessConfig, RatingRecord, harness_key

__all__ = ["HallOfFame", "FailureHallOfFame"]


class HallOfFame:
    """A bounded set of frozen harness versions, best ``mu`` first (T3.4).

    Capacity is enforced on insertion: once full, a new member displaces the
    weakest one, and an offer weaker than every member is dropped. The rating is
    kept beside the config because it is the only ordering the PRD gives, and
    because a report showing the Hall of Fame shows both.
    """

    __slots__ = ("_capacity", "_members")

    def __init__(self, *, capacity: int = 16) -> None:
        """Build an empty Hall of Fame.

        Args:
            capacity: Maximum number of frozen versions kept.

        Raises:
            InvalidConfigError: If ``capacity`` is below one.
        """
        if capacity < 1:
            raise InvalidConfigError("a Hall of Fame holds at least one member", capacity=capacity)
        self._capacity = int(capacity)
        self._members: dict[str, tuple[HarnessConfig, RatingRecord]] = {}

    def freeze(self, harness: HarnessConfig, rating: RatingRecord) -> str:
        """Freeze one harness version and return its key.

        Re-freezing a key that is already a member refreshes its rating and keeps
        one slot: a version is frozen once, whatever its rating does afterwards.

        Args:
            harness: The version to freeze. Its ``config_hash`` is already filled
                by ``HarnessConfig.__post_init__``, so the member carries the
                "config + prompt hashed" identity T3.4 asks for.
            rating: The rating of **that** version. It is the ordering key of
                :meth:`members` and of the eviction rule.

        Returns:
            The harness key, ``<harness_id>@<version>+<config_hash[:8]>``.

        Raises:
            InvalidConfigError: If ``rating.harness_key`` is neither empty nor
                equal to the key of ``harness``. A rating that belongs to another
                version would silently order the Hall of Fame by the wrong
                number, and the two arguments are only ever built together.
        """
        key = harness_key(harness)
        if rating.harness_key and rating.harness_key != key:
            raise InvalidConfigError(
                "the rating does not belong to this harness version",
                harness_key=key,
                rating_key=rating.harness_key,
            )
        stamped = RatingRecord(
            harness_key=key,
            mu=float(rating.mu),
            sigma=float(rating.sigma),
            matches=int(rating.matches),
        )
        self._members[key] = (harness, stamped)
        if len(self._members) > self._capacity:
            weakest = sorted(self._members.values(), key=_member_order)[-1][1].harness_key
            del self._members[weakest]
        return key

    def members(self) -> tuple[HarnessConfig, ...]:
        """Return the frozen versions, best ``mu`` first.

        The order is ``(-mu, sigma, harness_key)``, the same one
        :meth:`pxe.tournament.ratings.RatingService.leaderboard` uses, so a
        report can put the two side by side.

        Returns:
            The frozen configs, exactly as they were handed to :meth:`freeze`.
        """
        return tuple(config for config, _rating in sorted(self._members.values(), key=_member_order))


def _member_order(member: tuple[HarnessConfig, RatingRecord]) -> tuple[float, float, str]:
    """Return the sort key of one Hall of Fame member: best ``mu`` first.

    Args:
        member: A ``(config, rating)`` pair.

    Returns:
        ``(-mu, sigma, harness_key)``.
    """
    _config, rating = member
    return (-rating.mu, rating.sigma, rating.harness_key)


class FailureHallOfFame:
    """The worst ``(template_id, seed)`` pairs of each harness (T5.3).

    A pair is recorded with a **deficit in cents**: how far the harness fell
    short of whatever the caller compares it against (the field, its parent, its
    own average). Larger is worse. Recording the same pair twice keeps the worst
    of the two observations, so replaying a known failure cannot dilute it.

    The capacity is per harness key. A global cap would let one collapsing
    harness evict every other harness's failures, and the list exists precisely
    to be replayed per harness at the next iteration.
    """

    __slots__ = ("_capacity", "_deficits")

    def __init__(self, *, capacity: int = 32) -> None:
        """Build an empty failure archive.

        Args:
            capacity: Maximum number of pairs kept per harness key.

        Raises:
            InvalidConfigError: If ``capacity`` is below one.
        """
        if capacity < 1:
            raise InvalidConfigError("a failure Hall of Fame holds at least one pair", capacity=capacity)
        self._capacity = int(capacity)
        self._deficits: dict[str, dict[tuple[str, int], int]] = {}

    def record(self, *, template_id: str, seed: int, harness_key: str, deficit_cents: int) -> None:
        """Record one under-performance of one harness on one scenario instance.

        Args:
            template_id: Scenario template of the match, for example
                ``"election"``.
            seed: Root seed of the match, which together with the template is
                everything needed to replay it (section 3.1).
            harness_key: The harness that under-performed.
            deficit_cents: How much it fell short, in cents. Larger is worse.

        Raises:
            InvalidConfigError: If ``template_id`` or ``harness_key`` is empty,
                or if ``seed`` does not fit in 63 unsigned bits.
        """
        if not template_id:
            raise InvalidConfigError("a failure needs a template id", harness_key=harness_key)
        if not harness_key:
            raise InvalidConfigError("a failure needs a harness key", template_id=template_id)
        if not 0 <= seed < SEED_SPACE:
            raise InvalidConfigError("seed must fit in 63 unsigned bits", seed=seed)
        pairs = self._deficits.setdefault(harness_key, {})
        pair = (template_id, int(seed))
        previous = pairs.get(pair)
        pairs[pair] = int(deficit_cents) if previous is None else max(previous, int(deficit_cents))
        if len(pairs) > self._capacity:
            kept = sorted(pairs.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))[: self._capacity]
            self._deficits[harness_key] = dict(kept)

    def worst(self, harness_key: str, *, limit: int = 10) -> tuple[tuple[str, int], ...]:
        """Return the worst scenario instances of one harness.

        Args:
            harness_key: The harness to look up. An unknown key returns an empty
                tuple: a harness with no recorded failure is not an error.
            limit: Maximum number of pairs returned.

        Returns:
            ``(template_id, seed)`` pairs ordered by decreasing deficit, then by
            template id and seed so the order is total.

        Raises:
            InvalidConfigError: If ``limit`` is negative.
        """
        if limit < 0:
            raise InvalidConfigError("limit must be non negative", limit=limit)
        pairs = self._deficits.get(harness_key)
        if not pairs:
            return ()
        ordered = sorted(pairs.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
        return tuple(pair for pair, _deficit in ordered[:limit])
