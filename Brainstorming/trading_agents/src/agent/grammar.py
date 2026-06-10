"""
GP Grammar — trading primitives for DEAP genetic programming.

Defines the building blocks that DEAP will combine into strategy trees:
  - Indicators: SMA, RSI, BB upper/lower, ATR (one per window)
  - Alpha factors: ROC, VPT, PSR, VR, HH, LL, VS, MACD histogram
  - Price data: close, high, low (zero-arg primitives)
  - Operators: AND, OR, NOT, GT, LT, cross_above, cross_below
  - Constants: threshold values as Series

Each primitive operates on pd.Series and returns pd.Series (bool or float).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import vectorbt as vbt  # type: ignore[import-untyped]
from deap import gp  # type: ignore[import-untyped]

# ── Shared data context (set before evaluation) ──────────────

_ctx: dict[str, pd.Series] = {}


def set_context(df: pd.DataFrame) -> None:
    """Set the OHLCV data context for primitive evaluation."""
    global _ctx
    _ctx = {
        "close": df["Close"],
        "high": df["High"],
        "low": df["Low"],
        "open": df["Open"],
        "volume": df["Volume"].astype(float),
    }


# ── Custom types for GP ──────────────────────────────────────

SeriesFloat = type("SeriesFloat", (object,), {})
SeriesBool = type("SeriesBool", (object,), {})

INDICATOR_WINDOWS = [7, 10, 14, 20, 30, 50]

# All indicator primitive names — used by tree_complexity_score to detect nesting.
INDICATOR_NAMES: set[str] = set()
for _w in INDICATOR_WINDOWS:
    INDICATOR_NAMES |= {f"SMA{_w}", f"RSI{_w}", f"BBU{_w}", f"BBL{_w}", f"ATR{_w}"}

# Alpha factor primitive names — zero-arg factors that internally reference OHLCV data.
ALPHA_FACTOR_NAMES: set[str] = set()
for _n in [5, 10, 20]:
    ALPHA_FACTOR_NAMES.add(f"ROC{_n}")
ALPHA_FACTOR_NAMES.add("VPT")
for _w in [10, 20, 50]:
    ALPHA_FACTOR_NAMES.add(f"PSR{_w}")
ALPHA_FACTOR_NAMES |= {"VR7_30", "VR14_50"}
for _n in [10, 20, 50]:
    ALPHA_FACTOR_NAMES |= {f"HH{_n}", f"LL{_n}"}
for _n in [10, 20]:
    ALPHA_FACTOR_NAMES.add(f"VS{_n}")
ALPHA_FACTOR_NAMES.add("MACDH12_26")

# Merge alpha factors into INDICATOR_NAMES so nesting detection covers them too.
INDICATOR_NAMES |= ALPHA_FACTOR_NAMES

# Primitives that use price data internally — tree_complexity_score should not
# penalize trees using these as "missing price data".
_USES_PRICE_DATA: set[str] = set()
for _n in [5, 10, 20]:
    _USES_PRICE_DATA.add(f"ROC{_n}")
for _w in [10, 20, 50]:
    _USES_PRICE_DATA.add(f"PSR{_w}")
for _n in [10, 20, 50]:
    _USES_PRICE_DATA |= {f"HH{_n}", f"LL{_n}"}


# ── Safe wrapper ─────────────────────────────────────────────

def _resolve(val):
    """Convert sentinel terminal values to actual Series."""
    if isinstance(val, pd.Series):
        return val
    if val == "__close__" and _ctx:
        return _ctx["close"]
    if val == "__false__" and _ctx:
        return pd.Series(False, index=_ctx["close"].index)
    if isinstance(val, (int, float)) and _ctx:
        return pd.Series(val, index=_ctx["close"].index)
    return val


def _safe(func):
    """Wrap a primitive to catch errors during evolution."""
    def wrapper(*args, **kwargs):
        try:
            resolved = [_resolve(a) for a in args]
            return func(*resolved, **kwargs)
        except Exception:
            if _ctx:
                return pd.Series(np.nan, index=_ctx["close"].index)
            return pd.Series(dtype=float)
    wrapper.__name__ = func.__name__
    return wrapper


# ── All primitives as plain functions ────────────────────────

# Price data (zero-arg -> SeriesFloat)
def _close(): return _ctx["close"]
def _high(): return _ctx["high"]
def _low(): return _ctx["low"]

# Threshold constants (zero-arg -> SeriesFloat)
def _make_thresh(val):
    def f(): return pd.Series(val, index=_ctx["close"].index)
    f.__name__ = f"T{val}"
    return f

# Indicators (SeriesFloat -> SeriesFloat)
def _make_sma(w):
    def f(s): return vbt.MA.run(s, window=w).ma.squeeze()
    f.__name__ = f"sma{w}"
    return f

def _make_rsi(w):
    def f(s): return vbt.RSI.run(s, window=w).rsi.squeeze()
    f.__name__ = f"rsi{w}"
    return f

def _make_bbu(w):
    def f(s): return vbt.BBANDS.run(s, window=w, alpha=2.0).upper.squeeze()
    f.__name__ = f"bbu{w}"
    return f

def _make_bbl(w):
    def f(s): return vbt.BBANDS.run(s, window=w, alpha=2.0).lower.squeeze()
    f.__name__ = f"bbl{w}"
    return f

def _make_atr(w):
    def f(): return vbt.ATR.run(_ctx["high"], _ctx["low"], _ctx["close"], window=w).atr.squeeze()
    f.__name__ = f"atr{w}"
    return f

# ── Alpha factor factories (zero-arg -> SeriesFloat) ────────

# Rate of Change: (close - close[n]) / close[n]
def _make_roc(n):
    def f():
        close = _ctx["close"]
        return ((close - close.shift(n)) / close.shift(n)).fillna(0.0)
    f.__name__ = f"roc{n}"
    return f

# Volume-Price Trend: cumulative sum of volume * price change ratio
def _make_vpt():
    def f():
        close = _ctx["close"]
        vol = _ctx["volume"]
        return (vol * (close - close.shift(1)) / close.shift(1)).cumsum().fillna(0.0)
    f.__name__ = "vpt"
    return f

# Price / SMA ratio (how far price is from moving average, 1.0 = at average)
def _make_price_sma_ratio(w):
    def f():
        close = _ctx["close"]
        sma = vbt.MA.run(close, window=w).ma.squeeze()
        return (close / sma).fillna(0.0)
    f.__name__ = f"psr{w}"
    return f

# Volatility ratio: ATR(fast) / ATR(slow) — expansion > 1, contraction < 1
def _make_vol_ratio(fast, slow):
    def f():
        atr_f = vbt.ATR.run(_ctx["high"], _ctx["low"], _ctx["close"], window=fast).atr.squeeze()
        atr_s = vbt.ATR.run(_ctx["high"], _ctx["low"], _ctx["close"], window=slow).atr.squeeze()
        return (atr_f / atr_s).fillna(0.0)
    f.__name__ = f"vr{fast}_{slow}"
    return f

# Higher High detection: close > rolling max of high over n bars
def _make_higher_high(n):
    def f():
        return (_ctx["close"] > _ctx["high"].rolling(n).max().shift(1)).astype(float).fillna(0.0)
    f.__name__ = f"hh{n}"
    return f

# Lower Low detection: close < rolling min of low over n bars
def _make_lower_low(n):
    def f():
        return (_ctx["close"] < _ctx["low"].rolling(n).min().shift(1)).astype(float).fillna(0.0)
    f.__name__ = f"ll{n}"
    return f

# Volume spike: volume / SMA(volume, n) — > 2 means abnormal volume
def _make_vol_spike(n):
    def f():
        vol = _ctx["volume"]
        return (vol / vol.rolling(n).mean()).fillna(0.0)
    f.__name__ = f"vs{n}"
    return f

# MACD histogram: MACD - Signal line
def _make_macd_hist(fast, slow, signal):
    def f():
        close = _ctx["close"]
        macd_obj = vbt.MACD.run(close, fast_window=fast, slow_window=slow, signal_window=signal)
        return (macd_obj.macd - macd_obj.signal).squeeze().fillna(0.0)
    f.__name__ = f"macdh{fast}_{slow}"
    return f

# Comparisons (SeriesFloat, SeriesFloat -> SeriesBool)
def _gt(a, b): return (a > b).fillna(False)
def _lt(a, b): return (a < b).fillna(False)

def _cross_above(a, b):
    above = a > b
    return (above & ~above.shift(1).fillna(False)).fillna(False)

def _cross_below(a, b):
    below = a < b
    return (below & ~below.shift(1).fillna(False)).fillna(False)

# Logic (SeriesBool -> SeriesBool)
def _and(a, b): return a & b
def _or(a, b): return a | b
def _not(a): return ~a

# Bool terminals (zero-arg -> SeriesBool)
def _true(): return pd.Series(True, index=_ctx["close"].index)
def _false(): return pd.Series(False, index=_ctx["close"].index)


# ── Tree complexity scoring ──────────────────────────────────

# Price-data primitives that reference actual OHLC prices.
_PRICE_NAMES: set[str] = {"Close", "High", "Low"}


def tree_complexity_score(individual) -> float:
    """Compute a complexity penalty that discourages bloated / nonsensical trees.

    The score is always >= 0.  Higher means *more* complex (= worse).

    Components
    ----------
    1. **Base node count** — ``len(individual)`` (same as the old flat penalty).
    2. **Nested-indicator penalty (+2 each)** — an indicator whose *direct*
       child is also an indicator (e.g. ``SMA(RSI(…))``) is almost always
       meaningless noise-fitting.  Each such occurrence adds +2.
    3. **No-price-data penalty (+3)** — if the tree never references
       ``Close``, ``High``, or ``Low`` directly *and* none of the alpha
       factors that internally use price data (ROC, PSR, HH, LL), it is
       operating purely on derived data (like ``ATR``).  A credible strategy
       should touch actual price at least once.

    Parameters
    ----------
    individual : deap.gp.PrimitiveTree
        A DEAP GP individual (flat prefix-ordered list of nodes).

    Returns
    -------
    float
        Complexity score (non-negative).
    """
    tree_size = len(individual)
    base_score: float = float(tree_size)

    # -- Nested-indicator penalty --
    nesting_penalty: float = 0.0
    i = 0
    while i < tree_size:
        node = individual[i]
        if isinstance(node, gp.Primitive) and node.name in INDICATOR_NAMES:
            # Only indicators with arity >= 1 can nest (ATR has arity 0).
            if node.arity >= 1:
                child = individual[i + 1]
                if isinstance(child, gp.Primitive) and child.name in INDICATOR_NAMES:
                    nesting_penalty += 2.0
        i += 1

    # -- Missing price-data penalty --
    # Alpha factors that internally reference price data count as "using price".
    _price_or_alpha = _PRICE_NAMES | _USES_PRICE_DATA
    has_price = any(
        isinstance(node, gp.Primitive) and node.name in _price_or_alpha
        for node in individual
    )
    price_penalty: float = 0.0 if has_price else 3.0

    return base_score + nesting_penalty + price_penalty


# ── Primitive Set Builder ────────────────────────────────────

def create_pset() -> gp.PrimitiveSetTyped:
    """Create the typed primitive set for GP evolution."""
    pset = gp.PrimitiveSetTyped("strategy", [], SeriesBool)

    # Comparisons: (SF, SF) -> SB
    pset.addPrimitive(_safe(_gt), [SeriesFloat, SeriesFloat], SeriesBool, name="GT")
    pset.addPrimitive(_safe(_lt), [SeriesFloat, SeriesFloat], SeriesBool, name="LT")
    pset.addPrimitive(_safe(_cross_above), [SeriesFloat, SeriesFloat], SeriesBool, name="XAbove")
    pset.addPrimitive(_safe(_cross_below), [SeriesFloat, SeriesFloat], SeriesBool, name="XBelow")

    # Logic: (SB, SB) -> SB
    pset.addPrimitive(_safe(_and), [SeriesBool, SeriesBool], SeriesBool, name="AND")
    pset.addPrimitive(_safe(_or), [SeriesBool, SeriesBool], SeriesBool, name="OR")
    pset.addPrimitive(_safe(_not), [SeriesBool], SeriesBool, name="NOT")

    # Indicators: (SF) -> SF, one per window
    for w in INDICATOR_WINDOWS:
        pset.addPrimitive(_safe(_make_sma(w)), [SeriesFloat], SeriesFloat, name=f"SMA{w}")
        pset.addPrimitive(_safe(_make_rsi(w)), [SeriesFloat], SeriesFloat, name=f"RSI{w}")
        pset.addPrimitive(_safe(_make_bbu(w)), [SeriesFloat], SeriesFloat, name=f"BBU{w}")
        pset.addPrimitive(_safe(_make_bbl(w)), [SeriesFloat], SeriesFloat, name=f"BBL{w}")
        pset.addPrimitive(_safe(_make_atr(w)), [], SeriesFloat, name=f"ATR{w}")

    # ── Alpha factors: zero-arg primitives ([] -> SF) ────────

    # Rate of Change
    for n in [5, 10, 20]:
        pset.addPrimitive(_safe(_make_roc(n)), [], SeriesFloat, name=f"ROC{n}")

    # Volume-Price Trend
    pset.addPrimitive(_safe(_make_vpt()), [], SeriesFloat, name="VPT")

    # Price/SMA ratio
    for w in [10, 20, 50]:
        pset.addPrimitive(_safe(_make_price_sma_ratio(w)), [], SeriesFloat, name=f"PSR{w}")

    # Volatility ratio
    pset.addPrimitive(_safe(_make_vol_ratio(7, 30)), [], SeriesFloat, name="VR7_30")
    pset.addPrimitive(_safe(_make_vol_ratio(14, 50)), [], SeriesFloat, name="VR14_50")

    # Higher High / Lower Low
    for n in [10, 20, 50]:
        pset.addPrimitive(_safe(_make_higher_high(n)), [], SeriesFloat, name=f"HH{n}")
        pset.addPrimitive(_safe(_make_lower_low(n)), [], SeriesFloat, name=f"LL{n}")

    # Volume spike
    for n in [10, 20]:
        pset.addPrimitive(_safe(_make_vol_spike(n)), [], SeriesFloat, name=f"VS{n}")

    # MACD histogram
    pset.addPrimitive(_safe(_make_macd_hist(12, 26, 9)), [], SeriesFloat, name="MACDH12_26")

    # Price data: zero-arg primitives (called at evaluation time)
    pset.addPrimitive(_safe(_close), [], SeriesFloat, name="Close")
    pset.addPrimitive(_safe(_high), [], SeriesFloat, name="High")
    pset.addPrimitive(_safe(_low), [], SeriesFloat, name="Low")

    # Threshold constants: zero-arg primitives producing constant Series
    for val in [20, 25, 30, 35, 50, 65, 70, 75, 80]:
        pset.addPrimitive(_safe(_make_thresh(val)), [], SeriesFloat, name=f"T{val}")

    # Bool primitives
    pset.addPrimitive(_safe(_true), [], SeriesBool, name="TRUE")
    pset.addPrimitive(_safe(_false), [], SeriesBool, name="FALSE")

    # DEAP requires at least one terminal per type for genGrow leaf selection.
    # These are sentinel values; _safe wrappers and fitness handle them gracefully.
    pset.addTerminal("__close__", SeriesFloat, name="TClose")
    pset.addTerminal("__false__", SeriesBool, name="TFalse")

    return pset
