"""The ``memory`` sensor of CONTRACTS_V2 18.1 (package S1): the agent's own record of itself.

It costs nothing and gates ``Observation.memory``. It is per market (ruling R286): the observation-level
counts are repeated in every market's block, which is what a rule evaluated per ``(market, bar)`` needs,
and the one per-market value is the agent's own history on the market in front of it.

``memory_category_hits_permille`` reads the reliability bins of 8.3: a bin at or above the fifth of ten
states a probability above one half, so its hits are its ``n_yes`` and the hits of a lower bin are its
misses' complement. ``pmx.metrics.calibration`` owns the ratio a scorer computes (12.2); this is a count
of sides, not a calibration statistic, and it is integer permille.

``memory_market_forecasts`` reads the agent's own notes on this market, which is the one per-market record
``MemoryView`` (8.3) carries: it has no forecast log. The substitution is reported as a contract issue.
"""

from __future__ import annotations

from pmx.sensors.catalogue import SensorBlock, SensorInputsLike, SensorSpec, block_of
from pmx.types import CALIBRATION_BINS, MemoryView, milli_ratio

#: The first bin whose stated probability is above one half, on the ten-bin grid of 12.2.
_MIDPOINT_BIN = CALIBRATION_BINS // 2


def category_hits(memory: MemoryView, category: str) -> tuple[int, int]:
    """``(hits, resolved)`` over the agent's own bins in ``category``: the forecasts that were on the
    right side of ``500_000`` ppm, and how many there were."""
    hits = 0
    resolved = 0
    for entry in memory.calibration:
        if entry.category != category:
            continue
        resolved += entry.n
        hits += entry.n_yes if entry.bin >= _MIDPOINT_BIN else entry.n - entry.n_yes
    return hits, resolved


def sense(view: SensorInputsLike, *, now_ms: int, spec: SensorSpec) -> SensorBlock:
    """``memory``'s four features (18.1)."""
    del now_ms
    memory = view.memory
    if memory is None:
        return block_of(spec, view.meta.id, [None] * len(spec.features))
    hits, resolved = category_hits(memory, view.meta.category)
    values: list[int | None] = [
        sum(entry.n for entry in memory.calibration),
        resolved,
        milli_ratio(hits, resolved) if resolved else None,
        sum(1 for note in memory.notes if note.market_id == view.meta.id),
    ]
    return block_of(spec, view.meta.id, values)
