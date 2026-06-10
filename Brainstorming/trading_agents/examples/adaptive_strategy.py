"""
Adaptive Strategy — automatic regime detection + strategy switching.

Uses ADX + Hurst exponent to classify the market regime, then applies:
  - TRENDING:   MA crossover (trend-following)
  - REVERTING:  RSI + Bollinger Bands (mean-reversion)
  - UNCERTAIN:  stay in cash (no trade)

Compares with the 3 previous examples on the bottom chart.
"""

import os
import sys

import numpy as np
import pandas as pd
import vectorbt as vbt  # type: ignore[import-untyped]
import plotly.graph_objects as go  # type: ignore[import-untyped]
from plotly.subplots import make_subplots  # type: ignore[import-untyped]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.backtesting.engine import (
    BacktestConfig, ComparisonCurve,
    run_backtest, print_header, print_results, save_plot,
)
from src.data.provider import load_price_data, get_ticker_info, INTERVAL_TO_FREQ
from src.evaluation.regime import compute_regime_series, Regime

# ── Configuration ──────────────────────────────────────────────
SYMBOL = "BTC-USD"
INTERVAL = "1d"
START = "2020-01-01"
END = "2026-05-31"
INIT_CASH = 10_000
FEES = 0.001

# Regime detection
ADX_WINDOW = 14
HURST_WINDOW = 60

# Trend-following params (MA crossover)
TREND_FAST_MA = 20
TREND_SLOW_MA = 50

# Mean-reversion params (RSI + BB)
REV_RSI_WINDOW = 14
REV_RSI_LO = 30
REV_RSI_HI = 70
REV_BB_WINDOW = 20
REV_BB_ALPHA = 2.0
# ───────────────────────────────────────────────────────────────


