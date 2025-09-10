# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Turtle is a comprehensive Python + Streamlit trading bot application that combines data visualization with algorithmic trading strategies. It features interactive candlestick charts, real-time data downloading, portfolio management, and automated strategy execution using the Turtle Trading methodology.

## Development Commands

### Setup and Environment
```bash
# Create virtual environment
create_venv.bat

# Activate environment (must be done manually)
venv\Scripts\activate.bat

# Install dependencies with uv (requires activated venv)
install_requirements.bat

# Run the application (auto-activates venv)
run_app.bat
```

### Running the Application
The app runs via Streamlit from the frontend directory:
```bash
cd src/frontend
streamlit run frontend_main.py
```

## Architecture

### Project Structure
```
src/
├── frontend/
│   ├── frontend_main.py      # Main Streamlit application entry point
│   ├── chart_utils.py        # Chart utilities and processing functions
│   ├── download_ui.py        # Data download UI components
│   ├── sidebar_components.py # Sidebar UI components
│   ├── display_components.py # Main display UI components
│   ├── trading_pairs.py      # Trading pair definitions
│   └── period_utils.py       # Period validation utilities
├── models/
│   ├── __init__.py
│   ├── candle.py            # OHLC candle data model
│   ├── chart_data.py        # Chart data container
│   ├── chart_metadata.py    # Chart metadata model
│   ├── portfolio.py         # Portfolio management model
│   ├── trade.py             # Trade execution model
│   ├── trade_status.py      # Trade status enums
│   └── trade_type.py        # Trade type enums
├── download_data.py         # Data fetching from APIs (Binance, Forex)
├── position_manager.py      # Position and risk management
├── strategy_engine.py       # Core strategy execution engine
├── strategy_loader.py       # Dynamic strategy loading
└── trading_service.py       # Trading operations service
inputs/                        # Chart history files (JSON)
strategies/                  # Strategy definitions (Markdown files)
```

### Core Components
- **`frontend_main.py`**: Main Streamlit application with UI orchestration
- **`chart_utils.py`**: Chart utilities and data processing functions
- **`download_ui.py`**: Data download interface components
- **`sidebar_components.py`**: Sidebar UI components (chart selection, strategy, portfolio)
- **`display_components.py`**: Main display components (portfolio summary, signals, data info)
- **`models/`**: Type-safe data models using dataclasses
- **`strategy_engine.py`**: Turtle trading strategy implementation
- **`position_manager.py`**: Portfolio and position management
- **`download_data.py`**: Enhanced data fetching with historical date range support

### Data Flow
```
API inputs/JSON Files → ChartData → Strategy Engine → Portfolio Manager → UI Visualization
                                      ↓
                               Trading Signals → Position Updates → P&L Calculation
```

### Key Models
- `Candle`: OHLC data with timestamp
- `ChartMetadata`: Asset name, currency, period duration
- `ChartData`: Container combining metadata with candle list
- `Portfolio`: Portfolio balance, currency, and performance tracking
- `Trade`: Individual trade records with entry/exit data
- `TradeType`: Long/Short position types
- `TradeStatus`: Open/Closed trade status

## Data Format

Chart files are JSON with this structure:
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

## Features

### Data Management
- **Enhanced Historical Data Download**: 
  - **Cryptocurrency**: Binance API with date range support using `startTime`/`endTime` parameters
  - **Forex**: Alpha Vantage API for real historical data (30+ years) with intelligent fallback to synthetic data
  - **Date Range Selection**: UI date pickers for custom historical periods
  - **Smart Validation**: Date range validation with error handling and reasonable limits (max 5 years)
- **Multiple Timeframes**: Support for 1min, 5min, 15min, 1h, 4h, 12h, 1d, 1w intervals
- **Data Resampling**: Convert between different timeframes on-the-fly
- **Enhanced File Management**: 
  - **Improved Filename Format**: Uses separators for easy replacement (- for dates, ! for times)
  - **Example**: `btcusdt_1m_2025-01-01_10-00-00_2025-01-31_23-59-59.json`
  - **Dropbox Compatible**: Replace all `-` with `/` in dates and `:` in times for standard datetime format

