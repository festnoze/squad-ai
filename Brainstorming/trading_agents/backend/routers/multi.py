"""Multi-strategy comparison and temporal allocation endpoints."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import vectorbt as vbt  # type: ignore[import-untyped]
from fastapi import APIRouter, HTTPException

_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.data.provider import load_price_data, INTERVAL_TO_FREQ  # noqa: E402
from src.backtesting.engine import BacktestConfig, run_backtest  # noqa: E402
from src.evaluation.regime import compute_regime_series, Regime  # noqa: E402
from src.evaluation.scoring import compute_risk_metrics, composite_score, drawdown_analysis  # noqa: E402
from src.evaluation.allocator import (  # noqa: E402
    StrategyPerformance, allocate_portfolio, DEFAULT_AFFINITIES,
)
from backend.schemas import MultiBacktestRequest  # noqa: E402
from backend.routers.backtest import (  # noqa: E402
    _build_ma_crossover_signals, _build_rsi_bb_signals, _build_adaptive_signals,
)

router = APIRouter()


def _safe(v: float) -> float | None:
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    return round(float(v), 6)


@router.post("/compare")
async def compare_strategies(req: MultiBacktestRequest):
    """Run multiple strategies on the same data and compare them."""
    try:
        df = load_price_data(req.symbol, interval=req.interval, start=req.start, end=req.end)
        price = df["Close"]
        freq = INTERVAL_TO_FREQ[req.interval]

        results = []
        for strat_cfg in req.strategies:
            name = strat_cfg.get("name", strat_cfg["type"])
            stype = strat_cfg["type"]
            params = strat_cfg.get("params", {})

            if stype == "ma_crossover":
                entries, exits = _build_ma_crossover_signals(price, params)
            elif stype == "rsi_bb":
                entries, exits = _build_rsi_bb_signals(price, params)
            elif stype == "adaptive":
                entries, exits = _build_adaptive_signals(df, price, params)
            else:
                continue

            config = BacktestConfig(
                symbol=req.symbol, interval=req.interval,
                start=req.start, end=req.end,
                init_cash=req.init_cash, fees=req.fees,
            )
            bt_result = run_backtest(config, entries, exits, price=price)
            portfolio = bt_result.portfolio

            metrics = compute_risk_metrics(portfolio)
            score = composite_score(metrics)
            dd = drawdown_analysis(portfolio)

            pv = portfolio.value()
            results.append({
                "name": name,
                "type": stype,
                "metrics": {k: _safe(v) if isinstance(v, float) else v for k, v in metrics.items()},
                "composite_score": _safe(score),
                "drawdown": {
                    "max_depth": _safe(dd["max_depth"]),
                    "avg_depth": _safe(dd["avg_depth"]),
                    "time_in_drawdown_pct": _safe(dd["time_in_drawdown_pct"]),
                    "n_periods": len(dd["periods"]),
                },
                "portfolio_values": [
                    {"date": str(idx), "value": round(float(val), 2)}
                    for idx, val in pv.items()
                ],
            })

        # Sort by composite score
        results.sort(key=lambda r: r["composite_score"] or 0, reverse=True)
        for i, r in enumerate(results):
            r["rank"] = i + 1

        # Buy & hold for comparison
        bh = req.init_cash * (price / price.iloc[0])
        buy_hold = [{"date": str(idx), "value": round(float(val), 2)} for idx, val in bh.items()]

        return {
            "strategies": results,
            "buy_hold": buy_hold,
            "symbol": req.symbol,
            "interval": req.interval,
            "bars": len(price),
        }

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Compare failed: {exc}")


@router.post("/allocate")
async def allocate_strategies(req: MultiBacktestRequest):
    """Run multiple strategies and compute optimal temporal allocation."""
    try:
        df = load_price_data(req.symbol, interval=req.interval, start=req.start, end=req.end)
        price = df["Close"]
        freq = INTERVAL_TO_FREQ[req.interval]

        # Compute regimes
        regime_df = compute_regime_series(df)
        regime_series = regime_df["regime"]

        strat_perfs = []
        for strat_cfg in req.strategies:
            name = strat_cfg.get("name", strat_cfg["type"])
            stype = strat_cfg["type"]
            params = strat_cfg.get("params", {})

            if stype == "ma_crossover":
                entries, exits = _build_ma_crossover_signals(price, params)
            elif stype == "rsi_bb":
                entries, exits = _build_rsi_bb_signals(price, params)
            elif stype == "adaptive":
                entries, exits = _build_adaptive_signals(df, price, params)
            else:
                continue

            config = BacktestConfig(
                symbol=req.symbol, interval=req.interval,
                start=req.start, end=req.end,
                init_cash=req.init_cash, fees=req.fees,
            )
            bt_result = run_backtest(config, entries, exits, price=price)
            pv = bt_result.portfolio.value()

            # Get regime affinity
            affinity_key = stype
            affinity = DEFAULT_AFFINITIES.get(affinity_key, DEFAULT_AFFINITIES["ma_crossover"])

            strat_perfs.append(StrategyPerformance(
                name=name,
                portfolio_value=pv,
                entries=entries,
                exits=exits,
                regime_affinity=affinity,
            ))

        # Run allocation
        alloc_result = allocate_portfolio(strat_perfs, regime_series, init_cash=req.init_cash)

        # Format response
        combined = alloc_result["combined_value"]
        weights = alloc_result["weights_over_time"]

        # Downsample weights for JSON (every 5th point)
        step = max(1, len(weights) // 200)
        weights_sampled = weights.iloc[::step]

        # Buy & hold
        bh = req.init_cash * (price / price.iloc[0])

        return {
            "combined_portfolio": [
                {"date": str(idx), "value": round(float(val), 2)}
                for idx, val in combined.items()
            ],
            "buy_hold": [
                {"date": str(idx), "value": round(float(val), 2)}
                for idx, val in bh.items()
            ],
            "strategy_values": {
                name: [{"date": str(idx), "value": round(float(val), 2)}
                       for idx, val in vals.items()]
                for name, vals in alloc_result["strategy_values"].items()
            },
            "weights": {
                col: [{"date": str(idx), "value": round(float(val), 4)}
                      for idx, val in weights_sampled[col].items()]
                for col in weights_sampled.columns
            },
            "regime": [
                {"date": str(idx), "regime": r.value if hasattr(r, "value") else str(r)}
                for idx, r in regime_series.items()
            ][::step],
            "metrics": {k: _safe(v) if isinstance(v, float) else v
                        for k, v in alloc_result["metrics"].items()},
        }

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Allocation failed: {exc}")
