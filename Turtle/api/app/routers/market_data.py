"""Market data API endpoints."""

from typing import List, Dict
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.models.chart import ChartDataRequest, ChartDataResponse
from app.services.market_data_service import MarketDataService

router = APIRouter()
market_data_service = MarketDataService()


@router.get("/sources")
async def get_data_sources():
    """Get available data sources."""
    return {
        "sources": [
            {
                "name": "binance",
                "description": "Binance Exchange API",
                "type": "cryptocurrency",
                "supported_intervals": ["1m", "5m", "15m", "1h", "4h", "12h", "1d", "1w"]
            },
            {
                "name": "alpha_vantage",
                "description": "Alpha Vantage Financial Data",
                "type": "forex",
                "supported_intervals": ["1d"]
            },
            {
                "name": "synthetic",
                "description": "Synthetic Data Generator",
                "type": "demo",
                "supported_intervals": ["1m", "5m", "15m", "1h", "4h", "12h", "1d", "1w"]
            }
        ]
    }


@router.get("/pairs/crypto")
async def get_crypto_pairs():
    """Get available cryptocurrency trading pairs."""
    try:
        pairs = await market_data_service.get_crypto_pairs()
        return pairs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pairs/forex")
async def get_forex_pairs():
    """Get available forex trading pairs."""
    try:
        pairs = await market_data_service.get_forex_pairs()
        return pairs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download/crypto", response_model=ChartDataResponse)
async def download_crypto_data(
    symbol: str,
    interval: str = "1d",
    limit: int = Query(default=1000, ge=1, le=5000),
    start_date: str = None,
    end_date: str = None,
    source: str = "binance"
):
    """Download cryptocurrency data."""
    try:
        request = ChartDataRequest(
            symbol=symbol,
            interval=interval,
            limit=limit,
            start_date=start_date,
            end_date=end_date
        )
        result = await market_data_service.download_crypto_data(request, source)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download/forex", response_model=ChartDataResponse)
async def download_forex_data(
    base_currency: str,
    quote_currency: str,
    interval: str = "1d",
    limit: int = Query(default=100, ge=1, le=1000),
    start_date: str = None,
    end_date: str = None
):
    """Download forex data."""
    try:
        symbol = f"{base_currency}{quote_currency}"
        request = ChartDataRequest(
            symbol=symbol,
            interval=interval,
            limit=limit,
            start_date=start_date,
            end_date=end_date
        )
        result = await market_data_service.download_forex_data(
            base_currency, quote_currency, request
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download/synthetic", response_model=ChartDataResponse)
async def generate_synthetic_data(
    symbol: str,
    interval: str = "1d",
    limit: int = Query(default=1000, ge=1, le=10000),
    volatility: float = Query(default=0.02, ge=0.001, le=0.1),
    trend: float = Query(default=0.0, ge=-0.01, le=0.01),
    start_price: float = Query(default=100.0, gt=0)
):
    """Generate synthetic market data for testing."""
    try:
        result = await market_data_service.generate_synthetic_data(
            symbol=symbol,
            interval=interval,
            limit=limit,
            volatility=volatility,
            trend=trend,
            start_price=start_price
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validate")
async def validate_data_range(
    start_date: str,
    end_date: str
):
    """Validate date range for data download."""
    try:
        result = await market_data_service.validate_date_range(start_date, end_date)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intervals")
async def get_supported_intervals():
    """Get supported time intervals."""
    return {
        "intervals": [
            {"value": "1m", "label": "1 Minute", "seconds": 60},
            {"value": "5m", "label": "5 Minutes", "seconds": 300},
            {"value": "15m", "label": "15 Minutes", "seconds": 900},
            {"value": "1h", "label": "1 Hour", "seconds": 3600},
            {"value": "4h", "label": "4 Hours", "seconds": 14400},
            {"value": "12h", "label": "12 Hours", "seconds": 43200},
            {"value": "1d", "label": "1 Day", "seconds": 86400},
            {"value": "1w", "label": "1 Week", "seconds": 604800}
        ]
    }


@router.get("/latest/{symbol}")
async def get_latest_price(symbol: str):
    """Get latest price for a symbol."""
    try:
        price_data = await market_data_service.get_latest_price(symbol)
        if not price_data:
            raise HTTPException(status_code=404, detail="Symbol not found")
        return price_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{symbol}")
async def get_price_history(
    symbol: str,
    interval: str = "1d",
    limit: int = Query(default=30, ge=1, le=1000)
):
    """Get price history for a symbol."""
    try:
        history = await market_data_service.get_price_history(symbol, interval, limit)
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))