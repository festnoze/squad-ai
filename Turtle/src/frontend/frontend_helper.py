import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from pathlib import Path
import os
import sys
sys.path.append('..')
from models import ChartData, Candle
from src.download_data import download_btc_data, download_eur_usd_data, download_eth_data
from src.strategy_loader import StrategyLoader
from src.strategy_engine import StrategyEngine


def load_chart_files():
    """Load all chart files from the data directory"""
    data_dir = Path("./../data")
    if not data_dir.exists():
        return []
    
    chart_files = []
    for file_path in data_dir.glob("*.json"):
        chart_files.append(str(file_path))
    
    return chart_files


def resample_candles(candles: list[Candle], target_period: str) -> list[Candle]:
    """Resample 1-minute candles to a different time period"""
    if not candles:
        return []
    
    # Period mapping to minutes
    period_minutes = {
        "1min": 1,
        "5min": 5,
        "15min": 15,
        "1h": 60,
        "4h": 240,
        "12h": 720,
        "1d": 1440,
        "1w": 10080
    }
    
    if target_period not in period_minutes:
        return candles
    
    minutes = period_minutes[target_period]
    
    if minutes == 1:  # No resampling needed
        return candles
    
    # Convert to DataFrame for easier resampling
    df = pd.DataFrame([
        {
            'timestamp': candle.timestamp,
            'open': candle.open,
            'high': candle.high,
            'low': candle.low,
            'close': candle.close
        }
        for candle in candles
    ])
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    
    # Resample to target period
    freq_map = {
        "5min": "5T",
        "15min": "15T", 
        "1h": "1H",
        "4h": "4H",
        "12h": "12H",
        "1d": "1D",
        "1w": "1W"
    }
    
    freq = freq_map.get(target_period, "1T")
    
    resampled = df.resample(freq).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).dropna()
    
    # Convert back to Candle objects
    resampled_candles = []
    for timestamp, row in resampled.iterrows():
        resampled_candles.append(Candle(
            timestamp=timestamp.to_pydatetime(),
            open=row['open'],
            high=row['high'],
            low=row['low'],
            close=row['close']
        ))
    
    return resampled_candles


