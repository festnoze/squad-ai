"""A narrow, causal bridge into the existing symbolic miner's RowTable.

Only the existing tape sensor is enabled. Archive expiry metadata is not presumed to have
been known historically. Fitting sees resolved training groups and completed tradable bars
strictly before the fit cutoff. Execution uses exactly the same tape sensor and history cap.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import cast

from pmx.rules.tester import BarRow, MarketRows, RowTable
from pmx.sensors.catalogue import SENSORS, SensorBlock, SensorInputsLike
from pmx.sensors.tape import sense
from pmx.types import Bar, Dataset, Market, MarketMeta, MarketView, interval_ms

FEATURE_VERSION = "discovery-tape.v1"
FEATURES = (
    "last_price_bp", "ret_1b_bp", "ret_7b_bp", "realised_vol_bp_30b",
    "dist_from_high_bp_30b", "dist_from_low_bp_30b",
)
HISTORY_BARS = 31
MAX_FIT_ROWS_PER_MARKET = 256


@dataclass(frozen=True, slots=True)
class TapeMeta:
    """The tape sensor reads these three public fields, never a resolution."""

    id: str
    provider: str
    category: str


def tape_blocks(
    bars: Sequence[Bar], *, market_id: str, provider: str, category: str, now_ms: int, interval: int
) -> Mapping[str, SensorBlock]:
    completed = tuple(bar for bar in bars if bar.t_ms + interval <= now_ms)[-HISTORY_BARS:]
    # tape.sense's deliberately narrow input only reads meta.id/provider/category and bars.
    inputs = SimpleNamespace(meta=TapeMeta(market_id, provider, category), bars=completed)
    return {"tape": sense(cast(SensorInputsLike, inputs), now_ms=now_ms, spec=SENSORS["tape"])}


def blocks_for_view(view: MarketView, *, now_ms: int, interval: int) -> Mapping[str, SensorBlock]:
    return tape_blocks(
        view.bars, market_id=view.market_id, provider=view.provider, category=view.category,
        now_ms=now_ms, interval=interval,
    )


def training_table(
    dataset: Dataset, metas: Sequence[MarketMeta], *, provider: str, fit_t1_ms: int
) -> RowTable:
    """No validation/sealed market loader is called, including when a group spans the cutoff."""
    span = interval_ms(dataset.manifest.interval_min)
    group_ready: dict[str, int] = {}
    for meta in dataset.metas:
        if meta.provider == provider and meta.kind == "binary" and meta.fold != "sealed":
            key = meta.event_key or meta.id
            group_ready[key] = max(group_ready.get(key, 0), meta.resolved_at_ms)
    markets = []
    for meta in sorted(metas, key=lambda item: item.id):
        if (
            meta.fold != "train" or meta.provider != provider or meta.kind != "binary"
            or group_ready[meta.event_key or meta.id] >= fit_t1_ms
        ):
            continue
        market = dataset.market(meta.id)
        if not isinstance(market, Market):
            raise ValueError("Discovery supports binary markets only")
        eligible = [
            index for index, bar in enumerate(market.bars)
            if bar.volume_milli > 0 and bar.t_ms + span < fit_t1_ms and bar.t_ms + 3 * span <= meta.close_at_ms
        ]
        if len(eligible) > MAX_FIT_ROWS_PER_MARKET:
            eligible = [
                eligible[index * (len(eligible) - 1) // (MAX_FIT_ROWS_PER_MARKET - 1)]
                for index in range(MAX_FIT_ROWS_PER_MARKET)
            ]
        rows = []
        for index in eligible:
            bar = market.bars[index]
            now = bar.t_ms + span
            rows.append(BarRow(
                t_ms=bar.t_ms, close_bp=bar.close_bp,
                blocks=tape_blocks(
                    market.bars[max(0, index + 1 - HISTORY_BARS):index + 1],
                    market_id=meta.id, provider=meta.provider, category=meta.category,
                    now_ms=now, interval=span,
                ),
            ))
        if rows:
            markets.append(MarketRows(
                meta=meta, bars=tuple(rows), block=meta.event_key or meta.id,
                fold_key_ms=group_ready[meta.event_key or meta.id],
            ))
    return RowTable(
        dataset_hash=dataset.manifest.dataset_hash, interval_min=dataset.manifest.interval_min,
        split=dataset.manifest.split, markets=tuple(markets), purpose=dataset.purpose,
    )
