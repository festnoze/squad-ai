"""The ``gdelt_recent`` sensor of CONTRACTS_V2 18.1 (package S1): GDELT DOC 2.0 articles.

It gates the ``news`` items of source ``gdelt``. The stamp is a ``seendate`` on a fifteen-minute grid and
the safety lag is fifteen minutes, which is why 18.3 admits the source to a minute dataset at exactly its
granularity ceiling and no finer.

``gdelt_domains_24b`` counts distinct **source domains**, read off the item's url by string, because a
domain is what makes two reports of one story two independent observations rather than one.
"""

from __future__ import annotations

from pmx.sensors.catalogue import SensorBlock, SensorInputsLike, SensorSpec, block_of
from pmx.types import MS_PER_MINUTE, NewsView

_SOURCE = "gdelt"


def domain_of(url: str) -> str:
    """The host of ``url``, lowercase, without a scheme, a port, a leading ``www.`` or a path.

    Pure string work: this module opens no socket and resolves no name (architecture rules 5 and 12).
    """
    rest = url.split("://", 1)[-1]
    host = rest.split("/", 1)[0].split("@")[-1].split(":", 1)[0].lower()
    return host[4:] if host.startswith("www.") else host


def _bar_start_ms(view: SensorInputsLike, span: int) -> int | None:
    bars = view.bars
    if not bars:
        return None
    return bars[-span].t_ms if len(bars) >= span else bars[0].t_ms


def _window(items: tuple[NewsView, ...], start_ms: int | None) -> tuple[NewsView, ...] | None:
    if start_ms is None:
        return None
    return tuple(item for item in items if item.published_at_ms >= start_ms)


def sense(view: SensorInputsLike, *, now_ms: int, spec: SensorSpec) -> SensorBlock:
    """``gdelt_recent``'s four features (18.1)."""
    items = view.news.get(_SOURCE, ())
    last_bar = _window(items, _bar_start_ms(view, 1))
    day = _window(items, _bar_start_ms(view, 24))
    minutes_since_article: int | None = None
    if items:
        minutes_since_article = max(0, now_ms - max(item.published_at_ms for item in items)) // MS_PER_MINUTE
    values: list[int | None] = [
        None if last_bar is None else len(last_bar),
        None if day is None else len(day),
        None if day is None else len({domain_of(item.url) for item in day if item.url}),
        minutes_since_article,
    ]
    return block_of(spec, view.meta.id, values)
