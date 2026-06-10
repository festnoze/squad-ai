"""
Fitness evaluation — convert GP trees into a trading score via VectorBT.

Supports two modes:
  1. **Single-tree** (legacy): one GP tree produces a boolean signal;
     entries = rising edges, exits = falling edges.
  2. **Pair** (new): separate entry tree + exit tree each produce a boolean
     signal; entries/exits are the rising edges of each respective signal.

Both modes use walk-forward evaluation: split training data into K rolling
windows, evaluate only on the out-of-sample portion of each window, and
return the mean OOS Sharpe ratio.  This prevents overfitting to the full
training period.

Includes complexity penalty to favor simpler strategies.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import vectorbt as vbt  # type: ignore[import-untyped]
from deap import gp  # type: ignore[import-untyped]

from src.agent.grammar import set_context, _resolve, tree_complexity_score


# ── Walk-forward splitting (shared by single-tree and pair modes) ───────


def _walk_forward_splits(
    n_rows: int, n_splits: int, train_pct: float
) -> list[tuple[int, int, int]]:
    """Generate walk-forward (start, split, end) index triples.

    Each triple defines a window where:
        - [start : split] is the burn-in / in-sample portion (train_pct)
        - [split : end]   is the out-of-sample portion to evaluate

    The windows tile the dataset with equal-sized steps so that
    every OOS region is non-overlapping and covers the data after
    the first burn-in.
    """
    # Minimum total rows needed for even a single useful window
    min_window = 60  # hard floor — need enough bars for indicators
    if n_rows < min_window:
        return []

    # Total usable rows after the first burn-in
    first_burn = int(n_rows * train_pct)
    oos_total = n_rows - first_burn
    if oos_total < n_splits:
        # Not enough OOS bars to form the requested number of splits
        return []

    oos_per_split = oos_total // n_splits
    splits: list[tuple[int, int, int]] = []
    for i in range(n_splits):
        # Each window starts from 0 so indicators have full history
        start = 0
        split = first_burn + i * oos_per_split
        end = split + oos_per_split if i < n_splits - 1 else n_rows
        splits.append((start, split, end))
    return splits


# ── Single-tree evaluation (backward-compatible) ───────────────────────


def _evaluate_window(
    individual,
    toolbox,
    df_window: pd.DataFrame,
    oos_start_idx: int,
    freq: str,
    init_cash: float,
    fees: float,
) -> float | None:
    """Evaluate a single GP tree on one walk-forward window.

    The full window (including burn-in) is passed through ``set_context``
    so that indicators warm up properly, but only the OOS portion
    (from ``oos_start_idx`` onward) is scored.

    Returns the OOS Sharpe ratio, 0.0 if < 1 trade in OOS, or None on error.
    """
    # Set data context for the full window (burn-in + OOS)
    set_context(df_window)

    func = toolbox.compile(expr=individual)
    signal = func

    signal = _resolve(signal)
    if not isinstance(signal, pd.Series):
        return None

    signal = signal.astype(bool)

    # Slice to OOS only for signal checks and backtesting
    signal_oos = signal.iloc[oos_start_idx:]
    price_oos = df_window["Close"].iloc[oos_start_idx:]

    # Safety checks on OOS portion
    n_signals = signal_oos.sum()
    if n_signals < 2 or n_signals > len(signal_oos) * 0.8:
        return None

    # Build entry/exit on OOS slice
    entries = signal_oos & ~signal_oos.shift(1).infer_objects(copy=False).fillna(False)
    exits = ~signal_oos & signal_oos.shift(1).infer_objects(copy=False).fillna(True)

    portfolio = vbt.Portfolio.from_signals(
        price_oos, entries=entries, exits=exits,
        init_cash=init_cash, fees=fees, freq=freq,
    )

    n_trades = portfolio.trades.count()
    if n_trades < 1:
        return 0.0

    sharpe = portfolio.sharpe_ratio()
    if np.isnan(sharpe) or np.isinf(sharpe):
        return 0.0

    return float(sharpe)


def evaluate_tree(
    individual,
    toolbox,
    df: pd.DataFrame,
    freq: str,
    init_cash: float = 10_000,
    fees: float = 0.001,
    complexity_penalty: float = 0.01,
    n_splits: int = 3,
    train_pct: float = 0.7,
) -> tuple[float,]:
    """Evaluate a GP individual's fitness using walk-forward analysis.

    This is the **single-tree** evaluator (backward-compatible).  The tree
    produces a boolean signal; entries are rising edges, exits are falling
    edges of that signal.

    The training DataFrame is split into ``n_splits`` rolling windows.
    For each window the first ``train_pct`` of data is used as indicator
    burn-in and only the remaining out-of-sample portion is scored.
    The final fitness is the **mean OOS Sharpe** across all windows,
    minus a complexity penalty.

    Args:
        individual: DEAP GP tree.
        toolbox: DEAP toolbox (with compile method).
        df: OHLCV DataFrame for the evaluation period.
        freq: VectorBT frequency string.
        init_cash: Starting capital.
        fees: Commission per trade.
        complexity_penalty: Sharpe penalty per tree node (anti-overfitting).
        n_splits: Number of walk-forward splits.
        train_pct: Fraction of each window used for indicator burn-in
                   (not scored).

    Returns:
        Tuple of (adjusted_score,) — DEAP expects a tuple.
    """
    try:
        splits = _walk_forward_splits(len(df), n_splits, train_pct)
        if not splits:
            return (-999.0,)

        oos_sharpes: list[float] = []
        valid_windows = 0

        for start, split, end in splits:
            df_window = df.iloc[start:end]
            oos_start_idx = split - start  # relative index within df_window

            result = _evaluate_window(
                individual, toolbox, df_window, oos_start_idx,
                freq, init_cash, fees,
            )
            if result is None:
                # Window produced no usable signal — skip it entirely
                continue

            valid_windows += 1
            oos_sharpes.append(result)

        # Need at least one valid window to produce a score
        if valid_windows == 0:
            return (-999.0,)

        mean_sharpe = float(np.mean(oos_sharpes))

        # Penalty for tree complexity (nesting + missing price data + base size)
        penalty = tree_complexity_score(individual) * complexity_penalty

        adjusted_score = mean_sharpe - penalty

        return (adjusted_score,)

    except Exception:
        return (-999.0,)


def decode_strategy(individual, toolbox, df: pd.DataFrame, freq: str,
                    init_cash: float = 10_000, fees: float = 0.001) -> dict:
    """Decode a single GP tree into human-readable strategy info + full backtest results."""
    set_context(df)
    func = toolbox.compile(expr=individual)
    signal = func

    signal = _resolve(signal)
    if not isinstance(signal, pd.Series):
        return {"error": "Non-series output"}

    signal = signal.astype(bool)
    price = df["Close"]

    entries = signal & ~signal.shift(1).infer_objects(copy=False).fillna(False)
    exits = ~signal & signal.shift(1).infer_objects(copy=False).fillna(True)

    portfolio = vbt.Portfolio.from_signals(
        price, entries=entries, exits=exits,
        init_cash=init_cash, fees=fees, freq=freq,
    )

    return {
        "expression": str(individual),
        "tree_size": len(individual),
        "tree_depth": individual.height,
        "total_return": portfolio.total_return(),
        "sharpe_ratio": portfolio.sharpe_ratio(),
        "sortino_ratio": portfolio.sortino_ratio(),
        "max_drawdown": portfolio.max_drawdown(),
        "n_trades": portfolio.trades.count(),
        "win_rate": portfolio.trades.win_rate(),
        "profit_factor": portfolio.trades.profit_factor(),
        "portfolio": portfolio,
        "entries": entries,
        "exits": exits,
        "price": price,
    }


# ── Pair evaluation (separate entry tree + exit tree) ──────────────────


def _evaluate_window_pair(
    entry_tree,
    exit_tree,
    toolbox,
    df_window: pd.DataFrame,
    oos_start_idx: int,
    freq: str,
    init_cash: float,
    fees: float,
) -> float | None:
    """Evaluate an entry/exit GP tree pair on one walk-forward window.

    The full window (including burn-in) is passed through ``set_context``
    so that indicators warm up properly, but only the OOS portion
    (from ``oos_start_idx`` onward) is scored.

    Entry signals are the rising edges of the entry tree's boolean output.
    Exit signals are the rising edges of the exit tree's boolean output.

    Returns the OOS Sharpe ratio, 0.0 if < 1 trade in OOS, or None on error.
    """
    # Set data context for the full window (burn-in + OOS)
    set_context(df_window)

    # Compile both trees
    entry_func = toolbox.compile(expr=entry_tree)
    exit_func = toolbox.compile(expr=exit_tree)

    # Resolve sentinel values to actual Series
    entry_signal = _resolve(entry_func)
    exit_signal = _resolve(exit_func)

    if not isinstance(entry_signal, pd.Series) or not isinstance(exit_signal, pd.Series):
        return None

    entry_signal = entry_signal.astype(bool)
    exit_signal = exit_signal.astype(bool)

    # Slice to OOS only
    entry_oos = entry_signal.iloc[oos_start_idx:]
    exit_oos = exit_signal.iloc[oos_start_idx:]
    price_oos = df_window["Close"].iloc[oos_start_idx:]

    # Rising edges: signal transitions from False -> True
    entries = entry_oos & ~entry_oos.shift(1).infer_objects(copy=False).fillna(False)
    exits = exit_oos & ~exit_oos.shift(1).infer_objects(copy=False).fillna(False)

    # Need at least 2 entry signals to form a meaningful strategy
    if entries.sum() < 2:
        return None

    portfolio = vbt.Portfolio.from_signals(
        price_oos, entries=entries, exits=exits,
        init_cash=init_cash, fees=fees, freq=freq,
    )

    n_trades = portfolio.trades.count()
    if n_trades < 1:
        return 0.0

    sharpe = portfolio.sharpe_ratio()
    if np.isnan(sharpe) or np.isinf(sharpe):
        return 0.0

    return float(sharpe)


def evaluate_pair(
    entry_tree,
    exit_tree,
    toolbox,
    df: pd.DataFrame,
    freq: str,
    init_cash: float = 10_000,
    fees: float = 0.001,
    complexity_penalty: float = 0.05,
    n_splits: int = 3,
    train_pct: float = 0.7,
) -> tuple[float,]:
    """Evaluate a pair of GP trees (entry + exit) using walk-forward analysis.

    Each tree independently produces a boolean signal.  Entry signals are
    the rising edges of the entry tree output; exit signals are the rising
    edges of the exit tree output.  This allows the GP to evolve separate
    logic for when to open vs. close positions.

    The training DataFrame is split into ``n_splits`` rolling windows.
    For each window the first ``train_pct`` of data is used as indicator
    burn-in and only the remaining out-of-sample portion is scored.
    The final fitness is the **mean OOS Sharpe** across all windows,
    minus a combined complexity penalty from both trees.

    Args:
        entry_tree: DEAP GP tree for entry signals.
        exit_tree: DEAP GP tree for exit signals.
        toolbox: DEAP toolbox (with compile method).
        df: OHLCV DataFrame for the evaluation period.
        freq: VectorBT frequency string.
        init_cash: Starting capital.
        fees: Commission per trade.
        complexity_penalty: Sharpe penalty per complexity point
                            (anti-overfitting).
        n_splits: Number of walk-forward splits.
        train_pct: Fraction of each window used for indicator burn-in
                   (not scored).

    Returns:
        Tuple of (adjusted_score,) — DEAP expects a tuple.
    """
    try:
        splits = _walk_forward_splits(len(df), n_splits, train_pct)
        if not splits:
            return (-999.0,)

        oos_sharpes: list[float] = []
        valid_windows = 0

        for start, split, end in splits:
            df_window = df.iloc[start:end]
            oos_start_idx = split - start  # relative index within df_window

            result = _evaluate_window_pair(
                entry_tree, exit_tree, toolbox, df_window,
                oos_start_idx, freq, init_cash, fees,
            )
            if result is None:
                continue

            valid_windows += 1
            oos_sharpes.append(result)

        if valid_windows == 0:
            return (-999.0,)

        mean_sharpe = float(np.mean(oos_sharpes))

        # Combined complexity penalty from both trees
        penalty = (
            tree_complexity_score(entry_tree) + tree_complexity_score(exit_tree)
        ) * complexity_penalty

        adjusted_score = mean_sharpe - penalty

        return (adjusted_score,)

    except Exception:
        return (-999.0,)


def decode_pair(
    entry_tree,
    exit_tree,
    toolbox,
    df: pd.DataFrame,
    freq: str,
    init_cash: float = 10_000,
    fees: float = 0.001,
) -> dict:
    """Decode an entry/exit GP tree pair into strategy info + full backtest results.

    Unlike ``decode_strategy`` (single tree), this uses separate trees for
    entry and exit signals.  Both are compiled and their rising edges are
    used as entry/exit triggers.

    Returns a dict with expressions, tree sizes, performance metrics,
    and the portfolio / signal objects needed for plotting.
    """
    set_context(df)

    entry_func = toolbox.compile(expr=entry_tree)
    exit_func = toolbox.compile(expr=exit_tree)

    entry_signal = _resolve(entry_func)
    exit_signal = _resolve(exit_func)

    if not isinstance(entry_signal, pd.Series) or not isinstance(exit_signal, pd.Series):
        return {"error": "Non-series output from entry or exit tree"}

    entry_signal = entry_signal.astype(bool)
    exit_signal = exit_signal.astype(bool)
    price = df["Close"]

    # Rising edges for both signals
    entries = entry_signal & ~entry_signal.shift(1).infer_objects(copy=False).fillna(False)
    exits = exit_signal & ~exit_signal.shift(1).infer_objects(copy=False).fillna(False)

    portfolio = vbt.Portfolio.from_signals(
        price, entries=entries, exits=exits,
        init_cash=init_cash, fees=fees, freq=freq,
    )

    return {
        "entry_expression": str(entry_tree),
        "exit_expression": str(exit_tree),
        "entry_tree_size": len(entry_tree),
        "exit_tree_size": len(exit_tree),
        "entry_tree_depth": entry_tree.height,
        "exit_tree_depth": exit_tree.height,
        "total_return": portfolio.total_return(),
        "sharpe_ratio": portfolio.sharpe_ratio(),
        "sortino_ratio": portfolio.sortino_ratio(),
        "max_drawdown": portfolio.max_drawdown(),
        "n_trades": portfolio.trades.count(),
        "win_rate": portfolio.trades.win_rate(),
        "profit_factor": portfolio.trades.profit_factor(),
        "portfolio": portfolio,
        "entries": entries,
        "exits": exits,
        "price": price,
    }
