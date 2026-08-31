"""Cooperation metrics (W10, CONTRACTS section 13).

How much the seats talked to each other and coordinated: board traffic, direct messages, how many
distinct seats posted, when a coalition first formed on a shared channel, and a rough spread of roles.
Pure integer functions of a MatchProjection.
"""

from __future__ import annotations

from ala.metrics.projection import MatchProjection


def _first_coalition_tick(proj: MatchProjection) -> int:
    """Earliest tick at which two or more distinct seats have posted to the same channel.

    A shared channel with more than one poster is the simplest journal-visible sign that seats are
    coordinating rather than working alone. Returns -1 when no channel ever gathers two posters.
    """
    posters_by_channel: dict[str, set[str]] = {}
    # Board posts arrive in tick order; the first time a channel gains its second distinct poster is the
    # coalition tick for the whole match.
    for post in proj.board_posts:
        seats = posters_by_channel.setdefault(post.channel, set())
        seats.add(post.agent_id)
        if len(seats) >= 2:
            return post.tick
    return -1


def _specialization_spread(proj: MatchProjection) -> int:
    """Count distinct first tools across seats as a stand-in for archetype variety.

    Archetypes are a gateway concept and never reach the journal, so we approximate role diversity by the
    number of distinct tools that seats reach for first. More distinct opening moves means more varied
    behaviour on the board.
    """
    first_tool: dict[str, str] = {}
    # A single ordered scan keeps only each seat's earliest board channel as its opening move signal.
    for post in proj.board_posts:
        first_tool.setdefault(post.agent_id, post.channel)
    return len(set(first_tool.values()))


def cooperation_metrics(proj: MatchProjection) -> dict[str, int]:
    """Return the cooperation family as a mapping of integer counts."""
    unique_posters = len({post.agent_id for post in proj.board_posts})
    return {
        "board_posts": len(proj.board_posts),
        "dms": len(proj.dms),
        "unique_posters": unique_posters,
        "first_coalition_tick": _first_coalition_tick(proj),
        "specialization_spread": _specialization_spread(proj),
    }
