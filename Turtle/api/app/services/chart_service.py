"""Chart data service - handles chart data operations."""

import json
import os
from pathlib import Path
from typing import List, Optional
import pandas as pd
from datetime import datetime

from app.models.chart import ChartData, ChartMetadata, ChartDataRequest, ChartDataResponse
from app.models.candle import Candle
from app.core.config import settings


class ChartService:
    """Service for managing chart data operations."""
    
    def __init__(self):
        self.data_dir = Path(settings.CHART_DATA_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    async def list_chart_files(self) -> List[str]:
        """List all available chart files."""
        try:
            files = []
            for file_path in self.data_dir.glob("*.json"):
                files.append(file_path.name)
            return sorted(files)
        except Exception as e:
            raise Exception(f"Failed to list chart files: {str(e)}")
    
    async def load_chart_data(self, filename: str) -> Optional[ChartData]:
        """Load chart data from file."""
        try:
            file_path = self.data_dir / filename
            if not file_path.exists():
                return None
            
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Convert to Pydantic models
            metadata = ChartMetadata(**data['metadata'])
            candles = [Candle(**candle) for candle in data['candles']]
            
            return ChartData(metadata=metadata, candles=candles)
        
        except Exception as e:
            raise Exception(f"Failed to load chart data: {str(e)}")
    
    async def save_chart_data(self, chart_data: ChartData, filename: str) -> bool:
        """Save chart data to file."""
        try:
            file_path = self.data_dir / filename
            
            # Convert to dict for JSON serialization
            data = {
                'metadata': chart_data.metadata.dict(),
                'candles': [candle.dict() for candle in chart_data.candles]
            }
            
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            
            return True
        
        except Exception as e:
            raise Exception(f"Failed to save chart data: {str(e)}")
    
    async def delete_chart_file(self, filename: str) -> bool:
        """Delete a chart file."""
        try:
            file_path = self.data_dir / filename
            if file_path.exists():
                file_path.unlink()
                return True
            return False
        
        except Exception as e:
            raise Exception(f"Failed to delete chart file: {str(e)}")
    
    async def get_chart_metadata(self, filename: str) -> Optional[ChartMetadata]:
        """Get chart metadata without loading full data."""
        try:
            file_path = self.data_dir / filename
            if not file_path.exists():
                return None
            
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            return ChartMetadata(**data['metadata'])
        
        except Exception as e:
            raise Exception(f"Failed to get chart metadata: {str(e)}")
    
    async def resample_chart_data(self, filename: str, target_period: str) -> ChartData:
        """Resample chart data to different timeframe."""
        try:
            chart_data = await self.load_chart_data(filename)
            if not chart_data:
                raise Exception("Chart file not found")
            
            # Convert candles to DataFrame
            df = pd.DataFrame([
                {
                    'timestamp': pd.to_datetime(candle.timestamp),
                    'open': candle.open,
                    'high': candle.high,
                    'low': candle.low,
                    'close': candle.close,
                    'volume': candle.volume or 0
                }
                for candle in chart_data.candles
            ])
            
            df.set_index('timestamp', inplace=True)
            
            # Period mapping
            freq_map = {
                "5min": "5T",
                "15min": "15T",
                "1h": "1H",
                "4h": "4H",
                "12h": "12H",
                "1d": "1D",
                "1w": "1W"
            }
            
            freq = freq_map.get(target_period, "1D")
            
            # Resample data
            resampled = df.resample(freq).agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            
            # Convert back to Candle objects
            resampled_candles = []
            for timestamp, row in resampled.iterrows():
                resampled_candles.append(Candle(
                    timestamp=timestamp.to_pydatetime(),
                    open=row['open'],
                    high=row['high'],
                    low=row['low'],
                    close=row['close'],
                    volume=row['volume']
                ))
            
            # Update metadata
            new_metadata = chart_data.metadata.copy()
            new_metadata.period_duration = target_period
            
            return ChartData(metadata=new_metadata, candles=resampled_candles)
        
        except Exception as e:
            raise Exception(f"Failed to resample chart data: {str(e)}")
    
    async def download_chart_data(self, request: ChartDataRequest) -> ChartDataResponse:
        """Download new chart data (placeholder - will be implemented by market data service)."""
        # This will be implemented by importing from the existing download modules
        # For now, return a placeholder response
        return ChartDataResponse(
            success=False,
            message="Download functionality to be implemented"
        )
    
    def _generate_filename(self, symbol: str, interval: str, start_date: str = None, end_date: str = None) -> str:
        """Generate filename for chart data."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        if start_date and end_date:
            return f"{symbol.lower()}_{interval}_{start_date}_{end_date}.json"
        else:
            return f"{symbol.lower()}_{interval}_{timestamp}.json"