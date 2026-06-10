"""
Risk-adjusted strategy scoring -- composite score favouring high returns
with minimal drawdown exposure.

A strategy that earns 50 % with -10 % max DD beats one that earns 100 %
with -60 % max DD.  The composite score rewards *efficiency* (return per
unit of market exposure) and *stability* (short drawdown periods, high
win rate, strong profit factor).

Standalone module: no DEAP / GP imports required.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Default composite-score weights
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, float] = {
    "return_score": 0.25,      # Higher return = better
    "risk_score": 0.30,        # Lower drawdown + better ratios = better
    "efficiency_score": 0.25,  # More return per unit of exposure = better
    "stability_score": 0.20,   # Consistent returns, low underwater time = better
}


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


def _dd_duration_days(portfolio: Any) -> float:
    """Max drawdown duration in calendar days.

    Uses the drawdown series to find the longest contiguous stretch where the
    portfolio stayed below its previous peak.
    """
    try:
        value = portfolio.value()
        peak = value.cummax()
        in_dd = value < peak

        if not in_dd.any():
            return 0.0

        # Group consecutive drawdown bars and find the longest run
        groups = (~in_dd).cumsum()
        dd_groups = groups[in_dd]

        if dd_groups.empty:
            return 0.0

        longest = 0.0
        for _, grp in dd_groups.groupby(dd_groups):
            start = grp.index[0]
            end = grp.index[-1]
            # Try to compute calendar-day difference
            try:
                delta = (pd.Timestamp(end) - pd.Timestamp(start)).days
            except Exception:
                delta = len(grp)
            if delta > longest:
                longest = delta

        return float(longest)
    except Exception:
        return 0.0


def _compute_exposure(portfolio: Any) -> float:
    """Percentage of bars where the portfolio holds a position (not 100 % cash).

    Compares portfolio value to the value it would have if sitting in cash
    the whole time.  When the portfolio has open positions its value diverges
    from the pure-cash line.  Alternatively, uses position records if
    available.
    """
    try:
        # VectorBT tracks asset value -- when > 0, we are "in market"
        asset_value = portfolio.asset_value()
        if isinstance(asset_value, pd.DataFrame):
            asset_value = asset_value.iloc[:, 0]
        in_market = asset_value.abs() > 1e-10
        return float(in_market.mean())
    except Exception:
        return 0.0


def _compute_underwater_pct(portfolio: Any) -> float:
    """Percentage of bars where the portfolio is in drawdown > 5 % below peak."""
    try:
        value = portfolio.value()
        peak = value.cummax()
        drawdown = (value - peak) / peak  # negative when underwater
        deep_dd = drawdown < -0.05
        return float(deep_dd.mean())
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_risk_metrics(portfolio: Any) -> dict[str, float]:
    """Extract comprehensive risk / return metrics from a VectorBT portfolio.

    All float outputs are sanitised via ``_clean`` so that downstream code
    never has to worry about NaN or Inf.
    """
    # --- avg winning / losing trade (may not exist for every VBT version) ---
    try:
        avg_win = _clean(portfolio.trades.winning.pnl.mean())
    except Exception:
        avg_win = 0.0

    try:
        avg_loss = _clean(portfolio.trades.losing.pnl.mean())
    except Exception:
        avg_loss = 0.0

    return {
        "total_return": _clean(portfolio.total_return()),
        "sharpe_ratio": _clean(portfolio.sharpe_ratio()),
        "sortino_ratio": _clean(portfolio.sortino_ratio()),
        "calmar_ratio": _clean(portfolio.calmar_ratio()),
        "max_drawdown": abs(_clean(portfolio.max_drawdown())),
        "max_dd_duration": _dd_duration_days(portfolio),
        "n_trades": int(portfolio.trades.count()),
        "win_rate": _clean(portfolio.trades.win_rate()),
        "profit_factor": _clean(portfolio.trades.profit_factor()),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "exposure_pct": _compute_exposure(portfolio),
        "underwater_pct": _compute_underwater_pct(portfolio),
    }


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------

def _return_score(metrics: dict[str, float]) -> float:
    """Logarithmic return score, capped at 10.

    ``log(1 + max(total_return, 0)) * 10``, clamped to [0, 10].
    The log scale prevents overfitted blow-up returns from dominating.
    """
    tr = max(metrics.get("total_return", 0.0), 0.0)
    return min(math.log(1.0 + tr) * 10.0, 10.0)


def _risk_score(metrics: dict[str, float]) -> float:
    """Risk score: reward low drawdown and high risk-adjusted ratios.

    ``max(0, (1 - max_drawdown * 2)) * 5
        + min(calmar_ratio, 3)
        + min(sortino_ratio, 3)``

    A max drawdown > 50 % zeroes out the first term entirely.
    """
    dd = metrics.get("max_drawdown", 1.0)
    calmar = metrics.get("calmar_ratio", 0.0)
    sortino = metrics.get("sortino_ratio", 0.0)

    dd_component = max(0.0, (1.0 - dd * 2.0)) * 5.0
    calmar_component = min(max(calmar, 0.0), 3.0)
    sortino_component = min(max(sortino, 0.0), 3.0)

    return dd_component + calmar_component + sortino_component


def _efficiency_score(metrics: dict[str, float]) -> float:
    """Efficiency score: return per unit of market exposure.

    ``(total_return / exposure_pct) * 5`` if exposure > 0, else 0.
    Rewards strategies that achieve good returns while being in the market
    less of the time.
    """
    exposure = metrics.get("exposure_pct", 0.0)
    if exposure <= 0.0:
        return 0.0
    tr = max(metrics.get("total_return", 0.0), 0.0)
    return (tr / exposure) * 5.0


def _stability_score(metrics: dict[str, float]) -> float:
    """Stability score: consistency and predictability.

    ``(1 - underwater_pct) * 3
        + min(win_rate, 1) * 2
        + min(profit_factor / 3, 1) * 2``
    """
    underwater = metrics.get("underwater_pct", 1.0)
    win_rate = min(max(metrics.get("win_rate", 0.0), 0.0), 1.0)
    pf = max(metrics.get("profit_factor", 0.0), 0.0)

    underwater_component = (1.0 - underwater) * 3.0
    win_rate_component = win_rate * 2.0
    pf_component = min(pf / 3.0, 1.0) * 2.0

    return underwater_component + win_rate_component + pf_component


def composite_score(
    metrics: dict[str, float],
    weights: dict[str, float] | None = None,
) -> tuple[float, dict[str, float]]:
    """Compute a weighted composite score balancing return vs risk.

    Args:
        metrics: Output of :func:`compute_risk_metrics`.
        weights: Per-component weights (default ``DEFAULT_WEIGHTS``).

    Returns:
        ``(final_score, breakdown)`` where *breakdown* maps each component
        name to its raw (unweighted) value.  Typical range is 0--10.
    """
    w = weights if weights is not None else DEFAULT_WEIGHTS

    breakdown = {
        "return_score": _return_score(metrics),
        "risk_score": _risk_score(metrics),
        "efficiency_score": _efficiency_score(metrics),
        "stability_score": _stability_score(metrics),
    }

    # Weighted sum, then normalise to a 0-10 range.
    # Maximum theoretical raw = 10*(0.25) + 11*(0.30) + inf*(0.25) + 7*(0.20)
    # We cap the efficiency score contribution so the total stays bounded.
    capped_efficiency = min(breakdown["efficiency_score"], 10.0)

    raw = (
        breakdown["return_score"] * w.get("return_score", 0.25)
        + breakdown["risk_score"] * w.get("risk_score", 0.30)
        + capped_efficiency * w.get("efficiency_score", 0.25)
        + breakdown["stability_score"] * w.get("stability_score", 0.20)
    )

    # Normalise: max possible raw ~ 10*0.25 + 11*0.30 + 10*0.25 + 7*0.20
    # = 2.5 + 3.3 + 2.5 + 1.4 = 9.7  (already roughly 0-10)
    final = max(0.0, min(raw, 10.0))

    return final, breakdown


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def rank_strategies(results: list[dict]) -> list[dict]:
    """Score and rank a list of strategy results.

    Each element in *results* must contain a ``"metrics"`` key produced by
    :func:`compute_risk_metrics`.  The function **mutates** each dict in
    place, adding ``composite_score``, ``score_breakdown``, and ``rank``
    fields, then returns the list sorted best-first.

    Args:
        results: List of strategy result dicts, each with a ``"metrics"`` key.

    Returns:
        Same list, sorted descending by composite score, with ranking fields
        added.
    """
    for res in results:
        metrics = res.get("metrics", {})
        score, breakdown = composite_score(metrics)
        res["composite_score"] = score
        res["score_breakdown"] = breakdown

    # Sort descending by composite score (stable sort preserves insertion
    # order for ties)
    results.sort(key=lambda r: r["composite_score"], reverse=True)

    for rank, res in enumerate(results, start=1):
        res["rank"] = rank

    return results


# ---------------------------------------------------------------------------
# Drawdown analysis
# ---------------------------------------------------------------------------

def drawdown_analysis(portfolio: Any) -> dict:
    """Deep drawdown analysis with per-period breakdown.

    Returns
    -------
    dict with keys:
        drawdown_series : pd.Series  -- full drawdown series (negative values)
        periods         : list[dict] -- significant DD periods (> 5 % depth)
            Each period dict: {start, end, depth, duration_days, recovery_days}
        max_depth       : float      -- worst drawdown (most negative)
        avg_depth       : float      -- mean drawdown when underwater > 5 %
        time_in_drawdown_pct : float -- fraction of bars in DD > 5 %
    """
    value = portfolio.value()
    peak = value.cummax()
    drawdown = (value - peak) / peak  # 0 at peaks, negative when underwater

    in_dd = drawdown < -0.05  # significant drawdown threshold

    # --- Identify contiguous drawdown periods > 5 % -----------------------
    periods: list[dict] = []
    if in_dd.any():
        # Detect transitions into / out of deep drawdown
        shifted = in_dd.shift(1, fill_value=False)
        starts = in_dd & ~shifted    # False -> True  (entering DD)
        ends = ~in_dd & shifted      # True  -> False (exiting DD)

        start_indices = list(starts[starts].index)
        end_indices = list(ends[ends].index)

        # If we end still in drawdown, close the last period at the final bar
        if len(start_indices) > len(end_indices):
            end_indices.append(drawdown.index[-1])

        for s, e in zip(start_indices, end_indices):
            dd_slice = drawdown.loc[s:e]
            depth = float(dd_slice.min())

            try:
                duration_days = (pd.Timestamp(e) - pd.Timestamp(s)).days
            except Exception:
                duration_days = len(dd_slice)

            # Recovery: bars from deepest point to end of this DD period
            trough_idx = dd_slice.idxmin()
            try:
                recovery_days = (pd.Timestamp(e) - pd.Timestamp(trough_idx)).days
            except Exception:
                recovery_days = len(dd_slice.loc[trough_idx:])

            periods.append({
                "start": s,
                "end": e,
                "depth": depth,
                "duration_days": duration_days,
                "recovery_days": recovery_days,
            })

    return {
        "drawdown_series": drawdown,
        "periods": periods,
        "max_depth": float(drawdown.min()),
        "avg_depth": float(drawdown[in_dd].mean()) if in_dd.any() else 0.0,
        "time_in_drawdown_pct": float(in_dd.mean()),
    }
