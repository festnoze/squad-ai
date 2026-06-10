"""
Monte Carlo permutation tests for strategy validation.

Determines whether a strategy's observed performance is statistically
significant or merely the result of luck / noise.  Three independent tests
are provided:

1. **Permutation test** -- shuffles daily returns to build a null
   distribution of Sharpe ratios and checks where the real Sharpe falls.
2. **Bootstrap confidence intervals** -- resamples returns with
   replacement to estimate confidence intervals for key metrics.
3. **Random entry test** -- generates random entry/exit signals on the
   same price data and compares the strategy against the resulting
   distribution of random-trader outcomes.

A convenience ``full_validation`` function runs all three tests and
returns a combined verdict.

Standalone module: no GP / DEAP imports required.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt  # type: ignore[import-untyped]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_sharpe(returns: np.ndarray, ann_factor: float = 252.0) -> float:
    """Compute annualised Sharpe from a 1-D array of daily returns.

    Returns 0.0 when the standard deviation is zero or the result is
    non-finite (NaN / Inf).
    """
    if len(returns) < 2:
        return 0.0
    std = float(np.std(returns, ddof=1))
    if std < 1e-15:
        return 0.0
    sharpe = float(np.mean(returns)) / std * math.sqrt(ann_factor)
    if not math.isfinite(sharpe):
        return 0.0
    return sharpe


def _safe_max_drawdown(returns: np.ndarray) -> float:
    """Compute maximum drawdown from a 1-D array of daily returns.

    Returns a *positive* number representing the peak-to-trough decline
    as a fraction (e.g. 0.15 means 15 % drawdown).  Returns 0.0 when
    the input is empty or the result is non-finite.
    """
    if len(returns) < 1:
        return 0.0
    cum = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(cum)
    dd = (peak - cum) / np.where(peak > 0, peak, 1.0)
    max_dd = float(np.max(dd))
    if not math.isfinite(max_dd):
        return 0.0
    return max_dd


def _safe_total_return(returns: np.ndarray) -> float:
    """Cumulative return from a 1-D array of daily returns."""
    if len(returns) < 1:
        return 0.0
    total = float(np.prod(1.0 + returns) - 1.0)
    if not math.isfinite(total):
        return 0.0
    return total


def _extract_daily_returns(portfolio: Any) -> np.ndarray:
    """Extract clean daily returns from a VectorBT portfolio object.

    Returns a 1-D numpy array with NaN values removed.
    """
    value = portfolio.value()
    returns = value.pct_change().dropna()
    arr = returns.values.astype(float)
    return arr[np.isfinite(arr)]


# ---------------------------------------------------------------------------
# 1. Permutation test
# ---------------------------------------------------------------------------

def permutation_test(
    portfolio: Any,
    n_simulations: int = 1000,
    seed: int = 42,
) -> dict:
    """Test whether the strategy's Sharpe ratio is statistically significant.

    Method
    ------
    1. Extract daily returns from the portfolio.
    2. Compute the real (observed) Sharpe ratio.
    3. For each of *n_simulations* iterations, randomly shuffle the daily
       returns and compute the Sharpe of the shuffled series.
    4. The p-value is the proportion of simulated Sharpes that are >= the
       real Sharpe.

    Parameters
    ----------
    portfolio : vbt.Portfolio
        A VectorBT portfolio object from a completed backtest.
    n_simulations : int
        Number of random permutations to run.
    seed : int
        Seed for ``np.random.default_rng`` for reproducibility.

    Returns
    -------
    dict
        Keys: ``real_sharpe``, ``simulated_sharpes``, ``mean_simulated``,
        ``std_simulated``, ``p_value``, ``percentile``,
        ``is_significant_95``, ``is_significant_99``.
    """
    rng = np.random.default_rng(seed)
    daily_returns = _extract_daily_returns(portfolio)

    if len(daily_returns) < 2:
        return {
            "real_sharpe": 0.0,
            "simulated_sharpes": [0.0] * n_simulations,
            "mean_simulated": 0.0,
            "std_simulated": 0.0,
            "p_value": 1.0,
            "percentile": 0.0,
            "is_significant_95": False,
            "is_significant_99": False,
        }

    real_sharpe = _safe_sharpe(daily_returns)

    simulated_sharpes: list[float] = []
    for _ in range(n_simulations):
        shuffled = rng.permutation(daily_returns)
        simulated_sharpes.append(_safe_sharpe(shuffled))

    sim_array = np.array(simulated_sharpes)
    mean_sim = float(np.mean(sim_array))
    std_sim = float(np.std(sim_array, ddof=1)) if len(sim_array) > 1 else 0.0

    # p-value: proportion of simulated Sharpes >= real Sharpe
    p_value = float(np.mean(sim_array >= real_sharpe))

    # Percentile rank of the real Sharpe in the simulated distribution
    percentile = float(np.mean(sim_array < real_sharpe) * 100.0)

    return {
        "real_sharpe": real_sharpe,
        "simulated_sharpes": simulated_sharpes,
        "mean_simulated": mean_sim,
        "std_simulated": std_sim,
        "p_value": p_value,
        "percentile": percentile,
        "is_significant_95": p_value < 0.05,
        "is_significant_99": p_value < 0.01,
    }


# ---------------------------------------------------------------------------
# 2. Bootstrap confidence intervals
# ---------------------------------------------------------------------------

def bootstrap_confidence_interval(
    portfolio: Any,
    n_bootstraps: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
) -> dict:
    """Compute bootstrap confidence intervals for key performance metrics.

    Method
    ------
    1. Extract daily returns from the portfolio.
    2. For each bootstrap iteration, resample the returns *with replacement*
       (same length as the original).
    3. For each resampled series, compute cumulative return, Sharpe ratio,
       and maximum drawdown.
    4. Compute the confidence interval from the distribution of each metric.

    Parameters
    ----------
    portfolio : vbt.Portfolio
        A VectorBT portfolio object from a completed backtest.
    n_bootstraps : int
        Number of bootstrap resamples.
    confidence : float
        Confidence level, e.g. 0.95 for a 95 % interval.
    seed : int
        Seed for ``np.random.default_rng`` for reproducibility.

    Returns
    -------
    dict
        Keys: ``total_return``, ``sharpe_ratio``, ``max_drawdown`` (each a
        dict with ``lower``, ``upper``, ``median``), and
        ``confidence_level``.
    """
    rng = np.random.default_rng(seed)
    daily_returns = _extract_daily_returns(portfolio)

    if len(daily_returns) < 2:
        empty_ci = {"lower": 0.0, "upper": 0.0, "median": 0.0}
        return {
            "total_return": empty_ci.copy(),
            "sharpe_ratio": empty_ci.copy(),
            "max_drawdown": empty_ci.copy(),
            "confidence_level": confidence,
        }

    alpha = 1.0 - confidence
    lower_pct = (alpha / 2.0) * 100.0
    upper_pct = (1.0 - alpha / 2.0) * 100.0

    boot_returns: list[float] = []
    boot_sharpes: list[float] = []
    boot_dds: list[float] = []

    n = len(daily_returns)
    for _ in range(n_bootstraps):
        indices = rng.integers(0, n, size=n)
        resampled = daily_returns[indices]

        boot_returns.append(_safe_total_return(resampled))
        boot_sharpes.append(_safe_sharpe(resampled))
        boot_dds.append(_safe_max_drawdown(resampled))

    def _ci(values: list[float]) -> dict[str, float]:
        arr = np.array(values)
        return {
            "lower": float(np.percentile(arr, lower_pct)),
            "upper": float(np.percentile(arr, upper_pct)),
            "median": float(np.median(arr)),
        }

    return {
        "total_return": _ci(boot_returns),
        "sharpe_ratio": _ci(boot_sharpes),
        "max_drawdown": _ci(boot_dds),
        "confidence_level": confidence,
    }


# ---------------------------------------------------------------------------
# 3. Random entry test
# ---------------------------------------------------------------------------

def random_entry_test(
    price: pd.Series,
    n_trades: int,
    avg_holding_period: int,
    n_simulations: int = 1000,
    init_cash: float = 10_000,
    fees: float = 0.001,
    freq: str = "1D",
    seed: int = 42,
) -> dict:
    """Compare the strategy against randomly timed entry/exit signals.

    For each simulation, ``n_trades`` random entry dates are generated.
    Each trade is held for approximately ``avg_holding_period`` bars (with
    a small random perturbation of +/- 30 %).  A VectorBT backtest is run
    with these random signals, and the resulting Sharpe ratio, total
    return, and max drawdown are recorded.

    Parameters
    ----------
    price : pd.Series
        Close-price series used for backtesting.
    n_trades : int
        Number of trades the real strategy made (we match this count).
    avg_holding_period : int
        Average number of bars per trade in the real strategy.
    n_simulations : int
        Number of random-entry simulations.
    init_cash : float
        Starting capital for each simulation.
    fees : float
        Transaction fee rate per trade.
    freq : str
        Data frequency string (e.g. ``"1D"``, ``"1h"``).
    seed : int
        Seed for ``np.random.default_rng`` for reproducibility.

    Returns
    -------
    dict
        Distribution statistics for the random traders plus p-values
        comparing the random distribution against the real strategy.
        Note: ``p_value_return`` and ``p_value_sharpe`` are set to 1.0
        here -- the caller (``full_validation``) fills them in using the
        real portfolio's metrics.
    """
    rng = np.random.default_rng(seed)
    n_bars = len(price)

    if n_bars < 5 or n_trades < 1 or avg_holding_period < 1:
        return {
            "n_simulations": n_simulations,
            "n_trades": n_trades,
            "avg_holding_period": avg_holding_period,
            "random_returns": [0.0] * n_simulations,
            "random_sharpes": [0.0] * n_simulations,
            "random_max_dds": [0.0] * n_simulations,
            "mean_random_return": 0.0,
            "mean_random_sharpe": 0.0,
            "p_value_return": 1.0,
            "p_value_sharpe": 1.0,
        }

    # Leave enough room at the end for the holding period
    max_entry_bar = max(1, n_bars - avg_holding_period - 1)

    random_returns: list[float] = []
    random_sharpes: list[float] = []
    random_max_dds: list[float] = []

    for _ in range(n_simulations):
        entries = pd.Series(False, index=price.index)
        exits = pd.Series(False, index=price.index)

        # Pick random, non-overlapping trade windows
        used_bars: set[int] = set()
        trades_placed = 0

        for _attempt in range(n_trades * 5):
            if trades_placed >= n_trades:
                break

            entry_bar = rng.integers(0, max_entry_bar)

            # Randomise holding period by +/- 30 %
            jitter = rng.uniform(0.7, 1.3)
            hold = max(1, int(avg_holding_period * jitter))
            exit_bar = min(entry_bar + hold, n_bars - 1)

            # Check for overlap with existing trades
            trade_range = set(range(entry_bar, exit_bar + 1))
            if trade_range & used_bars:
                continue

            entries.iloc[entry_bar] = True
            exits.iloc[exit_bar] = True
            used_bars.update(trade_range)
            trades_placed += 1

        # Run backtest with random signals
        try:
            pf = vbt.Portfolio.from_signals(
                price,
                entries=entries,
                exits=exits,
                init_cash=init_cash,
                fees=fees,
                freq=freq,
            )
            ret = float(pf.total_return())
            sharpe = float(pf.sharpe_ratio())
            max_dd = float(pf.max_drawdown())

            # Sanitise non-finite values
            if not math.isfinite(ret):
                ret = 0.0
            if not math.isfinite(sharpe):
                sharpe = 0.0
            if not math.isfinite(max_dd):
                max_dd = 0.0

            random_returns.append(ret)
            random_sharpes.append(sharpe)
            random_max_dds.append(abs(max_dd))
        except Exception:
            random_returns.append(0.0)
            random_sharpes.append(0.0)
            random_max_dds.append(0.0)

    return {
        "n_simulations": n_simulations,
        "n_trades": n_trades,
        "avg_holding_period": avg_holding_period,
        "random_returns": random_returns,
        "random_sharpes": random_sharpes,
        "random_max_dds": random_max_dds,
        "mean_random_return": float(np.mean(random_returns)),
        "mean_random_sharpe": float(np.mean(random_sharpes)),
        # p-values are computed by the caller against the real strategy
        "p_value_return": 1.0,
        "p_value_sharpe": 1.0,
    }


# ---------------------------------------------------------------------------
# 4. Full validation
# ---------------------------------------------------------------------------

def full_validation(
    portfolio: Any,
    price: pd.Series,
    n_simulations: int = 500,
    seed: int = 42,
) -> dict:
    """Run all three Monte Carlo tests and return a combined validation report.

    Extracts the number of trades and average holding period from the
    portfolio, then delegates to :func:`permutation_test`,
    :func:`bootstrap_confidence_interval`, and :func:`random_entry_test`.

    Parameters
    ----------
    portfolio : vbt.Portfolio
        A VectorBT portfolio object from a completed backtest.
    price : pd.Series
        Close-price series used for the backtest.
    n_simulations : int
        Number of simulations for each sub-test.
    seed : int
        Seed for ``np.random.default_rng`` for reproducibility.

    Returns
    -------
    dict
        Keys: ``permutation``, ``bootstrap``, ``random_entry``,
        ``verdict`` (one of ``"SIGNIFICANT"``, ``"MARGINAL"``,
        ``"NOT_SIGNIFICANT"``), and ``summary`` (a human-readable
        explanation).
    """
    # --- Extract trade statistics from the portfolio -----------------------
    try:
        n_trades = int(portfolio.trades.count())
    except Exception:
        n_trades = 0

    try:
        # Average trade duration in bars
        durations = portfolio.trades.duration
        if hasattr(durations, "mean"):
            avg_holding = max(1, int(durations.mean()))
        else:
            avg_holding = 5  # sensible fallback
    except Exception:
        avg_holding = 5

    # --- Run each test with different sub-seeds for independence -----------
    perm_result = permutation_test(portfolio, n_simulations, seed=seed)
    boot_result = bootstrap_confidence_interval(
        portfolio, n_simulations, seed=seed + 1,
    )
    random_result = random_entry_test(
        price, n_trades, avg_holding, n_simulations,
        seed=seed + 2,
    )

    # --- Compute p-values for the random entry test -----------------------
    real_return = _safe_total_return(_extract_daily_returns(portfolio))
    real_sharpe = perm_result["real_sharpe"]

    random_returns_arr = np.array(random_result["random_returns"])
    random_sharpes_arr = np.array(random_result["random_sharpes"])

    random_result["p_value_return"] = float(
        np.mean(random_returns_arr >= real_return),
    )
    random_result["p_value_sharpe"] = float(
        np.mean(random_sharpes_arr >= real_sharpe),
    )

    # --- Determine verdict ------------------------------------------------
    perm_p = perm_result["p_value"]
    rand_sharpe_p = random_result["p_value_sharpe"]

    if perm_p < 0.05 and rand_sharpe_p < 0.10:
        verdict = "SIGNIFICANT"
    elif perm_p < 0.10 or rand_sharpe_p < 0.20:
        verdict = "MARGINAL"
    else:
        verdict = "NOT_SIGNIFICANT"

    # --- Build human-readable summary -------------------------------------
    summary_lines = [
        f"Permutation test: p-value = {perm_p:.4f} "
        f"({'significant at 5%' if perm_result['is_significant_95'] else 'not significant at 5%'})",
        f"  Real Sharpe: {real_sharpe:.3f} | "
        f"Mean simulated: {perm_result['mean_simulated']:.3f} +/- {perm_result['std_simulated']:.3f} | "
        f"Percentile: {perm_result['percentile']:.1f}%",
        f"Bootstrap 95% CI for Sharpe: "
        f"[{boot_result['sharpe_ratio']['lower']:.3f}, "
        f"{boot_result['sharpe_ratio']['upper']:.3f}]",
        f"Random entry test: "
        f"p_sharpe = {rand_sharpe_p:.4f}, p_return = {random_result['p_value_return']:.4f}",
        f"  Strategy beats {(1 - rand_sharpe_p) * 100:.0f}% of random traders (Sharpe)",
        f"Verdict: {verdict}",
    ]
    summary = "\n".join(summary_lines)

    return {
        "permutation": perm_result,
        "bootstrap": boot_result,
        "random_entry": random_result,
        "verdict": verdict,
        "summary": summary,
    }
