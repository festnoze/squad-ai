from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from .trade_type import TradeType
from .trade_status import TradeStatus


@dataclass
class Trade:
    """Represents a single trade with entry/exit information"""
    id: str
    symbol: str
    trade_type: TradeType
    entry_price: float
    quantity: float
    entry_time: datetime
    stop_loss: float
    take_profit: Optional[float] = None
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    status: TradeStatus = TradeStatus.OPEN
    pnl: float = 0.0
    commission: float = 0.0
    units: int = 1  # Number of units for pyramiding
    
    @property
    def current_pnl(self) -> float:
        """Calculate current P&L for open trades"""
        if self.status == TradeStatus.CLOSED:
            return self.pnl
        return 0.0  # Will be calculated with current price
    
    @property
    def value(self) -> float:
        """Calculate trade value"""
        return self.quantity * self.entry_price