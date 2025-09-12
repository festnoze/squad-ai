"""Simple tests for ChartService to verify basic functionality."""

import pytest
from datetime import datetime

from app.services.chart_service import ChartService
from app.models.candle import Candle


class TestChartServiceSimple:
    """Basic test cases for ChartService."""
    
    def test_init(self):
        """Test service initialization."""
        service = ChartService()
        assert service is not None
        
    @pytest.mark.asyncio
    async def test_create_sample_data(self):
        """Test creating sample chart data."""
        service = ChartService()
        data = await service.create_sample_data(days=3)
        
        assert len(data) == 3
        assert all(isinstance(candle, Candle) for candle in data)
        
        # Verify data structure
        for candle in data:
            assert isinstance(candle.timestamp, datetime)
            assert isinstance(candle.open, float)
            assert isinstance(candle.high, float)
            assert isinstance(candle.low, float)
            assert isinstance(candle.close, float)
            assert isinstance(candle.volume, float)
            
            # Basic sanity checks
            assert candle.high >= max(candle.open, candle.close)
            assert candle.low <= min(candle.open, candle.close)
            assert candle.volume >= 0
            
    @pytest.mark.asyncio
    async def test_calculate_sma(self):
        """Test Simple Moving Average calculation."""
        service = ChartService()
        
        # Create test data
        prices = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0]
        sma = await service.calculate_sma(prices, period=3)
        
        # SMA should have values
        assert len(sma) > 0
        assert all(isinstance(x, float) for x in sma)
        
    @pytest.mark.asyncio
    async def test_get_market_summary(self):
        """Test getting market summary."""
        service = ChartService()
        
        summary = await service.get_market_summary("AAPL")
        
        assert isinstance(summary, dict)
        assert "symbol" in summary
        assert summary["symbol"] == "AAPL"