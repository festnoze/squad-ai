"""Chart data service - handles chart data operations."""

import json
from pathlib import Path
from typing import List, Optional, Dict
import pandas as pd
import random
from datetime import datetime, timedelta

from app.models.chart import ChartData, ChartMetadata, ChartDataRequest, ChartDataResponse
from app.models.candle import Candle
from app.core.config import settings


class ChartService:
    """Service for managing chart data operations."""
    
    def __init__(self):
        self.data_dir = Path(settings.CHART_DATA_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    async def create_sample_data(self, days: int = 30) -> List[Candle]:
        """Create sample chart data for testing."""
        candles = []
        base_price = random.uniform(50, 200)
        
        for i in range(days):
            # Simple random walk
            change = random.uniform(-0.05, 0.05)
            base_price = base_price * (1 + change)
            
            volatility = random.uniform(0.01, 0.03)
            high = base_price * (1 + volatility)
            low = base_price * (1 - volatility)
            open_price = random.uniform(low, high)
            close_price = random.uniform(low, high)
            
            candle = Candle(
                timestamp=datetime.now() - timedelta(days=days-i),
                open=round(open_price, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close_price, 2),
                volume=random.uniform(1000, 10000)
            )
            candles.append(candle)
        
        return candles
    
    async def calculate_sma(self, prices: List[float], period: int) -> List[float]:
        """Calculate Simple Moving Average."""
        if len(prices) < period:
            return []
        
        sma_values = []
        for i in range(period - 1, len(prices)):
            sma = sum(prices[i - period + 1:i + 1]) / period
            sma_values.append(sma)
        
        return sma_values
    
    
    async def calculate_ema(self, prices: List[float], period: int) -> List[float]:
        """Calculate Exponential Moving Average."""
        if len(prices) < period:
            return [float('nan')] * len(prices)
        
        df = pd.Series(prices)
        ema = df.ewm(span=period, adjust=False).mean()
        
        # Set first few values as NaN
        ema.iloc[:period-1] = float('nan')
        
        return ema.tolist()
    
    async def calculate_rsi(self, prices: List[float], period: int = 14) -> List[float]:
        """Calculate RSI (Relative Strength Index)."""
        if len(prices) < period + 1:
            return [float('nan')] * len(prices)
        
        df = pd.Series(prices)
        delta = df.diff()
        
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.tolist()
    
    async def calculate_bollinger_bands(self, prices: List[float], period: int = 20, std_dev: float = 2):
        """Calculate Bollinger Bands."""
        df = pd.Series(prices)
        
        # Middle band (SMA)
        middle = df.rolling(window=period).mean()
        
        # Standard deviation
        std = df.rolling(window=period).std()
        
        # Upper and lower bands
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        return upper.tolist(), middle.tolist(), lower.tolist()
    
    async def calculate_macd(self, prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
        """Calculate MACD (Moving Average Convergence Divergence)."""
        df = pd.Series(prices)
        
        # Calculate EMAs
        ema_fast = df.ewm(span=fast).mean()
        ema_slow = df.ewm(span=slow).mean()
        
        # MACD line
        macd_line = ema_fast - ema_slow
        
        # Signal line
        signal_line = macd_line.ewm(span=signal).mean()
        
        # Histogram
        histogram = macd_line - signal_line
        
        return macd_line.tolist(), signal_line.tolist(), histogram.tolist()
    
    async def get_chart_data_with_indicators(self, request: ChartDataRequest, 
                                           indicators: List[str] = None) -> ChartDataResponse:
        """Get chart data with technical indicators."""
        # Create sample data
        candles = await self.create_sample_data(request.limit or 100)
        
        # Extract close prices for indicators
        close_prices = [candle.close for candle in candles]
        
        indicator_data = {}
        if indicators:
            if "sma" in indicators:
                indicator_data["sma"] = await self.calculate_sma(close_prices, 20)
            
            if "ema" in indicators:
                indicator_data["ema"] = await self.calculate_ema(close_prices, 20)
            
            if "rsi" in indicators:
                indicator_data["rsi"] = await self.calculate_rsi(close_prices)
            
            if "bollinger" in indicators:
                upper, middle, lower = await self.calculate_bollinger_bands(close_prices)
                indicator_data["bollinger_upper"] = upper
                indicator_data["bollinger_middle"] = middle
                indicator_data["bollinger_lower"] = lower
            
            if "macd" in indicators:
                macd_line, signal_line, histogram = await self.calculate_macd(close_prices)
                indicator_data["macd_line"] = macd_line
                indicator_data["macd_signal"] = signal_line
                indicator_data["macd_histogram"] = histogram
        
        # Create metadata for chart data
        metadata = ChartMetadata(
            asset_name=request.symbol,
            currency="USD",  # Default currency
            period_duration=request.interval,
            symbol=request.symbol,
            exchange="synthetic"  # Default exchange for sample data
        )
        
        return ChartDataResponse(
            success=True,
            message="Chart data retrieved successfully",
            data=candles,
            indicators=indicator_data,
            metadata=metadata
        )
    
    def detect_patterns(self, candles: List[Candle]) -> List[Dict]:
        """Detect chart patterns."""
        patterns = []
        
        # Simple pattern detection (placeholder)
        if len(candles) >= 5:
            # Check for ascending triangle pattern
            recent_highs = [c.high for c in candles[-5:]]
            recent_lows = [c.low for c in candles[-5:]]
            
            if max(recent_highs) == recent_highs[-1] and min(recent_lows) > recent_lows[0]:
                patterns.append({
                    "type": "ascending_triangle",
                    "confidence": 0.7,
                    "start_index": len(candles) - 5,
                    "end_index": len(candles) - 1
                })
        
        return patterns
    
    def get_support_resistance_levels(self, candles: List[Candle]) -> Dict[str, List[float]]:
        """Get support and resistance levels."""
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        
        # Simple support/resistance calculation
        support_levels = []
        resistance_levels = []
        
        # Find local minima and maxima
        for i in range(2, len(closes) - 2):
            # Support level (local low)
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                support_levels.append(lows[i])
            
            # Resistance level (local high)  
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                resistance_levels.append(highs[i])
        
        return {
            "support": sorted(list(set(support_levels)))[-3:],  # Top 3 support levels
            "resistance": sorted(list(set(resistance_levels)), reverse=True)[:3]  # Top 3 resistance levels
        }
    
    def calculate_volatility(self, candles: List[Candle], period: int = 20) -> float:
        """Calculate price volatility."""
        if len(candles) < period:
            return 0.0
        
        closes = [c.close for c in candles[-period:]]
        df = pd.Series(closes)
        returns = df.pct_change().dropna()
        
        return float(returns.std() * (252 ** 0.5))  # Annualized volatility
    
    async def get_market_summary(self, symbol: str) -> Dict:
        """Get market summary for a symbol."""
        # Generate sample data for the summary
        candles = await self.create_sample_data(1)
        candle = candles[0]
        
        previous_close = candle.close * 0.99  # Simulate previous close
        change = candle.close - previous_close
        change_percent = (change / previous_close) * 100
        
        return {
            "symbol": symbol,
            "price": candle.close,
            "change": round(change, 2),
            "change_percent": round(change_percent, 2),
            "volume": candle.volume,
            "high": candle.high,
            "low": candle.low,
            "open": candle.open
        }
    
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