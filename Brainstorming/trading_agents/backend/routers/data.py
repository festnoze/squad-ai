"""Data endpoints — load price data, ticker info, cache listing."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

# Ensure project root is importable
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.data.provider import load_price_data, get_ticker_info, DATA_DIR  # noqa: E402
from backend.schemas import DataLoadResponse, TickerInfoResponse, CacheEntry  # noqa: E402

router = APIRouter()


@router.get("/load", response_model=DataLoadResponse)
async def load_data(
    symbol: str = Query(..., description="Ticker symbol, e.g. AAPL"),
    interval: str = Query("1d", description="Bar size: 1m, 5m, 15m, 1h, 4h, 1d, 1w"),
    start: str = Query("2020-01-01", description="Start date YYYY-MM-DD"),
    end: str = Query("2026-05-31", description="End date YYYY-MM-DD"),
):
    """Load OHLCV price data (downloads or reads from cache)."""
    try:
        # Determine if the data is already cached before loading
        from src.data.provider import _cache_path, _find_covering_cache

        exact_hit = _cache_path(symbol, interval, start, end).exists()
        covering_hit = _find_covering_cache(symbol, interval, start, end) is not None
        cached = exact_hit or covering_hit

        df = load_price_data(symbol, interval=interval, start=start, end=end)

        # Build preview rows (first / last 5)
        head_df = df.head(5).copy()
        tail_df = df.tail(5).copy()

        def _rows_to_dicts(frame):
            rows = []
            for idx, row in frame.iterrows():
                d = {"date": str(idx)}
                d.update(row.to_dict())
                rows.append(d)
            return rows

        return DataLoadResponse(
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            bars=len(df),
            date_range=[str(df.index[0]), str(df.index[-1])],
            cached=cached,
            preview_head=_rows_to_dicts(head_df),
            preview_tail=_rows_to_dicts(tail_df),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load data: {exc}")


@router.get("/ticker-info", response_model=TickerInfoResponse)
async def ticker_info(
    symbol: str = Query(..., description="Ticker symbol"),
):
    """Fetch ticker metadata (name, currency, etc.)."""
    try:
        info = get_ticker_info(symbol)
        return TickerInfoResponse(
            symbol=symbol,
            name=info.get("shortName", info.get("longName", symbol)),
            currency=info.get("currency", "USD"),
            extra={
                k: v
                for k, v in info.items()
                if k in ("sector", "industry", "exchange", "marketCap", "trailingPE")
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch ticker info: {exc}")


@router.get("/cache", response_model=list[CacheEntry])
async def list_cache():
    """List all cached .parquet files with sizes."""
    try:
        if not DATA_DIR.exists():
            return []

        entries: list[CacheEntry] = []
        for path in sorted(DATA_DIR.glob("*.parquet")):
            stem = path.stem  # e.g. "AAPL_1d_2020-01-01_2026-05-31"
            parts = stem.split("_")
            # Parse: SYMBOL_INTERVAL_START_END
            if len(parts) >= 4:
                symbol = parts[0]
                interval = parts[1]
                start = parts[2]
                end = parts[3]
            else:
                symbol = stem
                interval = ""
                start = ""
                end = ""

            size_kb = path.stat().st_size / 1024.0
            entries.append(CacheEntry(
                filename=path.name,
                size_kb=round(size_kb, 2),
                symbol=symbol,
                interval=interval,
                start=start,
                end=end,
            ))
        return entries
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list cache: {exc}")
