"""Pydantic models for request / response validation."""
from __future__ import annotations

from pydantic import BaseModel, Field


# ── Data ─────────────────────────────────────────────────────────

class DataLoadResponse(BaseModel):
    symbol: str
    interval: str
    start: str
    end: str
    bars: int
    date_range: list[str]
    cached: bool
    preview_head: list[dict]
    preview_tail: list[dict]


class TickerInfoResponse(BaseModel):
    symbol: str
    name: str
    currency: str
    extra: dict = Field(default_factory=dict)


class CacheEntry(BaseModel):
    filename: str
    size_kb: float
    symbol: str
    interval: str
    start: str
    end: str


# ── Backtest ─────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    symbol: str
    interval: str = "1d"
    start: str = "2020-01-01"
    end: str = "2026-05-31"
    strategy: str = "ma_crossover"  # ma_crossover | rsi_bb | adaptive
    params: dict = Field(default_factory=dict)
    init_cash: float = 10_000
    fees: float = 0.001


class MetricsResponse(BaseModel):
    total_return: float
    sharpe: float
    max_dd: float
    trades: int
    win_rate: float
    profit_factor: float


class PortfolioPoint(BaseModel):
    date: str
    value: float


class EntryExitPoint(BaseModel):
    date: str
    price: float


class BacktestResponse(BaseModel):
    metrics: MetricsResponse
    portfolio_values: list[PortfolioPoint]
    buy_hold_values: list[PortfolioPoint]
    entries: list[EntryExitPoint]
    exits: list[EntryExitPoint]


# ── Sweep ────────────────────────────────────────────────────────

class SweepRequest(BaseModel):
    symbol: str
    interval: str = "1d"
    start: str = "2020-01-01"
    end: str = "2026-05-31"
    fast_range: list[float] = Field(default=[5, 51, 5], description="[min, max, step]")
    slow_range: list[float] = Field(default=[20, 201, 10], description="[min, max, step]")
    init_cash: float = 10_000
    fees: float = 0.001


class SweepBest(BaseModel):
    fast: int
    slow: int
    sharpe: float


class SweepStats(BaseModel):
    mean: float
    median: float
    max: float
    valid_count: int


class SweepResponse(BaseModel):
    sharpe_matrix: list[list[float | None]]
    fast_values: list[int]
    slow_values: list[int]
    best: SweepBest
    stats: SweepStats


# ── Evolution ────────────────────────────────────────────────────

# ── Multi-strategy allocation ───────────────────────────────────

class MultiBacktestRequest(BaseModel):
    symbol: str
    interval: str = "1d"
    start: str = "2020-01-01"
    end: str = "2026-05-31"
    strategies: list[dict] = Field(
        default_factory=lambda: [
            {"name": "MA(20/50)", "type": "ma_crossover", "params": {"fast_ma": 20, "slow_ma": 50}},
            {"name": "RSI+BB", "type": "rsi_bb", "params": {}},
            {"name": "Adaptive", "type": "adaptive", "params": {}},
        ]
    )
    init_cash: float = 10_000
    fees: float = 0.001


# ── Evolution ────────────────────────────────────────────────────

class EvolutionConfig(BaseModel):
    symbol: str
    interval: str = "1d"
    start: str = "2020-01-01"
    end: str = "2026-05-31"
    train_end: str = "2025-06-01"
    pop_size: int = 100
    n_gen: int = 20
    max_depth: int = 8
    complexity_penalty: float = 0.01
    seed: int = 42
