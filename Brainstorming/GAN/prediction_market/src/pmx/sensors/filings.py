"""The ``filings`` sensor of CONTRACTS_V2 18.1 (package S1): SEC EDGAR acceptance times.

It gates the ``news`` items of source ``edgar``. The stamp is the filing's acceptance time to the second
and the safety lag is one minute, so a filing is visible one minute after the registrant filed it and
never at the instant the wire carried it.

A current report is recognised by its form, which EDGAR puts in the item's ``section`` and, when the
section is absent, at the head of the headline. The match is case insensitive and exact on the form
string, so a "10-K" that merely mentions an 8-K in its text is not counted as one.
"""

from __future__ import annotations

from pmx.sensors.catalogue import SensorBlock, SensorInputsLike, SensorSpec, block_of
from pmx.types import MS_PER_MINUTE, NewsView

_SOURCE = "edgar"
_CURRENT_REPORT_FORM = "8-k"


def _is_current_report(item: NewsView) -> bool:
    if item.section is not None:
        return item.section.strip().lower() == _CURRENT_REPORT_FORM
    return item.headline.strip().lower().startswith(_CURRENT_REPORT_FORM)


def sense(view: SensorInputsLike, *, now_ms: int, spec: SensorSpec) -> SensorBlock:
    """``filings``'s three features (18.1)."""
    items = view.news.get(_SOURCE, ())
    bars = view.bars
    window: tuple[NewsView, ...] | None = None
    if bars:
        start_ms = bars[-30].t_ms if len(bars) >= 30 else bars[0].t_ms
        window = tuple(item for item in items if item.published_at_ms >= start_ms)
    minutes_since_filing: int | None = None
    if items:
        minutes_since_filing = max(0, now_ms - max(item.published_at_ms for item in items)) // MS_PER_MINUTE
    values: list[int | None] = [
        None if window is None else len(window),
        None if window is None else sum(1 for item in window if _is_current_report(item)),
        minutes_since_filing,
    ]
    return block_of(spec, view.meta.id, values)
