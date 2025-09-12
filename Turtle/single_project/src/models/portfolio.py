from dataclasses import dataclass, field
from typing import List, Dict
from .trade import Trade


@dataclass
class Portfolio:
    """Portfolio container tracking balance and trades"""
    initial_balance: float
    current_balance: float
    total_pnl: float = 0.0
    open_trades: List[Trade] = field(default_factory=list)
    closed_trades: List[Trade] = field(default_factory=list)
    trade_history: List[Dict] = field(default_factory=list)
    
    @property
    def equity(self) -> float:
        """Current equity including unrealized P&L"""
        unrealized_pnl = sum(trade.current_pnl for trade in self.open_trades)
        return self.current_balance + unrealized_pnl
    
    @property
    def used_margin(self) -> float:
        """Calculate used margin from open positions"""
        return sum(trade.value for trade in self.open_trades)
    
    @property
    def available_balance(self) -> float:
        """Available balance for new trades"""
        return self.current_balance - self.used_margin
    
    @property
    def portfolio_heat(self) -> float:
        """Current portfolio heat (risk exposure)"""
        total_risk = 0.0
        for trade in self.open_trades:
            risk_per_share = abs(trade.entry_price - trade.stop_loss)
            total_risk += risk_per_share * trade.quantity
        return total_risk / self.equity if self.equity > 0 else 0.0