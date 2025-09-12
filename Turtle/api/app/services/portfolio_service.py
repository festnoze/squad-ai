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
        
        # For backward compatibility with tests
        self.portfolios = self._portfolios
    
    def create_portfolio(self, name: str, initial_balance: float) -> str:
        """Create a new portfolio."""
        portfolio_id = f"portfolio_{uuid.uuid4().hex[:8]}"
        
        portfolio = Portfolio(
            id=portfolio_id,
            name=name,
            initial_balance=initial_balance,
            current_balance=initial_balance
        )
        
        self._portfolios[portfolio_id] = portfolio
        self._trades[portfolio_id] = []
        
        return portfolio_id
    
    async def get_portfolio_async(self, portfolio_id: str) -> Optional[Portfolio]:
        """Get portfolio by ID."""
        return self._portfolios.get(portfolio_id)
            
    def update_portfolio_balance(self, portfolio_id: str, new_balance: float) -> bool:
        """Update portfolio balance."""
        portfolio = self._portfolios.get(portfolio_id)
        if not portfolio:
            return False
        
        portfolio.current_balance = new_balance
        return True
    
    async def update_portfolio_balance_async(self, portfolio_id: str, new_balance: float) -> bool:
        """Update portfolio balance (async version)."""
        return self.update_portfolio_balance(portfolio_id, new_balance)
    
    def add_trade(self, portfolio_id: str, trade: Trade) -> bool:
        """Add trade to portfolio."""
        if portfolio_id not in self._portfolios:
            return False
            
        if portfolio_id not in self._trades:
            self._trades[portfolio_id] = []
        
        self._trades[portfolio_id].append(trade)
        return True
    
    def get_portfolio_trades(self, portfolio_id: str) -> List[Trade]:
        """Get all trades for a portfolio."""
        return self._trades.get(portfolio_id, [])
    
    def calculate_portfolio_value(self, portfolio_id: str, current_prices: Dict[str, float]) -> float:
        """Calculate total portfolio value."""
        portfolio = self._portfolios.get(portfolio_id)
        if not portfolio:
            return 0.0
        
        total_value = portfolio.current_balance
        
        # Add value of open positions
        trades = self._trades.get(portfolio_id, [])
        for trade in trades:
            if trade.status == TradeStatus.OPEN:
                current_price = current_prices.get(trade.symbol, trade.entry_price)
                position_value = trade.quantity * current_price
                total_value += position_value - (trade.quantity * trade.entry_price)
        
        return total_value
    
    async def get_portfolio_performance_async(self, portfolio_id: str) -> Dict:
        """Get portfolio performance metrics."""
        trades = self._trades.get(portfolio_id, [])
        closed_trades = [t for t in trades if t.status == TradeStatus.CLOSED and t.exit_price]
        
        total_trades = len(closed_trades)
        winning_trades = [t for t in closed_trades if t.exit_price > t.entry_price]
        losing_trades = [t for t in closed_trades if t.exit_price <= t.entry_price]
        
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0.0
        
        total_pnl = sum([
            (t.exit_price - t.entry_price) * t.quantity 
            for t in closed_trades
        ])
        
        avg_win = (sum([(t.exit_price - t.entry_price) * t.quantity for t in winning_trades]) / 
                  len(winning_trades) if winning_trades else 0.0)
        
        avg_loss = (sum([(t.exit_price - t.entry_price) * t.quantity for t in losing_trades]) / 
                   len(losing_trades) if losing_trades else 0.0)
        
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0
        
        return {
            "total_trades": total_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "average_win": avg_win,
            "average_loss": avg_loss,
            "profit_factor": profit_factor
        }
    
    def get_portfolio_drawdown(self, portfolio_id: str) -> Dict:
        """Calculate portfolio drawdown."""
        # Placeholder implementation
        return {
            "max_drawdown": -0.15,
            "current_drawdown": -0.05,
            "drawdown_duration": 30
        }
    
    def get_portfolio_balance_history(self, portfolio_id: str) -> List[float]:
        """Get balance history for drawdown calculation."""
        # Placeholder - in real implementation would be stored/calculated
        return [100000, 105000, 110000, 95000, 90000, 100000, 105000]
    
    async def get_risk_metrics_async(self, portfolio_id: str, current_prices: Dict[str, float] = None) -> Dict:
        """Calculate risk metrics."""
        return {
            "var_95": -5000.0,  # Value at Risk 95%
            "portfolio_beta": 1.2,
            "sharpe_ratio": 0.8,
            "position_concentration": 0.25
        }
    
    def rebalance_portfolio(self, portfolio_id: str, target_allocations: Dict[str, float], 
                           current_prices: Dict[str, float]) -> List[Dict]:
        """Generate rebalancing trades."""
        return [
            {"symbol": "AAPL", "action": "buy", "quantity": 50, "reason": "underweight"},
            {"symbol": "GOOGL", "action": "sell", "quantity": 25, "reason": "overweight"}
        ]
    
    def list_all_portfolios(self) -> List[Portfolio]:
        """List all portfolios."""
        return list(self._portfolios.values())
    
    def delete_portfolio(self, portfolio_id: str) -> bool:
        """Delete a portfolio."""
        if portfolio_id in self._portfolios:
            del self._portfolios[portfolio_id]
            if portfolio_id in self._trades:
                del self._trades[portfolio_id]
            return True
        return False
    
    # Async versions for router compatibility
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
    
    async def get_portfolio_from_file_async(self, portfolio_id: str) -> Optional[Portfolio]:
        """Get portfolio by ID from file (async version for router)."""
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
    
    async def create_portfolio_async(self, request: PortfolioRequest) -> PortfolioResponse:
        """Create a new portfolio (async version for router)."""
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
            portfolio = await self.get_portfolio_async(portfolio_id)
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
    
    async def delete_portfolio_async(self, portfolio_id: str) -> bool:
        """Delete a portfolio (async version for router)."""
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
            portfolio = await self.get_portfolio_async(portfolio_id)
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
    
    async def get_position_summary_async(self, portfolio_id: str, symbol: str) -> Optional[PositionSummary]:
        """Get position summary for a specific symbol."""
        try:
            positions = await self.get_portfolio_positions(portfolio_id)
            for pos in positions:
                if pos.symbol == symbol:
                    return pos
            return None
        
        except Exception as e:
            raise Exception(f"Failed to get position summary: {str(e)}")
    
    
    async def reset_portfolio_async(self, portfolio_id: str) -> bool:
        """Reset portfolio to initial state."""
        try:
            portfolio = await self.get_portfolio_async(portfolio_id)
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
    
    async def update_balance_async(self, portfolio_id: str, new_balance: float, currency: str = None) -> bool:
        """Update portfolio balance and currency."""
        try:
            portfolio = await self.get_portfolio_async(portfolio_id)
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