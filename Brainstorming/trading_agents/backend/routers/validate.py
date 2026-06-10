"""Validation endpoints — Monte Carlo + multi-asset robustness testing."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import vectorbt as vbt  # type: ignore[import-untyped]
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.data.provider import load_price_data, INTERVAL_TO_FREQ  # noqa: E402
from src.evaluation.montecarlo import permutation_test, bootstrap_confidence_interval, random_entry_test  # noqa: E402
from src.evaluation.multiasset import (  # noqa: E402
    cross_asset_backtest, robustness_score,
    build_ma_crossover_builder, build_rsi_bb_builder,
    DEFAULT_VALIDATION_SYMBOLS,
)
from backend.routers.backtest import (  # noqa: E402
    _build_ma_crossover_signals, _build_rsi_bb_signals, _build_adaptive_signals,
)

router = APIRouter()


def _safe(v: float) -> float | None:
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    return round(float(v), 6)


class ValidateRequest(BaseModel):
    symbol: str
    interval: str = "1d"
    start: str = "2020-01-01"
    end: str = "2026-05-31"
    strategy: str = "ma_crossover"
    params: dict = Field(default_factory=dict)
    init_cash: float = 10_000
    fees: float = 0.001
    n_simulations: int = 500
    validation_symbols: list[str] = Field(default_factory=lambda: list(DEFAULT_VALIDATION_SYMBOLS))


@router.post("/montecarlo")
async def run_montecarlo(req: ValidateRequest):
    """Run Monte Carlo permutation test on a strategy."""
    try:
        df = load_price_data(req.symbol, interval=req.interval, start=req.start, end=req.end)
        price = df["Close"]
        freq = INTERVAL_TO_FREQ[req.interval]

        # Build signals
        if req.strategy == "ma_crossover":
            entries, exits = _build_ma_crossover_signals(price, req.params)
        elif req.strategy == "rsi_bb":
            entries, exits = _build_rsi_bb_signals(price, req.params)
        elif req.strategy == "adaptive":
            entries, exits = _build_adaptive_signals(df, price, req.params)
        else:
            raise ValueError(f"Unknown strategy: {req.strategy}")

        portfolio = vbt.Portfolio.from_signals(
            price, entries=entries, exits=exits,
            init_cash=req.init_cash, fees=req.fees, freq=freq,
        )

        # Permutation test
        perm = permutation_test(portfolio, n_simulations=req.n_simulations)

        # Bootstrap CI
        boot = bootstrap_confidence_interval(portfolio, n_bootstraps=req.n_simulations)

        # Random entry test
        n_trades = int(portfolio.trades.count())
        avg_holding = max(5, len(price) // max(n_trades, 1))
        rand = random_entry_test(
            price, n_trades=max(n_trades, 3), avg_holding_period=avg_holding,
            n_simulations=req.n_simulations, init_cash=req.init_cash,
            fees=req.fees, freq=freq,
        )

        # Build histogram data (downsample for JSON)
        step = max(1, len(perm["simulated_sharpes"]) // 100)
        sim_sharpes_hist = sorted(perm["simulated_sharpes"])[::step]

        return {
            "permutation": {
                "real_sharpe": _safe(perm["real_sharpe"]),
                "p_value": _safe(perm["p_value"]),
                "percentile": _safe(perm["percentile"]),
                "is_significant_95": perm["is_significant_95"],
                "is_significant_99": perm["is_significant_99"],
                "simulated_sharpes": [_safe(s) for s in sim_sharpes_hist],
                "mean_simulated": _safe(perm["mean_simulated"]),
                "std_simulated": _safe(perm["std_simulated"]),
            },
            "bootstrap": {
                "total_return": {k: _safe(v) for k, v in boot["total_return"].items()},
                "sharpe_ratio": {k: _safe(v) for k, v in boot["sharpe_ratio"].items()},
                "max_drawdown": {k: _safe(v) for k, v in boot["max_drawdown"].items()},
                "confidence_level": boot["confidence_level"],
            },
            "random_entry": {
                "p_value_return": _safe(rand["p_value_return"]),
                "p_value_sharpe": _safe(rand["p_value_sharpe"]),
                "mean_random_return": _safe(rand["mean_random_return"]),
                "mean_random_sharpe": _safe(rand["mean_random_sharpe"]),
                "n_simulations": rand["n_simulations"],
            },
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Monte Carlo failed: {exc}")


@router.post("/multiasset")
async def run_multiasset(req: ValidateRequest):
    """Test strategy robustness across multiple assets."""
    try:
        # Build signal builder based on strategy type
        params = req.params
        if req.strategy == "ma_crossover":
            builder = build_ma_crossover_builder(
                int(params.get("fast_ma", 20)),
                int(params.get("slow_ma", 50)),
            )
        elif req.strategy == "rsi_bb":
            builder = build_rsi_bb_builder(
                rsi_window=int(params.get("rsi_window", 14)),
                rsi_lo=int(params.get("rsi_lo", 30)),
                rsi_hi=int(params.get("rsi_hi", 70)),
                bb_window=int(params.get("bb_window", 20)),
                bb_alpha=float(params.get("bb_alpha", 2.0)),
            )
        else:
            # Default to MA crossover for unknown types
            builder = build_ma_crossover_builder(20, 50)

        results = cross_asset_backtest(
            symbols=req.validation_symbols,
            interval=req.interval,
            start=req.start,
            end=req.end,
            signal_builder=builder,
            init_cash=req.init_cash,
            fees=req.fees,
        )

        robustness = robustness_score(results)

        # Sanitize for JSON
        for r in robustness["per_asset"]:
            for k, v in r.items():
                if isinstance(v, float):
                    r[k] = _safe(v)
            # Keep portfolio_values but limit size
            if "portfolio_values" in r:
                step = max(1, len(r["portfolio_values"]) // 200)
                r["portfolio_values"] = r["portfolio_values"][::step]

        return {
            "robustness": {
                "grade": robustness["robustness_grade"],
                "n_assets": robustness["n_assets"],
                "n_profitable": robustness["n_profitable"],
                "profitable_pct": _safe(robustness["profitable_pct"]),
                "mean_sharpe": _safe(robustness["mean_sharpe"]),
                "sharpe_std": _safe(robustness["sharpe_std"]),
                "mean_return": _safe(robustness["mean_return"]),
                "mean_max_dd": _safe(robustness["mean_max_dd"]),
            },
            "per_asset": robustness["per_asset"],
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Multi-asset failed: {exc}")
