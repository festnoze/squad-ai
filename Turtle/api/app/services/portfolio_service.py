"""Portfolio management service."""

import json
import uuid
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from app.models.portfolio import (
    Portfolio, PortfolioSummary, PortfolioRequest, PortfolioResponse,
    PositionSummary, PortfolioPerformance
)
from app.models.trade import Trade, TradeStatus
from app.core.config import settings


class PortfolioService:
    """Service for managing portfolios."""
    
    def __init__(self):
        self.data_dir = Path("./data/portfolios")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._portfolios: Dict[str, Portfolio] = {}
        self._trades: Dict[str, List[Trade]] = {}  # portfolio_id -> trades
    
    async def list_portfolios(self) -> List[Portfolio]:
        """List all portfolios."""
        try:
            portfolios = []
            
            # Load from files
            for file_path in self.data_dir.glob("*.json"):
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                    portfolio = Portfolio(**data)
                    portfolios.append(portfolio)
                    self._portfolios[portfolio.id] = portfolio
                except Exception as e:
                    print(f"Error loading portfolio {file_path}: {e}")
                    continue
            
            # If no portfolios exist, create a default one
            if not portfolios:
                default_portfolio = await self._create_default_portfolio()
                portfolios.append(default_portfolio)
            
            return portfolios
        
        except Exception as e:
            raise Exception(f"Failed to list portfolios: {str(e)}")
    
    async def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        """Get portfolio by ID."""
        try:
            # Check cache first
            if portfolio_id in self._portfolios:
                return self._portfolios[portfolio_id]
            
            # Load from file
            file_path = self.data_dir / f"{portfolio_id}.json"
            if not file_path.exists():
                return None
            
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            portfolio = Portfolio(**data)
            self._portfolios[portfolio_id] = portfolio
            return portfolio
        
        except Exception as e:
            raise Exception(f"Failed to get portfolio: {str(e)}")
    
    async def create_portfolio(self, request: PortfolioRequest) -> PortfolioResponse:
        """Create a new portfolio."""
        try:
            portfolio_id = str(uuid.uuid4())
            
            portfolio = Portfolio(
                id=portfolio_id,
                name=request.name,
                initial_balance=request.initial_balance,
                current_balance=request.initial_balance,
                currency=request.currency,
                total_value=request.initial_balance,
                risk_per_trade=request.risk_per_trade
            )
            
            # Save to file
            await self._save_portfolio(portfolio)
            
            # Update cache
            self._portfolios[portfolio_id] = portfolio
            self._trades[portfolio_id] = []
            
            return PortfolioResponse(
                success=True,
                message="Portfolio created successfully",
                portfolio=portfolio
            )
        
        except Exception as e:
            return PortfolioResponse(
                success=False,
                message=f"Failed to create portfolio: {str(e)}"
            )
    
    async def update_portfolio(self, portfolio_id: str, request: PortfolioRequest) -> PortfolioResponse:
        """Update portfolio settings."""
        try:
            portfolio = await self.get_portfolio(portfolio_id)
            if not portfolio:
                return PortfolioResponse(
                    success=False,
                    message="Portfolio not found"
                )
            
            # Update portfolio
            portfolio.name = request.name
            portfolio.currency = request.currency
            portfolio.risk_per_trade = request.risk_per_trade
            
            # Save to file
            await self._save_portfolio(portfolio)
            
            # Update cache
            self._portfolios[portfolio_id] = portfolio
            
            return PortfolioResponse(
                success=True,
                message="Portfolio updated successfully",
                portfolio=portfolio
            )
        
        except Exception as e:
            return PortfolioResponse(
                success=False,
                message=f"Failed to update portfolio: {str(e)}"
            )
    
    async def delete_portfolio(self, portfolio_id: str) -> bool:
        """Delete a portfolio."""
        try:
            file_path = self.data_dir / f"{portfolio_id}.json"
            if file_path.exists():
                file_path.unlink()
                
                # Remove from cache
                if portfolio_id in self._portfolios:
                    del self._portfolios[portfolio_id]
                if portfolio_id in self._trades:
                    del self._trades[portfolio_id]
                
                return True
            return False
        
        except Exception as e:
            raise Exception(f"Failed to delete portfolio: {str(e)}")
    
    async def get_portfolio_summary(self, portfolio_id: str) -> Optional[PortfolioSummary]:
        """Get portfolio summary with key metrics."""
        try:
            portfolio = await self.get_portfolio(portfolio_id)
            if not portfolio:
                return None
            
            # Calculate metrics based on trades
            trades = self._trades.get(portfolio_id, [])
            open_trades = len([t for t in trades if t.status == TradeStatus.OPEN])
            
            summary = PortfolioSummary(
                current_balance=portfolio.current_balance,
                equity=portfolio.equity,
                total_pnl=portfolio.total_pnl,
                unrealized_pnl=portfolio.unrealized_pnl,
                realized_pnl=portfolio.realized_pnl,
                open_trades=open_trades,
                total_trades=portfolio.total_trades,
                win_rate=portfolio.win_rate,
                return_percentage=portfolio.return_percentage,
                max_drawdown=portfolio.max_drawdown
            )
            
            return summary
        
        except Exception as e:
            raise Exception(f"Failed to get portfolio summary: {str(e)}")
    
    async def get_portfolio_positions(self, portfolio_id: str) -> List[PositionSummary]:
        """Get portfolio positions."""
        try:
            trades = self._trades.get(portfolio_id, [])
            open_trades = [t for t in trades if t.status == TradeStatus.OPEN]
            
            # Group by symbol
            positions = {}
            for trade in open_trades:
                if trade.symbol not in positions:
                    positions[trade.symbol] = {
                        'open_positions': 0,
                        'total_units': 0,
                        'total_value': 0,
                        'unrealized_pnl': 0,
                        'side': 'flat'
                    }
                
                pos = positions[trade.symbol]
                pos['open_positions'] += 1
                
                if trade.trade_type.value == 'long':
                    pos['total_units'] += trade.quantity
                    pos['side'] = 'long'
                else:
                    pos['total_units'] -= trade.quantity
                    pos['side'] = 'short'
                
                pos['total_value'] += trade.entry_price * trade.quantity
                pos['unrealized_pnl'] += trade.unrealized_pnl
            
            # Convert to PositionSummary objects
            position_summaries = []
            for symbol, pos in positions.items():
                avg_price = pos['total_value'] / abs(pos['total_units']) if pos['total_units'] != 0 else 0
                
                position_summaries.append(PositionSummary(
                    symbol=symbol,
                    open_positions=pos['open_positions'],
                    total_units=abs(pos['total_units']),
                    average_price=avg_price,
                    unrealized_pnl=pos['unrealized_pnl'],
                    side=pos['side']
                ))
            
            return position_summaries
        
        except Exception as e:
            raise Exception(f"Failed to get portfolio positions: {str(e)}")
    
    async def get_position_summary(self, portfolio_id: str, symbol: str) -> Optional[PositionSummary]:
        """Get position summary for a specific symbol."""
        try:
            positions = await self.get_portfolio_positions(portfolio_id)
            for pos in positions:
                if pos.symbol == symbol:
                    return pos
            return None
        
        except Exception as e:
            raise Exception(f"Failed to get position summary: {str(e)}")
    
    async def get_portfolio_performance(self, portfolio_id: str, days: int = 30) -> Optional[PortfolioPerformance]:
        """Get portfolio performance metrics over time."""
        try:
            portfolio = await self.get_portfolio(portfolio_id)
            if not portfolio:
                return None
            
            # Generate placeholder performance data
            # In real implementation, this would load historical data
            dates = []
            equity_curve = []
            daily_returns = []
            cumulative_returns = []
            
            start_date = datetime.now() - timedelta(days=days)
            current_equity = portfolio.initial_balance
            
            for i in range(days):
                date = start_date + timedelta(days=i)
                dates.append(date.strftime('%Y-%m-%d'))
                
                # Simulate daily return (placeholder)
                daily_return = 0.001 * (1 - 2 * (i % 2))  # Alternating small gains/losses
                daily_returns.append(daily_return)
                
                current_equity *= (1 + daily_return)
                equity_curve.append(current_equity)
                
                cumulative_return = (current_equity - portfolio.initial_balance) / portfolio.initial_balance
                cumulative_returns.append(cumulative_return)
            
            performance = PortfolioPerformance(
                daily_returns=daily_returns,
                cumulative_returns=cumulative_returns,
                equity_curve=equity_curve,
                dates=dates,
                sharpe_ratio=1.2,  # Placeholder
                max_drawdown=portfolio.max_drawdown,
                volatility=0.15  # Placeholder
            )
            
            return performance
        
        except Exception as e:
            raise Exception(f"Failed to get portfolio performance: {str(e)}")
    
    async def reset_portfolio(self, portfolio_id: str) -> bool:
        """Reset portfolio to initial state."""
        try:
            portfolio = await self.get_portfolio(portfolio_id)
            if not portfolio:
                return False
            
            # Reset portfolio state
            portfolio.current_balance = portfolio.initial_balance
            portfolio.total_value = portfolio.initial_balance
            portfolio.unrealized_pnl = 0
            portfolio.realized_pnl = 0
            portfolio.total_pnl = 0
            portfolio.total_trades = 0
            portfolio.winning_trades = 0
            portfolio.losing_trades = 0
            portfolio.max_drawdown = 0
            
            # Clear trades
            self._trades[portfolio_id] = []
            
            # Save to file
            await self._save_portfolio(portfolio)
            
            # Update cache
            self._portfolios[portfolio_id] = portfolio
            
            return True
        
        except Exception as e:
            raise Exception(f"Failed to reset portfolio: {str(e)}")
    
    async def update_balance(self, portfolio_id: str, new_balance: float, currency: str = None) -> bool:
        """Update portfolio balance and currency."""
        try:
            portfolio = await self.get_portfolio(portfolio_id)
            if not portfolio:
                return False
            
            portfolio.current_balance = new_balance
            portfolio.initial_balance = new_balance
            portfolio.total_value = new_balance
            
            if currency:
                portfolio.currency = currency
            
            # Save to file
            await self._save_portfolio(portfolio)
            
            # Update cache
            self._portfolios[portfolio_id] = portfolio
            
            return True
        
        except Exception as e:
            raise Exception(f"Failed to update portfolio balance: {str(e)}")
    
    async def get_risk_metrics(self, portfolio_id: str) -> Optional[Dict]:
        """Get portfolio risk metrics."""
        try:
            portfolio = await self.get_portfolio(portfolio_id)
            if not portfolio:
                return None
            
            # Calculate risk metrics
            risk_metrics = {
                'total_exposure': 0,
                'leverage': 1.0,
                'risk_per_trade': portfolio.risk_per_trade,
                'max_drawdown': portfolio.max_drawdown,
                'var_95': 0,  # Value at Risk 95%
                'current_risk': 0,
                'available_capital': portfolio.current_balance
            }
            
            return risk_metrics
        
        except Exception as e:
            raise Exception(f"Failed to get risk metrics: {str(e)}")
    
    async def _create_default_portfolio(self) -> Portfolio:
        """Create a default portfolio."""
        portfolio_id = str(uuid.uuid4())
        
        portfolio = Portfolio(
            id=portfolio_id,
            name="Default Portfolio",
            initial_balance=settings.DEFAULT_PORTFOLIO_BALANCE,
            current_balance=settings.DEFAULT_PORTFOLIO_BALANCE,
            currency=settings.DEFAULT_PORTFOLIO_CURRENCY,
            total_value=settings.DEFAULT_PORTFOLIO_BALANCE
        )
        
        await self._save_portfolio(portfolio)
        self._portfolios[portfolio_id] = portfolio
        self._trades[portfolio_id] = []
        
        return portfolio
    
    async def _save_portfolio(self, portfolio: Portfolio) -> None:
        """Save portfolio to file."""
        file_path = self.data_dir / f"{portfolio.id}.json"
        
        with open(file_path, 'w') as f:
            json.dump(portfolio.dict(), f, indent=2, default=str)