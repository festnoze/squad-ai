"""
MA Crossover Backtest — configurable symbol, timeframe, and date range.

Strategy: Buy when fast MA crosses above slow MA, sell when it crosses below.
"""

import os
import sys

import vectorbt as vbt  # type: ignore[import-untyped]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.backtesting.engine import BacktestConfig, run_backtest, print_header, print_results, build_plot, save_plot
from src.data.provider import load_price_data, INTERVAL_TO_FREQ

# ── Configuration ──────────────────────────────────────────────
SYMBOL = "GOOGL"
INTERVAL = "1h"            # 1m, 5m, 15m, 1h, 4h, 1d, 1w
START = "2024-06-01"        # YYYY-MM-DD
END = "2026-05-29"          # YYYY-MM-DD

FAST_MA = 10
SLOW_MA = 50
INIT_CASH = 10_000
FEES = 0.001                # 0.1%
# ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    config = BacktestConfig(
        symbol=SYMBOL, interval=INTERVAL,
        start=START, end=END,
        init_cash=INIT_CASH, fees=FEES,
    )

    # Load price data (cached)
    df = load_price_data(SYMBOL, interval=INTERVAL, start=START, end=END)
    price = df["Close"]
    freq = INTERVAL_TO_FREQ[INTERVAL]

    # Strategy: MA crossover
    fast_ma = vbt.MA.run(price, window=FAST_MA)
    slow_ma = vbt.MA.run(price, window=SLOW_MA)
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Run backtest
    result = run_backtest(config, entries, exits, price=price)

    # Output
    print_header(result)
    print(f"  Strategy: MA({FAST_MA}/{SLOW_MA}) crossover")
    print(f"  Loaded {len(price)} bars\n")
    print_results(result)

    fig = build_plot(result)
    out_dir = os.path.dirname(os.path.abspath(__file__))
    save_plot(fig, os.path.join(out_dir, f"{SYMBOL}_{INTERVAL}_backtest.png"))
