"""The ``microstructure`` sensor of CONTRACTS_V2 18.1 (package S1): quotes and prints.

It gates ``best_bid_bp``, ``best_ask_bp``, ``trades``, the two quote fields inside every ``Bar`` and the
``history`` research kind. Its inputs are the last completed bar's quotes and the prints of the completed
bars, so an unquoted tape reads the sentinel and never a fabricated spread.
"""

from __future__ import annotations

from pmx.sensors.catalogue import SensorBlock, SensorInputsLike, SensorSpec, block_of
from pmx.types import round_half_up


def sense(view: SensorInputsLike, *, now_ms: int, spec: SensorSpec) -> SensorBlock:
    """``microstructure``'s three features (18.1)."""
    del now_ms
    bars = view.bars
    quotes = view.quotes
    last_price_bp = bars[-1].close_bp if bars else None
    spread_bp: int | None = None
    mid_minus_last_bp: int | None = None
    if quotes is not None:
        best_bid_bp, best_ask_bp = quotes
        spread_bp = best_ask_bp - best_bid_bp
        if last_price_bp is not None:
            mid_minus_last_bp = round_half_up(best_bid_bp + best_ask_bp, 2) - last_price_bp
    prints_10b: int | None = None
    if bars:
        window_start_ms = bars[-10].t_ms if len(bars) >= 10 else bars[0].t_ms
        prints_10b = sum(1 for trade in view.trades if trade.t_ms >= window_start_ms)
    return block_of(spec, view.meta.id, [spread_bp, mid_minus_last_bp, prints_10b])
