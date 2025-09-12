# Turtle Trading API

## Project Goal
REST API for trading strategy backtesting and execution, implementing the Turtle Trading methodology with real-time market data integration and portfolio management.

## Tech Stack
- **Framework:** FastAPI + Uvicorn ASGI server
- **Validation:** Pydantic models with type validation
- **Data Processing:** Pandas for market data analysis
- **Real-time:** WebSockets for live trading updates
- **Market Data:** Multiple sources (Binance, yfinance, Alpha Vantage)
- **Testing:** pytest with asyncio support for comprehensive test coverage

## Dependencies
```
fastapi - Web framework
uvicorn[standard] - ASGI server
pydantic - Data validation
pydantic-settings - Configuration management  
pandas - Data processing with technical indicators
requests - HTTP client for market data APIs
websockets - Real-time communication
yfinance - Yahoo Finance data source
pytest - Testing framework
pytest-asyncio - Async testing support
```

## Architecture

### Core (`app/core/`)
- `config.py` - Application settings and environment configuration

### Models (`app/models/`)
- `candle.py` - OHLCV candlestick data structures
- `chart.py` - Chart data requests/responses with metadata
- `trade.py` - Trade execution models (Trade, TradeRequest, TradeResponse)  
- `portfolio.py` - Portfolio management and performance tracking
- `strategy.py` - Trading signals and strategy definitions

## Router to Service Mapping

### Charts Router (`app/routers/charts.py`) → ChartService
**Service:** `app.services.chart_service.ChartService`
**Endpoints:**
- `GET /api/charts/data` - Get chart data with technical indicators
- `GET /api/charts/indicators` - Calculate technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands)
- `GET /api/charts/patterns` - Detect chart patterns
- `GET /api/charts/support-resistance` - Get support/resistance levels  
- `GET /api/charts/volatility` - Calculate price volatility
- `GET /api/charts/market-summary` - Get market summary for symbol

### Market Data Router (`app/routers/market_data.py`) → MarketDataService  
**Service:** `app.services.market_data_service.MarketDataService`
**Endpoints:**
- `GET /api/market-data/sources` - List available data sources (Binance, yfinance, Alpha Vantage, synthetic)
- `GET /api/market-data/binance` - Get Binance cryptocurrency data
- `GET /api/market-data/yahoo` - Get Yahoo Finance stock data
- `GET /api/market-data/alpha-vantage` - Get Alpha Vantage API data
- `GET /api/market-data/synthetic` - Generate synthetic data for testing
- `GET /api/market-data/chart-data` - Get chart data from any source
- `GET /api/market-data/latest-price` - Get current price for symbol
- `GET /api/market-data/multiple-symbols` - Get data for multiple symbols

### Trading Router (`app/routers/trading.py`) → TradingService + WebSocketManager
**Services:** `app.services.trading_service.TradingService`, `app.services.websocket_manager.WebSocketManager`
**Endpoints:**
- `GET /api/trading/trades` - Get all trades (open/closed)
- `POST /api/trading/trade` - Create new trade
- `POST /api/trading/close` - Close existing trade
- `GET /api/trading/positions` - Get open positions  
- `GET /api/trading/performance` - Get trading performance statistics
- `GET /api/trading/stops-targets` - Check stop losses and take profits
- `POST /api/trading/calculate-position` - Calculate position size based on risk
- `WebSocket /api/trading/ws` - Real-time trade updates

### Portfolio Router (`app/routers/portfolio.py`) → PortfolioService
**Service:** `app.services.portfolio_service.PortfolioService`
**Endpoints:**
- `GET /api/portfolio/list` - List all portfolios
- `POST /api/portfolio/create` - Create new portfolio
- `GET /api/portfolio/{id}` - Get portfolio by ID
- `PUT /api/portfolio/{id}/balance` - Update portfolio balance
- `POST /api/portfolio/{id}/trade` - Add trade to portfolio
- `GET /api/portfolio/{id}/trades` - Get portfolio trades
- `GET /api/portfolio/{id}/value` - Calculate total portfolio value
- `GET /api/portfolio/{id}/performance` - Get performance metrics (win rate, PnL, ratios)
- `GET /api/portfolio/{id}/drawdown` - Calculate portfolio drawdown
- `GET /api/portfolio/{id}/risk-metrics` - Get risk metrics (VaR, beta, Sharpe ratio)
- `POST /api/portfolio/{id}/rebalance` - Generate rebalancing trades
- `DELETE /api/portfolio/{id}` - Delete portfolio

### Strategies Router (`app/routers/strategies.py`) → StrategyService + StrategyEngine  
**Services:** `app.services.strategy_service.StrategyService`, `app.services.strategy_engine.StrategyEngine`
**Endpoints:**
- `GET /api/strategies/list` - List available strategies
- `POST /api/strategies/backtest` - Run strategy backtest
- `GET /api/strategies/signals` - Get trading signals from strategies
- `POST /api/strategies/execute` - Execute strategy on live data
- `GET /api/strategies/performance` - Get strategy performance metrics

## Additional Services (Backend Only)

### Position Service (`app/services/position_service.py`)
- Advanced position management with turtle-specific logic
- Market data processing and breakout signal detection  
- Trailing stops and pyramiding position management

### WebSocket Manager (`app/services/websocket_manager.py`)
- Real-time client connection management
- Topic-based subscription system (trades, signals, portfolio)
- Broadcasting trade updates, signals, and portfolio changes
- Error handling and connection cleanup

## API Endpoints Summary
- **Root:** `/` (API info), `/health` (health check)  
- **Charts:** `/api/charts/*` - 6 endpoints for charting and technical analysis
- **Market Data:** `/api/market-data/*` - 7 endpoints for multi-source data
- **Trading:** `/api/trading/*` - 7 endpoints + WebSocket for trade management
- **Portfolio:** `/api/portfolio/*` - 10 endpoints for portfolio management  
- **Strategies:** `/api/strategies/*` - 5 endpoints for strategy execution

## Development & Testing
- **Launch Config:** VS Code debug with direct uvicorn execution (fixed multiprocessing issues)
- **Hot Reload:** Development server with auto-reload
- **CORS:** Configured for frontend integration  
- **Test Suite:** 114 tests covering all services with pytest + asyncio
- **Test Coverage:** Core functionality tested for all services with both sync/async method variants