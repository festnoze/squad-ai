"""The ``tape`` sensor of CONTRACTS_V2 18.1 (package S1): the always-on price view.

``tape`` costs nothing and is in every diet by law (18.1: a genome that omits it is refused with
``InvalidConfigError``), because a view without a price is not a view an agent can decide on. It gates
the six price and time fields of every ``Bar``, ``first_price_bp`` and ``last_price_bp``, and it carries
the two ``category`` fields of ``features.v1`` (indices 19 and 20): a market's provider and category are
metadata known before its first bar, so they cost nothing to know.
"""

from __future__ import annotations

from pmx.scoring import logit_milli
from pmx.sensors.catalogue import SensorBlock, SensorInputsLike, SensorSpec, block_of
from pmx.types import (
    CATEGORIES,
    PROVIDERS,
    Bar,
    clamp_price_bp,
    ppm_from_bp,
    round_half_up,
)


def _return_bp(bars: tuple[Bar, ...], span: int) -> int | None:
    """The close-to-close price change over the last ``span`` completed bars, ``None`` before there are
    ``span + 1`` of them (a return no bar measured is a missing input, not a zero return)."""
    if len(bars) <= span:
        return None
    return bars[-1].close_bp - bars[-1 - span].close_bp


def _realised_vol_bp(bars: tuple[Bar, ...], span: int) -> int | None:
    """The mean absolute bar return over the last ``span`` completed bars."""
    window = bars[-(span + 1) :]
    if len(window) < 2:
        return None
    total = sum(abs(window[i].close_bp - window[i - 1].close_bp) for i in range(1, len(window)))
    return round_half_up(total, len(window) - 1)


def sense(view: SensorInputsLike, *, now_ms: int, spec: SensorSpec) -> SensorBlock:
    """``tape``'s eleven features (18.1). ``now_ms`` is unused: every value is a fact of the completed
    bars, whose as-of filtering the caller has already applied (5.4)."""
    del now_ms
    bars = view.bars
    last_price_bp = bars[-1].close_bp if bars else None
    window = bars[-30:]
    values: list[int | None] = [
        last_price_bp,
        logit_milli(ppm_from_bp(clamp_price_bp(last_price_bp))) if last_price_bp is not None else None,
        _return_bp(bars, 1),
        _return_bp(bars, 7),
        _return_bp(bars, 30),
        _return_bp(bars, 90),
        _realised_vol_bp(bars, 30),
        # The two distances are unsigned by their bounds (``lo = 0``), which is what the names say: the
        # distance from the extreme, not the signed difference the descriptions spell.
        max(bar.close_bp for bar in window) - last_price_bp if window and last_price_bp is not None else None,
        last_price_bp - min(bar.close_bp for bar in window) if window and last_price_bp is not None else None,
        PROVIDERS.index(view.meta.provider) if view.meta.provider in PROVIDERS else None,
        CATEGORIES.index(view.meta.category) if view.meta.category in CATEGORIES else None,
    ]
    return block_of(spec, view.meta.id, values)
