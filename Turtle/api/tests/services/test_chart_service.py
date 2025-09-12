"""Tests for ChartService."""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime
import pandas as pd

from app.services.chart_service import ChartService
from app.models.candle import Candle
from app.models.chart import ChartDataRequest, ChartDataResponse


class TestChartService:
    """Test cases for ChartService."""
    
    def test_init(self):
        """Test service initialization."""
        service = ChartService()
        assert service is not None
        
    @pytest.mark.asyncio
    async def test_create_sample_data(self):
        """Test creating sample chart data."""
        service = ChartService()
        data = await service.create_sample_data(days=5)
        
        assert len(data) == 5
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
        prices = [10, 12, 14, 16, 18, 20, 22, 24, 26, 28]
        sma = await service.calculate_sma(prices, period=5)
        
        # SMA should start from index 4 (5th element)
        expected_length = len(prices) - 5 + 1  # 6 values
        assert len(sma) == expected_length
        
        # First SMA value should be average of first 5 prices
        assert sma[0] == (10 + 12 + 14 + 16 + 18) / 5  # 14.0
        
        # Last SMA value should be average of last 5 prices
        assert sma[-1] == (20 + 22 + 24 + 26 + 28) / 5  # 24.0
        
    @pytest.mark.asyncio
    async def test_calculate_sma_insufficient_data(self):
        """Test SMA calculation with insufficient data."""
        service = ChartService()
        
        prices = [10, 12, 14]  # Less than period
        sma = await service.calculate_sma(prices, period=5)
        
        assert sma == []
        
    @pytest.mark.asyncio
    async def test_calculate_ema(self):
        """Test Exponential Moving Average calculation."""
        service = ChartService()
        
        prices = [10, 12, 14, 16, 18, 20, 22, 24, 26, 28]
        ema = await service.calculate_ema(prices, period=5)
        
        # EMA should have same length as input
        assert len(ema) == len(prices)
        
        # First few values should be NaN until we have enough data
        assert pd.isna(ema[0])
        assert pd.isna(ema[1])
        assert pd.isna(ema[2])
        assert pd.isna(ema[3])
        
        # From period index onwards, should have valid values
        assert not pd.isna(ema[4])
        assert not pd.isna(ema[-1])
        
        # EMA should be more responsive than SMA (last value should be higher)
        sma = await service.calculate_sma(prices, period=5)
        assert ema[-1] > sma[-1]
        
    @pytest.mark.asyncio
    async def test_calculate_rsi(self):
        """Test RSI calculation."""
        service = ChartService()
        
        # Create test data with clear trend
        prices = [44, 44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.85, 47.25, 47.92, 46.96, 45.66, 46.81, 47.64]
        rsi = await service.calculate_rsi(prices, period=14)
        
        # RSI should have same length as input
        assert len(rsi) == len(prices)
        
        # First 13 values should be NaN (need 14 periods)
        for i in range(13):
            assert pd.isna(rsi[i])
            
        # RSI values should be between 0 and 100
        valid_rsi = [x for x in rsi if not pd.isna(x)]
        for value in valid_rsi:
            assert 0 <= value <= 100
            
    @pytest.mark.asyncio
    async def test_calculate_bollinger_bands(self):
        """Test Bollinger Bands calculation."""
        service = ChartService()
        
        prices = [20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34]
        upper, middle, lower = await service.calculate_bollinger_bands(prices, period=10, std_dev=2)
        
        # All bands should have same length as input
        assert len(upper) == len(prices)
        assert len(middle) == len(prices)
        assert len(lower) == len(prices)
        
        # Middle band should be SMA
        sma = await service.calculate_sma(prices, period=10)
        valid_middle = [x for x in middle if not pd.isna(x)]
        assert len(valid_middle) == len(sma)
        
        # Upper band should be above middle, lower band should be below
        for i in range(len(prices)):
            if not pd.isna(upper[i]):
                assert upper[i] > middle[i]
                assert lower[i] < middle[i]
                
    @pytest.mark.asyncio
    async def test_calculate_macd(self):
        """Test MACD calculation."""
        service = ChartService()
        
        # Create longer price series for MACD
        prices = list(range(50, 100))  # 50 price points
        macd_line, signal_line, histogram = await service.calculate_macd(prices, fast=12, slow=26, signal=9)
        
        # All should have same length as input
        assert len(macd_line) == len(prices)
        assert len(signal_line) == len(prices)
        assert len(histogram) == len(prices)
        
        # Histogram should be MACD - Signal
        for i in range(len(prices)):
            if not pd.isna(macd_line[i]) and not pd.isna(signal_line[i]):
                expected_hist = macd_line[i] - signal_line[i]
                assert abs(histogram[i] - expected_hist) < 1e-10
                
    @pytest.mark.asyncio
    async def test_get_chart_data_with_indicators(self):
        """Test getting chart data with technical indicators."""
        service = ChartService()
        
        with patch.object(service, 'create_sample_data') as mock_create_sample:
            # Create mock candles
            mock_candles = []
            for i in range(20):
                candle = Candle(
                    timestamp=datetime.now(),
                    open=100.0 + i,
                    high=105.0 + i,
                    low=95.0 + i,
                    close=102.0 + i,
                    volume=1000.0
                )
                mock_candles.append(candle)
            mock_create_sample.return_value = mock_candles
            
            request = ChartDataRequest(
                symbol="AAPL",
                source="synthetic",
                interval="1d",
                limit=20
            )
            
            response = await service.get_chart_data_with_indicators(
                request, 
                indicators=["sma", "ema", "rsi", "bollinger", "macd"]
            )
            
            assert isinstance(response, ChartDataResponse)
            assert len(response.data) == 20
            assert "sma" in response.indicators
            assert "ema" in response.indicators
            assert "rsi" in response.indicators
            assert "bollinger_upper" in response.indicators
            assert "bollinger_middle" in response.indicators
            assert "bollinger_lower" in response.indicators
            assert "macd_line" in response.indicators
            assert "macd_signal" in response.indicators
            assert "macd_histogram" in response.indicators
            
    def test_detect_patterns(self):
        """Test pattern detection."""
        service = ChartService()
        
        # Create test candles with a clear pattern
        candles = []
        for i in range(10):
            candle = Candle(
                timestamp=datetime.now(),
                open=100.0 + i,
                high=105.0 + i,
                low=95.0 + i,
                close=102.0 + i,
                volume=1000.0
            )
            candles.append(candle)
            
        patterns = service.detect_patterns(candles)
        
        assert isinstance(patterns, list)
        # Pattern detection should return some results (implementation dependent)
        
    def test_get_support_resistance_levels(self):
        """Test support and resistance level detection."""
        service = ChartService()
        
        # Create test candles with clear levels
        candles = []
        prices = [100, 102, 98, 101, 99, 103, 97, 104, 96, 105]  # Some variation
        
        for i, price in enumerate(prices):
            candle = Candle(
                timestamp=datetime.now(),
                open=price,
                high=price + 2,
                low=price - 2,
                close=price + 1,
                volume=1000.0
            )
            candles.append(candle)
            
        levels = service.get_support_resistance_levels(candles)
        
        assert isinstance(levels, dict)
        assert "support" in levels
        assert "resistance" in levels
        assert isinstance(levels["support"], list)
        assert isinstance(levels["resistance"], list)
        
    def test_calculate_volatility(self):
        """Test volatility calculation."""
        service = ChartService()
        
        candles = []
        for i in range(20):
            candle = Candle(
                timestamp=datetime.now(),
                open=100.0,
                high=110.0,
                low=90.0,
                close=100.0 + (i % 5 - 2) * 5,  # Some variation
                volume=1000.0
            )
            candles.append(candle)
            
        volatility = service.calculate_volatility(candles, period=10)
        
        assert isinstance(volatility, float)
        assert volatility >= 0
        
    @pytest.mark.asyncio
    async def test_get_market_summary(self):
        """Test getting market summary."""
        service = ChartService()
        
        with patch.object(service, 'create_sample_data') as mock_create_sample:
            mock_candles = [
                Candle(
                    timestamp=datetime.now(),
                    open=100.0,
                    high=110.0,
                    low=95.0,
                    close=105.0,
                    volume=1000000.0
                )
            ]
            mock_create_sample.return_value = mock_candles
            
            summary = await service.get_market_summary("AAPL")
            
            assert isinstance(summary, dict)
            assert "symbol" in summary
            assert "price" in summary
            assert "change" in summary
            assert "volume" in summary