def build_regime_plot(
    df: pd.DataFrame,
    regimes: pd.DataFrame,
    portfolio,
    entries: pd.Series,
    exits: pd.Series,
    comparisons: list[ComparisonCurve],
    asset_name: str,
    symbol: str,
    currency: str,
) -> go.Figure:
    """Build a 3-subplot figure: price+signals, regime bands, portfolio comparison."""
    price = df["Close"]
    idx = [str(x) for x in price.index]
    buy_mask = entries.values.flatten()
    sell_mask = exits.values.flatten()
    cs = {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3"}.get(currency, currency + " ")

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(
            f"{symbol} Price & Adaptive Signals",
            "Market Regime (ADX + Hurst)",
            "Portfolio Value — All Strategies",
        ),
        row_heights=[0.4, 0.2, 0.4],
    )

    # ── Row 1: Price + signals ──
    fig.add_trace(go.Scatter(
        x=idx, y=price.values, mode="lines",
        name="Close", line=dict(color="#636EFA", width=1.5),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=np.array(idx)[buy_mask], y=price.values[buy_mask],
        mode="markers", name="Buy",
        marker=dict(symbol="triangle-up", size=10, color="#00CC96"),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=np.array(idx)[sell_mask], y=price.values[sell_mask],
        mode="markers", name="Sell",
        marker=dict(symbol="triangle-down", size=10, color="#EF553B"),
    ), row=1, col=1)

    # Background shading for regimes on price chart
    regime_colors = {
        Regime.TRENDING: "rgba(0,200,100,0.12)",
        Regime.REVERTING: "rgba(200,100,0,0.12)",
        Regime.UNCERTAIN: "rgba(150,150,150,0.06)",
    }
    regime_series = regimes["regime"]
    prev_regime = None
    block_start = 0
    for i in range(len(regime_series)):
        r = regime_series.iloc[i]
        if r != prev_regime:
            if prev_regime is not None and prev_regime != Regime.UNCERTAIN:
                fig.add_vrect(
                    x0=idx[block_start], x1=idx[i - 1],
                    fillcolor=regime_colors[prev_regime],
                    layer="below", line_width=0,
                    row=1, col=1,
                )
            block_start = i
            prev_regime = r
    # Last block
    if prev_regime is not None and prev_regime != Regime.UNCERTAIN:
        fig.add_vrect(
            x0=idx[block_start], x1=idx[-1],
            fillcolor=regime_colors[prev_regime],
            layer="below", line_width=0,
            row=1, col=1,
        )

    # ── Row 2: ADX + Hurst ──
    fig.add_trace(go.Scatter(
        x=idx, y=regimes["adx"].values, mode="lines",
        name="ADX", line=dict(color="#FF6B35", width=1.5),
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=idx, y=regimes["hurst"].values * 100, mode="lines",
        name="Hurst x100", line=dict(color="#1B998B", width=1.5),
    ), row=2, col=1)
    # Threshold lines
    fig.add_hline(y=25, line=dict(color="#FF6B35", dash="dot", width=1), row=2, col=1)
    fig.add_hline(y=20, line=dict(color="#FF6B35", dash="dot", width=1), row=2, col=1)
    fig.add_hline(y=40, line=dict(color="#1B998B", dash="dot", width=1), row=2, col=1)
    fig.add_hline(y=35, line=dict(color="#1B998B", dash="dot", width=1), row=2, col=1)

    # ── Row 3: Portfolio values ──
    portfolio_value = portfolio.value()
    buy_hold_value = INIT_CASH * (price / price.iloc[0])

    fig.add_trace(go.Scatter(
        x=idx, y=buy_hold_value.values, mode="lines",
        name="Buy & Hold", line=dict(color="gray", width=1.5, dash="dot"),
    ), row=3, col=1)

    for comp in comparisons:
        comp_idx = [str(x) for x in comp.values.index]
        fig.add_trace(go.Scatter(
            x=comp_idx, y=comp.values.values, mode="lines",
            name=comp.name, line=dict(color=comp.color, width=1.5, dash=comp.dash),
        ), row=3, col=1)

    fig.add_trace(go.Scatter(
        x=idx, y=portfolio_value.values, mode="lines",
        name="Ex4: Adaptive", line=dict(color="#AB63FA", width=2.5),
    ), row=3, col=1)

    fig.update_yaxes(title_text=f"Price ({cs})", row=1, col=1)
    fig.update_yaxes(title_text="ADX / Hurst", row=2, col=1)
    fig.update_yaxes(title_text=f"Value ({cs})", row=3, col=1)
    fig.update_layout(
        title=dict(
            text=f"{asset_name} ({symbol}) \u2014 Adaptive Strategy",
            x=0.5, xanchor="center", font=dict(size=20),
        ),
        height=1000, width=1400,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(t=100),
    )
    return fig


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


