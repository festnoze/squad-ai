"""Trade and trading-related models."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class TradeType(str, Enum):
    """Trade type enumeration."""
    LONG = "long"
    SHORT = "short"


class TradeStatus(str, Enum):
    """Trade status enumeration."""
    OPEN = "open"
    CLOSED = "closed"
    PENDING = "pending"
    CANCELLED = "cancelled"


class Trade(BaseModel):
    """Trade execution model."""
    
    id: str = Field(..., description="Unique trade identifier")
    symbol: str = Field(..., description="Trading symbol")
    trade_type: TradeType = Field(..., description="Trade type (long/short)")
    status: TradeStatus = Field(default=TradeStatus.OPEN, description="Trade status")
    
    # Entry details
    entry_price: float = Field(..., gt=0, description="Entry price")
    entry_time: datetime = Field(..., description="Entry timestamp")
    quantity: float = Field(..., gt=0, description="Trade quantity/units")
    
    # Exit details (optional for open trades)
    exit_price: Optional[float] = Field(default=None, description="Exit price")
    exit_time: Optional[datetime] = Field(default=None, description="Exit timestamp")
    
    # Risk management
    stop_loss: Optional[float] = Field(default=None, description="Stop loss price")
    take_profit: Optional[float] = Field(default=None, description="Take profit price")
    
    # P&L calculation
    realized_pnl: float = Field(default=0, description="Realized profit/loss")
    unrealized_pnl: float = Field(default=0, description="Unrealized profit/loss")
    
    # Metadata
    strategy_name: str = Field(default="", description="Strategy that generated this trade")
    notes: str = Field(default="", description="Additional notes")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    def calculate_pnl(self, current_price: float) -> float:
        """Calculate current P&L for the trade."""
        if self.status == TradeStatus.CLOSED:
            return self.realized_pnl
        
        if self.trade_type == TradeType.LONG:
            return (current_price - self.entry_price) * self.quantity
        else:  # SHORT
            return (self.entry_price - current_price) * self.quantity
    
    def close_trade(self, exit_price: float, exit_time: datetime) -> None:
        """Close the trade."""
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.status = TradeStatus.CLOSED
        self.realized_pnl = self.calculate_pnl(exit_price)
        self.unrealized_pnl = 0


class TradeRequest(BaseModel):
    """Request model for trade operations."""
    
    symbol: str = Field(..., description="Trading symbol")
    trade_type: TradeType = Field(..., description="Trade type")
    quantity: float = Field(..., gt=0, description="Trade quantity")
    price: Optional[float] = Field(default=None, description="Specific price (market price if None)")
    stop_loss: Optional[float] = Field(default=None, description="Stop loss price")
    take_profit: Optional[float] = Field(default=None, description="Take profit price")
    strategy_name: str = Field(default="manual", description="Strategy name")


class TradeResponse(BaseModel):
    """Response model for trade operations."""
    
    success: bool = Field(..., description="Operation success")
    message: str = Field(default="", description="Response message")
    trade: Optional[Trade] = Field(default=None, description="Trade data")