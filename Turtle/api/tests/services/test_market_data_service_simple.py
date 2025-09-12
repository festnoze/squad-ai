"""Simple tests for MarketDataService to verify basic functionality."""

import pytest
from datetime import datetime
from unittest.mock import patch, Mock

from app.services.market_data_service import MarketDataService
from app.models.chart import ChartDataRequest
from app.models.candle import Candle


class TestMarketDataServiceSimple:
    """Basic test cases for MarketDataService."""
    
    def test_init(self):
        """Test service initialization."""
        service = MarketDataService()
        assert service is not None
        
    @pytest.mark.asyncio
    async def test_get_available_sources(self):
        """Test getting available data sources."""
        service = MarketDataService()
        sources = await service.get_available_sources()
        
        assert isinstance(sources, list)
        assert len(sources) > 0
        
    @pytest.mark.asyncio
    async def test_get_synthetic_data(self):
        """Test synthetic data generation."""
        service = MarketDataService()
        data = await service.get_synthetic_data("TEST", days=3)
        
        assert len(data) == 3
        assert all(isinstance(candle, Candle) for candle in data)
        
        # Check data structure
        for candle in data:
            assert candle.open > 0
            assert candle.high >= candle.open
            assert candle.low <= candle.open
            assert candle.volume > 0
            
    @pytest.mark.asyncio
    async def test_get_chart_data_synthetic(self):
        """Test getting chart data with synthetic source."""
        service = MarketDataService()
        
        request = ChartDataRequest(
            symbol="AAPL",
            source="synthetic", 
            interval="1d",
            limit=5
        )
        
        data = await service.get_chart_data(request)
        
        assert len(data) == 5
        assert all(isinstance(candle, Candle) for candle in data)
        
    @pytest.mark.asyncio
    async def test_get_latest_price_synthetic(self):
        """Test getting latest price for synthetic data."""
        service = MarketDataService()
        price = await service.get_latest_price("TEST", source="synthetic")
        
        assert isinstance(price, float)
        assert price > 0
        
    @pytest.mark.asyncio
    async def test_get_multiple_symbols(self):
        """Test getting data for multiple symbols."""
        service = MarketDataService()
        symbols = ["AAPL", "GOOGL"]
        
        data = await service.get_multiple_symbols(symbols, source="synthetic", limit=2)
        
        assert len(data) == 2
        assert "AAPL" in data
        assert "GOOGL" in data
        assert len(data["AAPL"]) == 2
        assert len(data["GOOGL"]) == 2