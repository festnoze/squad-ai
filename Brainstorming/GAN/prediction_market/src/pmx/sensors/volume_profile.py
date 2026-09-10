"""The ``volume_profile`` sensor of CONTRACTS_V2 18.1 (package S1): traded size, open interest and the
applied cash events of 17.3 (ruling R233 puts ``cash_events`` behind this sensor).

Every level is reported as ``ln(1 + x)`` in milli-nats through ``pmx.sensors.catalogue.ln1p_milli``,
because a volume spans nine orders of magnitude across the venues of section 2 and a rule threshold on
the raw count would mean a different thing on each of them.
"""

from __future__ import annotations

from math import isqrt

from pmx.sensors.catalogue import SensorBlock, SensorInputsLike, SensorSpec, block_of, ln1p_milli
from pmx.types import Bar, milli_ratio, round_half_up


def _volume_z_milli(bars: tuple[Bar, ...], span: int) -> int | None:
    """The last bar's volume as a z score over the last ``span`` completed bars, in milli.

    ``None`` before two bars and on a flat window: a z score with no dispersion is not zero standard
    deviations, it is undefined, and the sentinel is what says so.
    """
    window = bars[-span:]
    if len(window) < 2:
        return None
    volumes = [bar.volume_milli for bar in window]
    mean = round_half_up(sum(volumes), len(volumes))
    variance = sum((volume - mean) ** 2 for volume in volumes) // len(volumes)
    deviation = isqrt(variance)
    if deviation == 0:
        return None
    return milli_ratio(volumes[-1] - mean, deviation)


def sense(view: SensorInputsLike, *, now_ms: int, spec: SensorSpec) -> SensorBlock:
    """``volume_profile``'s six features (18.1).

    ``*_to_date`` reads the completed bars the run's ``bars_window`` carries, which is the widest history
    ``SensorInputs`` declares (12.11): the sensor never reaches past the window the observation was built
    from, so a wider window is a larger number and never a leak.
    """
    del now_ms
    bars = view.bars
    last = bars[-1] if bars else None
    cash_events_30b: int | None = None
    if bars:
        window_start_ms = bars[-30].t_ms if len(bars) >= 30 else bars[0].t_ms
        cash_events_30b = sum(1 for event in view.cash_events if event.applied_at_ms >= window_start_ms)
    values: list[int | None] = [
        ln1p_milli(last.volume_milli) if last is not None else None,
        _volume_z_milli(bars, 30),
        ln1p_milli(sum(bar.volume_milli for bar in bars)) if bars else None,
        ln1p_milli(sum(bar.n_trades for bar in bars)) if bars else None,
        ln1p_milli(last.open_interest) if last is not None and last.open_interest is not None else None,
        cash_events_30b,
    ]
    return block_of(spec, view.meta.id, values)
