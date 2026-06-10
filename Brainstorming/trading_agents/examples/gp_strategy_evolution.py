"""
GP Strategy Evolution — DEAP discovers trading strategies from scratch.

Evolves populations of strategy trees using genetic programming:
  - Grammar: SMA, RSI, BB, ATR, price data, logical operators
  - Fitness: VectorBT Sharpe ratio with complexity penalty
  - Validation: in-sample train + out-of-sample test
  - Compares discovered strategies with previous examples
"""

import os
import sys
import warnings

import numpy as np
import pandas as pd
import vectorbt as vbt  # type: ignore[import-untyped]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.data.provider import load_price_data, get_ticker_info, INTERVAL_TO_FREQ
from src.backtesting.engine import (
    BacktestConfig, ComparisonCurve,
    run_backtest, print_header, print_results, build_plot, save_plot,
)
from src.agent.evolution import setup_evolution, run_evolution, validate_top_strategies
from src.agent.grammar import set_context

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Configuration ──────────────────────────────────────────────
SYMBOL = "BTC-USD"
INTERVAL = "1d"
START = "2020-01-01"
END = "2026-05-31"
INIT_CASH = 10_000
FEES = 0.001

# Train/test split
TRAIN_END = "2025-01-01"   # 5 years train
# Test: 2025-01-01 -> 2026-05-31 (~17 months OOS)

# GP parameters
POP_SIZE = 300
N_GENERATIONS = 50
MAX_DEPTH = 6
COMPLEXITY_PENALTY = 0.05  # Sharpe points per complexity unit (nesting-aware)
SEED = 42
# ───────────────────────────────────────────────────────────────


def run_comparison_ma(price, freq, fast_w, slow_w):
    """Run MA crossover, return portfolio value series."""
    fast_ma = vbt.MA.run(price, window=fast_w)
    slow_ma = vbt.MA.run(price, window=slow_w)
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)
    pf = vbt.Portfolio.from_signals(
        price, entries=entries, exits=exits,
        init_cash=INIT_CASH, fees=FEES, freq=freq,
    )
    return pf.value()


if __name__ == "__main__":
    freq = INTERVAL_TO_FREQ[INTERVAL]
    info = get_ticker_info(SYMBOL)
    asset_name = info.get("shortName", SYMBOL)
    currency = info.get("currency", "USD")

    print(f"\n{'=' * 70}")
    print(f"  GP Strategy Evolution -- {asset_name} ({SYMBOL})")
    print(f"  Train: {START} -> {TRAIN_END} | Test: {TRAIN_END} -> {END}")
    print(f"  Pop: {POP_SIZE} | Gen: {N_GENERATIONS} | MaxDepth: {MAX_DEPTH}")
    print(f"  Complexity penalty: {COMPLEXITY_PENALTY} Sharpe/node")
    print(f"{'=' * 70}\n")

    # Load and split data
    df = load_price_data(SYMBOL, interval=INTERVAL, start=START, end=END)
    df_train = df.loc[:TRAIN_END]
    df_test = df.loc[TRAIN_END:]
    print(f"Train: {len(df_train)} bars | Test: {len(df_test)} bars\n")

    # Setup evolution
    toolbox, pset, stats, hof = setup_evolution(
        df_train, freq,
        init_cash=INIT_CASH, fees=FEES,
        complexity_penalty=COMPLEXITY_PENALTY,
        max_depth=MAX_DEPTH,
        seed=SEED,
    )

    # Run evolution
    pop, logbook = run_evolution(
        toolbox, stats, hof,
        pop_size=POP_SIZE, n_gen=N_GENERATIONS,
    )

    # Validate top strategies
    print(f"\n{'=' * 70}")
    print(f"  Top 5 Strategies — In-Sample vs Out-of-Sample")
    print(f"{'=' * 70}\n")

    results = validate_top_strategies(
        hof, toolbox, df_train, df_test, freq,
        init_cash=INIT_CASH, fees=FEES, top_n=5,
    )

    for r in results:
        print(f"#{r['rank']} (size={r['tree_size']}, depth={r['tree_depth']})")
        print(f"  Rule: {r['expression'][:100]}{'...' if len(r['expression']) > 100 else ''}")
        print(f"  TRAIN: ret={r['train_return']:+.1%} sharpe={r['train_sharpe']:.2f} "
              f"dd={r['train_drawdown']:.1%} trades={r['train_trades']}")
        print(f"  TEST:  ret={r['test_return']:+.1%} sharpe={r['test_sharpe']:.2f} "
              f"dd={r['test_drawdown']:.1%} trades={r['test_trades']}")
        is_overfit = r['test_sharpe'] < r['train_sharpe'] * 0.3
        print(f"  {'** OVERFIT **' if is_overfit else 'OK'}\n")

    # Plot best strategy on TEST set
    best = results[0]
    if best.get("test_portfolio") is not None:
        config = BacktestConfig(
            symbol=SYMBOL, interval=INTERVAL,
            start=TRAIN_END, end=END,
            init_cash=INIT_CASH, fees=FEES,
        )
        result = run_backtest(
            config, best["test_entries"], best["test_exits"],
            price=best["test_price"],
        )

        # Comparison: MA strategies on test period
        test_price = df_test["Close"]
        ma_10_50 = run_comparison_ma(test_price, freq, 10, 50)
        ma_40_200 = run_comparison_ma(test_price, freq, 40, 200)

        comparisons = [
            ComparisonCurve("MA(10/50)", ma_10_50, color="#FF6B35", dash="dash"),
            ComparisonCurve("MA(40/200)", ma_40_200, color="#1B998B", dash="dashdot"),
        ]

        fig = build_plot(result, comparisons=comparisons, strategy_name="GP Best (OOS)")
        out_dir = os.path.dirname(os.path.abspath(__file__))
        save_plot(fig, os.path.join(out_dir, f"{SYMBOL}_gp_evolution.png"))

        print(f"\nBest strategy rule:")
        print(f"  {best['expression']}")
