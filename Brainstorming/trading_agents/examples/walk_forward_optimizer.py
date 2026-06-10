"""
Walk-Forward Multi-Indicator Optimizer — RSI + Bollinger Bands + SL/TP.

Demonstrates VectorBT's advanced capabilities:
  1. Multi-indicator strategy (RSI + Bollinger Bands)
  2. Stop-Loss / Take-Profit per trade
  3. Walk-forward optimization (train/test rolling windows)
  4. Composite scoring (Sharpe + Sortino + Profit Factor)
  5. Comparison with previous examples (MA crossover strategies)
"""

import os
import sys
from itertools import product

import numpy as np
import pandas as pd
import vectorbt as vbt  # type: ignore[import-untyped]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.backtesting.engine import (
    BacktestConfig, ComparisonCurve,
    run_backtest, print_header, print_results, build_plot, save_plot,
)
from src.data.provider import load_price_data, get_ticker_info, INTERVAL_TO_FREQ

# ── Configuration ──────────────────────────────────────────────
SYMBOL = "BTC-USD"
INTERVAL = "1d"
START = "2020-01-01"
END = "2026-05-31"
INIT_CASH = 10_000
FEES = 0.001

# Walk-forward windows (in calendar days)
TRAIN_DAYS = 180     # 6 mois d'optimisation
TEST_DAYS = 60       # 2 mois de validation
STEP_DAYS = 60       # avance de 2 mois

# Parameter grid for sweep
RSI_WINDOWS = [10, 14, 20]
RSI_THRESHOLDS = [(25, 75), (30, 70), (35, 65)]    # (oversold, overbought)
BB_WINDOWS = [15, 20, 25]
BB_ALPHAS = [1.5, 2.0, 2.5]
SL_STOPS = [0.03, 0.05]     # 3%, 5%
TP_STOPS = [0.06, 0.10]     # 6%, 10%
# ───────────────────────────────────────────────────────────────


def composite_score(portfolio) -> float:
    """Weighted composite: 40% Sharpe + 30% Sortino + 30% Profit Factor (normalized)."""
    sharpe = portfolio.sharpe_ratio()
    sortino = portfolio.sortino_ratio()
    pf = portfolio.trades.profit_factor()
    if np.isnan(sharpe) or np.isnan(sortino) or np.isnan(pf) or np.isinf(pf):
        return -999.0
    # Normalize profit factor (cap at 10 to avoid outliers dominating)
    pf_norm = min(pf, 10.0) / 10.0 * 4.0  # scale to ~same range as Sharpe
    return 0.4 * sharpe + 0.3 * sortino + 0.3 * pf_norm


def sweep_on_window(price: pd.Series, freq: str) -> tuple[dict, float]:
    """Sweep all parameter combos on a price window. Returns (best_params, best_score)."""
    best_score = -np.inf
    best_params = {}

    for rsi_w, (rsi_lo, rsi_hi), bb_w, bb_a, sl, tp in product(
        RSI_WINDOWS, RSI_THRESHOLDS, BB_WINDOWS, BB_ALPHAS, SL_STOPS, TP_STOPS
    ):
        rsi = vbt.RSI.run(price, window=rsi_w).rsi
        bb = vbt.BBANDS.run(price, window=bb_w, alpha=bb_a)

        # Entry: RSI oversold AND price below lower BB
        entries = (rsi < rsi_lo) & (price < bb.lower)
        # Exit: RSI overbought AND price above upper BB
        exits = (rsi > rsi_hi) & (price > bb.upper)

        pf = vbt.Portfolio.from_signals(
            price, entries=entries, exits=exits,
            init_cash=INIT_CASH, fees=FEES, freq=freq,
            sl_stop=sl, tp_stop=tp,
        )

        score = composite_score(pf)
        if score > best_score:
            best_score = score
            best_params = dict(
                rsi_w=rsi_w, rsi_lo=rsi_lo, rsi_hi=rsi_hi,
                bb_w=bb_w, bb_a=bb_a, sl=sl, tp=tp,
            )

    return best_params, best_score


