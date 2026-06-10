"""
Market regime detector — ADX + Hurst exponent.

Classifies market into:
  - TRENDING:   strong directional movement  (ADX > 25 AND Hurst > 0.55)
  - REVERTING:  mean-reverting / range-bound  (ADX < 20 AND Hurst < 0.45)
  - UNCERTAIN:  mixed / transitional
"""

from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd


class Regime(Enum):
    TRENDING = "trending"
    REVERTING = "reverting"
    UNCERTAIN = "uncertain"


# ── ADX (Average Directional Index) ───────────────────────────

def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Compute ADX from OHLC data.

    ADX measures trend strength (0-100), not direction.
    ADX > 25 = strong trend, ADX < 20 = weak/no trend.
    """
    # True Range
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Directional Movement
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # Smoothed with Wilder's EMA (alpha = 1/window)
    atr = pd.Series(tr, index=close.index).ewm(alpha=1 / window, min_periods=window).mean()
    plus_di = 100 * pd.Series(plus_dm, index=close.index).ewm(alpha=1 / window, min_periods=window).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=close.index).ewm(alpha=1 / window, min_periods=window).mean() / atr

    # DX and ADX
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1 / window, min_periods=window).mean()

    return adx


# ── Hurst Exponent ────────────────────────────────────────────

def compute_hurst(series: pd.Series, window: int = 100, max_lag: int = 20) -> pd.Series:
    """Compute rolling Hurst exponent using variance of lagged differences.

    Uses the scaling property: Var(X(t+lag) - X(t)) ~ lag^(2H)
    More robust than R/S analysis, less biased toward H > 0.5.

    H > 0.5 = persistent (trending)
    H = 0.5 = random walk
    H < 0.5 = anti-persistent (mean-reverting)
    """
    log_prices = np.log(series)
    hurst_values = pd.Series(np.nan, index=series.index)

    values = log_prices.values
    lags = np.arange(2, min(max_lag + 1, window // 3))

    for i in range(window, len(values)):
        chunk = values[i - window:i]
        log_lags = []
        log_vars = []

        for lag in lags:
            diffs = chunk[lag:] - chunk[:-lag]
            if len(diffs) < 3:
                continue
            var = np.var(diffs)
            if var > 1e-20:
                log_lags.append(np.log(lag))
                log_vars.append(np.log(var))

        if len(log_lags) >= 3:
            # Var ~ lag^(2H) => log(Var) = 2H * log(lag) + c
            coeffs = np.polyfit(log_lags, log_vars, 1)
            hurst_values.iloc[i] = coeffs[0] / 2.0

    return hurst_values


# ── Regime Classifier ─────────────────────────────────────────

def classify_regime(
    adx: float,
    hurst: float,
    adx_trend_threshold: float = 25.0,
    adx_range_threshold: float = 20.0,
    hurst_trend_threshold: float = 0.40,
    hurst_range_threshold: float = 0.35,
) -> Regime:
    """Classify a single point in time into a market regime."""
    if np.isnan(adx) or np.isnan(hurst):
        return Regime.UNCERTAIN

    is_trending = adx > adx_trend_threshold and hurst > hurst_trend_threshold
    is_reverting = adx < adx_range_threshold and hurst < hurst_range_threshold

    if is_trending:
        return Regime.TRENDING
    elif is_reverting:
        return Regime.REVERTING
    return Regime.UNCERTAIN


def compute_regime_series(
    df: pd.DataFrame,
    adx_window: int = 14,
    hurst_window: int = 100,
) -> pd.DataFrame:
    """Compute ADX, Hurst, and regime classification for a full OHLCV DataFrame.

    Returns DataFrame with columns: adx, hurst, regime.
    """
    adx = compute_adx(df["High"], df["Low"], df["Close"], window=adx_window)
    hurst = compute_hurst(df["Close"], window=hurst_window)

    regimes = pd.Series(Regime.UNCERTAIN, index=df.index)
    for i in range(len(df)):
        regimes.iloc[i] = classify_regime(adx.iloc[i], hurst.iloc[i])

    return pd.DataFrame({
        "adx": adx,
        "hurst": hurst,
        "regime": regimes,
    }, index=df.index)
