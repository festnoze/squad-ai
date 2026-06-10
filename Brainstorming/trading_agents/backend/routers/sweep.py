"""Parameter sweep endpoint — vectorized MA crossover optimization."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import vectorbt as vbt  # type: ignore[import-untyped]
from fastapi import APIRouter, HTTPException

# Ensure project root is importable
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.data.provider import load_price_data, INTERVAL_TO_FREQ  # noqa: E402
from backend.schemas import (  # noqa: E402
    SweepRequest,
    SweepResponse,
    SweepBest,
    SweepStats,
)

router = APIRouter()


@router.post("/run", response_model=SweepResponse)
async def run_sweep(req: SweepRequest):
    """Run a vectorized MA crossover parameter sweep.

    Sweeps all fast/slow MA window combinations and returns
    a Sharpe ratio matrix with summary statistics.
    """
    try:
        # Validate range params (must be [min, max, step])
        if len(req.fast_range) != 3 or len(req.slow_range) != 3:
            raise ValueError(
                "fast_range and slow_range must each have exactly 3 elements: [min, max, step]"
            )

        fast_min, fast_max, fast_step = req.fast_range
        slow_min, slow_max, slow_step = req.slow_range

        fast_values = np.arange(int(fast_min), int(fast_max), int(fast_step))
        slow_values = np.arange(int(slow_min), int(slow_max), int(slow_step))

        if len(fast_values) == 0 or len(slow_values) == 0:
            raise ValueError("fast_range or slow_range produced no values")

        if len(fast_values) * len(slow_values) > 10_000:
            raise ValueError(
                f"Sweep grid too large: {len(fast_values)} x {len(slow_values)} = "
                f"{len(fast_values) * len(slow_values)}. Max 10,000 combinations."
            )

        df = load_price_data(req.symbol, interval=req.interval, start=req.start, end=req.end)
        price = df["Close"]
        freq = INTERVAL_TO_FREQ[req.interval]

        # Compute ALL MAs at once (vectorized)
        all_windows = np.unique(np.concatenate([fast_values, slow_values]))
        all_ma = vbt.MA.run(price, window=all_windows)

        # Build Sharpe matrix
        sharpe_matrix = np.full((len(fast_values), len(slow_values)), np.nan)
        best_sharpe = -np.inf
        best_fast, best_slow = int(fast_values[0]), int(slow_values[0])

        for i, fast_w in enumerate(fast_values):
            for j, slow_w in enumerate(slow_values):
                if fast_w >= slow_w:
                    continue  # fast must be < slow

                fast_ma = all_ma.ma[fast_w]
                slow_ma = all_ma.ma[slow_w]

                entries = fast_ma > slow_ma
                entries = entries & (
                    ~entries.shift(1).fillna(False).infer_objects(copy=False)
                )
                exits = fast_ma < slow_ma
                exits = exits & (
                    ~exits.shift(1).fillna(False).infer_objects(copy=False)
                )

                pf = vbt.Portfolio.from_signals(
                    price,
                    entries=entries,
                    exits=exits,
                    init_cash=req.init_cash,
                    fees=req.fees,
                    freq=freq,
                )
                sharpe = pf.sharpe_ratio()
                if not (np.isnan(sharpe) or np.isinf(sharpe)):
                    sharpe_matrix[i, j] = sharpe
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_fast = int(fast_w)
                        best_slow = int(slow_w)

        # Convert matrix: NaN -> None for JSON
        matrix_out: list[list[float | None]] = []
        for row in sharpe_matrix:
            matrix_out.append([
                None if np.isnan(v) else round(float(v), 4)
                for v in row
            ])

        valid_mask = ~np.isnan(sharpe_matrix)
        valid_count = int(valid_mask.sum())

        if valid_count == 0:
            raise ValueError("No valid parameter combinations found")

        valid_sharpes = sharpe_matrix[valid_mask]

        return SweepResponse(
            sharpe_matrix=matrix_out,
            fast_values=[int(v) for v in fast_values],
            slow_values=[int(v) for v in slow_values],
            best=SweepBest(
                fast=best_fast,
                slow=best_slow,
                sharpe=round(float(best_sharpe), 4),
            ),
            stats=SweepStats(
                mean=round(float(np.mean(valid_sharpes)), 4),
                median=round(float(np.median(valid_sharpes)), 4),
                max=round(float(np.max(valid_sharpes)), 4),
                valid_count=valid_count,
            ),
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Sweep failed: {exc}")
