"""The ``calendar`` sensor of CONTRACTS_V2 18.1 (package S1): the venue's published schedule.

It costs nothing and gates ``close_at_ms``, ``session_calendar_id`` and ``hours_to_next_bar``. A published
schedule is not a datum about the future (7.9), which is why a free sensor may carry it.

``hours_to_next_bar`` and ``session_close_within_1b`` have no input in ``SensorInputs`` (12.11): the
declaration carries a ``MarketMeta``, which holds no ``session_calendar_id`` and no calendar, and the
completed bars do not say when the next session opens. Both therefore read their sentinel, ``0``, which
is what a continuous calendar answers anyway, and the gap is reported as a contract issue.
"""

from __future__ import annotations

from pmx.sensors.catalogue import SensorBlock, SensorInputsLike, SensorSpec, block_of, ln1p_milli
from pmx.types import MS_PER_DAY, MS_PER_HOUR, interval_ms

#: 1970-01-01 was a Thursday, and ``day_of_week`` counts Monday as ``0`` (18.1's table).
_EPOCH_DAY_OF_WEEK = 3


def sense(view: SensorInputsLike, *, now_ms: int, spec: SensorSpec) -> SensorBlock:
    """``calendar``'s seven features (18.1)."""
    meta = view.meta
    bar_ms = interval_ms(meta.interval_min)
    close_at_ms = meta.close_at_ms if meta.close_time_verified else 0
    bars_to_close: int | None = None
    ms_to_close_log_milli: int | None = None
    if close_at_ms > 0:
        remaining_ms = max(0, close_at_ms - now_ms)
        bars_to_close = remaining_ms // bar_ms
        ms_to_close_log_milli = ln1p_milli(remaining_ms)
    bars_since_listed: int | None = None
    if meta.created_at_ms > 0 and now_ms >= meta.created_at_ms:
        bars_since_listed = (now_ms - meta.created_at_ms) // bar_ms
    values: list[int | None] = [
        bars_to_close,
        ms_to_close_log_milli,
        bars_since_listed,
        (now_ms // MS_PER_DAY + _EPOCH_DAY_OF_WEEK) % 7,
        (now_ms % MS_PER_DAY) // MS_PER_HOUR,
        None,
        None,
    ]
    return block_of(spec, meta.id, values)
