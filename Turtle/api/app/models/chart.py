"""Chart data models."""

from typing import List
from pydantic import BaseModel, Field
from .candle import Candle


class ChartMetadata(BaseModel):
    """Chart metadata model."""
    
    asset_name: str = Field(..., description="Name of the asset")
    currency: str = Field(..., description="Quote currency")
    period_duration: str = Field(..., description="Time period duration (e.g., '1min', '1h', '1d')")
    symbol: str = Field(default="", description="Trading symbol")
    exchange: str = Field(default="", description="Exchange name")


class ChartData(BaseModel):
    """Chart data container model."""
    
    metadata: ChartMetadata = Field(..., description="Chart metadata")
    candles: List[Candle] = Field(..., description="List of OHLC candles")
    
    @property
    def symbol(self) -> str:
        """Get the trading symbol."""
        return self.metadata.symbol or self.metadata.asset_name.upper()
    
    @property
    def latest_price(self) -> float:
        """Get the latest closing price."""
        if not self.candles:
            return 0.0
        return self.candles[-1].close
    
    @property
    def price_change(self) -> float:
        """Get price change from first to last candle."""
        if len(self.candles) < 2:
            return 0.0
        return self.candles[-1].close - self.candles[0].close
    
    @property
    def price_change_percent(self) -> float:
        """Get price change percentage."""
        if len(self.candles) < 2 or self.candles[0].close == 0:
            return 0.0
        return (self.price_change / self.candles[0].close) * 100


class ChartDataRequest(BaseModel):
    """Request model for chart data operations."""
    
    symbol: str = Field(..., description="Trading symbol")
    interval: str = Field(default="1d", description="Time interval")
    limit: int = Field(default=100, ge=1, le=5000, description="Number of candles")
    start_date: str = Field(default=None, description="Start date (YYYY-MM-DD)")
    end_date: str = Field(default=None, description="End date (YYYY-MM-DD)")


class ChartDataResponse(BaseModel):
    """Response model for chart data."""
    
    success: bool = Field(..., description="Operation success status")
    message: str = Field(default="", description="Response message")
    data: ChartData = Field(default=None, description="Chart data")
    filename: str = Field(default="", description="Generated filename")