"""Backtest endpoints — run strategies and compute market regimes."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import vectorbt as vbt  # type: ignore[import-untyped]
from fastapi import APIRouter, HTTPException, Query

# Ensure project root is importable
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.data.provider import load_price_data, INTERVAL_TO_FREQ  # noqa: E402
from src.backtesting.engine import BacktestConfig, run_backtest  # noqa: E402
from src.evaluation.regime import compute_regime_series, Regime  # noqa: E402
from backend.schemas import (  # noqa: E402
    BacktestRequest,
    BacktestResponse,
    MetricsResponse,
    PortfolioPoint,
    EntryExitPoint,
)

router = APIRouter()


# ── Signal builders ──────────────────────────────────────────────

def _build_ma_crossover_signals(
    price: pd.Series,
    params: dict,
) -> tuple[pd.Series, pd.Series]:
    """MA crossover: buy when fast > slow (rising edge), sell when fast < slow."""
    fast_w = int(params.get("fast_ma", 20))
    slow_w = int(params.get("slow_ma", 50))

    fast_ma = vbt.MA.run(price, window=fast_w)
    slow_ma = vbt.MA.run(price, window=slow_w)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)
    return entries, exits


def _build_rsi_bb_signals(
    price: pd.Series,
    params: dict,
) -> tuple[pd.Series, pd.Series]:
    """RSI + Bollinger Bands mean-reversion strategy."""
    rsi_window = int(params.get("rsi_window", 14))
    rsi_lo = float(params.get("rsi_lo", 30))
    rsi_hi = float(params.get("rsi_hi", 70))
    bb_window = int(params.get("bb_window", 20))
    bb_alpha = float(params.get("bb_alpha", 2.0))

    rsi = vbt.RSI.run(price, window=rsi_window).rsi
    bb = vbt.BBANDS.run(price, window=bb_window, alpha=bb_alpha)

    entries = (rsi < rsi_lo) & (price < bb.lower)
    exits = (rsi > rsi_hi) & (price > bb.upper)
    return entries, exits


def _build_adaptive_signals(
    df: pd.DataFrame,
    price: pd.Series,
    params: dict,
) -> tuple[pd.Series, pd.Series]:
    """Adaptive regime-switching strategy (trending -> MA, reverting -> RSI+BB)."""
    # Regime params
    adx_window = int(params.get("adx_window", 14))
    hurst_window = int(params.get("hurst_window", 60))

    # Trend-following params
    fast_ma_w = int(params.get("fast_ma", 20))
    slow_ma_w = int(params.get("slow_ma", 50))

    # Mean-reversion params
    rsi_window = int(params.get("rsi_window", 14))
    rsi_lo = float(params.get("rsi_lo", 30))
    rsi_hi = float(params.get("rsi_hi", 70))
    bb_window = int(params.get("bb_window", 20))
    bb_alpha = float(params.get("bb_alpha", 2.0))

    # Compute regimes
    regimes = compute_regime_series(df, adx_window=adx_window, hurst_window=hurst_window)
    regime_series = regimes["regime"]

    trending_mask = regime_series == Regime.TRENDING
    reverting_mask = regime_series == Regime.REVERTING
    uncertain_mask = regime_series == Regime.UNCERTAIN

    # Compute indicators
    fast_ma = vbt.MA.run(price, window=fast_ma_w)
    slow_ma = vbt.MA.run(price, window=slow_ma_w)
    ma_bullish = fast_ma.ma.squeeze() > slow_ma.ma.squeeze()
    ma_crossover = fast_ma.ma_crossed_above(slow_ma)
    ma_crossunder = fast_ma.ma_crossed_below(slow_ma)

    rsi = vbt.RSI.run(price, window=rsi_window).rsi
    bb = vbt.BBANDS.run(price, window=bb_window, alpha=bb_alpha)
    rsi_oversold = (rsi < rsi_lo) & (price < bb.lower)
    rsi_overbought = (rsi > rsi_hi) & (price > bb.upper)

    # Regime transitions
    prev_regime = regime_series.shift(1)
    entered_trending = trending_mask & (prev_regime != Regime.TRENDING)
    entered_reverting = reverting_mask & (prev_regime != Regime.REVERTING)
    left_active = uncertain_mask & (prev_regime != Regime.UNCERTAIN)

    # Trend entries/exits
    trend_entries = (ma_crossover & trending_mask) | (entered_trending & ma_bullish)
    trend_exits = ma_crossunder & trending_mask

    # Reversion entries/exits
    rev_entries = (rsi_oversold & reverting_mask) | (entered_reverting & rsi_oversold)
    rev_entries = rev_entries & (~rev_entries.shift(1).fillna(False).infer_objects(copy=False))
    rev_exits = rsi_overbought & reverting_mask

    entries = trend_entries | rev_entries
    exits = trend_exits | rev_exits | left_active

    return entries, exits


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/run", response_model=BacktestResponse)
async def run_backtest_endpoint(req: BacktestRequest):
    """Run a backtest with the specified strategy and parameters."""
    try:
        df = load_price_data(req.symbol, interval=req.interval, start=req.start, end=req.end)
        price = df["Close"]

        # Build entry/exit signals based on strategy type
        if req.strategy == "ma_crossover":
            entries, exits = _build_ma_crossover_signals(price, req.params)
        elif req.strategy == "rsi_bb":
            entries, exits = _build_rsi_bb_signals(price, req.params)
        elif req.strategy == "adaptive":
            entries, exits = _build_adaptive_signals(df, price, req.params)
        else:
            raise ValueError(
                f"Unknown strategy '{req.strategy}'. "
                "Supported: ma_crossover, rsi_bb, adaptive"
            )

        config = BacktestConfig(
            symbol=req.symbol,
            interval=req.interval,
            start=req.start,
            end=req.end,
            init_cash=req.init_cash,
            fees=req.fees,
        )
        result = run_backtest(config, entries, exits, price=price)

        p = result.portfolio

        # Extract metrics
        total_return = float(p.total_return())
        sharpe = float(p.sharpe_ratio())
        max_dd = float(p.max_drawdown())
        trades = int(p.trades.count())
        win_rate = float(p.trades.win_rate()) if trades > 0 else 0.0
        profit_factor = float(p.trades.profit_factor()) if trades > 0 else 0.0

        # Sanitize NaN / Inf
        def _clean(v: float) -> float:
            if np.isnan(v) or np.isinf(v):
                return 0.0
            return v

        metrics = MetricsResponse(
            total_return=_clean(total_return),
            sharpe=_clean(sharpe),
            max_dd=_clean(max_dd),
            trades=trades,
            win_rate=_clean(win_rate),
            profit_factor=_clean(profit_factor),
        )

        # Portfolio value time series
        portfolio_value = p.value()
        portfolio_points = [
            PortfolioPoint(date=str(idx), value=float(val))
            for idx, val in portfolio_value.items()
        ]

        # Buy & hold value
        buy_hold = req.init_cash * (price / price.iloc[0])
        buy_hold_points = [
            PortfolioPoint(date=str(idx), value=float(val))
            for idx, val in buy_hold.items()
        ]

        # Entry / exit points
        entry_mask = result.entries.values.flatten()
        exit_mask = result.exits.values.flatten()

        entry_points = [
            EntryExitPoint(date=str(price.index[i]), price=float(price.iloc[i]))
            for i in range(len(price))
            if entry_mask[i]
        ]
        exit_points = [
            EntryExitPoint(date=str(price.index[i]), price=float(price.iloc[i]))
            for i in range(len(price))
            if exit_mask[i]
        ]

        return BacktestResponse(
            metrics=metrics,
            portfolio_values=portfolio_points,
            buy_hold_values=buy_hold_points,
            entries=entry_points,
            exits=exit_points,
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {exc}")


@router.get("/regime")
async def get_regime(
    symbol: str = Query(..., description="Ticker symbol"),
    interval: str = Query("1d"),
    start: str = Query("2020-01-01"),
    end: str = Query("2026-05-31"),
):
    """Compute market regime series (ADX + Hurst)."""
    try:
        df = load_price_data(symbol, interval=interval, start=start, end=end)
        regime_df = compute_regime_series(df)

        dates = [str(idx) for idx in regime_df.index]
        adx_vals = [
            None if np.isnan(v) else round(float(v), 4)
            for v in regime_df["adx"].values
        ]
        hurst_vals = [
            None if np.isnan(v) else round(float(v), 4)
            for v in regime_df["hurst"].values
        ]
        regime_vals = [r.value for r in regime_df["regime"].values]

        return {
            "dates": dates,
            "adx": adx_vals,
            "hurst": hurst_vals,
            "regime": regime_vals,
        }

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Regime computation failed: {exc}")