def walk_forward(price: pd.Series, freq: str):
    """Run walk-forward optimization. Returns stitched entries/exits and window log."""
    full_entries = pd.Series(False, index=price.index)
    full_exits = pd.Series(False, index=price.index)
    windows_log = []

    total_combos = (len(RSI_WINDOWS) * len(RSI_THRESHOLDS) * len(BB_WINDOWS)
                    * len(BB_ALPHAS) * len(SL_STOPS) * len(TP_STOPS))

    start_dt = price.index[0]
    end_dt = price.index[-1]
    train_delta = pd.Timedelta(days=TRAIN_DAYS)
    test_delta = pd.Timedelta(days=TEST_DAYS)
    step_delta = pd.Timedelta(days=STEP_DAYS)

    cursor = start_dt
    window_num = 0

    while cursor + train_delta + test_delta <= end_dt:
        train_start = cursor
        train_end = cursor + train_delta
        test_start = train_end
        test_end = test_start + test_delta

        train_price = price.loc[train_start:train_end]
        test_price = price.loc[test_start:test_end]

        if len(train_price) < 50 or len(test_price) < 10:
            cursor += step_delta
            continue

        window_num += 1
        print(f"  Window {window_num}: train {train_start.date()}->{train_end.date()} "
              f"| test {test_start.date()}->{test_end.date()} "
              f"| {total_combos} combos ... ", end="", flush=True)

        best_params, train_score = sweep_on_window(train_price, freq)

        # Apply best params on test period
        p = best_params
        rsi = vbt.RSI.run(test_price, window=p["rsi_w"]).rsi
        bb = vbt.BBANDS.run(test_price, window=p["bb_w"], alpha=p["bb_a"])
        test_entries = (rsi < p["rsi_lo"]) & (test_price < bb.lower)
        test_exits = (rsi > p["rsi_hi"]) & (test_price > bb.upper)

        # Stitch into full signal series
        full_entries.loc[test_entries.index] = test_entries
        full_exits.loc[test_exits.index] = test_exits

        # Evaluate OOS performance
        test_pf = vbt.Portfolio.from_signals(
            test_price, entries=test_entries, exits=test_exits,
            init_cash=INIT_CASH, fees=FEES, freq=freq,
            sl_stop=p["sl"], tp_stop=p["tp"],
        )
        test_score = composite_score(test_pf)
        test_return = test_pf.total_return()

        print(f"best=RSI({p['rsi_w']},{p['rsi_lo']}/{p['rsi_hi']}) "
              f"BB({p['bb_w']},{p['bb_a']}) SL={p['sl']:.0%} TP={p['tp']:.0%} "
              f"| train_score={train_score:.2f} | OOS: {test_return:+.1%} score={test_score:.2f}")

        windows_log.append(dict(
            window=window_num,
            train_start=train_start, train_end=train_end,
            test_start=test_start, test_end=test_end,
            train_score=train_score, test_score=test_score,
            test_return=test_return, **best_params,
        ))

        cursor += step_delta

    return full_entries, full_exits, windows_log


def run_comparison_strategy(price, freq, fast_w, slow_w):
    """Run a simple MA crossover and return the portfolio value series."""
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

    total_combos = (len(RSI_WINDOWS) * len(RSI_THRESHOLDS) * len(BB_WINDOWS)
                    * len(BB_ALPHAS) * len(SL_STOPS) * len(TP_STOPS))

    print(f"\n{'=' * 70}")
    print(f"  Walk-Forward Optimizer — {asset_name} ({SYMBOL})")
    print(f"  RSI + Bollinger Bands + SL/TP | {total_combos} combos/window")
    print(f"  Train: {TRAIN_DAYS}d | Test: {TEST_DAYS}d | Step: {STEP_DAYS}d")
    print(f"{'=' * 70}\n")

    # Load data
    df = load_price_data(SYMBOL, interval=INTERVAL, start=START, end=END)
    price = df["Close"]
    print(f"Loaded {len(price)} bars\n")

    # Walk-forward optimization
    print("--- Walk-Forward Windows ---")
    entries, exits, windows_log = walk_forward(price, freq)

    # Summary of walk-forward
    print(f"\n--- Walk-Forward Summary ({len(windows_log)} windows) ---")
    oos_returns = [w["test_return"] for w in windows_log]
    oos_scores = [w["test_score"] for w in windows_log]
    print(f"OOS returns:  mean={np.mean(oos_returns):+.1%}  "
          f"min={np.min(oos_returns):+.1%}  max={np.max(oos_returns):+.1%}")
    print(f"OOS scores:   mean={np.mean(oos_scores):.2f}  "
          f"min={np.min(oos_scores):.2f}  max={np.max(oos_scores):.2f}")

    # Parameter stability
    print("\nParam evolution per window:")
    for w in windows_log:
        print(f"  W{w['window']}: RSI({w['rsi_w']},{w['rsi_lo']}/{w['rsi_hi']}) "
              f"BB({w['bb_w']},{w['bb_a']}) SL={w['sl']:.0%} TP={w['tp']:.0%} "
              f"-> OOS {w['test_return']:+.1%}")

    # Full backtest with stitched WF signals (no SL/TP here — already baked into window selection)
    config = BacktestConfig(
        symbol=SYMBOL, interval=INTERVAL,
        start=START, end=END,
        init_cash=INIT_CASH, fees=FEES,
    )
    result = run_backtest(config, entries, exits, price=price)

    print_header(result)
    print("  Strategy: Walk-Forward RSI+BB+SL/TP\n")
    print_results(result)

    # Build comparison curves from previous examples
    print("\n--- Computing comparison strategies ---")
    ma_10_50_value = run_comparison_strategy(price, freq, fast_w=10, slow_w=50)
    print("  MA(10/50) done")
    ma_40_200_value = run_comparison_strategy(price, freq, fast_w=40, slow_w=200)
    print("  MA(40/200) done")

    comparisons = [
        ComparisonCurve("Ex1: MA(10/50)", ma_10_50_value, color="#FF6B35", dash="dash"),
        ComparisonCurve("Ex2: MA(40/200)", ma_40_200_value, color="#1B998B", dash="dashdot"),
    ]

    fig = build_plot(result, comparisons=comparisons, strategy_name="Ex3: WF RSI+BB")
    out_dir = os.path.dirname(os.path.abspath(__file__))
    save_plot(fig, os.path.join(out_dir, f"{SYMBOL}_walk_forward.png"))
