# Trading Agents -- API Reference

Base URL: `http://localhost:8000/api`

## Health

### `GET /api/health`

Health check.

**Response** `200`
```json
{ "status": "ok" }
```

---

## Data

### `GET /api/data/load`

Load OHLCV data for a symbol. Downloads from yfinance if not cached, otherwise loads from Parquet cache.

**Query params**

| Param | Type | Required | Example | Description |
|-------|------|----------|---------|-------------|
| symbol | string | yes | BTC-USD | Ticker symbol |
| interval | string | yes | 1d | Bar size: 1m, 5m, 15m, 1h, 4h, 1d, 1w |
| start | string | yes | 2020-01-01 | Start date (YYYY-MM-DD) |
| end | string | yes | 2026-05-31 | End date (YYYY-MM-DD) |

**Response** `200`
```json
{
  "symbol": "BTC-USD",
  "interval": "1d",
  "start": "2020-01-01",
  "end": "2026-05-31",
  "bars": 2341,
  "from_cache": true,
  "date_range": {
    "first": "2020-01-01T00:00:00",
    "last": "2026-05-30T00:00:00"
  },
  "preview": {
    "columns": ["Open", "High", "Low", "Close", "Volume"],
    "head": [...],
    "tail": [...]
  }
}
```

**Errors**: `400` if symbol invalid or yfinance returns no data.

---

### `GET /api/data/ticker-info`

Fetch asset metadata from yfinance.

**Query params**

| Param | Type | Required | Example |
|-------|------|----------|---------|
| symbol | string | yes | GOOGL |

**Response** `200`
```json
{
  "symbol": "GOOGL",
  "name": "Alphabet Inc.",
  "currency": "USD"
}
```

---

### `GET /api/data/cache`

List all cached Parquet files.

**Response** `200`
```json
{
  "files": [
    {
      "filename": "BTC-USD_1d_2020-01-01_2026-05-31.parquet",
      "size_kb": 152,
      "symbol": "BTC-USD",
      "interval": "1d"
    }
  ]
}
```

---

## Backtest

### `POST /api/backtest/run`

Run a backtest with a specified strategy.

**Request body**
```json
{
  "symbol": "BTC-USD",
  "interval": "1d",
  "start": "2020-01-01",
  "end": "2026-05-31",
  "strategy": "ma_crossover",
  "params": {
    "fast_ma": 20,
    "slow_ma": 50
  },
  "init_cash": 10000,
  "fees": 0.001
}
```

**Strategy types and params**:

| Strategy | Required params |
|----------|----------------|
| `ma_crossover` | `fast_ma` (int), `slow_ma` (int) |
| `rsi_bb` | `rsi_window` (int), `rsi_lo` (int), `rsi_hi` (int), `bb_window` (int), `bb_alpha` (float) |
| `adaptive` | `trend_fast` (int), `trend_slow` (int), `rev_rsi_window` (int), `rev_rsi_lo` (int), `rev_rsi_hi` (int), `adx_window` (int), `hurst_window` (int) |

**Response** `200`
```json
{
  "metrics": {
    "total_return": 2.5718,
    "sharpe_ratio": 0.92,
    "max_drawdown": -0.2343,
    "n_trades": 23,
    "win_rate": 0.7391,
    "profit_factor": 7.04
  },
  "portfolio_values": [
    { "date": "2020-01-01T00:00:00", "value": 10000.0 },
    ...
  ],
  "buy_hold_values": [
    { "date": "2020-01-01T00:00:00", "value": 10000.0 },
    ...
  ],
  "price_data": [
    { "date": "2020-01-01T00:00:00", "value": 7200.17 },
    ...
  ],
  "entries": ["2020-03-15T00:00:00", ...],
  "exits": ["2020-05-10T00:00:00", ...]
}
```

---

### `GET /api/backtest/regime`

Compute market regime classification over a period.

**Query params**

| Param | Type | Required | Example |
|-------|------|----------|---------|
| symbol | string | yes | BTC-USD |
| interval | string | yes | 1d |
| start | string | yes | 2020-01-01 |
| end | string | yes | 2026-05-31 |

**Response** `200`
```json
{
  "dates": ["2020-01-01T00:00:00", ...],
  "adx": [25.3, 28.1, ...],
  "hurst": [0.42, 0.38, ...],
  "regime": ["trending", "uncertain", "reverting", ...]
}
```

---

## Sweep

### `POST /api/sweep/run`

Run a vectorized parameter sweep for MA crossover.

**Request body**
```json
{
  "symbol": "BTC-USD",
  "interval": "1d",
  "start": "2020-01-01",
  "end": "2026-05-31",
  "fast_range": [5, 50, 5],
  "slow_range": [20, 200, 10],
  "init_cash": 10000,
  "fees": 0.001
}
```

`fast_range` and `slow_range` are `[min, max, step]` arrays.

**Response** `200`
```json
{
  "sharpe_matrix": [[1.2, 1.5, ...], ...],
  "fast_values": [5, 10, 15, ...],
  "slow_values": [20, 30, 40, ...],
  "best": {
    "fast": 40,
    "slow": 200,
    "sharpe": 4.06
  },
  "stats": {
    "mean": 2.90,
    "median": 2.94,
    "max": 4.06,
    "valid_count": 174
  },
  "total_combos": 190
}
```

---

## Evolution (WebSocket)

### `WebSocket /api/evolution/ws`

Run GP strategy evolution with real-time progress updates.

**Connection**: `ws://localhost:8000/api/evolution/ws`

**Send config** (JSON, after connection opens):
```json
{
  "symbol": "BTC-USD",
  "interval": "1d",
  "start": "2020-01-01",
  "end": "2026-05-31",
  "train_end": "2025-01-01",
  "pop_size": 300,
  "n_gen": 50,
  "max_depth": 6,
  "complexity_penalty": 0.05,
  "seed": 42
}
```

**Receive messages** (JSON, multiple types):

#### Generation progress
```json
{
  "type": "generation",
  "gen": 5,
  "nevals": 228,
  "avg": 0.156,
  "best": 1.846,
  "viable": 140
}
```
Sent after each generation. `avg` is the mean fitness of viable individuals, `best` is the top fitness, `viable` is the count of individuals with fitness > -900.

#### Evolution complete
```json
{
  "type": "complete",
  "top_strategies": [
    {
      "rank": 1,
      "expression": "GT(RSI14(Close()), T30())",
      "tree_size": 5,
      "tree_depth": 3,
      "train_return": 0.45,
      "train_sharpe": 1.2,
      "train_drawdown": -0.15,
      "train_trades": 25,
      "test_return": 0.12,
      "test_sharpe": 0.8,
      "test_drawdown": -0.10,
      "test_trades": 8,
      "is_overfit": false
    },
    ...
  ]
}
```

#### Error
```json
{
  "type": "error",
  "message": "No data returned for symbol XYZ"
}
```

---

## Running the servers

### Backend
```bash
cd trading_agents
source .venv/Scripts/activate   # Windows
python -m uvicorn backend.main:app --reload --port 8000
```

### Frontend
```bash
cd trading_agents/frontend
npm run dev
# Opens at http://localhost:5173
```

---

## Error handling

All REST endpoints return errors as:
```json
{
  "detail": "Error description message"
}
```

| Code | Meaning |
|------|---------|
| 400 | Bad request (invalid symbol, dates, params) |
| 500 | Internal server error (computation failed) |

---

## Rate limits

None. The API is designed for local use only. Long-running operations (sweep, evolution) may take several minutes. Use the WebSocket for evolution to get real-time progress instead of HTTP polling.
