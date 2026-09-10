"""The ``hn`` sensor of CONTRACTS_V2 18.1 (package S1): Hacker News through Algolia.

18.3 fixes the wire format this sensor reads: a story is a ``NewsItem`` whose ``text`` carries
``points=<n> comments=<n>`` on its **first line**, so the two integers are parsed here and nowhere else.
An item whose first line does not carry the pair is a comment or a malformed story and contributes no
points, which is a missing input and not a story worth zero points.

``hn_mentions_subject`` is 18.1's "a visible linked story names one of the market's ``wiki_subjects``
through the linker". ``MarketMeta`` carries no ``subject`` on this tree (7.14's four facets are DS1's and
DS2's, 18.8), so the test applied here is the linker's own verdict, which is the datum ``NewsView``
carries: an item whose ``match_score_permille`` reaches ``LINK_THRESHOLD_PERMILLE`` was linked to this
market by the subject match of 7.6. It is reported as an agreement so the facet can replace it.
"""

from __future__ import annotations

import re

from pmx.sensors.catalogue import SensorBlock, SensorInputsLike, SensorSpec, block_of
from pmx.types import LINK_THRESHOLD_PERMILLE, MS_PER_DAY, MS_PER_MINUTE, NewsView

_SOURCE = "hn"
_STORY_KIND = "story"
#: 18.3's first line, verbatim: ``points=<n> comments=<n>``.
RE_HN_COUNTS = re.compile(r"^points=([0-9]{1,9}) comments=([0-9]{1,9})$")


def _counts_of(item: NewsView) -> tuple[int, int] | None:
    """``(points, comments)`` off the item's first line, ``None`` when it does not carry the pair."""
    first_line = item.text.split("\n", 1)[0].strip()
    match = RE_HN_COUNTS.match(first_line)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def sense(view: SensorInputsLike, *, now_ms: int, spec: SensorSpec) -> SensorBlock:
    """``hn``'s five features (18.1). The window is 1440 minutes, which is one day whatever the grid."""
    items = view.news.get(_SOURCE, ())
    window_start_ms = now_ms - MS_PER_DAY
    stories = tuple(
        item for item in items if item.kind == _STORY_KIND and item.published_at_ms > window_start_ms
    )
    ranked = sorted(
        ((counts, item) for item in stories if (counts := _counts_of(item)) is not None),
        key=lambda pair: (-pair[0][0], pair[1].news_id),
    )
    top_points: int | None = None
    top_comments: int | None = None
    if ranked:
        top_points, top_comments = ranked[0][0]
    minutes_since_story: int | None = None
    if stories:
        minutes_since_story = max(0, now_ms - max(item.published_at_ms for item in stories)) // MS_PER_MINUTE
    values: list[int | None] = [
        top_points,
        top_comments,
        1 if any(item.match_score_permille >= LINK_THRESHOLD_PERMILLE for item in stories) else 0,
        minutes_since_story,
        len(stories),
    ]
    return block_of(spec, view.meta.id, values)