def run_comparison_rsi_bb(price, freq):
    """Run RSI+BB mean-reversion, return portfolio value series."""
    rsi = vbt.RSI.run(price, window=REV_RSI_WINDOW).rsi
    bb = vbt.BBANDS.run(price, window=REV_BB_WINDOW, alpha=REV_BB_ALPHA)
    entries = (rsi < REV_RSI_LO) & (price < bb.lower)
    exits = (rsi > REV_RSI_HI) & (price > bb.upper)
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
    print(f"  Adaptive Strategy \u2014 {asset_name} ({SYMBOL})")
    print(f"  Regime: ADX({ADX_WINDOW}) + Hurst({HURST_WINDOW})")
    print(f"  Trending -> MA({TREND_FAST_MA}/{TREND_SLOW_MA})")
    print(f"  Reverting -> RSI({REV_RSI_WINDOW},{REV_RSI_LO}/{REV_RSI_HI}) + BB({REV_BB_WINDOW},{REV_BB_ALPHA})")
    print(f"  Uncertain -> cash")
    print(f"{'=' * 70}\n")

    # Load data
    df = load_price_data(SYMBOL, interval=INTERVAL, start=START, end=END)
    price = df["Close"]
    print(f"Loaded {len(price)} bars\n")

    # Compute regimes
    print("Computing market regimes...")
    regimes = compute_regime_series(df, adx_window=ADX_WINDOW, hurst_window=HURST_WINDOW)

    regime_counts = regimes["regime"].value_counts()
    for r in Regime:
        c = regime_counts.get(r, 0)
        print(f"  {r.value:12s}: {c:5d} bars ({c / len(df) * 100:.1f}%)")

    # Compute indicator states (full period)
    print("\nComputing indicator signals...")
    fast_ma = vbt.MA.run(price, window=TREND_FAST_MA)
    slow_ma = vbt.MA.run(price, window=TREND_SLOW_MA)
    ma_bullish = fast_ma.ma.squeeze() > slow_ma.ma.squeeze()  # continuous state
    ma_crossover = fast_ma.ma_crossed_above(slow_ma)           # point event
    ma_crossunder = fast_ma.ma_crossed_below(slow_ma)

    rsi = vbt.RSI.run(price, window=REV_RSI_WINDOW).rsi
    bb = vbt.BBANDS.run(price, window=REV_BB_WINDOW, alpha=REV_BB_ALPHA)
    rsi_oversold = (rsi < REV_RSI_LO) & (price < bb.lower)
    rsi_overbought = (rsi > REV_RSI_HI) & (price > bb.upper)

    # Adaptive signals: select based on regime
    print("Building adaptive signal series...")
    regime_series = regimes["regime"]
    trending_mask = regime_series == Regime.TRENDING
    reverting_mask = regime_series == Regime.REVERTING
    uncertain_mask = regime_series == Regime.UNCERTAIN

    # Detect regime transitions
    prev_regime = regime_series.shift(1)
    entered_trending = trending_mask & (prev_regime != Regime.TRENDING)
    entered_reverting = reverting_mask & (prev_regime != Regime.REVERTING)
    left_active = uncertain_mask & (prev_regime != Regime.UNCERTAIN)

    # Trend entries: crossover during trending OR entering trending with MAs already bullish
    trend_entries = (ma_crossover & trending_mask) | (entered_trending & ma_bullish)
    trend_exits = ma_crossunder & trending_mask

    # Reversion entries: RSI oversold during reverting OR entering reverting with RSI already oversold
    rev_entries = (rsi_oversold & reverting_mask) | (entered_reverting & rsi_oversold)
    # Deduplicate: only take rising edge of reverting entries
    rev_entries = rev_entries & (~rev_entries.shift(1).fillna(False).infer_objects(copy=False))
    rev_exits = rsi_overbought & reverting_mask

    entries = trend_entries | rev_entries
    exits = trend_exits | rev_exits | left_active  # force exit on regime -> uncertain

    n_trend_entries = trend_entries.sum()
    n_rev_entries = rev_entries.sum()
    n_forced_exits = left_active.sum()
    print(f"  Trend entries: {n_trend_entries} | Reversion entries: {n_rev_entries} | Forced exits: {n_forced_exits}")

    # Run backtest
    config = BacktestConfig(
        symbol=SYMBOL, interval=INTERVAL,
        start=START, end=END,
        init_cash=INIT_CASH, fees=FEES,
    )
    result = run_backtest(config, entries, exits, price=price)

    print_header(result)
    print("  Strategy: Adaptive (regime-switched)\n")
    print_results(result)

    # Comparison strategies
    print("\n--- Computing comparison strategies ---")
    ma_10_50 = run_comparison_ma(price, freq, 10, 50)
    print("  Ex1: MA(10/50) done")
    ma_40_200 = run_comparison_ma(price, freq, 40, 200)
    print("  Ex2: MA(40/200) done")
    rsi_bb = run_comparison_rsi_bb(price, freq)
    print("  Ex3: RSI+BB done")

    comparisons = [
        ComparisonCurve("Ex1: MA(10/50)", ma_10_50, color="#FF6B35", dash="dash"),
        ComparisonCurve("Ex2: MA(40/200)", ma_40_200, color="#1B998B", dash="dashdot"),
        ComparisonCurve("Ex3: RSI+BB", rsi_bb, color="#FFC914", dash="dot"),
    ]

    # Build and save plot
    fig = build_regime_plot(
        df, regimes, result.portfolio, entries, exits,
        comparisons, asset_name, SYMBOL, currency,
    )
    out_dir = os.path.dirname(os.path.abspath(__file__))
    save_plot(fig, os.path.join(out_dir, f"{SYMBOL}_adaptive.png"))
