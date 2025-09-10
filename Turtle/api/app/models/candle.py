"""Candle data model."""

from datetime import datetime
from pydantic import BaseModel, Field


class Candle(BaseModel):
    """OHLC candle data model."""
    
    timestamp: datetime = Field(..., description="Candle timestamp")
    open: float = Field(..., gt=0, description="Opening price")
    high: float = Field(..., gt=0, description="Highest price")
    low: float = Field(..., gt=0, description="Lowest price")
    close: float = Field(..., gt=0, description="Closing price")
    volume: float = Field(default=0, ge=0, description="Trading volume")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        
    def __post_init__(self):
        """Validate OHLC relationships."""
        if self.high < max(self.open, self.close):
            raise ValueError("High must be >= max(open, close)")
        if self.low > min(self.open, self.close):
            raise ValueError("Low must be <= min(open, close)")