def create_candlestick_chart(chart_data: ChartData):
    """Create a candlestick chart from chart data"""
    df = pd.DataFrame([
        {
            'timestamp': candle.timestamp,
            'open': candle.open,
            'high': candle.high,
            'low': candle.low,
            'close': candle.close
        }
        for candle in chart_data.candles
    ])
    
    fig = go.Figure(data=go.Candlestick(
        x=df['timestamp'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name=f"{chart_data.metadata.asset_name}"
    ))
    
    fig.update_layout(
        title=f"{chart_data.metadata.asset_name} ({chart_data.metadata.currency}) - {chart_data.metadata.period_duration}",
        xaxis_title="Time",
        yaxis_title=f"Price ({chart_data.metadata.currency})",
        xaxis_rangeslider_visible=False
    )
    
    return fig


def format_filename(filename):
    """Clean up filename for display"""
    # Get just the filename without path
    name = os.path.basename(filename)
    # Remove .json extension
    name = name.replace('.json', '')
    # Replace underscores and hyphens with spaces
    name = name.replace('_', ' ').replace('-', ' ')
    # Capitalize first letter of each word
    return ' '.join(word.capitalize() for word in name.split())


def render_download_section():
    """Render the collapsible download data section"""
    with st.expander("📥 Download Data", expanded=False):
        # Data source selection
        data_source = st.selectbox(
            "Data Source:",
            ["Cryptocurrency (Binance)", "Forex (Synthetic)"]
        )
        
        if data_source == "Cryptocurrency (Binance)":
            # Crypto parameters
            symbol = st.text_input("Trading Pair:", value="BTCUSDT", help="e.g., BTCUSDT, ETHUSDT, ADAUSDT")
            asset_name = st.text_input("Asset Name:", value="Bitcoin", help="Display name for the asset")
            currency = st.text_input("Currency:", value="USDT", help="Quote currency")
            
            interval = st.selectbox(
                "Interval:",
                ["1m", "5m", "15m", "1h", "4h", "12h", "1d", "1w"],
                index=0
            )
            
            limit = st.number_input("Number of Candles:", min_value=1, value=1000)
            
            # Download button for crypto
            if st.button("📥 Download Online Data", type="primary"):
                with st.spinner(f"Downloading {symbol}..."):
                    if download_btc_data(symbol, interval, limit, asset_name, currency):
                        st.success(f"✓ {symbol} downloaded successfully!")
                        st.rerun()
                    else:
                        st.error(f"✗ Failed to download {symbol}")
        
        else:  # Forex
            # Forex parameters
            base_currency = st.text_input("Base Currency:", value="EUR", help="e.g., EUR, GBP, JPY")
            quote_currency = st.text_input("Quote Currency:", value="USD", help="e.g., USD, EUR")
            asset_name = st.text_input("Asset Name:", value="Euro", help="Display name for the asset")
            
            interval = st.selectbox(
                "Interval:",
                ["1m", "5m", "15m", "1h", "4h", "12h", "1d", "1w"],
                index=0,
                key="forex_interval"
            )
            
            limit = st.number_input("Number of Candles:", min_value=1, value=100, key="forex_limit")
            
            # Download button for forex
            if st.button("📥 Download Forex Data", type="primary"):
                with st.spinner(f"Downloading {base_currency}/{quote_currency}..."):
                    if download_eur_usd_data(base_currency, quote_currency, limit, asset_name, interval):
                        st.success(f"✓ {base_currency}/{quote_currency} downloaded successfully!")
                        st.rerun()
                    else:
                        st.error(f"✗ Failed to download {base_currency}/{quote_currency}")


def render_chart_selection(chart_files):
    """Render chart file selection section"""
    if chart_files:
        st.header("📊 Select Chart")
        
        selected_file = st.selectbox(
            "Select a chart file:",
            chart_files,
            format_func=format_filename
        )
        
        # Period selection
        st.header("⏱️ Time Period")
        period_options = ["1min", "5min", "15min", "1h", "4h", "12h", "1d", "1w"]
        selected_period = st.selectbox(
            "Select time period:",
            period_options,
            index=0
        )
        
        return selected_file, selected_period
    else:
        st.warning("No chart files found. Download some data first.")
        return None, "1min"


def render_portfolio_info_section():
    """Render portfolio configuration section"""
    st.header("💰 Portfolio Settings")
    
    # Initialize session state for portfolio settings
    if 'portfolio_balance' not in st.session_state:
        st.session_state.portfolio_balance = 100000.0
    if 'portfolio_currency' not in st.session_state:
        st.session_state.portfolio_currency = "USD"
    
    # Portfolio balance input
    portfolio_balance = st.number_input(
        "Portfolio Balance:",
        min_value=1000.0,
        value=st.session_state.portfolio_balance,
        step=1000.0,
        format="%.2f"
    )
    st.session_state.portfolio_balance = portfolio_balance
    
    # Currency dropdown
    currency_options = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY", "BTC", "ETH", "USDT"]
    portfolio_currency = st.selectbox(
        "Portfolio Currency:",
        currency_options,
        index=currency_options.index(st.session_state.portfolio_currency)
    )
    st.session_state.portfolio_currency = portfolio_currency
    
    # Strategy selection for running
    strategies = st.session_state.strategy_loader.load_all_strategies()
    if strategies:
        strategy_names = ["Select Strategy..."] + [s.name for s in strategies]
        selected_strategy_name = st.selectbox(
            "Strategy to Run:",
            strategy_names,
            key="run_strategy_select"
        )
        
        # Run strategy button
        if selected_strategy_name != "Select Strategy...":
            if st.button("🚀 Run Strategy on Full Chart", type="primary", use_container_width=True):
                selected_strategy = st.session_state.strategy_loader.get_strategy_by_name(selected_strategy_name)
                if selected_strategy:
                    # Store the strategy to run for later processing
                    st.session_state.run_strategy = selected_strategy
                    st.session_state.run_strategy_triggered = True
                    st.success(f"Running {selected_strategy_name} on full chart data...")
                    st.rerun()
    else:
        st.warning("No strategies available")


def render_strategy_section():
    """Render trading strategy selection section"""
    st.header("🐢 Trading Strategy")
    strategies = st.session_state.strategy_loader.load_all_strategies()
    
    if strategies:
        strategy_names = ["None"] + [s.name for s in strategies]
        selected_strategy_name = st.selectbox(
            "Select strategy:",
            strategy_names
        )
        
        if selected_strategy_name != "None":
            selected_strategy = st.session_state.strategy_loader.get_strategy_by_name(selected_strategy_name)
            if selected_strategy:
                st.session_state.strategy_engine.load_strategy(selected_strategy)
                st.success(f"✓ {selected_strategy_name} loaded")
                
                # Strategy controls
                trading_enabled = st.checkbox("Enable Trading", value=st.session_state.strategy_engine.is_enabled)
                st.session_state.strategy_engine.enable_trading(trading_enabled)
                
                if st.button("Reset Portfolio"):
                    st.session_state.strategy_engine.reset_portfolio()
                    st.success("Portfolio reset to $100,000")
                    st.rerun()
        else:
            st.session_state.strategy_engine.load_strategy(None)
    else:
        st.warning("No strategies found in strategies/ directory")


def render_portfolio_summary():
    """Render portfolio summary metrics"""
    if st.session_state.strategy_engine.strategy_config:
        portfolio_summary = st.session_state.strategy_engine.get_portfolio_summary()
        
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Balance", f"${portfolio_summary['current_balance']:,.2f}")
        with col2:
            st.metric("Equity", f"${portfolio_summary['equity']:,.2f}")
        with col3:
            st.metric("Total P&L", f"${portfolio_summary['total_pnl']:,.2f}")
        with col4:
            st.metric("Open Trades", portfolio_summary['open_trades'])
        with col5:
            st.metric("Win Rate", f"{portfolio_summary['win_rate']:.1%}")


def render_asset_metadata(chart_data, selected_period):
    """Render asset metadata metrics"""
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Asset", chart_data.metadata.asset_name)
    with col2:
        st.metric("Currency", chart_data.metadata.currency)
    with col3:
        st.metric("Original Period", chart_data.metadata.period_duration)
    with col4:
        st.metric("Display Period", selected_period)


def render_trading_signals(signals):
    """Render recent trading signals"""
    if signals:
        st.subheader("📈 Recent Trading Signals")
        for signal in signals[-5:]:  # Show last 5 signals
            signal_color = "🟢" if signal.trade_type.value == "long" else "🔴"
            st.write(f"{signal_color} **{signal.signal_type.upper()}** {signal.trade_type.value} at ${signal.price:.2f} - {signal.reason}")


def render_position_summary(symbol):
    """Render position summary for a symbol"""
    if st.session_state.strategy_engine.strategy_config:
        position_summary = st.session_state.strategy_engine.get_position_summary(symbol)
        if position_summary.get('open_positions', 0) > 0:
            st.subheader("📊 Position Summary")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Open Positions", position_summary['open_positions'])
            with col2:
                st.metric("Total Units", position_summary['total_units'])
            with col3:
                st.metric("Unrealized P&L", f"${position_summary['unrealized_pnl']:.2f}")


def render_data_information(chart_data, resampled_candles, selected_period, symbol):
    """Render data information section"""
    st.subheader("📋 Data Information")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"Original candles: {len(chart_data.candles)}")
        st.write(f"Displayed candles ({selected_period}): {len(resampled_candles)}")
    with col2:
        if resampled_candles:
            st.write(f"Date range: {resampled_candles[0].timestamp.strftime('%Y-%m-%d')} to {resampled_candles[-1].timestamp.strftime('%Y-%m-%d')}")
        if st.session_state.strategy_engine.strategy_config and symbol in st.session_state.strategy_engine.position_manager.market_data:
            market_data = st.session_state.strategy_engine.position_manager.market_data[symbol]
            st.write(f"Current ATR: {market_data.atr:.4f}")


def add_strategy_overlays_to_chart(fig, symbol):
    """Add strategy breakout levels to chart"""
    if st.session_state.strategy_engine.strategy_config and symbol in st.session_state.strategy_engine.position_manager.market_data:
        market_data = st.session_state.strategy_engine.position_manager.market_data[symbol]
        
        # Add breakout levels
        fig.add_hline(y=market_data.high_20, line_dash="dash", line_color="blue", 
                    annotation_text="20-day High")
        fig.add_hline(y=market_data.low_20, line_dash="dash", line_color="blue", 
                    annotation_text="20-day Low")
        fig.add_hline(y=market_data.high_55, line_dash="dot", line_color="red", 
                    annotation_text="55-day High")
        fig.add_hline(y=market_data.low_55, line_dash="dot", line_color="red", 
                    annotation_text="55-day Low")