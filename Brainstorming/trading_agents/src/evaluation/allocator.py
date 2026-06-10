"""
Temporal multi-strategy allocator — dynamic strategy weighting by regime and performance.

Combines multiple strategies into a single portfolio by assigning weights
that shift over time based on:
  - **Regime affinity**: each strategy declares how well it works per regime
  - **Rolling performance**: strategies that performed well recently get more weight
  - **Drawdown penalty**: strategies in significant drawdown are down-weighted

Usage:
    from src.evaluation.allocator import StrategyPerformance, allocate_portfolio
    from src.evaluation.regime import compute_regime_series

    regime_df = compute_regime_series(ohlcv_df)
    result = allocate_portfolio(strategies, regime_df["regime"])
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.evaluation.regime import Regime


# ── Default regime affinities per strategy type ──────────────────

DEFAULT_AFFINITIES: dict[str, dict[str, float]] = {
    "ma_crossover": {"trending": 0.7, "reverting": 0.1, "uncertain": 0.2},
    "rsi_bb": {"trending": 0.1, "reverting": 0.7, "uncertain": 0.2},
    "adaptive": {"trending": 0.5, "reverting": 0.3, "uncertain": 0.2},
    "gp_evolved": {"trending": 0.4, "reverting": 0.4, "uncertain": 0.2},
}


# ── Data structures ──────────────────────────────────────────────


@dataclass
class StrategyPerformance:
    """Container for a single strategy's backtest results and regime preferences."""

    name: str
    portfolio_value: pd.Series       # daily portfolio value
    entries: pd.Series               # boolean entry signals
    exits: pd.Series                 # boolean exit signals
    regime_affinity: dict[str, float] = field(default_factory=dict)
    # e.g., {"trending": 0.8, "reverting": 0.1, "uncertain": 0.1}


# ── Rolling performance helpers ──────────────────────────────────


