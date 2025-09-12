from dataclasses import dataclass
from datetime import datetime


@dataclass
class Candle:
    """Represents a single candlestick with OHLC data"""
    timestamp: datetime
    open: float
    close: float
    high: float
    low: float