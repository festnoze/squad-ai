"""Trading service for trade execution and portfolio management."""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
import uuid
from app.models.trade import Trade, TradeType, TradeStatus, TradeRequest, TradeResponse
from app.models.portfolio import Portfolio
from app.models.strategy import TradingSignal


class TradingService:
    """Core trading service for balance management and trade execution"""
    
    def __init__(self, initial_balance: float = 100000.0, commission_rate: float = 0.001):
        self.portfolio = Portfolio(
            id=f"portfolio_{uuid.uuid4().hex[:8]}",
            name="Turtle Trading Portfolio",
            initial_balance=initial_balance,
            current_balance=initial_balance
        )
        self.commission_rate = commission_rate  # 0.1% default commission
        self.trade_counter = 0
        
        # Trade management (separate from portfolio model)
        self.open_trades: List[Trade] = []
        self.closed_trades: List[Trade] = []
        self.trade_history: List[Dict] = []
        
    @property
    def available_balance(self) -> float:
        """Calculate available balance for trading."""
        return self.portfolio.current_balance
    
    @property
    def portfolio_heat(self) -> float:
        """Calculate portfolio heat (risk exposure)."""
        # Simple implementation: ratio of open trade value to equity
        if not self.open_trades:
            return 0.0
        
        total_trade_value = 0.0
        for trade in self.open_trades:
            trade_value = trade.quantity * trade.entry_price
            total_trade_value += trade_value
        
        equity = self.portfolio.equity
        if equity <= 0:
            return 0.0
        
        return total_trade_value / equity
        
    async def calculate_position_size(self, price: float, atr: float, risk_percent: float = 0.01, 
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
        if trade_value > self.available_balance:
            quantity = self.available_balance / price * 0.9  # 90% to leave buffer
        
        return max(0.0, quantity), units
    
    async def can_add_position(self, symbol: str, max_heat: float = 0.25) -> bool:
        """Check if we can add more positions without exceeding heat limit"""
        if self.portfolio_heat >= max_heat:
            return False
        return True
    
    async def create_trade(self, request: TradeRequest) -> TradeResponse:
        """Create a new trade from request"""
        try:
            if request.quantity <= 0:
                return TradeResponse(
                    success=False,
                    message="Invalid quantity",
                    trade=None
                )
            
            price = request.price if request.price else 0.0  # Use market price if None
            trade_value = request.quantity * price
            commission = trade_value * self.commission_rate
            
            # Check if we have enough balance
            if trade_value + commission > self.available_balance:
                return TradeResponse(
                    success=False,
                    message="Insufficient balance",
                    trade=None
                )
            
            self.trade_counter += 1
            trade = Trade(
                id=f"T{self.trade_counter:06d}",
                symbol=request.symbol,
                trade_type=request.trade_type,
                entry_price=price,
                quantity=request.quantity,
                entry_time=datetime.now(),
                stop_loss=request.stop_loss,
                take_profit=request.take_profit,
                strategy_name=request.strategy_name
            )
            
            # Update portfolio
            self.open_trades.append(trade)
            self.portfolio.current_balance -= (trade_value + commission)
            
            # Record trade
            self.trade_history.append({
                'action': 'enter',
                'trade_id': trade.id,
                'symbol': request.symbol,
                'type': request.trade_type.value,
                'price': price,
                'quantity': request.quantity,
                'time': trade.entry_time,
                'balance': self.portfolio.current_balance
            })
            
            return TradeResponse(
                success=True,
                message="Trade created successfully",
                trade=trade
            )
            
        except Exception as e:
            return TradeResponse(
                success=False,
                message=f"Error creating trade: {str(e)}",
                trade=None
            )
    
    async def close_trade(self, trade_id: str, exit_price: Optional[float] = None) -> TradeResponse:
        """Close an existing trade"""
        try:
            # Find trade
            trade = None
            for t in self.open_trades:
                if t.id == trade_id:
                    trade = t
                    break
            
            if not trade:
                return TradeResponse(
                    success=False,
                    message="Trade not found",
                    trade=None
                )
            
            if trade.status == TradeStatus.CLOSED:
                return TradeResponse(
                    success=False,
                    message="Trade already closed",
                    trade=trade
                )
            
            # Use current price if not provided
            if exit_price is None:
                exit_price = trade.entry_price  # Placeholder - should get market price
            
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
            trade.realized_pnl = net_pnl
            trade.status = TradeStatus.CLOSED
            
            # Update portfolio
            self.portfolio.current_balance += trade_value - exit_commission
            self.portfolio.total_pnl += net_pnl
            
            # Move trade to closed trades
            self.open_trades.remove(trade)
            self.closed_trades.append(trade)
            
            # Record trade
            self.trade_history.append({
                'action': 'exit',
                'trade_id': trade.id,
                'symbol': trade.symbol,
                'reason': "manual",
                'price': exit_price,
                'pnl': net_pnl,
                'time': trade.exit_time,
                'balance': self.portfolio.current_balance
            })
            
            return TradeResponse(
                success=True,
                message="Trade closed successfully",
                trade=trade
            )
            
        except Exception as e:
            return TradeResponse(
                success=False,
                message=f"Error closing trade: {str(e)}",
                trade=None
            )
    
    async def cancel_trade(self, trade_id: str) -> bool:
        """Cancel a pending trade"""
        try:
            # Find and remove trade
            for trade in self.open_trades:
                if trade.id == trade_id and trade.status == TradeStatus.PENDING:
                    trade.status = TradeStatus.CANCELLED
                    self.open_trades.remove(trade)
                    # Refund balance
                    trade_value = trade.quantity * trade.entry_price
                    commission = trade_value * self.commission_rate
                    self.portfolio.current_balance += trade_value + commission
                    return True
            return False
        except Exception:
            return False
    
    async def get_trade(self, trade_id: str) -> Optional[Trade]:
        """Get trade by ID"""
        # Check open trades
        for trade in self.open_trades:
            if trade.id == trade_id:
                return trade
        
        # Check closed trades
        for trade in self.closed_trades:
            if trade.id == trade_id:
                return trade
        
        return None
    
    async def get_trades(self, symbol: str = None, status: str = None, limit: int = 100) -> List[Trade]:
        """Get trades with optional filtering"""
        all_trades = self.open_trades + self.closed_trades
        
        # Apply filters
        if symbol:
            all_trades = [t for t in all_trades if t.symbol.upper() == symbol.upper()]
        
        if status:
            status_enum = TradeStatus(status.lower())
            all_trades = [t for t in all_trades if t.status == status_enum]
        
        # Sort by entry time (newest first) and limit
        all_trades.sort(key=lambda t: t.entry_time, reverse=True)
        return all_trades[:limit]
    
    async def get_signals(self, symbol: str = None, strategy: str = None, limit: int = 50) -> List[TradingSignal]:
        """Get trading signals with optional filtering"""
        # This is a placeholder - signals would come from strategy engine
        return []
    
    async def process_market_data(self, symbol: str, strategy_name: str = None) -> List[TradingSignal]:
        """Process market data and generate trading signals"""
        # This is a placeholder - would integrate with strategy engine
        return []
    
    async def get_positions(self, symbol: str = None) -> List[Trade]:
        """Get current positions"""
        if symbol:
            return [trade for trade in self.open_trades if trade.symbol == symbol]
        return self.open_trades.copy()
    
    async def enable_auto_trading(self, strategy_name: str, symbol: str) -> bool:
        """Enable automatic trading for a strategy"""
        # Placeholder for auto-trading functionality
        return True
    
    async def disable_auto_trading(self, strategy_name: str, symbol: str = None) -> bool:
        """Disable automatic trading for a strategy"""
        # Placeholder for auto-trading functionality
        return True
    
    async def update_stop_loss(self, trade: Trade, new_stop: float) -> bool:
        """Update stop loss for an open trade"""
        if trade.status == TradeStatus.CLOSED:
            return False
        
        trade.stop_loss = new_stop
        return True
    
    async def check_stops_and_targets(self, current_prices: Dict[str, float]) -> List[Trade]:
        """Check all open trades for stop loss and take profit triggers"""
        triggered_trades = []
        
        for trade in self.open_trades.copy():
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
                await self._exit_trade_internal(trade, current_price, exit_reason)
                triggered_trades.append(trade)
        
        return triggered_trades
    
    async def _exit_trade_internal(self, trade: Trade, exit_price: float, reason: str = "manual") -> bool:
        """Internal method to exit a trade"""
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
        trade.realized_pnl = net_pnl
        trade.status = TradeStatus.CLOSED
        
        # Update portfolio
        self.portfolio.current_balance += trade_value - exit_commission
        self.portfolio.total_pnl += net_pnl
        
        # Move trade to closed trades
        self.open_trades.remove(trade)
        self.closed_trades.append(trade)
        
        # Record trade
        self.trade_history.append({
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
    
    async def get_open_positions(self, symbol: Optional[str] = None) -> List[Trade]:
        """Get open positions, optionally filtered by symbol"""
        if symbol:
            return [trade for trade in self.open_trades if trade.symbol == symbol]
        return self.open_trades.copy()
    
    async def get_performance_stats(self) -> Dict:
        """Calculate performance statistics"""
        if not self.closed_trades:
            total_return = (self.portfolio.equity - self.portfolio.initial_balance) / self.portfolio.initial_balance
            return {
                'total_trades': 0,
                'open_trades': len(self.open_trades),
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'total_return': total_return,
                'total_pnl': self.portfolio.total_pnl,
                'current_balance': self.portfolio.current_balance,
                'equity': self.portfolio.equity,
                'portfolio_heat': self.portfolio_heat
            }
        
        wins = [trade.realized_pnl for trade in self.closed_trades if trade.realized_pnl > 0]
        losses = [trade.realized_pnl for trade in self.closed_trades if trade.realized_pnl < 0]
        
        win_rate = len(wins) / len(self.closed_trades) if self.closed_trades else 0
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        profit_factor = sum(wins) / abs(sum(losses)) if losses else float('inf')
        total_return = (self.portfolio.equity - self.portfolio.initial_balance) / self.portfolio.initial_balance
        
        return {
            'total_trades': len(self.closed_trades),
            'open_trades': len(self.open_trades),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'total_return': total_return,
            'total_pnl': self.portfolio.total_pnl,
            'current_balance': self.portfolio.current_balance,
            'equity': self.portfolio.equity,
            'portfolio_heat': self.portfolio_heat
        }

    # Async methods with _async postfix for test compatibility
    async def calculate_position_size_async(self, entry_price: float, stop_loss: float, risk_percent: float = 0.01) -> float:
        """Calculate position size based on risk management."""
        if entry_price <= 0 or stop_loss <= 0:
            return 0.0
            
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share == 0:
            return 0.0
            
        risk_amount = self.portfolio.current_balance * risk_percent
        position_size = risk_amount / risk_per_share
        
        # Ensure we don't exceed available balance
        trade_value = position_size * entry_price
        if trade_value > self.available_balance:
            position_size = self.available_balance / entry_price * 0.9
            
        return max(0.0, position_size)
    
    async def enter_trade_async(self, request: TradeRequest) -> TradeResponse:
        """Enter a trade."""
        try:
            # Check if we have enough balance
            entry_price = request.price if request.price else 50.0  # Default price if None
            trade_value = request.quantity * entry_price
            commission = trade_value * self.commission_rate
            total_cost = trade_value + commission
            
            if total_cost > self.portfolio.current_balance:
                return TradeResponse(
                    success=False,
                    message="Insufficient balance for trade",
                    trade=None
                )
            
            # Create trade
            trade = Trade(
                id=f"trade_{uuid.uuid4().hex[:8]}",
                symbol=request.symbol,
                trade_type=request.trade_type,
                quantity=request.quantity,
                entry_price=entry_price,
                stop_loss=request.stop_loss,
                take_profit=request.take_profit,
                status=TradeStatus.OPEN,
                entry_time=datetime.now()
            )
            
            # Update balance
            self.portfolio.current_balance -= total_cost
            self.open_trades.append(trade)
            
            return TradeResponse(
                success=True,
                message="Trade entered successfully",
                trade=trade
            )
            
        except Exception as e:
            return TradeResponse(
                success=False,
                message=f"Error entering trade: {str(e)}",
                trade=None
            )
    
    async def exit_trade_async(self, trade_id: str, exit_price: float, reason: str = "manual") -> TradeResponse:
        """Exit a trade."""
        try:
            # Find the trade
            trade = None
            for t in self.open_trades:
                if t.id == trade_id:
                    trade = t
                    break
            
            if not trade:
                return TradeResponse(
                    success=False,
                    message="Trade not found",
                    trade=None
                )
            
            # Calculate PnL and update trade
            pnl = (exit_price - trade.entry_price) * trade.quantity
            commission = trade.quantity * exit_price * self.commission_rate
            net_pnl = pnl - commission
            
            trade.exit_price = exit_price
            trade.exit_time = datetime.now()
            trade.status = TradeStatus.CLOSED
            
            # Update balance
            trade_value = trade.quantity * exit_price
            self.portfolio.current_balance += trade_value - commission
            
            # Move to closed trades
            self.open_trades.remove(trade)
            self.closed_trades.append(trade)
            
            return TradeResponse(
                success=True,
                message="Trade exited successfully",
                trade=trade
            )
            
        except Exception as e:
            return TradeResponse(
                success=False,
                message=f"Error exiting trade: {str(e)}",
                trade=None
            )
    
    async def get_open_trades_async(self) -> List[Trade]:
        """Get all open trades."""
        return self.open_trades.copy()
    
    async def get_trade_history_async(self) -> List[Dict]:
        """Get trade history."""
        history = []
        for trade in self.closed_trades:
            history.append({
                "id": trade.id,
                "symbol": trade.symbol,
                "type": trade.trade_type.value,
                "quantity": trade.quantity,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "pnl": ((trade.exit_price or 0) - trade.entry_price) * trade.quantity,
                "timestamp": trade.entry_time.isoformat(),
                "exit_timestamp": trade.exit_time.isoformat() if trade.exit_time else None
            })
        return history
    
    async def get_portfolio_status_async(self) -> Dict:
        """Get portfolio status."""
        return {
            "initial_balance": self.portfolio.initial_balance,
            "current_balance": self.portfolio.current_balance,
            "equity": self.portfolio.equity,
            "total_trades": len(self.open_trades) + len(self.closed_trades),
            "open_trades": len(self.open_trades),
            "portfolio_heat": self.portfolio_heat
        }
    
    async def check_stops_and_targets_async(self, current_prices: Dict[str, float]) -> List[Dict]:
        """Check stop losses and take profits."""
        triggered = []
        
        for trade in self.open_trades.copy():
            current_price = current_prices.get(trade.symbol)
            if not current_price:
                continue
                
            # Check stop loss
            if trade.stop_loss:
                if ((trade.trade_type == TradeType.LONG and current_price <= trade.stop_loss) or
                    (trade.trade_type == TradeType.SHORT and current_price >= trade.stop_loss)):
                    
                    triggered.append({
                        "trade_id": trade.id,
                        "symbol": trade.symbol,
                        "trigger_type": "stop_loss",
                        "current_price": current_price,
                        "trigger_price": trade.stop_loss
                    })
                    
            # Check take profit
            if trade.take_profit:
                if ((trade.trade_type == TradeType.LONG and current_price >= trade.take_profit) or
                    (trade.trade_type == TradeType.SHORT and current_price <= trade.take_profit)):
                    
                    triggered.append({
                        "trade_id": trade.id,
                        "symbol": trade.symbol,
                        "trigger_type": "take_profit",
                        "current_price": current_price,
                        "trigger_price": trade.take_profit
                    })
        
        return triggered
    
    async def process_signal_async(self, signal: TradingSignal) -> Dict:
        """Process a trading signal."""
        return {
            "signal_processed": True,
            "symbol": signal.symbol,
            "signal_type": signal.signal_type,
            "confidence": signal.confidence,
            "timestamp": signal.timestamp.isoformat()
        }