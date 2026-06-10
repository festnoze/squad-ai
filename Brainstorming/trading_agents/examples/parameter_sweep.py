"""
Vectorized Parameter Sweep — MA Crossover optimization.

Sweeps all combinations of fast/slow MA windows in one vectorized call.
Produces a Sharpe ratio heatmap + runs the best combo through the standard backtest.
"""

import os
import sys

import numpy as np
import vectorbt as vbt  # type: ignore[import-untyped]
import plotly.graph_objects as go  # type: ignore[import-untyped]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.backtesting.engine import (
    BacktestConfig, run_backtest,
    print_header, print_results, build_plot, save_plot,
)
from src.data.provider import load_price_data, INTERVAL_TO_FREQ

# ── Configuration ──────────────────────────────────────────────
SYMBOL = "GOOGL"
INTERVAL = "1h"
START = "2024-06-01"
END = "2026-05-29"
INIT_CASH = 10_000
FEES = 0.001

# Sweep ranges
FAST_MA_RANGE = np.arange(5, 51, 5)      # 5, 10, 15, ... 50
SLOW_MA_RANGE = np.arange(20, 201, 10)   # 20, 30, 40, ... 200
# ───────────────────────────────────────────────────────────────


def build_heatmap(sharpe_matrix, fast_range, slow_range, best_fast, best_slow, best_sharpe, asset_name, symbol):
    """Build a Sharpe ratio heatmap with the best combo highlighted."""
    fig = go.Figure(data=go.Heatmap(
        z=sharpe_matrix,
        x=[str(s) for s in slow_range],
        y=[str(f) for f in fast_range],
        colorscale="RdYlGn",
        colorbar=dict(title="Sharpe"),
        zmin=-1, zmax=4,
    ))

    # Mark the best combo
    fig.add_trace(go.Scatter(
        x=[str(best_slow)], y=[str(best_fast)],
        mode="markers+text",
        marker=dict(size=18, color="white", line=dict(width=2, color="black")),
        text=[f"Best: {best_sharpe:.2f}"],
        textposition="top center",
        textfont=dict(size=12, color="white"),
        showlegend=False,
    ))

    fig.update_layout(
        title=dict(
            text=(
                f"{asset_name} ({symbol}) — MA Crossover Parameter Sweep<br>"
                f"<sub>{len(fast_range)} x {len(slow_range)} = {len(fast_range) * len(slow_range)} "
                f"combinations | Best: MA({best_fast}/{best_slow}) Sharpe={best_sharpe:.2f}</sub>"
            ),
            x=0.5, xanchor="center", font=dict(size=18),
        ),
        xaxis_title="Slow MA Window",
        yaxis_title="Fast MA Window",
        width=1200, height=700,
        template="plotly_white",
    )
    return fig


if __name__ == "__main__":
    freq = INTERVAL_TO_FREQ[INTERVAL]

    # Load data once
    df = load_price_data(SYMBOL, interval=INTERVAL, start=START, end=END)
    price = df["Close"]

    print(f"Loaded {len(price)} bars")
    print(f"Sweeping {len(FAST_MA_RANGE)} x {len(SLOW_MA_RANGE)} = "
          f"{len(FAST_MA_RANGE) * len(SLOW_MA_RANGE)} parameter combinations...\n")

    # Vectorized sweep: compute ALL MAs at once
    all_windows = np.unique(np.concatenate([FAST_MA_RANGE, SLOW_MA_RANGE]))
    all_ma = vbt.MA.run(price, window=all_windows)

    # Build Sharpe matrix
    sharpe_matrix = np.full((len(FAST_MA_RANGE), len(SLOW_MA_RANGE)), np.nan)
    best_sharpe = -np.inf
    best_fast, best_slow = 0, 0

    for i, fast_w in enumerate(FAST_MA_RANGE):
        for j, slow_w in enumerate(SLOW_MA_RANGE):
            if fast_w >= slow_w:
                continue  # skip invalid combos (fast must be < slow)

            fast_ma = all_ma.ma[fast_w]
            slow_ma = all_ma.ma[slow_w]

            entries = fast_ma > slow_ma
            entries = entries & (~entries.shift(1).fillna(False).infer_objects(copy=False))  # rising edge only
            exits = fast_ma < slow_ma
            exits = exits & (~exits.shift(1).fillna(False).infer_objects(copy=False))

            pf = vbt.Portfolio.from_signals(
                price, entries=entries, exits=exits,
                init_cash=INIT_CASH, fees=FEES, freq=freq,
            )
            sharpe = pf.sharpe_ratio()
            sharpe_matrix[i, j] = sharpe

            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_fast, best_slow = int(fast_w), int(slow_w)

    valid = ~np.isnan(sharpe_matrix)
    print(f"Evaluated {valid.sum()} valid combinations")
    print(f"Best: MA({best_fast}/{best_slow}) -> Sharpe = {best_sharpe:.2f}")
    print(f"Mean Sharpe: {np.nanmean(sharpe_matrix):.2f} | "
          f"Median: {np.nanmedian(sharpe_matrix):.2f} | "
          f"Max: {np.nanmax(sharpe_matrix):.2f}\n")

    # Save heatmap
    from src.data.provider import get_ticker_info
    info = get_ticker_info(SYMBOL)
    asset_name = info.get("shortName", SYMBOL)

    heatmap_fig = build_heatmap(
        sharpe_matrix, FAST_MA_RANGE, SLOW_MA_RANGE,
        best_fast, best_slow, best_sharpe, asset_name, SYMBOL,
    )
    out_dir = os.path.dirname(os.path.abspath(__file__))
    save_plot(heatmap_fig, os.path.join(out_dir, f"{SYMBOL}_sweep_heatmap.png"))

    # Run full backtest with best params
    print(f"\n--- Running best combo: MA({best_fast}/{best_slow}) ---")
    fast_ma = all_ma.ma[best_fast]
    slow_ma = all_ma.ma[best_slow]
    entries = fast_ma > slow_ma
    entries = entries & (~entries.shift(1).fillna(False).infer_objects(copy=False))
    exits = fast_ma < slow_ma
    exits = exits & (~exits.shift(1).fillna(False).infer_objects(copy=False))

    config = BacktestConfig(
        symbol=SYMBOL, interval=INTERVAL,
        start=START, end=END,
        init_cash=INIT_CASH, fees=FEES,
    )
    result = run_backtest(config, entries, exits, price=price)

    print_header(result)
    print(f"  Strategy: MA({best_fast}/{best_slow}) crossover [best from sweep]")
    print(f"  Loaded {len(price)} bars\n")
    print_results(result)

    fig = build_plot(result)
    save_plot(fig, os.path.join(out_dir, f"{SYMBOL}_best_backtest.png"))
