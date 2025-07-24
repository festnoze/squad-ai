import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from pathlib import Path
import os
import time
from datetime import datetime, timedelta
from models import ChartData, Candle
from download_data import download_btc_data, download_eur_usd_data, download_eth_data


def load_chart_files():
    """Load all chart files from the data directory"""
    data_dir = Path("data")
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


def main():
    st.set_page_config(
        page_title="Chart Viewer",
        page_icon="📈",
        layout="wide"
    )
    
    st.title("📈 Chart Viewer")
    st.markdown("Load and display candlestick charts from JSON files")
    
    # Load available chart files
    chart_files = load_chart_files()
    
    # Sidebar for data download and file selection
    with st.sidebar:
        st.header("📥 Download Data")
        
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
            if st.button("📥 Download  Online Data", type="primary"):
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
        
        st.divider()
        
        # File selection
        if chart_files:
            st.header("📊 Select Chart")
            selected_file = st.selectbox(
                "Select a chart file:",
                chart_files,
                format_func=lambda x: os.path.basename(x)
            )
            
            # Period selection
            st.header("⏱️ Time Period")
            period_options = ["1min", "5min", "15min", "1h", "4h", "12h", "1d", "1w"]
            selected_period = st.selectbox(
                "Select time period:",
                period_options,
                index=0
            )
        else:
            st.warning("No chart files found. Download some data first.")
            selected_file = None
            selected_period = "1min"
    
    if not chart_files:
        st.warning("No chart files found in the 'data' directory. Use the sidebar to download some data files.")
        st.info("Expected format: JSON files with metadata (asset_name, currency, period_duration) and candles data")
        return
    
    if selected_file:
        try:
            # Load chart data
            chart_data = ChartData.from_json_file(selected_file)
            
            # Resample candles if different period selected
            resampled_candles = resample_candles(chart_data.candles, selected_period)
            
            # Create new chart data with resampled candles
            resampled_chart_data = ChartData(
                metadata=chart_data.metadata,
                candles=resampled_candles
            )
            
            # Display metadata
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Asset", chart_data.metadata.asset_name)
            with col2:
                st.metric("Currency", chart_data.metadata.currency)
            with col3:
                st.metric("Original Period", chart_data.metadata.period_duration)
            with col4:
                st.metric("Display Period", selected_period)
            
            # Display chart
            fig = create_candlestick_chart(resampled_chart_data)
            # Update title to show current period
            fig.update_layout(
                title=f"{chart_data.metadata.asset_name} ({chart_data.metadata.currency}) - {selected_period}"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Display data info
            st.subheader("Data Information")
            st.write(f"Original candles: {len(chart_data.candles)}")
            st.write(f"Displayed candles ({selected_period}): {len(resampled_candles)}")
            if resampled_candles:
                st.write(f"Date range: {resampled_candles[0].timestamp} to {resampled_candles[-1].timestamp}")
            
        except Exception as e:
            st.error(f"Error loading chart file: {str(e)}")


if __name__ == "__main__":
    main()