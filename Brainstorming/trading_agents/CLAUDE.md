# Trading Agents - Auto-Improving Algorithmic Trading System

## Project Goal

Build **self-improving trading agents** that autonomously generate, backtest, evaluate, and iterate on trading strategies. The system uses an LLM-driven loop to propose strategies, test them against historical data, analyze results, and refine — converging toward profitable, risk-adjusted strategies without manual intervention.

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Agent Orchestrator                │
│         (LLM-driven strategy generation loop)       │
├─────────────┬──────────────┬────────────────────────┤
│  Strategy   │  Backtesting │   Performance          │
│  Generator  │  Engine      │   Analyzer             │
│  (propose)  │  (test)      │   (evaluate & rank)    │
├─────────────┴──────────────┴────────────────────────┤
│                   Data Layer                        │
│         (historical data download & caching)        │
├─────────────────────────────────────────────────────┤
│              Live Trading Bridge                    │
│         (paper trading → real execution)            │
└─────────────────────────────────────────────────────┘
```

## Technology Choices

### Backtesting: VectorBT

**Why VectorBT over LEAN/QuantConnect:**
- Pure Python, no C#/PythonNet overhead
- Vectorized NumPy operations — sweeps thousands of parameter combos in seconds
- Ideal for agent-driven iteration loops (fast feedback)
- Built-in yfinance integration for one-line data download
- Walk-forward analysis and portfolio optimization built-in
- Open source (free version covers our needs)

### Historical Data: yfinance + VectorBT built-in

- Free, no API key needed for basic use
- Stocks, ETFs, forex, crypto — daily/hourly/minute data
- VectorBT wraps yfinance natively (`vbt.YFData.download()`)
- For higher-frequency data later: consider Alpha Vantage or Polygon.io

### Broker: Interactive Brokers (via IB Ireland)

**Why IB over alternatives:**
- **EU-regulated**: Licensed in Ireland (CBI), Hungary (MNB), Luxembourg — full MiFID II
- **Lowest fees**: ~EUR 3 flat/trade or 0.05% tiered for EU stocks, no inactivity fees
- **Best API**: TWS API + Client Portal REST API + FIX protocol
- **Python**: `ib_insync` library wraps the verbose TWS API, reduces boilerplate ~70%
- **Paper trading**: Free full-API paper account for development
- **Asset coverage**: 150+ exchanges, stocks/ETFs/futures/forex/options/bonds

**Why not others:**
- DEGIRO: Cheapest fees but **no official API** (unofficial reverse-engineered wrapper, can break)
- Saxo Bank: Good OpenAPI but higher fees, thinner Python ecosystem
- XTB: No API access at all — not viable for algo trading
- Trading 212: Beta API, too immature for production automation

## Key Dependencies

```
vectorbt          # Backtesting engine (vectorized, fast)
yfinance          # Historical market data
ib_insync         # Interactive Brokers Python API wrapper
pandas / numpy    # Data manipulation
anthropic         # LLM-driven strategy generation & analysis
```

## Development Conventions

- Python 3.11+
- Async methods prefixed with `a` (e.g., `async def afetch_data(...)`)
- Activate venv before running anything: `source venv/Scripts/activate` (Windows)
- Strategies stored as serializable configs (JSON/YAML), not just code
- Every strategy run produces a structured result log for the agent to analyze

## Workflow: Agent Improvement Loop

1. **Generate**: LLM proposes a strategy (indicators, entry/exit rules, parameters)
2. **Backtest**: VectorBT runs the strategy on historical data (multiple timeframes, assets)
3. **Evaluate**: Compute Sharpe ratio, max drawdown, win rate, profit factor
4. **Analyze**: LLM reviews results, identifies weaknesses, proposes improvements
5. **Iterate**: Repeat with refined strategy — track lineage of all versions
6. **Graduate**: Top strategies promoted to paper trading on IB
7. **Deploy**: After paper validation, optional live trading with position limits

## Project Structure

```
trading_agents/
├── CLAUDE.md              # This file
├── config/                # Strategy configs, broker settings
│   └── settings.yaml
├── src/
│   ├── __init__.py
│   ├── agent/             # LLM orchestration (strategy generation, analysis)
│   │   ├── __init__.py
│   │   ├── orchestrator.py
│   │   └── prompts.py
│   ├── backtesting/       # VectorBT wrapper, strategy execution
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   └── strategies.py
│   ├── data/              # Data download, caching, preprocessing
│   │   ├── __init__.py
│   │   └── provider.py
│   ├── evaluation/        # Performance metrics, ranking
│   │   ├── __init__.py
│   │   └── metrics.py
│   └── trading/           # Live/paper trading bridge via IB
│       ├── __init__.py
│       └── broker.py
├── strategies/            # Generated strategy configs (JSON/YAML)
├── results/               # Backtest results, logs
└── tests/
    └── __init__.py
```
