from dataclasses import dataclass
from datetime import datetime
from typing import List
import json


@dataclass
class Candle:
    timestamp: datetime
    open: float
    close: float
    high: float
    low: float


@dataclass
class ChartMetadata:
    asset_name: str
    currency: str
    period_duration: str = "1min"


@dataclass
class ChartData:
    metadata: ChartMetadata
    candles: List[Candle]
    
    @classmethod
    def from_json_file(cls, file_path: str) -> 'ChartData':
        """Load chart data from JSON file"""
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        metadata = ChartMetadata(**data['metadata'])
        candles = [
            Candle(
                timestamp=datetime.fromisoformat(candle['timestamp']),
                open=candle['open'],
                close=candle['close'],
                high=candle['high'],
                low=candle['low']
            )
            for candle in data['candles']
        ]
        
        return cls(metadata=metadata, candles=candles)