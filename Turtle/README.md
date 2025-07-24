# 🐢 Turtle Trading Bot

A comprehensive Python + Streamlit trading bot application that combines data visualization with algorithmic trading strategies. Features interactive candlestick charts, real-time data downloading, portfolio management, and automated strategy execution using the Turtle Trading methodology.

## ✨ Features

### 📊 Data Management
- **Real-time Data Download**: Fetch live data from Binance (cryptocurrency) and synthetic Forex data
- **Multiple Timeframes**: Support for 1min, 5min, 15min, 1h, 4h, 12h, 1d, 1w intervals
- **Data Resampling**: Convert between different timeframes on-the-fly
- **File Management**: Automatic JSON file handling and storage

### 💰 Portfolio Management
- **Configurable Portfolio**: Set custom portfolio balance and currency
- **Multi-Currency Support**: USD, EUR, GBP, JPY, AUD, CAD, CHF, CNY, BTC, ETH, USDT
- **Performance Tracking**: Real-time P&L, equity, win rate calculations
- **Risk Management**: Position sizing and portfolio risk controls

### 🚀 Trading Strategies
- **Turtle Trading System**: Complete implementation of the classic trend-following strategy
- **Strategy Loader**: Dynamic loading of strategies from Markdown files
- **Backtesting**: Run strategies against full historical chart data
- **Signal Visualization**: Visual overlays showing entry/exit points and breakout levels

### 🎯 User Interface
- **Interactive Charts**: Plotly-based candlestick charts with zoom and pan
- **Modular Sidebar**: Organized sections for data download, chart selection, portfolio settings, and strategy controls
- **Real-time Updates**: Live portfolio metrics and trading signals
- **Responsive Design**: Clean, professional interface optimized for trading analysis

## 🚀 Quick Start

1. **Create virtual environment:**
   ```bash
   create_venv.bat
   ```

2. **Activate virtual environment:**
   ```bash
   venv\Scripts\activate.bat
   ```

3. **Install requirements with uv:**
   ```bash
   install_requirements.bat
   ```

4. **Run the application:**
   ```bash
   run_app.bat
   ```

## 📖 Usage

1. **Download Data**: Use the sidebar to fetch live cryptocurrency or forex data
2. **Select Chart**: Choose from downloaded chart files and set display timeframe
3. **Configure Portfolio**: Set your portfolio balance and preferred currency
4. **Load Strategy**: Select and enable a trading strategy (Turtle Trading included)
5. **Run Backtest**: Execute the strategy against full chart data to see results

## 💾 Chart Data Format

Chart files are stored as JSON in the `data/` directory:

```json
{
  "metadata": {
    "asset_name": "Bitcoin",
    "currency": "USD",
    "period_duration": "1min"
  },
  "candles": [
    {
      "timestamp": "2024-01-01T10:00:00",
      "open": 42000.50,
      "close": 42100.25,
      "high": 42150.75,
      "low": 41950.30
    }
  ]
}
```

## 📁 Project Structure

```
turtle/
├── src/
│   ├── frontend/
│   │   ├── frontend_main.py      # Main Streamlit application
│   │   └── frontend_helper.py    # UI components and helpers
│   ├── models/
│   │   ├── candle.py            # OHLC candle data model
│   │   ├── chart_data.py        # Chart data container
│   │   ├── chart_metadata.py    # Chart metadata model
│   │   ├── portfolio.py         # Portfolio management
│   │   ├── trade.py             # Trade execution model
│   │   ├── trade_status.py      # Trade status enums
│   │   └── trade_type.py        # Trade type enums
│   ├── download_data.py         # API data fetching
│   ├── position_manager.py      # Position management
│   ├── strategy_engine.py       # Strategy execution engine
│   ├── strategy_loader.py       # Dynamic strategy loading
│   └── trading_service.py       # Trading operations
├── data/                        # Chart data files (JSON)
├── strategies/                  # Strategy definitions (Markdown)
├── venv/                       # Virtual environment
├── requirements.txt            # Python dependencies
├── create_venv.bat            # Create virtual environment
├── install_requirements.bat   # Install dependencies with uv
└── run_app.bat               # Run the application
```

## 🛠️ Technology Stack

- **Streamlit**: Web application framework
- **Plotly**: Interactive charting
- **Pandas**: Data manipulation and analysis
- **Requests**: HTTP client for API calls
- **uv**: Fast Python package installer

## 📋 Requirements

- Python 3.8+
- Windows (batch scripts provided)
- Internet connection for live data download