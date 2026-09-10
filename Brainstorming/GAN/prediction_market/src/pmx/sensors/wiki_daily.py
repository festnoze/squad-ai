"""The ``wiki_daily`` sensor of CONTRACTS_V2 18.1 (package S1): Wikipedia Current events and Wayback.

It gates the ``news`` items of sources ``wikipedia_current_events`` and ``wayback`` in both
``MarketView.news`` and ``Observation.news``, and the ``news`` research kind. It is the one news sensor
whose features are ``features.v1`` fields (indices 21 to 26), which is why a ``torch_policy`` genome must
buy it (ruling R299).

The three lexicon scores read D5's category word lists through the door D5 opened for exactly this
(``pmx.data.news.linker``: ``load_lexicon``, ``signed_hits_permille``, ``load_stopwords``, ``tokens_of``).
Writing a second lexicon reader here would let one build score a headline two ways, so this module reads
the shipped one and states its own aggregation:

* ``news_direction_milli_7d`` is the item balance, ``(for - against) / (for + against)`` in milli, where
  an item counts once whatever its number of hits; a window with no lexicon evidence at all is a missing
  input and reads ``0``, never a floor of minus one thousand (ruling R285);
* ``news_intensity_milli_7d`` is the share of the window's items carrying lexicon evidence;
* ``news_novelty_milli_7d`` is the share of the window's tokens absent from the previous seven days.
"""

from __future__ import annotations

from pmx.data.news.linker import load_lexicon, load_stopwords, signed_hits_permille, tokens_of
from pmx.sensors.catalogue import SensorBlock, SensorInputsLike, SensorSpec, block_of
from pmx.types import MS_PER_DAY, NewsView, milli_ratio

_SOURCES = ("wayback", "wikipedia_current_events")


def _visible(view: SensorInputsLike) -> tuple[NewsView, ...]:
    items: list[NewsView] = []
    for source in _SOURCES:
        items.extend(view.news.get(source, ()))
    return tuple(sorted(items, key=lambda item: (item.published_at_ms, item.news_id)))


def _window(items: tuple[NewsView, ...], *, start_ms: int, end_ms: int) -> tuple[NewsView, ...]:
    return tuple(item for item in items if start_ms < item.published_at_ms <= end_ms)


def sense(view: SensorInputsLike, *, now_ms: int, spec: SensorSpec) -> SensorBlock:
    """``wiki_daily``'s six features (18.1)."""
    items = _visible(view)
    day = _window(items, start_ms=now_ms - MS_PER_DAY, end_ms=now_ms)
    week = _window(items, start_ms=now_ms - 7 * MS_PER_DAY, end_ms=now_ms)
    previous_week = _window(items, start_ms=now_ms - 14 * MS_PER_DAY, end_ms=now_ms - 7 * MS_PER_DAY)

    lexicon = load_lexicon(view.meta.category)
    signed = [signed_hits_permille(lexicon, (item.headline, item.text)) for item in week]
    n_for = sum(1 for value in signed if value > 0)
    n_against = sum(1 for value in signed if value < 0)
    direction_milli = milli_ratio(n_for - n_against, n_for + n_against) if n_for + n_against else None
    intensity_milli = milli_ratio(n_for + n_against, len(week)) if week else None

    stopwords = load_stopwords()
    week_tokens = tokens_of([text for item in week for text in (item.headline, item.text)], stopwords)
    previous_tokens = tokens_of(
        [text for item in previous_week for text in (item.headline, item.text)], stopwords
    )
    novelty_milli = milli_ratio(len(week_tokens - previous_tokens), len(week_tokens)) if week_tokens else None

    values: list[int | None] = [
        len(day),
        len(week),
        direction_milli,
        intensity_milli,
        novelty_milli,
        max((item.match_score_permille for item in items), default=None),
    ]
    return block_of(spec, view.meta.id, values)
