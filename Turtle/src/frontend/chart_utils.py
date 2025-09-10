"""Chart utilities and data processing functions."""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from pathlib import Path
import os
import sys
sys.path.append('..')
from models import ChartData, Candle


def load_chart_files():
    """Load all chart files from the data directory"""
    data_dir = Path("../inputs")
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
        "5min": "5min",
        "15min": "15min", 
        "1h": "1h",
        "4h": "4h",
        "12h": "12h",
        "1d": "1d",
        "1w": "1W"
    }
    
    freq = freq_map.get(target_period, "1min")
    
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