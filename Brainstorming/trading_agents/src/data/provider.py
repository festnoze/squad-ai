"""
Market data provider with local Parquet caching.

Downloads OHLCV data via yfinance, caches to data/ as Parquet files.
On subsequent calls, loads from cache if available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]
import yfinance as yf  # type: ignore[import-untyped]

# Cache directory at project root
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _cache_path(symbol: str, interval: str, start: str, end: str) -> Path:
    """Build a deterministic cache file path."""
    return DATA_DIR / f"{symbol}_{interval}_{start}_{end}.parquet"


def _find_covering_cache(symbol: str, interval: str, start: str, end: str) -> Path | None:
    """Find a cached file for the same symbol/interval that covers the requested date range."""
    if not DATA_DIR.exists():
        return None

    req_start = pd.Timestamp(start)
    req_end = pd.Timestamp(end)
    prefix = f"{symbol}_{interval}_"

    for path in DATA_DIR.glob(f"{prefix}*.parquet"):
        # Parse dates from filename: SYMBOL_INTERVAL_START_END.parquet
        stem = path.stem[len(prefix):]  # "2024-06-01_2026-05-29"
        parts = stem.split("_", 1)
        if len(parts) != 2:
            continue
        try:
            cached_start = pd.Timestamp(parts[0])
            cached_end = pd.Timestamp(parts[1])
        except ValueError:
            continue

        if cached_start <= req_start and cached_end >= req_end:
            return path

    return None


def get_ticker_info(symbol: str) -> dict[str, Any]:
    """Fetch ticker metadata (name, currency, etc.)."""
    return yf.Ticker(symbol).info


def load_price_data(
    symbol: str,
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Load OHLCV data for a symbol, using cache if available.

    Args:
        symbol: Ticker symbol (e.g., "AAPL", "GOOGL").
        interval: Bar size — "1m", "5m", "15m", "1h", "4h", "1d", "1w".
        start: Start date as "YYYY-MM-DD".
        end: End date as "YYYY-MM-DD".

    Returns:
        DataFrame with OHLCV columns indexed by datetime.
    """
    start = start or "2020-01-01"
    end = end or pd.Timestamp.now().strftime("%Y-%m-%d")

    cache_file = _cache_path(symbol, interval, start, end)

    if cache_file.exists():
        print(f"[cache] Loading {symbol} {interval} from {cache_file.name}")
        return pd.read_parquet(cache_file)

    # Check if a wider cached file covers this range
    covering = _find_covering_cache(symbol, interval, start, end)
    if covering is not None:
        print(f"[cache] Slicing {symbol} {interval} from {covering.name}")
        df = pd.read_parquet(covering)
        return df.loc[start:end]

    print(f"[download] Fetching {symbol} {interval} {start} -> {end} ...")
    df = yf.download(symbol, start=start, end=end, interval=interval, progress=False)

    if df.empty:
        raise ValueError(
            f"No data returned for {symbol} ({interval}, {start} -> {end}). "
            "Check symbol/dates or yfinance interval limits: "
            "1m=7d, 2m/5m/15m/30m=60d, 1h=730d, 1d/1w=unlimited."
        )

    # Flatten multi-level columns if present (yfinance sometimes returns them)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_file)
    print(f"[cache] Saved to {cache_file.name} ({len(df)} bars)")

    return df


# Mapping from interval string to pandas freq alias (for VectorBT)
INTERVAL_TO_FREQ = {
    "1m": "1min",
    "2m": "2min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
    "1w": "1W",
}
