"""
Backtesting engine — reusable helpers for running and visualizing backtests.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt  # type: ignore[import-untyped]
from plotly.subplots import make_subplots  # type: ignore[import-untyped]
import plotly.graph_objects as go  # type: ignore[import-untyped]

from src.data.provider import load_price_data, get_ticker_info, INTERVAL_TO_FREQ

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "JPY": "\u00a5"}


@dataclass
class BacktestConfig:
    symbol: str
    interval: str       # 1m, 5m, 15m, 1h, 4h, 1d, 1w
    start: str           # YYYY-MM-DD
    end: str             # YYYY-MM-DD
    init_cash: float = 10_000
    fees: float = 0.001  # 0.1%


@dataclass
class BacktestResult:
    portfolio: Any       # vbt.Portfolio (untyped)
    price: pd.Series
    entries: pd.Series
    exits: pd.Series
    config: BacktestConfig
    asset_name: str
    currency: str


def run_backtest(
    config: BacktestConfig,
    entries: pd.Series,
    exits: pd.Series,
    price: pd.Series | None = None,
) -> BacktestResult:
    """Run a backtest from pre-computed entry/exit signals and return structured results.

    Args:
        config: Backtest configuration.
        entries: Boolean series of entry signals.
        exits: Boolean series of exit signals.
        price: Pre-loaded close price series. If None, loads from cache/download.
    """
    info = get_ticker_info(config.symbol)
    asset_name = info.get("shortName", config.symbol)
    currency = info.get("currency", "USD")
    freq = INTERVAL_TO_FREQ[config.interval]

    if price is None:
        df = load_price_data(config.symbol, interval=config.interval, start=config.start, end=config.end)
        price = df["Close"]

    portfolio = vbt.Portfolio.from_signals(
        price, entries=entries, exits=exits,
        init_cash=config.init_cash, fees=config.fees, freq=freq,
    )

    return BacktestResult(
        portfolio=portfolio, price=price,
        entries=entries, exits=exits,
        config=config, asset_name=asset_name, currency=currency,
    )


def print_header(result: BacktestResult) -> None:
    """Print a formatted header with asset info and config."""
    c = result.config
    print(f"\n{'=' * 60}")
    print(f"  {result.asset_name} ({c.symbol}) | {c.interval} | {c.start} -> {c.end}")
    print(f"  Cash: {c.init_cash:,.0f} {result.currency} | Fees: {c.fees:.1%}")
    print(f"{'=' * 60}\n")


def print_results(result: BacktestResult) -> None:
    """Print key backtest metrics."""
    p = result.portfolio
    print("=== Backtest Results ===")
    print(f"Total Return:    {p.total_return():.2%}")
    print(f"Sharpe Ratio:    {p.sharpe_ratio():.2f}")
    print(f"Max Drawdown:    {p.max_drawdown():.2%}")
    print(f"Total Trades:    {p.trades.count()}")
    print(f"Win Rate:        {p.trades.win_rate():.2%}")
    print(f"Profit Factor:   {p.trades.profit_factor():.2f}")


@dataclass
class ComparisonCurve:
    """An extra portfolio-value curve to overlay on the bottom chart."""
    name: str
    values: pd.Series    # portfolio value series (same index as price)
    color: str
    dash: str = "solid"  # solid, dot, dash, dashdot


def build_plot(
    result: BacktestResult,
    comparisons: list[ComparisonCurve] | None = None,
    strategy_name: str = "Strategy",
) -> go.Figure:
    """Build a 2-subplot figure: price+signals on top, portfolio value vs buy-and-hold on bottom.

    Args:
        result: The main backtest result to plot.
        comparisons: Optional extra curves to overlay on the bottom chart.
        strategy_name: Label for the main strategy curve.
    """
    price = result.price
    idx = [str(x) for x in price.index]
    buy_mask = result.entries.values.flatten()
    sell_mask = result.exits.values.flatten()
    cs = CURRENCY_SYMBOLS.get(result.currency, result.currency + " ")

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.12,
        subplot_titles=(f"{result.config.symbol} Price & Signals", "Portfolio Value vs Buy & Hold"),
        row_heights=[0.5, 0.5],
    )

    # Top: price + buy/sell markers
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

    # Bottom: buy-and-hold baseline
    portfolio_value = result.portfolio.value()
    buy_hold_value = result.config.init_cash * (price / price.iloc[0])
    fig.add_trace(go.Scatter(
        x=idx, y=buy_hold_value.values, mode="lines",
        name="Buy & Hold", line=dict(color="gray", width=1.5, dash="dot"),
    ), row=2, col=1)

    # Bottom: comparison curves (behind main strategy)
    for comp in (comparisons or []):
        comp_idx = [str(x) for x in comp.values.index]
        fig.add_trace(go.Scatter(
            x=comp_idx, y=comp.values.values, mode="lines",
            name=comp.name, line=dict(color=comp.color, width=1.5, dash=comp.dash),
        ), row=2, col=1)

    # Bottom: main strategy (on top)
    fig.add_trace(go.Scatter(
        x=idx, y=portfolio_value.values, mode="lines",
        name=strategy_name, line=dict(color="#AB63FA", width=2.5),
    ), row=2, col=1)

    fig.update_yaxes(title_text=f"Price ({cs})", row=1, col=1)
    fig.update_yaxes(title_text=f"Value ({cs})", row=2, col=1)
    fig.update_layout(
        title=dict(
            text=f"{result.asset_name} ({result.config.symbol}) \u2014 {result.currency}",
            x=0.5, xanchor="center", font=dict(size=20),
        ),
        height=750, width=1400,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(t=100),
    )
    return fig


def save_plot(fig: go.Figure, output_path: str | Path) -> None:
    """Fix timestamp serialization and save figure to PNG."""
    for trace in fig.data:
        if hasattr(trace, "x") and trace.x is not None and hasattr(trace.x, "dtype"):
            trace.x = [str(x) for x in trace.x]
    fig.write_image(str(output_path))
    print(f"\nPlot saved to {output_path}")
