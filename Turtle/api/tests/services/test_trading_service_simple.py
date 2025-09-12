"""Simple tests for TradingService to verify basic functionality."""

import pytest
from datetime import datetime

from app.services.trading_service import TradingService
from app.models.trade import TradeRequest, TradeType


class TestTradingServiceSimple:
    """Basic test cases for TradingService."""
    
    def test_init(self):
        """Test service initialization."""
        service = TradingService(initial_balance=50000.0, commission_rate=0.002)
        
        assert service.portfolio.initial_balance == 50000.0
        assert service.portfolio.current_balance == 50000.0
        assert service.commission_rate == 0.002
        assert len(service.open_trades) == 0
        assert len(service.closed_trades) == 0
        
    def test_available_balance(self):
        """Test available balance property."""
        service = TradingService(initial_balance=100000.0)
        assert service.available_balance == 100000.0
        
    def test_portfolio_heat_no_trades(self):
        """Test portfolio heat with no open trades."""
        service = TradingService()
        assert service.portfolio_heat == 0.0
        
    @pytest.mark.asyncio
    async def test_calculate_position_size(self):
        """Test position size calculation."""
        service = TradingService(initial_balance=100000.0)
        
        # Use the _async method with the correct signature
        position_size = await service.calculate_position_size_async(
            entry_price=100.0,
            stop_loss=95.0,
            risk_percent=0.01
        )
        
        # Should calculate reasonable position size
        assert position_size > 0
        
    @pytest.mark.asyncio 
    async def test_can_add_position(self):
        """Test position addition check."""
        service = TradingService()
        
        can_add = await service.can_add_position("AAPL")
        assert can_add is True  # No existing positions
        
    @pytest.mark.asyncio
    async def test_create_trade(self):
        """Test trade creation."""
        service = TradingService(initial_balance=100000.0)
        
        request = TradeRequest(
            symbol="AAPL",
            trade_type=TradeType.LONG,
            quantity=100,
            price=150.0
        )
        
        response = await service.enter_trade_async(request)
        
        # Should create trade successfully
        assert response.success is True
        assert response.trade is not None
        assert response.trade.symbol == "AAPL"
        
    @pytest.mark.asyncio
    async def test_get_trades(self):
        """Test getting trades."""
        service = TradingService()
        
        trades = await service.get_open_trades_async()
        assert isinstance(trades, list)
        
    @pytest.mark.asyncio
    async def test_get_performance_stats(self):
        """Test getting performance statistics."""
        service = TradingService()
        
        stats = await service.get_performance_stats()
        
        assert isinstance(stats, dict)
        assert "total_trades" in stats
        assert "current_balance" in stats
        assert "equity" in stats