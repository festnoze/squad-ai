"""
Google (GOOGL) intraday MA crossover backtests.

Runs the same MA crossover strategy at two timeframes:
  - 1m interval (7 days max from yfinance)
  - 1h interval (2 years)
"""

import os

import numpy as np
import vectorbt as vbt  # type: ignore[import-untyped]
from plotly.subplots import make_subplots  # type: ignore[import-untyped]
import plotly.graph_objects as go  # type: ignore[import-untyped]


def build_plot(price, portfolio, entries, exits, symbol: str, asset_name: str, currency: str):
    """Build a 2-subplot figure: price + signals, portfolio value vs buy-and-hold."""
    idx = [str(x) for x in price.index]

    buy_mask = entries.values.flatten()
    sell_mask = exits.values.flatten()

    currency_symbol = {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "JPY": "\u00a5"}.get(currency, currency + " ")

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.12,
        subplot_titles=(f"{symbol} Price & Signals", "Portfolio Value vs Buy & Hold"),
        row_heights=[0.5, 0.5],
    )

    # --- Top: price + buy/sell markers ---
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

    # --- Bottom: portfolio value vs buy-and-hold ---
    portfolio_value = portfolio.value()
    buy_hold_value = 10_000 * (price / price.iloc[0])

    fig.add_trace(go.Scatter(
        x=idx, y=buy_hold_value.values, mode="lines",
        name="Buy & Hold", line=dict(color="gray", width=1.5, dash="dot"),
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=idx, y=portfolio_value.values, mode="lines",
        name="Strategy", line=dict(color="#AB63FA", width=2),
    ), row=2, col=1)

    fig.update_yaxes(title_text=f"Price ({currency_symbol})", row=1, col=1)
    fig.update_yaxes(title_text=f"Value ({currency_symbol})", row=2, col=1)
    fig.update_layout(
        title=dict(
            text=f"{asset_name} ({symbol}) — {currency}",
            x=0.5, xanchor="center",
            font=dict(size=20),
        ),
        height=750, width=1400,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(t=100),
    )
    return fig


def run_backtest(symbol: str, period: str, interval: str, freq: str, fast_w: int, slow_w: int) -> None:
    """Run MA crossover backtest and print results."""
    print(f"\n{'=' * 60}")
    print(f"  {symbol} | {interval} bars | period={period} | MA({fast_w}/{slow_w})")
    print(f"{'=' * 60}")

    import yfinance as yf  # type: ignore[import-untyped]
    ticker_info = yf.Ticker(symbol).info
    asset_name = ticker_info.get("shortName", symbol)
    currency = ticker_info.get("currency", "USD")

    price = vbt.YFData.download(symbol, period=period, interval=interval).get("Close")
    print(f"Downloaded {len(price)} bars of {asset_name} ({symbol}) [{currency}]")
    print(f"Date range: {price.index[0]} -> {price.index[-1]}\n")

    fast_ma = vbt.MA.run(price, window=fast_w)
    slow_ma = vbt.MA.run(price, window=slow_w)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    portfolio = vbt.Portfolio.from_signals(
        price,
        entries=entries,
        exits=exits,
        init_cash=10_000,
        fees=0.001,
        freq=freq,
    )

    print(f"Total Return:    {portfolio.total_return():.2%}")
    print(f"Sharpe Ratio:    {portfolio.sharpe_ratio():.2f}")
    print(f"Max Drawdown:    {portfolio.max_drawdown():.2%}")
    print(f"Total Trades:    {portfolio.trades.count()}")
    print(f"Win Rate:        {portfolio.trades.win_rate():.2%}")
    print(f"Profit Factor:   {portfolio.trades.profit_factor():.2f}")

    fig = build_plot(price, portfolio, entries, exits, symbol, asset_name, currency)
    out_dir = os.path.dirname(os.path.abspath(__file__))
    filename = f"google_{interval}_backtest.png"
    filepath = os.path.join(out_dir, filename)
    fig.write_image(filepath)
    print(f"\nPlot saved to {filepath}")


if __name__ == "__main__":
    # 1-minute: 7 days, MA(10/50) = 10min/50min crossover
    run_backtest("GOOGL", period="7d", interval="1m", freq="1min", fast_w=10, slow_w=50)

    # 1-hour: 2 years, MA(10/50) = 10h/50h crossover
    run_backtest("GOOGL", period="2y", interval="1h", freq="1h", fast_w=10, slow_w=50)
