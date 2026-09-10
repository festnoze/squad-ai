"""The ``wiki_asof`` sensor of CONTRACTS_V2 18.1 (package S1): point-in-time Wikipedia revisions.

It is the most expensive sensor of the catalogue at three units and it gates one thing: the ``wiki_asof``
research kind. A ``ResearchRequest`` of that kind from a diet that did not buy this sensor is
``action_rejected(bad_research)`` (18.1), and a granted request still pays
``RESEARCH_UNIT_COST["wiki_asof"]`` out of the run's research stock, because the two budgets price
different things: the sensor buys the right to ask, the research budget pays for the answer.

The block therefore reads ``SensorInputs.research["wiki_asof"]`` (12.11) and nothing else. Nothing
granted is a missing input, not a revision of zero tokens.
"""

from __future__ import annotations

from collections.abc import Sequence

from pmx.data.news.linker import load_stopwords, tokens_of
from pmx.sensors.catalogue import SensorBlock, SensorInputsLike, SensorSpec, block_of
from pmx.types import MS_PER_DAY, NewsView, milli_ratio

_KIND = "wiki_asof"


def granted_revisions(view: SensorInputsLike, *, now_ms: int) -> tuple[NewsView, ...]:
    """The granted ``wiki_asof`` payload, oldest first, filtered to what is visible at ``now_ms``.

    The payload is typed ``object`` in 12.11 because ``research`` is one map over three kinds, so it is
    narrowed here rather than trusted: a payload of any other shape is no revision at all.
    """
    payload = view.research.get(_KIND)
    if not isinstance(payload, Sequence) or isinstance(payload, str | bytes):
        return ()
    revisions = [item for item in payload if isinstance(item, NewsView) and item.published_at_ms <= now_ms]
    return tuple(sorted(revisions, key=lambda item: (item.published_at_ms, item.news_id)))


def sense(view: SensorInputsLike, *, now_ms: int, spec: SensorSpec) -> SensorBlock:
    """``wiki_asof``'s three features (18.1)."""
    revisions = granted_revisions(view, now_ms=now_ms)
    days_since: int | None = None
    if revisions:
        days_since = max(0, now_ms - revisions[-1].published_at_ms) // MS_PER_DAY
    text_delta_permille: int | None = None
    if len(revisions) >= 2:
        stopwords = load_stopwords()
        latest = tokens_of((revisions[-1].headline, revisions[-1].text), stopwords)
        previous = tokens_of((revisions[-2].headline, revisions[-2].text), stopwords)
        text_delta_permille = milli_ratio(len(latest - previous), len(latest)) if latest else None
    values: list[int | None] = [len(revisions), days_since, text_delta_permille]
    return block_of(spec, view.meta.id, values)