def compute_rolling_sharpe(values: pd.Series, window: int = 60) -> pd.Series:
    """Compute rolling annualized Sharpe ratio over a window.

    Args:
        values: Portfolio value series (not returns).
        window: Lookback window in periods.

    Returns:
        Rolling Sharpe ratio series (NaN where insufficient data).
    """
    returns = values.pct_change().fillna(0.0)
    rolling_mean = returns.rolling(window=window, min_periods=max(1, window // 2)).mean()
    rolling_std = returns.rolling(window=window, min_periods=max(1, window // 2)).std()

    # Avoid division by zero — treat zero-volatility windows as zero Sharpe
    safe_std = rolling_std.replace(0.0, np.nan)
    sharpe = (rolling_mean / safe_std) * np.sqrt(252)

    return sharpe.fillna(0.0)


def _compute_drawdown_series(values: pd.Series) -> pd.Series:
    """Compute running drawdown as a fraction (0 = no drawdown, 0.3 = 30% down from peak)."""
    running_max = values.cummax()
    drawdown = (running_max - values) / running_max
    return drawdown.fillna(0.0)


# ── Core allocation logic ────────────────────────────────────────


def compute_regime_weights(
    regime_series: pd.Series,
    strategies: list[StrategyPerformance],
) -> pd.DataFrame:
    """Compute per-day strategy weights based on regime, performance, and drawdown.

    For each day, the weight of each strategy is determined by:
      - **Base weight** (50%): regime affinity of the strategy for the current regime
      - **Performance weight** (30%): relative rolling Sharpe ratio
      - **Drawdown penalty** (20%): penalizes strategies in drawdown > 10%

    Args:
        regime_series: Series of Regime enum values, indexed by date.
        strategies: List of StrategyPerformance objects.

    Returns:
        DataFrame with columns = strategy names, index = dates, values = weights
        (rows sum to 1.0).
    """
    if len(strategies) == 0:
        return pd.DataFrame(index=regime_series.index)

    # Short-circuit: single strategy gets weight 1.0 everywhere
    if len(strategies) == 1:
        return pd.DataFrame(
            {strategies[0].name: 1.0},
            index=regime_series.index,
        )

    # Align all series to the regime index
    common_index = regime_series.index
    n_strats = len(strategies)
    strat_names = [s.name for s in strategies]

    # Pre-compute rolling Sharpe and drawdown for each strategy
    rolling_sharpes: dict[str, pd.Series] = {}
    drawdowns: dict[str, pd.Series] = {}

    for strat in strategies:
        # Reindex portfolio value to common index, forward-filling gaps
        pv = strat.portfolio_value.reindex(common_index).ffill().bfill()
        pv = pv.fillna(pv.iloc[0] if len(pv) > 0 else 0.0)

        rolling_sharpes[strat.name] = compute_rolling_sharpe(pv)
        drawdowns[strat.name] = _compute_drawdown_series(pv)

    # Build weight arrays
    weights = pd.DataFrame(0.0, index=common_index, columns=strat_names)

    # Vectorize regime affinity lookup
    regime_values = regime_series.values

    for i, date in enumerate(common_index):
        regime = regime_values[i]

        # Resolve regime to string key
        if isinstance(regime, Regime):
            regime_key = regime.value
        else:
            regime_key = str(regime)

        # ---- Base weights from regime affinity (50%) ----
        base_weights = np.zeros(n_strats)
        for j, strat in enumerate(strategies):
            affinity = strat.regime_affinity
            base_weights[j] = affinity.get(regime_key, 1.0 / n_strats)

        # Normalize base weights to sum to 1
        base_sum = base_weights.sum()
        if base_sum > 0:
            base_weights /= base_sum
        else:
            base_weights[:] = 1.0 / n_strats

        # ---- Performance weights from rolling Sharpe (30%) ----
        perf_raw = np.zeros(n_strats)
        for j, strat in enumerate(strategies):
            sharpe_val = rolling_sharpes[strat.name].iloc[i]
            perf_raw[j] = max(0.0, sharpe_val)

        perf_sum = perf_raw.sum()
        if perf_sum > 0:
            perf_weights = perf_raw / perf_sum
        else:
            # All strategies have non-positive Sharpe — equal weight
            perf_weights = np.ones(n_strats) / n_strats

        # ---- Drawdown penalty (20%) ----
        dd_penalty = np.zeros(n_strats)
        for j, strat in enumerate(strategies):
            dd = drawdowns[strat.name].iloc[i]
            if dd < 0.10:
                dd_penalty[j] = 1.0
            else:
                dd_penalty[j] = max(0.1, 1.0 - dd * 2.0)

        # ---- Combine: 50% base + 30% perf + 20% dd_penalty ----
        raw = 0.5 * base_weights + 0.3 * perf_weights + 0.2 * dd_penalty

        # Normalize to sum to 1
        raw_sum = raw.sum()
        if raw_sum > 0:
            normalized = raw / raw_sum
        else:
            normalized = np.ones(n_strats) / n_strats

        weights.iloc[i] = normalized

    return weights


# ── Portfolio allocation ─────────────────────────────────────────


def allocate_portfolio(
    strategies: list[StrategyPerformance],
    regime_series: pd.Series,
    init_cash: float = 10_000,
) -> dict:
    """Combine multiple strategies into a single portfolio using dynamic weights.

    The combined portfolio value is built from weighted daily returns:
        combined_return[t] = sum(weight[strat][t] * daily_return[strat][t])
        combined_value = init_cash * cumprod(1 + combined_returns)

    Args:
        strategies: List of StrategyPerformance objects.
        regime_series: Series of Regime enum values, indexed by date.
        init_cash: Starting capital for the combined portfolio.

    Returns:
        Dict with keys:
            - combined_value: pd.Series of combined portfolio value
            - weights_over_time: pd.DataFrame of strategy weights over time
            - strategy_values: dict mapping strategy name to its portfolio value
            - regime_series: the input regime series (for downstream plotting)
            - metrics: dict with total_return, max_drawdown, exposure_pct,
              regime_distribution
    """
    if len(strategies) == 0:
        return {
            "combined_value": pd.Series(dtype=float),
            "weights_over_time": pd.DataFrame(),
            "strategy_values": {},
            "regime_series": regime_series,
            "metrics": {
                "total_return": 0.0,
                "max_drawdown": 0.0,
                "exposure_pct": 0.0,
                "regime_distribution": {"trending": 0.0, "reverting": 0.0, "uncertain": 0.0},
            },
        }

    common_index = regime_series.index

    # Compute dynamic weights
    weights_df = compute_regime_weights(regime_series, strategies)

    # Compute daily returns for each strategy, aligned to common index
    strat_returns: dict[str, pd.Series] = {}
    strat_values: dict[str, pd.Series] = {}

    for strat in strategies:
        pv = strat.portfolio_value.reindex(common_index).ffill().bfill()
        pv = pv.fillna(pv.iloc[0] if len(pv) > 0 else 0.0)
        strat_values[strat.name] = pv
        strat_returns[strat.name] = pv.pct_change().fillna(0.0)

    # Build combined daily returns as weighted sum
    combined_returns = pd.Series(0.0, index=common_index)
    for strat in strategies:
        combined_returns += weights_df[strat.name] * strat_returns[strat.name]

    # Build combined portfolio value
    combined_value = init_cash * (1 + combined_returns).cumprod()

    # ---- Metrics ----
    total_return = (combined_value.iloc[-1] / init_cash - 1.0) if len(combined_value) > 0 else 0.0

    dd_series = _compute_drawdown_series(combined_value)
    max_drawdown = dd_series.max() if len(dd_series) > 0 else 0.0

    # Exposure: % of days with at least one strategy having an active position
    # Approximate by checking if any strategy has entries without subsequent exits
    exposure_flags = pd.Series(False, index=common_index)
    for strat in strategies:
        entries_aligned = strat.entries.reindex(common_index).fillna(False).astype(bool)
        exits_aligned = strat.exits.reindex(common_index).fillna(False).astype(bool)

        # Build position state: enter on entry signal, exit on exit signal
        in_position = pd.Series(False, index=common_index)
        currently_in = False
        for i in range(len(common_index)):
            if entries_aligned.iloc[i]:
                currently_in = True
            if exits_aligned.iloc[i]:
                currently_in = False
            in_position.iloc[i] = currently_in

        exposure_flags = exposure_flags | in_position

    exposure_pct = exposure_flags.mean() if len(exposure_flags) > 0 else 0.0

    # Regime distribution
    regime_dist: dict[str, float] = {"trending": 0.0, "reverting": 0.0, "uncertain": 0.0}
    n_total = len(regime_series)
    if n_total > 0:
        for regime_val in regime_series.values:
            if isinstance(regime_val, Regime):
                key = regime_val.value
            else:
                key = str(regime_val)
            if key in regime_dist:
                regime_dist[key] += 1.0
        for key in regime_dist:
            regime_dist[key] /= n_total

    return {
        "combined_value": combined_value,
        "weights_over_time": weights_df,
        "strategy_values": strat_values,
        "regime_series": regime_series,
        "metrics": {
            "total_return": float(total_return),
            "max_drawdown": float(max_drawdown),
            "exposure_pct": float(exposure_pct),
            "regime_distribution": regime_dist,
        },
    }
