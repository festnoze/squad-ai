from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import sys
sys.path.append('..')
from models import Trade, TradeType, TradeStatus, Portfolio


class TradingService:
    """Core trading service for balance management and trade execution"""
    
    def __init__(self, initial_balance: float = 100000.0, commission_rate: float = 0.001):
        self.portfolio = Portfolio(
            initial_balance=initial_balance,
            current_balance=initial_balance
        )
        self.commission_rate = commission_rate  # 0.1% default commission
        self.trade_counter = 0
        
    def calculate_position_size(self, price: float, atr: float, risk_percent: float = 0.01, 
                              stop_multiplier: float = 2.0) -> Tuple[float, int]:
        """Calculate position size based on ATR and risk management
        
        Args:
            price: Current price
            atr: Average True Range
            risk_percent: Risk per trade as percentage of equity
            stop_multiplier: ATR multiplier for stop loss
            
        Returns:
            Tuple of (quantity, units) where units is for turtle position sizing
        """
        risk_amount = self.portfolio.equity * risk_percent
        stop_distance = atr * stop_multiplier
        
        if stop_distance == 0:
            return 0.0, 0
        
        # Calculate base quantity
        quantity = risk_amount / stop_distance
        
        # Turtle units calculation (1 unit = 1% risk)
        units = 1
        
        # Ensure we don't exceed available balance
        trade_value = quantity * price
        if trade_value > self.portfolio.available_balance:
            quantity = self.portfolio.available_balance / price * 0.9  # 90% to leave buffer
        
        return max(0.0, quantity), units
    
    def can_add_position(self, symbol: str, max_heat: float = 0.25) -> bool:
        """Check if we can add more positions without exceeding heat limit"""
        if self.portfolio.portfolio_heat >= max_heat:
            return False
        return True
    
    def enter_trade(self, symbol: str, trade_type: TradeType, price: float, 
                   quantity: float, stop_loss: float, 
                   take_profit: Optional[float] = None) -> Optional[Trade]:
        """Enter a new trade"""
        if quantity <= 0:
            return None
        
        trade_value = quantity * price
        commission = trade_value * self.commission_rate
        
        # Check if we have enough balance
        if trade_value + commission > self.portfolio.available_balance:
            return None
        
        self.trade_counter += 1
        trade = Trade(
            id=f"T{self.trade_counter:06d}",
            symbol=symbol,
            trade_type=trade_type,
            entry_price=price,
            quantity=quantity,
            entry_time=datetime.now(),
            stop_loss=stop_loss,
            take_profit=take_profit,
            commission=commission
        )
        
        # Update portfolio
        self.portfolio.open_trades.append(trade)
        self.portfolio.current_balance -= (trade_value + commission)
        
        # Record trade
        self.portfolio.trade_history.append({
            'action': 'enter',
            'trade_id': trade.id,
            'symbol': symbol,
            'type': trade_type.value,
            'price': price,
            'quantity': quantity,
            'time': trade.entry_time,
            'balance': self.portfolio.current_balance
        })
        
        return trade
    
    def exit_trade(self, trade: Trade, exit_price: float, reason: str = "manual") -> bool:
        """Exit an existing trade"""
        if trade.status == TradeStatus.CLOSED:
            return False
        
        # Calculate P&L
        if trade.trade_type == TradeType.LONG:
            pnl = (exit_price - trade.entry_price) * trade.quantity
        else:  # SHORT
            pnl = (trade.entry_price - exit_price) * trade.quantity
        
        trade_value = trade.quantity * exit_price
        exit_commission = trade_value * self.commission_rate
        net_pnl = pnl - exit_commission
        
        # Update trade
        trade.exit_price = exit_price
        trade.exit_time = datetime.now()
        trade.pnl = net_pnl
        trade.status = TradeStatus.CLOSED
        
        # Update portfolio
        self.portfolio.current_balance += trade_value - exit_commission
        self.portfolio.total_pnl += net_pnl
        
        # Move trade to closed trades
        self.portfolio.open_trades.remove(trade)
        self.portfolio.closed_trades.append(trade)
        
        # Record trade
        self.portfolio.trade_history.append({
            'action': 'exit',
            'trade_id': trade.id,
            'symbol': trade.symbol,
            'reason': reason,
            'price': exit_price,
            'pnl': net_pnl,
            'time': trade.exit_time,
            'balance': self.portfolio.current_balance
        })
        
        return True
    
    def update_stop_loss(self, trade: Trade, new_stop: float) -> bool:
        """Update stop loss for an open trade"""
        if trade.status == TradeStatus.CLOSED:
            return False
        
        trade.stop_loss = new_stop
        return True
    
    def check_stops_and_targets(self, current_prices: Dict[str, float]) -> List[Trade]:
        """Check all open trades for stop loss and take profit triggers"""
        triggered_trades = []
        
        for trade in self.portfolio.open_trades.copy():
            if trade.symbol not in current_prices:
                continue
                
            current_price = current_prices[trade.symbol]
            should_exit = False
            exit_reason = ""
            
            if trade.trade_type == TradeType.LONG:
                if current_price <= trade.stop_loss:
                    should_exit = True
                    exit_reason = "stop_loss"
                elif trade.take_profit and current_price >= trade.take_profit:
                    should_exit = True
                    exit_reason = "take_profit"
            else:  # SHORT
                if current_price >= trade.stop_loss:
                    should_exit = True
                    exit_reason = "stop_loss"
                elif trade.take_profit and current_price <= trade.take_profit:
                    should_exit = True
                    exit_reason = "take_profit"
            
            if should_exit:
                self.exit_trade(trade, current_price, exit_reason)
                triggered_trades.append(trade)
        
        return triggered_trades
    
    def get_open_positions(self, symbol: Optional[str] = None) -> List[Trade]:
        """Get open positions, optionally filtered by symbol"""
        if symbol:
            return [trade for trade in self.portfolio.open_trades if trade.symbol == symbol]
        return self.portfolio.open_trades.copy()
    
    def get_performance_stats(self) -> Dict:
        """Calculate performance statistics"""
        if not self.portfolio.closed_trades:
            total_return = (self.portfolio.equity - self.portfolio.initial_balance) / self.portfolio.initial_balance
            return {
                'total_trades': 0,
                'open_trades': len(self.portfolio.open_trades),
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'total_return': total_return,
                'total_pnl': self.portfolio.total_pnl,
                'current_balance': self.portfolio.current_balance,
                'equity': self.portfolio.equity,
                'portfolio_heat': self.portfolio.portfolio_heat
            }
        
        wins = [trade.pnl for trade in self.portfolio.closed_trades if trade.pnl > 0]
        losses = [trade.pnl for trade in self.portfolio.closed_trades if trade.pnl < 0]
        
        win_rate = len(wins) / len(self.portfolio.closed_trades) if self.portfolio.closed_trades else 0
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        profit_factor = sum(wins) / abs(sum(losses)) if losses else float('inf')
        total_return = (self.portfolio.equity - self.portfolio.initial_balance) / self.portfolio.initial_balance
        
        return {
            'total_trades': len(self.portfolio.closed_trades),
            'open_trades': len(self.portfolio.open_trades),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'total_return': total_return,
            'total_pnl': self.portfolio.total_pnl,
            'current_balance': self.portfolio.current_balance,
            'equity': self.portfolio.equity,
            'portfolio_heat': self.portfolio.portfolio_heat
        }