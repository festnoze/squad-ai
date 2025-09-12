"""Tests for PortfolioService."""

import pytest
from unittest.mock import Mock
from datetime import datetime, timedelta
import uuid

from app.services.portfolio_service import PortfolioService
from app.models.portfolio import Portfolio
from app.models.trade import Trade, TradeType, TradeStatus


class TestPortfolioService:
    """Test cases for PortfolioService."""
    
    def test_init(self):
        """Test service initialization."""
        service = PortfolioService()
        assert service.portfolios == {}
        
    def test_create_portfolio(self):
        """Test portfolio creation."""
        service = PortfolioService()
        
        portfolio_id = service.create_portfolio(
            name="Test Portfolio",
            initial_balance=50000.0
        )
        
        assert portfolio_id is not None
        assert portfolio_id in service.portfolios
        
        portfolio = service.portfolios[portfolio_id]
        assert portfolio.name == "Test Portfolio"
        assert portfolio.initial_balance == 50000.0
        assert portfolio.current_balance == 50000.0
        
    @pytest.mark.asyncio
    async def test_get_portfolio_existing(self):
        """Test getting existing portfolio."""
        service = PortfolioService()
        
        portfolio_id = service.create_portfolio("Test Portfolio", 100000.0)
        portfolio = await service.get_portfolio_async(portfolio_id)
        
        assert portfolio is not None
        assert portfolio.name == "Test Portfolio"
        
    @pytest.mark.asyncio
    async def test_get_portfolio_nonexistent(self):
        """Test getting non-existent portfolio."""
        service = PortfolioService()
        
        portfolio = await service.get_portfolio_async("nonexistent_id")
        assert portfolio is None

    @pytest.mark.asyncio  
    async def test_update_portfolio_balance(self):
        """Test updating portfolio balance."""
        service = PortfolioService()
        
        portfolio_id = service.create_portfolio("Test Portfolio", 100000.0)
        success = await service.update_portfolio_balance_async(portfolio_id, 95000.0)
        
        assert success is True
        
        portfolio = await service.get_portfolio_async(portfolio_id)
        assert portfolio.current_balance == 95000.0
        
    def test_update_portfolio_balance_nonexistent(self):
        """Test updating non-existent portfolio balance."""
        service = PortfolioService()
        
        success = service.update_portfolio_balance("nonexistent", 50000.0)
        assert success is False
        
    def test_add_trade(self):
        """Test adding trade to portfolio."""
        service = PortfolioService()
        
        portfolio_id = service.create_portfolio("Test Portfolio", 100000.0)
        
        trade = Trade(
            id=f"trade_{uuid.uuid4().hex[:8]}",
            symbol="AAPL",
            trade_type=TradeType.LONG,
            quantity=100,
            entry_price=150.0,
            status=TradeStatus.OPEN,
            entry_time=datetime.now()
        )
        
        success = service.add_trade(portfolio_id, trade)
        assert success is True
        
    def test_add_trade_nonexistent_portfolio(self):
        """Test adding trade to non-existent portfolio."""
        service = PortfolioService()
        
        trade = Trade(
            id=f"trade_{uuid.uuid4().hex[:8]}",
            symbol="AAPL",
            trade_type=TradeType.LONG,
            quantity=100,
            entry_price=150.0,
            status=TradeStatus.OPEN,
            entry_time=datetime.now()
        )
        
        success = service.add_trade("nonexistent", trade)
        assert success is False
        
    def test_get_portfolio_trades(self):
        """Test getting portfolio trades."""
        service = PortfolioService()
        
        portfolio_id = service.create_portfolio("Test Portfolio", 100000.0)
        
        # Add some trades
        for i in range(3):
            trade = Trade(
                id=f"trade_{i}",
                symbol=f"STOCK{i}",
                trade_type=TradeType.LONG,
                quantity=100,
                entry_price=50.0 + i * 10,
                status=TradeStatus.OPEN,
                entry_time=datetime.now()
            )
            service.add_trade(portfolio_id, trade)
            
        trades = service.get_portfolio_trades(portfolio_id)
        assert len(trades) == 3
        
    def test_get_portfolio_trades_nonexistent(self):
        """Test getting trades from non-existent portfolio."""
        service = PortfolioService()
        
        trades = service.get_portfolio_trades("nonexistent")
        assert trades == []
        
    def test_calculate_portfolio_value(self):
        """Test calculating total portfolio value."""
        service = PortfolioService()
        
        portfolio_id = service.create_portfolio("Test Portfolio", 100000.0)
        
        # Add some trades
        trade1 = Trade(
            id="trade_1",
            symbol="AAPL",
            trade_type=TradeType.LONG,
            quantity=100,
            entry_price=150.0,
            status=TradeStatus.OPEN,
            entry_time=datetime.now()
        )
        
        trade2 = Trade(
            id="trade_2",
            symbol="GOOGL",
            trade_type=TradeType.LONG,
            quantity=50,
            entry_price=2000.0,
            status=TradeStatus.OPEN,
            entry_time=datetime.now()
        )
        
        service.add_trade(portfolio_id, trade1)
        service.add_trade(portfolio_id, trade2)
        
        # Mock current prices
        current_prices = {"AAPL": 160.0, "GOOGL": 2100.0}
        
        total_value = service.calculate_portfolio_value(portfolio_id, current_prices)
        
        # Expected: cash balance + position values
        # AAPL: 100 * 160 = 16000
        # GOOGL: 50 * 2100 = 105000
        # Cash: 100000 (assuming no cash was used for trades in this simplified test)
        # Total should include position values
        assert total_value > 100000.0
        
    def test_calculate_portfolio_value_no_prices(self):
        """Test calculating portfolio value without current prices."""
        service = PortfolioService()
        
        portfolio_id = service.create_portfolio("Test Portfolio", 100000.0)
        total_value = service.calculate_portfolio_value(portfolio_id, {})
        
        # Should return current balance when no positions can be valued
        assert total_value == 100000.0
        
    @pytest.mark.asyncio
    async def test_get_portfolio_performance(self):
        """Test getting portfolio performance metrics."""
        service = PortfolioService()
        
        portfolio_id = service.create_portfolio("Test Portfolio", 100000.0)
        
        # Add a closed profitable trade
        trade = Trade(
            id="trade_1",
            symbol="AAPL",
            trade_type=TradeType.LONG,
            quantity=100,
            entry_price=150.0,
            exit_price=160.0,
            status=TradeStatus.CLOSED,
            entry_time=datetime.now() - timedelta(days=1),
            exit_time=datetime.now()
        )
        
        service.add_trade(portfolio_id, trade)
        
        performance = await service.get_portfolio_performance_async(portfolio_id)
        
        assert isinstance(performance, dict)
        assert "total_trades" in performance
        assert "winning_trades" in performance
        assert "losing_trades" in performance
        assert "win_rate" in performance
        assert "total_pnl" in performance
        assert "average_win" in performance
        assert "average_loss" in performance
        assert "profit_factor" in performance
        
        assert performance["total_trades"] == 1
        assert performance["winning_trades"] == 1
        assert performance["losing_trades"] == 0
        assert performance["win_rate"] == 1.0
        
    def test_get_portfolio_drawdown(self):
        """Test calculating portfolio drawdown."""
        service = PortfolioService()
        
        portfolio_id = service.create_portfolio("Test Portfolio", 100000.0)
        
        # Simulate some balance history with drawdown
        balance_history = [100000, 105000, 110000, 95000, 90000, 100000, 105000]
        
        import pytest
        m = pytest.MonkeyPatch()
        # Mock balance history retrieval
        def mock_get_balance_history(pid):
            return balance_history
        m.setattr(service, 'get_portfolio_balance_history', mock_get_balance_history)
        
        drawdown = service.get_portfolio_drawdown(portfolio_id)
        
        assert isinstance(drawdown, dict)
        assert "max_drawdown" in drawdown
        assert "current_drawdown" in drawdown
        assert "drawdown_duration" in drawdown
            
    @pytest.mark.asyncio
    async def test_get_risk_metrics(self):
        """Test calculating risk metrics."""
        service = PortfolioService()
        
        portfolio_id = service.create_portfolio("Test Portfolio", 100000.0)
        
        # Add some trades
        for i in range(5):
            trade = Trade(
                id=f"trade_{i}",
                symbol=f"STOCK{i}",
                trade_type=TradeType.LONG,
                quantity=100,
                entry_price=100.0 + i * 5,
                status=TradeStatus.OPEN,
                entry_time=datetime.now()
            )
            service.add_trade(portfolio_id, trade)
            
        current_prices = {f"STOCK{i}": 100.0 + i * 5 + 5 for i in range(5)}  # All slightly profitable
        
        risk_metrics = await service.get_risk_metrics_async(portfolio_id, current_prices)
        
        assert isinstance(risk_metrics, dict)
        assert "var_95" in risk_metrics  # Value at Risk
        assert "portfolio_beta" in risk_metrics
        assert "sharpe_ratio" in risk_metrics
        assert "position_concentration" in risk_metrics
        
    def test_rebalance_portfolio(self):
        """Test portfolio rebalancing."""
        service = PortfolioService()
        
        portfolio_id = service.create_portfolio("Test Portfolio", 100000.0)
        
        # Target allocations
        target_allocations = {
            "AAPL": 0.4,
            "GOOGL": 0.3,
            "MSFT": 0.3
        }
        
        current_prices = {
            "AAPL": 150.0,
            "GOOGL": 2000.0,
            "MSFT": 250.0
        }
        
        rebalance_trades = service.rebalance_portfolio(
            portfolio_id, 
            target_allocations, 
            current_prices
        )
        
        assert isinstance(rebalance_trades, list)
        # Should suggest trades to achieve target allocation
        
    def test_list_all_portfolios(self):
        """Test listing all portfolios."""
        service = PortfolioService()
        
        # Create multiple portfolios
        id1 = service.create_portfolio("Portfolio 1", 100000.0)
        id2 = service.create_portfolio("Portfolio 2", 50000.0)
        
        portfolios = service.list_all_portfolios()
        
        assert len(portfolios) == 2
        portfolio_ids = [p.id for p in portfolios]
        assert id1 in portfolio_ids
        assert id2 in portfolio_ids
        
    def test_delete_portfolio(self):
        """Test deleting a portfolio."""
        service = PortfolioService()
        
        portfolio_id = service.create_portfolio("Test Portfolio", 100000.0)
        assert portfolio_id in service.portfolios
        
        success = service.delete_portfolio(portfolio_id)
        assert success is True
        assert portfolio_id not in service.portfolios
        
    def test_delete_portfolio_nonexistent(self):
        """Test deleting non-existent portfolio."""
        service = PortfolioService()
        
        success = service.delete_portfolio("nonexistent")
        assert success is False