### Portfolio Management
- **Configurable Portfolio**: Set custom portfolio balance and currency
- **Multi-Currency Support**: USD, EUR, GBP, JPY, AUD, CAD, CHF, CNY, BTC, ETH, USDT
- **Performance Tracking**: Real-time P&L, equity, win rate calculations
- **Risk Management**: Position sizing and portfolio risk controls

### Trading Strategies
- **Turtle Trading System**: Complete implementation of the classic trend-following strategy
- **Strategy Loader**: Dynamic loading of strategies from Markdown files
- **Backtesting**: Run strategies against full historical chart data
- **Signal Visualization**: Visual overlays showing entry/exit points and breakout levels

### User Interface
- **Interactive Charts**: Plotly-based candlestick charts with zoom and pan
- **Enhanced Sidebar**: Organized sections with improved UX:
  - **Smart Trading Pair Selection**: Dropdown lists with popular pairs for each data source
  - **Auto-populated Fields**: Asset names and currencies filled automatically based on pair selection
  - **Period Validation**: Prevents invalid downsampling below native data resolution
  - **Date Range Pickers**: Optional historical date selection with validation
- **Real-time Updates**: Live portfolio metrics and trading signals
- **Responsive Design**: Clean, professional interface optimized for trading analysis

## Technology Stack

- **Streamlit**: Web application framework for rapid UI development
- **Plotly**: Interactive charting library for candlestick visualizations
- **Pandas**: Data manipulation and time series analysis
- **Requests**: HTTP client for API data fetching
- **uv**: Fast Python package installer (preferred over pip)

## Development Notes

### Package Management
This project uses `uv` instead of pip for faster dependency installation. The `install_requirements.bat` script handles this automatically.

### File Organization
- Modular frontend with separated UI components across multiple specialized modules
- Clean separation between data models, business logic, and presentation
- Strategy definitions stored as Markdown files for easy modification
- Type-safe data models using Python dataclasses

### Error Handling
The application gracefully handles:
- Missing data directories and malformed JSON files
- API connection failures during data download
- Strategy loading errors with user-friendly messages
- Portfolio state management across sessions

### Chart Configuration
- Candlestick charts use full container width for better visibility
- Range slider disabled for cleaner appearance
- Dynamic overlays for strategy breakout levels (20-day and 55-day high/low)
- Real-time signal annotations on price action

### Strategy System
- Markdown-based strategy definitions for easy customization
- Dynamic strategy loading without code restart
- Configurable parameters for different market conditions
- Built-in risk management and position sizing algorithms

## Data Download API

### Cryptocurrency Data (`download_btc_data`, `download_eth_data`)
```python
download_btc_data(
    symbol="BTCUSDT",           # Trading pair (e.g., BTCUSDT, ETHUSDT)
    interval="1m",              # Timeframe (1m, 5m, 15m, 1h, 4h, 12h, 1d, 1w)
    limit=1000,                 # Number of candles (if no date range)
    asset_name="Bitcoin",       # Display name
    currency="USDT",            # Quote currency
    start_date="2025-01-01",    # Optional: Start date (YYYY-MM-DD)
    end_date="2025-01-31"       # Optional: End date (YYYY-MM-DD)
)
```

### Forex Data (`download_eur_usd_data`)
```python
download_eur_usd_data(
    base_currency="EUR",        # Base currency (EUR, GBP, JPY, etc.)
    quote_currency="USD",       # Quote currency
    limit=100,                  # Number of candles (if no date range)
    asset_name="Euro",          # Display name
    interval="1d",              # Daily data only (free tier)
    start_date="2025-01-01",    # Optional: Start date (YYYY-MM-DD)
    end_date="2025-01-31"       # Optional: End date (YYYY-MM-DD)
)
```

### Data Source Features
- **Binance API**: Real-time and historical cryptocurrency data with precise timestamps
- **Alpha Vantage API**: 30+ years of historical forex data (25 requests/day free tier)
- **Intelligent Fallback**: Automatic fallback to synthetic data when API limits exceeded
- **Date Validation**: Built-in validation with reasonable limits and error handling
- **Backward Compatibility**: Works with existing code (date parameters are optional)