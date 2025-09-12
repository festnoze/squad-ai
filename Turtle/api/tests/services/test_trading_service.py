"""Tests for TradingService."""

import pytest
from datetime import datetime
from unittest.mock import Mock
import uuid

from app.services.trading_service import TradingService
from app.models.trade import Trade, TradeType, TradeStatus, TradeRequest
from app.models.strategy import TradingSignal


class TestTradingService:
    """Test cases for TradingService."""
    
    def test_init(self):
        """Test service initialization."""
        service = TradingService(initial_balance=50000.0, commission_rate=0.002)
        
        assert service.portfolio.initial_balance == 50000.0
        assert service.portfolio.current_balance == 50000.0
        assert service.commission_rate == 0.002
        assert len(service.open_trades) == 0
        assert len(service.closed_trades) == 0
        
    def test_available_balance(self):
        """Test available balance calculation."""
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
        
        # Test with 1% risk
        position_size = await service.calculate_position_size_async(
            entry_price=50.0,
            stop_loss=45.0,
            risk_percent=0.01
        )
        
        # Risk = $1000 (1% of $100k), Risk per share = $5, Position = 200 shares
        expected_size = 1000.0 / 5.0  # 200 shares
        assert abs(position_size - expected_size) < 0.01
        
    @pytest.mark.asyncio
    async def test_calculate_position_size_zero_risk(self):
        """Test position size with zero risk."""
        service = TradingService()
        
        position_size = await service.calculate_position_size_async(
            entry_price=50.0,
            stop_loss=50.0,  # Same as entry price
            risk_percent=0.01
        )
        
        assert position_size == 0.0
        
    @pytest.mark.asyncio
    async def test_enter_trade_success(self):
        """Test successful trade entry."""
        service = TradingService(initial_balance=100000.0)
        
        trade_request = TradeRequest(
            symbol="AAPL",
            trade_type=TradeType.LONG,
            quantity=100,
            price=150.0,
            stop_loss=140.0,
            take_profit=170.0
        )
        
        result = await service.enter_trade_async(trade_request)
        
        assert result.success is True
        assert result.trade is not None
        assert result.trade.symbol == "AAPL"
        assert result.trade.status == TradeStatus.OPEN
        assert len(service.open_trades) == 1
        
        # Check balance update (entry price * quantity + commission)
        trade_value = 150.0 * 100
        commission = trade_value * service.commission_rate
        expected_cost = trade_value + commission
        expected_balance = 100000.0 - expected_cost
        assert abs(service.portfolio.current_balance - expected_balance) < 0.01
        
    @pytest.mark.asyncio
    async def test_enter_trade_insufficient_funds(self):
        """Test trade entry with insufficient funds."""
        service = TradingService(initial_balance=1000.0)  # Low balance
        
        trade_request = TradeRequest(
            symbol="AAPL",
            trade_type=TradeType.LONG,
            quantity=1000,  # Too large
            price=150.0,
            stop_loss=140.0
        )
        
        result = await service.enter_trade_async(trade_request)
        
        assert result.success is False
        assert "Insufficient balance" in result.message
        assert len(service.open_trades) == 0
        
    @pytest.mark.asyncio
    async def test_exit_trade_success(self):
        """Test successful trade exit."""
        service = TradingService(initial_balance=100000.0)
        
        # First enter a trade
        trade_request = TradeRequest(
            symbol="AAPL",
            trade_type=TradeType.LONG,
            quantity=100,
            price=150.0,
            stop_loss=140.0
        )
        
        enter_result = await service.enter_trade_async(trade_request)
        trade_id = enter_result.trade.id
        
        # Then exit the trade
        exit_result = await service.exit_trade_async(trade_id, exit_price=160.0, reason="Manual exit")
        
        assert exit_result.success is True
        assert len(service.open_trades) == 0
        assert len(service.closed_trades) == 1
        
        closed_trade = service.closed_trades[0]
        assert closed_trade.status == TradeStatus.CLOSED
        assert closed_trade.exit_price == 160.0
        # Trade model doesn't store exit_reason, just check it's closed successfully
        
    @pytest.mark.asyncio
    async def test_exit_trade_not_found(self):
        """Test exiting non-existent trade."""
        service = TradingService()
        
        result = await service.exit_trade_async("nonexistent", exit_price=100.0)
        
        assert result.success is False
        assert "Trade not found" in result.message
        
    @pytest.mark.asyncio
    async def test_get_open_trades(self):
        """Test getting open trades."""
        service = TradingService(initial_balance=100000.0)
        
        # Add two trades
        for i in range(2):
            trade_request = TradeRequest(
                symbol=f"STOCK{i}",
                trade_type=TradeType.LONG,
                quantity=100,
                price=50.0 + i * 10
            )
            await service.enter_trade_async(trade_request)
        
        open_trades = await service.get_open_trades_async()
        assert len(open_trades) == 2
        
    @pytest.mark.asyncio
    async def test_get_trade_history(self):
        """Test getting trade history."""
        service = TradingService(initial_balance=100000.0)
        
        # Enter and exit a trade
        trade_request = TradeRequest(
            symbol="AAPL",
            trade_type=TradeType.LONG,
            quantity=100,
            price=150.0
        )
        
        enter_result = await service.enter_trade_async(trade_request)
        await service.exit_trade_async(enter_result.trade.id, exit_price=160.0)
        
        history = await service.get_trade_history_async()
        assert len(history) >= 1
        
    @pytest.mark.asyncio
    async def test_get_portfolio_status(self):
        """Test getting portfolio status."""
        service = TradingService(initial_balance=100000.0)
        
        status = await service.get_portfolio_status_async()
        
        assert status["initial_balance"] == 100000.0
        assert status["current_balance"] == 100000.0
        assert status["total_trades"] == 0
        assert status["open_trades"] == 0
        
    @pytest.mark.asyncio
    async def test_get_performance_stats(self):
        """Test getting performance statistics."""
        service = TradingService(initial_balance=100000.0)
        
        # Add some trades
        trade_request = TradeRequest(
            symbol="AAPL",
            trade_type=TradeType.LONG,
            quantity=100,
            price=150.0
        )
        
        enter_result = await service.enter_trade_async(trade_request)
        await service.exit_trade_async(enter_result.trade.id, exit_price=160.0)  # Profitable
        
        stats = await service.get_performance_stats()
        
        assert "total_trades" in stats
        assert "win_rate" in stats
        assert "total_pnl" in stats
        
    @pytest.mark.asyncio
    async def test_check_stops_and_targets(self):
        """Test stop loss and take profit checking."""
        service = TradingService(initial_balance=100000.0)
        
        # Enter trade with stop and target
        trade_request = TradeRequest(
            symbol="AAPL",
            trade_type=TradeType.LONG,
            quantity=100,
            price=150.0,
            stop_loss=140.0,
            take_profit=170.0
        )
        
        enter_result = await service.enter_trade_async(trade_request)
        trade_id = enter_result.trade.id
        
        # Test stop loss trigger
        current_prices = {"AAPL": 135.0}  # Below stop loss
        triggered = await service.check_stops_and_targets_async(current_prices)
        
        assert len(triggered) == 1
        assert triggered[0]["trade_id"] == trade_id
        assert triggered[0]["trigger_type"] == "stop_loss"
        
    @pytest.mark.asyncio
    async def test_process_signal(self):
        """Test processing trading signals."""
        service = TradingService(initial_balance=100000.0)
        
        signal = TradingSignal(
            id="signal_1",
            symbol="AAPL",
            signal_type="entry",
            trade_type=TradeType.LONG,
            confidence=0.8,
            price=150.0,
            reason="Test signal",
            strategy_name="test_strategy",
            timestamp=datetime.now()
        )
        
        result = await service.process_signal_async(signal)
        
        # Should process signal successfully (implementation depends on strategy)
        assert result is not None