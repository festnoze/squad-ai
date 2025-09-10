"""Portfolio management models."""

from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from .trade import Trade


class Portfolio(BaseModel):
    """Portfolio management model."""
    
    id: str = Field(..., description="Portfolio identifier")
    name: str = Field(default="Default Portfolio", description="Portfolio name")
    
    # Balance information
    initial_balance: float = Field(..., gt=0, description="Initial portfolio balance")
    current_balance: float = Field(..., description="Current cash balance")
    currency: str = Field(default="USD", description="Portfolio currency")
    
    # Performance metrics
    total_value: float = Field(default=0, description="Total portfolio value")
    unrealized_pnl: float = Field(default=0, description="Unrealized P&L")
    realized_pnl: float = Field(default=0, description="Realized P&L")
    total_pnl: float = Field(default=0, description="Total P&L")
    
    # Statistics
    total_trades: int = Field(default=0, description="Total number of trades")
    winning_trades: int = Field(default=0, description="Number of winning trades")
    losing_trades: int = Field(default=0, description="Number of losing trades")
    
    # Risk metrics
    max_drawdown: float = Field(default=0, description="Maximum drawdown")
    risk_per_trade: float = Field(default=0.02, ge=0, le=1, description="Risk per trade (0-1)")
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage."""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100
    
    @property
    def equity(self) -> float:
        """Calculate total equity (cash + unrealized P&L)."""
        return self.current_balance + self.unrealized_pnl
    
    @property
    def return_percentage(self) -> float:
        """Calculate total return percentage."""
        if self.initial_balance == 0:
            return 0.0
        return ((self.equity - self.initial_balance) / self.initial_balance) * 100


class PortfolioSummary(BaseModel):
    """Portfolio summary model."""
    
    current_balance: float = Field(..., description="Current cash balance")
    equity: float = Field(..., description="Total equity")
    total_pnl: float = Field(..., description="Total P&L")
    unrealized_pnl: float = Field(..., description="Unrealized P&L")
    realized_pnl: float = Field(..., description="Realized P&L")
    open_trades: int = Field(..., description="Number of open trades")
    total_trades: int = Field(..., description="Total trades")
    win_rate: float = Field(..., description="Win rate percentage")
    return_percentage: float = Field(..., description="Total return percentage")
    max_drawdown: float = Field(..., description="Maximum drawdown")


class PortfolioRequest(BaseModel):
    """Request model for portfolio operations."""
    
    name: str = Field(default="Default Portfolio", description="Portfolio name")
    initial_balance: float = Field(default=100000, gt=0, description="Initial balance")
    currency: str = Field(default="USD", description="Portfolio currency")
    risk_per_trade: float = Field(default=0.02, ge=0, le=1, description="Risk per trade")


class PortfolioResponse(BaseModel):
    """Response model for portfolio operations."""
    
    success: bool = Field(..., description="Operation success")
    message: str = Field(default="", description="Response message")
    portfolio: Optional[Portfolio] = Field(default=None, description="Portfolio data")


class PositionSummary(BaseModel):
    """Position summary for a specific symbol."""
    
    symbol: str = Field(..., description="Trading symbol")
    open_positions: int = Field(default=0, description="Number of open positions")
    total_units: float = Field(default=0, description="Total units/quantity")
    average_price: float = Field(default=0, description="Average entry price")
    unrealized_pnl: float = Field(default=0, description="Unrealized P&L")
    side: str = Field(default="flat", description="Position side (long/short/flat)")


class PortfolioPerformance(BaseModel):
    """Portfolio performance metrics over time."""
    
    daily_returns: List[float] = Field(default=[], description="Daily returns")
    cumulative_returns: List[float] = Field(default=[], description="Cumulative returns")
    equity_curve: List[float] = Field(default=[], description="Equity curve values")
    dates: List[str] = Field(default=[], description="Corresponding dates")
    
    # Risk metrics
    sharpe_ratio: float = Field(default=0, description="Sharpe ratio")
    max_drawdown: float = Field(default=0, description="Maximum drawdown")
    volatility: float = Field(default=0, description="Portfolio volatility")