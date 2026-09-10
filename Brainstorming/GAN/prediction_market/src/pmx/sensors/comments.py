"""The ``comments`` sensor of CONTRACTS_V2 18.1 (package S1): Manifold comments.

It gates the ``news`` items of source ``manifold_comment`` and nothing else: a diet without it never sees
a comment, in ``MarketView.news`` or in ``Observation.news`` (ruling R233's source filter).

``commenter_count_24b`` has no input: ``NewsItem.author_key`` (7.3) is not a field of ``NewsView`` (8.3),
so the number of distinct commenters cannot be measured from ``SensorInputs.news``. It reads its
sentinel, ``0``, and the gap is reported as a contract issue rather than approximated by a count of urls,
which on Manifold is one per comment and would silently equal ``comment_count_24b``.
"""

from __future__ import annotations

from pmx.sensors.catalogue import SensorBlock, SensorInputsLike, SensorSpec, block_of
from pmx.types import MS_PER_MINUTE, NewsView

_SOURCE = "manifold_comment"


def _bar_start_ms(view: SensorInputsLike, span: int) -> int | None:
    """The open of the bar ``span`` completed bars back, or of the oldest bar the window carries."""
    bars = view.bars
    if not bars:
        return None
    return bars[-span].t_ms if len(bars) >= span else bars[0].t_ms


def _since(items: tuple[NewsView, ...], start_ms: int | None) -> int | None:
    if start_ms is None:
        return None
    return sum(1 for item in items if item.published_at_ms >= start_ms)


def _minutes_since_latest(items: tuple[NewsView, ...], now_ms: int) -> int | None:
    if not items:
        return None
    return max(0, now_ms - max(item.published_at_ms for item in items)) // MS_PER_MINUTE


def sense(view: SensorInputsLike, *, now_ms: int, spec: SensorSpec) -> SensorBlock:
    """``comments``'s four features (18.1)."""
    items = view.news.get(_SOURCE, ())
    values: list[int | None] = [
        _since(items, _bar_start_ms(view, 1)),
        _since(items, _bar_start_ms(view, 24)),
        None,
        _minutes_since_latest(items, now_ms),
    ]
    return block_of(spec, view.meta.id, values)
