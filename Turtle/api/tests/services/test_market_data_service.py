"""Tests for MarketDataService."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import pandas as pd

from app.services.market_data_service import MarketDataService
from app.models.candle import Candle
from app.models.chart import ChartDataRequest


class TestMarketDataService:
    """Test cases for MarketDataService."""
    
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
        assert all(isinstance(source, dict) for source in sources)
        
    @patch('requests.get')
    def test_get_binance_data_success(self, mock_get):
        """Test successful Binance data retrieval."""
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = [
            [1609459200000, "29000", "30000", "28500", "29500", "1000", 1609459259999, "29250000", 100, "500", "14625000", "0"]
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        service = MarketDataService()
        data = service.get_binance_data("BTCUSDT", "1d", limit=1)
        
        assert len(data) == 1
        candle = data[0]
        assert isinstance(candle, Candle)
        assert candle.open == 29000.0
        assert candle.high == 30000.0
        assert candle.low == 28500.0
        assert candle.close == 29500.0
        assert candle.volume == 1000.0
        
    @patch('requests.get')
    def test_get_binance_data_error(self, mock_get):
        """Test Binance data retrieval with error."""
        mock_get.side_effect = Exception("Connection error")
        
        service = MarketDataService()
        data = service.get_binance_data("BTCUSDT", "1d", limit=1)
        
        assert data == []
        
    @patch('yfinance.download')
    def test_get_yahoo_data_success(self, mock_download):
        """Test successful Yahoo Finance data retrieval."""
        # Mock DataFrame
        mock_df = pd.DataFrame({
            'Open': [100.0],
            'High': [110.0],
            'Low': [95.0],
            'Close': [105.0],
            'Volume': [1000000]
        }, index=[datetime.now()])
        
        mock_download.return_value = mock_df
        
        service = MarketDataService()
        data = service.get_yahoo_data("AAPL", period="1d")
        
        assert len(data) == 1
        candle = data[0]
        assert isinstance(candle, Candle)
        assert candle.open == 100.0
        assert candle.high == 110.0
        assert candle.low == 95.0
        assert candle.close == 105.0
        assert candle.volume == 1000000.0
        
    @patch('yfinance.download')
    def test_get_yahoo_data_empty(self, mock_download):
        """Test Yahoo Finance data retrieval with empty result."""
        mock_download.return_value = pd.DataFrame()
        
        service = MarketDataService()
        data = service.get_yahoo_data("INVALID", period="1d")
        
        assert data == []
        
    @patch('requests.get')
    def test_get_alpha_vantage_data_success(self, mock_get):
        """Test successful Alpha Vantage data retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "Time Series (Daily)": {
                "2023-01-01": {
                    "1. open": "100.00",
                    "2. high": "110.00", 
                    "3. low": "95.00",
                    "4. close": "105.00",
                    "5. volume": "1000000"
                }
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        service = MarketDataService()
        data = service.get_alpha_vantage_data("AAPL", function="TIME_SERIES_DAILY")
        
        assert len(data) == 1
        candle = data[0]
        assert isinstance(candle, Candle)
        assert candle.open == 100.0
        assert candle.high == 110.0
        assert candle.low == 95.0
        assert candle.close == 105.0
        assert candle.volume == 1000000.0
        
    @pytest.mark.asyncio
    async def test_get_synthetic_data(self):
        """Test synthetic data generation."""
        service = MarketDataService()
        data = await service.get_synthetic_data("TEST", days=5)
        
        assert len(data) == 5
        assert all(isinstance(candle, Candle) for candle in data)
        
        # Check that data looks reasonable
        for candle in data:
            assert candle.open > 0
            assert candle.high >= candle.open
            assert candle.low <= candle.open
            assert candle.volume > 0
            
    @pytest.mark.asyncio
    async def test_get_chart_data(self):
        """Test getting chart data."""
        service = MarketDataService()
        
        request = ChartDataRequest(
            symbol="AAPL",
            source="synthetic",
            interval="1d",
            limit=10
        )
        
        data = await service.get_chart_data(request)
        
        assert len(data) == 10
        assert all(isinstance(candle, Candle) for candle in data)
        
    @pytest.mark.asyncio
    async def test_get_chart_data_binance(self):
        """Test getting chart data from Binance."""
        service = MarketDataService()
        
        with patch.object(service, 'get_binance_data') as mock_binance:
            mock_candle = Candle(
                timestamp=datetime.now(),
                open=100.0,
                high=110.0,
                low=95.0,
                close=105.0,
                volume=1000.0
            )
            mock_binance.return_value = [mock_candle]
            
            request = ChartDataRequest(
                symbol="BTCUSDT",
                source="binance",
                interval="1h",
                limit=1
            )
            
            data = await service.get_chart_data(request)
            
            assert len(data) == 1
            assert data[0] == mock_candle
            
    @pytest.mark.asyncio
    async def test_get_chart_data_invalid_source(self):
        """Test getting chart data with invalid source."""
        service = MarketDataService()
        
        request = ChartDataRequest(
            symbol="AAPL",
            source="invalid_source",
            interval="1d",
            limit=10
        )
        
        with pytest.raises(ValueError):
            await service.get_chart_data(request)
            
    @pytest.mark.asyncio
    async def test_get_latest_price_synthetic(self):
        """Test getting latest price for synthetic data."""
        service = MarketDataService()
        price = await service.get_latest_price("TEST", source="synthetic")
        
        assert isinstance(price, float)
        assert price > 0
        
    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_get_latest_price_binance(self, mock_get):
        """Test getting latest price from Binance."""
        mock_response = Mock()
        mock_response.json.return_value = {"price": "50000.00"}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        service = MarketDataService()
        price = await service.get_latest_price("BTCUSDT", source="binance")
        
        assert price == 50000.00
        
    @pytest.mark.asyncio
    async def test_get_latest_price_invalid_source(self):
        """Test getting latest price with invalid source."""
        service = MarketDataService()
        
        with pytest.raises(ValueError):
            await service.get_latest_price("AAPL", source="invalid")
            
    @pytest.mark.asyncio
    async def test_get_multiple_symbols(self):
        """Test getting data for multiple symbols."""
        service = MarketDataService()
        symbols = ["AAPL", "GOOGL", "MSFT"]
        
        with patch.object(service, 'get_chart_data') as mock_get_chart:
            mock_candle = Candle(
                timestamp=datetime.now(),
                open=100.0,
                high=110.0,
                low=95.0,
                close=105.0,
                volume=1000.0
            )
            mock_get_chart.return_value = [mock_candle]
            
            data = await service.get_multiple_symbols(symbols, source="synthetic")
            
            assert len(data) == 3
            assert all(symbol in data for symbol in symbols)
            assert all(len(data[symbol]) == 1 for symbol in symbols)