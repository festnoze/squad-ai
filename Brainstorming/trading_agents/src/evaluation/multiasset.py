"""
Cross-asset validation -- test strategy robustness across multiple instruments.

A genuinely good strategy should generalise beyond the single asset it was
optimised on.  This module runs the same signal logic on several tickers,
collects per-asset metrics, and produces a robustness grade.
"""

from __future__ import annotations

import math
import traceback
from typing import Any, Callable

import numpy as np
import pandas as pd
import vectorbt as vbt  # type: ignore[import-untyped]

from src.data.provider import load_price_data, INTERVAL_TO_FREQ

# ---------------------------------------------------------------------------
# Default validation universe
# ---------------------------------------------------------------------------

DEFAULT_VALIDATION_SYMBOLS: list[str] = [
    "BTC-USD",
    "ETH-USD",
    "AAPL",
    "GOOGL",
    "MSFT",
]

# Type alias for signal builders
SignalBuilder = Callable[[pd.Series, pd.DataFrame], tuple[pd.Series, pd.Series]]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clean(v: Any) -> float:
    """Convert NaN / Inf / non-finite values to 0.0."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(f) or math.isinf(f):
        return 0.0
    return f


def _portfolio_values_to_list(portfolio: Any) -> list[dict[str, Any]]:
    """Extract portfolio value series as JSON-serializable list of dicts."""
    value_series = portfolio.value()
    return [
        {"date": str(dt), "value": float(val)}
        for dt, val in zip(value_series.index, value_series.values)
    ]


# ---------------------------------------------------------------------------
# Core: cross-asset backtest
# ---------------------------------------------------------------------------

def cross_asset_backtest(
    symbols: list[str],
    interval: str,
    start: str,
    end: str,
    signal_builder: SignalBuilder,
    init_cash: float = 10_000,
    fees: float = 0.001,
) -> list[dict]:
    """Run the same strategy on multiple assets and collect metrics.

    Args:
        symbols: Ticker symbols, e.g. ``["BTC-USD", "AAPL", "GOOGL"]``.
        interval: Bar size -- ``"1d"``, ``"1h"``, etc.
        start: Start date as ``"YYYY-MM-DD"``.
        end: End date as ``"YYYY-MM-DD"``.
        signal_builder: ``(price, df) -> (entries, exits)`` callable.
        init_cash: Starting cash per backtest.
        fees: Commission rate (0.001 = 0.1 %).

    Returns:
        List of per-asset result dicts.  Failed symbols are skipped with an
        error printed to stdout.
    """
    freq = INTERVAL_TO_FREQ.get(interval, "1D")
    results: list[dict] = []

    for symbol in symbols:
        try:
            # 1. Load data
            df = load_price_data(symbol, interval=interval, start=start, end=end)
            price = df["Close"]

            # 2. Generate signals
            entries, exits = signal_builder(price, df)

            # 3. Run backtest via VectorBT directly (skip get_ticker_info)
            portfolio = vbt.Portfolio.from_signals(
                price,
                entries=entries,
                exits=exits,
                init_cash=init_cash,
                fees=fees,
                freq=freq,
            )

            # 4. Collect metrics
            n_trades = int(portfolio.trades.count())
            win_rate = _clean(portfolio.trades.win_rate()) if n_trades > 0 else 0.0
            profit_factor = _clean(portfolio.trades.profit_factor()) if n_trades > 0 else 0.0

            result = {
                "symbol": symbol,
                "total_return": _clean(portfolio.total_return()),
                "sharpe_ratio": _clean(portfolio.sharpe_ratio()),
                "sortino_ratio": _clean(portfolio.sortino_ratio()),
                "max_drawdown": abs(_clean(portfolio.max_drawdown())),
                "n_trades": n_trades,
                "win_rate": win_rate,
                "profit_factor": profit_factor,
                "portfolio_values": _portfolio_values_to_list(portfolio),
            }
            results.append(result)
            print(f"[multiasset] {symbol}: return={result['total_return']:.2%}, "
                  f"sharpe={result['sharpe_ratio']:.2f}, trades={n_trades}")

        except Exception:
            print(f"[multiasset] ERROR processing {symbol}:")
            traceback.print_exc()
            continue

    return results


# ---------------------------------------------------------------------------
# Robustness scoring
# ---------------------------------------------------------------------------

def robustness_score(results: list[dict]) -> dict:
    """Analyse cross-asset consistency and assign a robustness grade.

    Args:
        results: Output of :func:`cross_asset_backtest`.

    Returns:
        Summary dict with aggregate statistics and a letter grade.
    """
    if not results:
        return {
            "n_assets": 0,
            "n_profitable": 0,
            "profitable_pct": 0.0,
            "mean_sharpe": 0.0,
            "min_sharpe": 0.0,
            "max_sharpe": 0.0,
            "sharpe_std": 0.0,
            "mean_return": 0.0,
            "mean_max_dd": 0.0,
            "robustness_grade": "F",
            "per_asset": [],
        }

    n_assets = len(results)
    returns = np.array([r["total_return"] for r in results])
    sharpes = np.array([r["sharpe_ratio"] for r in results])
    max_dds = np.array([r["max_drawdown"] for r in results])

    n_profitable = int(np.sum(returns > 0))
    profitable_pct = n_profitable / n_assets

    mean_sharpe = float(np.mean(sharpes))
    min_sharpe = float(np.min(sharpes))
    max_sharpe = float(np.max(sharpes))
    sharpe_std = float(np.std(sharpes, ddof=0)) if n_assets > 1 else 0.0

    mean_return = float(np.mean(returns))
    mean_max_dd = float(np.mean(max_dds))

    # --- Grading ---
    if profitable_pct >= 0.80 and mean_sharpe > 0.5 and sharpe_std < 1.0:
        grade = "A"
    elif profitable_pct >= 0.60 and mean_sharpe > 0.3:
        grade = "B"
    elif profitable_pct >= 0.40 and mean_sharpe > 0:
        grade = "C"
    elif profitable_pct >= 0.20:
        grade = "D"
    else:
        grade = "F"

    return {
        "n_assets": n_assets,
        "n_profitable": n_profitable,
        "profitable_pct": profitable_pct,
        "mean_sharpe": mean_sharpe,
        "min_sharpe": min_sharpe,
        "max_sharpe": max_sharpe,
        "sharpe_std": sharpe_std,
        "mean_return": mean_return,
        "mean_max_dd": mean_max_dd,
        "robustness_grade": grade,
        "per_asset": results,
    }


# ---------------------------------------------------------------------------
# Signal-builder factories
# ---------------------------------------------------------------------------

def build_ma_crossover_builder(fast_w: int, slow_w: int) -> SignalBuilder:
    """Factory returning a signal builder for MA crossover strategy.

    Args:
        fast_w: Fast moving-average window.
        slow_w: Slow moving-average window.

    Returns:
        Callable ``(price, df) -> (entries, exits)``.
    """
    def signal_builder(price: pd.Series, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        fast_ma = vbt.MA.run(price, window=fast_w)
        slow_ma = vbt.MA.run(price, window=slow_w)
        entries = fast_ma.ma_crossed_above(slow_ma)
        exits = fast_ma.ma_crossed_below(slow_ma)
        return entries, exits

    return signal_builder


def build_rsi_bb_builder(
    rsi_window: int = 14,
    rsi_lo: int = 30,
    rsi_hi: int = 70,
    bb_window: int = 20,
    bb_alpha: float = 2.0,
) -> SignalBuilder:
    """Factory returning a signal builder for RSI + Bollinger Bands strategy.

    Entry: RSI below ``rsi_lo`` AND price below lower Bollinger Band.
    Exit:  RSI above ``rsi_hi`` AND price above upper Bollinger Band.

    Args:
        rsi_window: RSI lookback period.
        rsi_lo: RSI oversold threshold (entry trigger).
        rsi_hi: RSI overbought threshold (exit trigger).
        bb_window: Bollinger Bands moving-average window.
        bb_alpha: Bollinger Bands standard-deviation multiplier.

    Returns:
        Callable ``(price, df) -> (entries, exits)``.
    """
    def signal_builder(price: pd.Series, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        rsi = vbt.RSI.run(price, window=rsi_window)
        bb = vbt.BBANDS.run(price, window=bb_window, alpha=bb_alpha)

        rsi_values = rsi.rsi

        entries = (rsi_values < rsi_lo) & (price < bb.lower)
        exits = (rsi_values > rsi_hi) & (price > bb.upper)

        return entries, exits

    return signal_builder
