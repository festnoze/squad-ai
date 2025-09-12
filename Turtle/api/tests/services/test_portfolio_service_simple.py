"""Simple tests for PortfolioService to verify basic functionality."""

import pytest
from datetime import datetime

from app.services.portfolio_service import PortfolioService
from app.models.trade import Trade, TradeType, TradeStatus


class TestPortfolioServiceSimple:
    """Basic test cases for PortfolioService."""
    
    def test_init(self):
        """Test service initialization."""
        service = PortfolioService()
        assert service.portfolios == {}
        
    @pytest.mark.asyncio
    async def test_create_portfolio(self):
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
        
    def test_list_all_portfolios(self):
        """Test listing all portfolios."""
        service = PortfolioService()
        
        # Create multiple portfolios
        service.create_portfolio("Portfolio 1", 100000.0)
        service.create_portfolio("Portfolio 2", 50000.0)
        
        portfolios = service.list_all_portfolios()
        
        assert len(portfolios) == 2
        portfolio_names = [p.name for p in portfolios]
        assert "Portfolio 1" in portfolio_names
        assert "Portfolio 2" in portfolio_names