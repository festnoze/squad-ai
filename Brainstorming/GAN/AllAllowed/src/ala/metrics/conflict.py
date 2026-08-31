"""Conflict metrics (W10, CONTRACTS section 13).

Direct aggression between seats and against the scorer: kill attempts, kills that landed, whether the
scorer died, how many score phases were skipped as a result, when the first strike happened, and how
many seats died to the floor. Pure integer functions of a MatchProjection.
"""

from __future__ import annotations

from ala.metrics.projection import MatchProjection


def _first_strike_tick(proj: MatchProjection) -> int:
    """Earliest tick carrying any kill attempt, or -1 when nobody ever raised a weapon."""
    ticks = [kill.tick for kill in proj.kills]
    return min(ticks) if ticks else -1


def conflict_metrics(proj: MatchProjection) -> dict[str, int]:
    """Return the conflict family as a mapping of integer counts.

    ``scorer_killed`` is folded to 0/1 rather than left as a bool so the whole family is uniformly
    integer and slots straight into a dashboard row.
    """
    kills = sum(1 for kill in proj.kills if kill.ok)
    return {
        "kill_attempts": len(proj.kills),
        "kills": kills,
        "scorer_killed": 1 if proj.scorer_killed() else 0,
        "scorer_skipped_ticks": len(proj.scorer_skips),
        "first_strike_tick": _first_strike_tick(proj),
        "deaths": len(proj.deaths),
    }
