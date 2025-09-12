"""Strategy engine service implementing turtle trading rules."""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from app.models.chart import ChartData
from app.models.candle import Candle
from app.models.trade import TradeType, Trade
from app.models.strategy import TradingSignal, StrategyConfig
from app.services.trading_service import TradingService
from app.services.position_service import PositionService, MarketData


@dataclass
class TradingSignalData:
    """Enhanced trading signal with additional metadata."""
    symbol: str
    signal_type: str  # 'entry', 'exit', 'pyramid'
    trade_type: TradeType
    price: float
    confidence: float
    reason: str
    timestamp: datetime
    quantity: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class StrategyEngine:
    """Main strategy engine implementing turtle trading rules."""
    
    def __init__(self, initial_balance: float = 100000.0):
        self.trading_service = TradingService(initial_balance)
        self.position_service = PositionService(self.trading_service)
        self.strategy_config: Optional[StrategyConfig] = None
        self.is_enabled = False
        self.signals_history: List[TradingSignalData] = []
        
    async def load_strategy(self, strategy_config: StrategyConfig):
        """Load strategy configuration."""
        self.strategy_config = strategy_config
        
    async def enable_trading(self, enabled: bool = True):
        """Enable/disable trading."""
        self.is_enabled = enabled
        
    async def process_market_data(self, symbol: str, chart_data: ChartData) -> List[TradingSignal]:
        """Process new market data and generate signals."""
        if not self.strategy_config or not self.is_enabled:
            return []
        
        # Update market data
        market_data = await self.position_service.update_market_data(symbol, chart_data.candles)
        if not market_data:
            return []
        
        signals = []
        
        # Check for exit signals first (stops, trailing stops)
        exit_signals = await self._check_exit_signals(symbol)
        signals.extend(exit_signals)
        
        # Check for new entry signals
        entry_signals = await self._check_entry_signals(symbol)
        signals.extend(entry_signals)
        
        # Check for pyramiding opportunities
        pyramid_signals = await self._check_pyramid_signals(symbol)
        signals.extend(pyramid_signals)
        
        # Convert to API model format
        api_signals = []
        for signal in signals:
            api_signal = TradingSignal(
                symbol=signal.symbol,
                signal_type=signal.signal_type,
                action=signal.trade_type.value,
                price=signal.price,
                confidence=signal.confidence,
                reason=signal.reason,
                timestamp=signal.timestamp,
                metadata={
                    "quantity": signal.quantity,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit
                }
            )
            api_signals.append(api_signal)
        
        # Store signals in history
        self.signals_history.extend(signals)
        
        return api_signals
    
    async def _check_exit_signals(self, symbol: str) -> List[TradingSignalData]:
        """Check for exit signals."""
        signals = []
        
        if not self.strategy_config:
            return signals
        
        # Check trailing stops
        trailing_trades = await self.position_service.check_trailing_stops(symbol, self.strategy_config.config)
        for trade in trailing_trades:
            signal = TradingSignalData(
                symbol=symbol,
                signal_type='exit',
                trade_type=trade.trade_type,
                price=trade.exit_price,
                confidence=1.0,
                reason=f"Trailing stop exit",
                timestamp=datetime.now()
            )
            signals.append(signal)
        
        # Update breakeven stops
        updated_count = await self.position_service.update_breakeven_stops(symbol, self.strategy_config.config)
        if updated_count > 0:
            signal = TradingSignalData(
                symbol=symbol,
                signal_type='update',
                trade_type=TradeType.LONG,  # Placeholder
                price=0.0,
                confidence=1.0,
                reason=f"Updated {updated_count} stops to breakeven",
                timestamp=datetime.now()
            )
            signals.append(signal)
        
        # Check regular stop losses via trading service
        if symbol in self.position_service.market_data:
            current_prices = {symbol: self.position_service.market_data[symbol].current_price}
            stopped_trades = await self.trading_service.check_stops_and_targets(current_prices)
            for trade in stopped_trades:
                signal = TradingSignalData(
                    symbol=symbol,
                    signal_type='exit',
                    trade_type=trade.trade_type,
                    price=trade.exit_price,
                    confidence=1.0,
                    reason="Stop loss or take profit hit",
                    timestamp=datetime.now()
                )
                signals.append(signal)
        
        return signals
    
    async def _check_entry_signals(self, symbol: str) -> List[TradingSignalData]:
        """Check for new entry signals."""
        signals = []
        
        if not self.strategy_config:
            return signals
        
        # Check if we can add more positions (heat limit)
        max_heat = self.strategy_config.config.get('risk', {}).get('max_heat_pct', 0.25)
        if not await self.trading_service.can_add_position(symbol, max_heat):
            return signals
        
        # Check for entry signals
        entry_signal = await self.position_service.check_entry_signals(symbol, self.strategy_config.config)
        if not entry_signal:
            return signals
        
        trade_type, reason = entry_signal
        market = self.position_service.market_data[symbol]
        
        # Calculate position size
        risk_pct = self.strategy_config.config.get('risk', {}).get('unit_pct', 0.01)
        stop_mult = self.strategy_config.config.get('exits', {}).get('stop_init_atr_mult', 2.0)
        
        quantity, units = await self.trading_service.calculate_position_size(
            market.current_price, market.atr, risk_pct, stop_mult
        )
        
        if quantity > 0:
            # Calculate stop loss
            stop_loss = await self.position_service.calculate_stop_loss(
                market.current_price, trade_type, market.atr, self.strategy_config.config
            )
            
            signal = TradingSignalData(
                symbol=symbol,
                signal_type='entry',
                trade_type=trade_type,
                price=market.current_price,
                confidence=0.8,
                reason=reason,
                timestamp=datetime.now(),
                quantity=quantity,
                stop_loss=stop_loss
            )
            signals.append(signal)
        
        return signals
    
    async def _check_pyramid_signals(self, symbol: str) -> List[TradingSignalData]:
        """Check for pyramiding opportunities."""
        signals = []
        
        if not self.strategy_config:
            return signals
        
        # Check if pyramiding is allowed
        if not await self.position_service.check_pyramiding_opportunity(symbol, self.strategy_config.config):
            return signals
        
        market = self.position_service.market_data[symbol]
        open_trades = await self.trading_service.get_open_positions(symbol)
        
        if open_trades:
            base_trade = open_trades[0]
            
            # Calculate add-on size (typically smaller than initial)
            risk_pct = self.strategy_config.config.get('risk', {}).get('unit_pct', 0.01) * 0.5  # Half size
            stop_mult = self.strategy_config.config.get('exits', {}).get('stop_init_atr_mult', 2.0)
            
            quantity, units = await self.trading_service.calculate_position_size(
                market.current_price, market.atr, risk_pct, stop_mult
            )
            
            if quantity > 0:
                signal = TradingSignalData(
                    symbol=symbol,
                    signal_type='pyramid',
                    trade_type=base_trade.trade_type,
                    price=market.current_price,
                    confidence=0.6,
                    reason=f"Pyramid add-on (unit {len(open_trades) + 1})",
                    timestamp=datetime.now(),
                    quantity=quantity
                )
                signals.append(signal)
        
        return signals
    
    async def execute_signal(self, signal: TradingSignalData) -> Optional[Trade]:
        """Execute a trading signal."""
        if not self.is_enabled or not self.strategy_config:
            return None
        
        if signal.symbol not in self.position_service.market_data:
            return None
        
        market = self.position_service.market_data[signal.symbol]
        
        if signal.signal_type == 'entry' or signal.signal_type == 'pyramid':
            # Calculate position size if not provided
            if not signal.quantity:
                risk_pct = self.strategy_config.config.get('risk', {}).get('unit_pct', 0.01)
                stop_mult = self.strategy_config.config.get('exits', {}).get('stop_init_atr_mult', 2.0)
                
                if signal.signal_type == 'pyramid':
                    risk_pct *= 0.5  # Smaller size for add-ons
                
                quantity, units = await self.trading_service.calculate_position_size(
                    signal.price, market.atr, risk_pct, stop_mult
                )
            else:
                quantity = signal.quantity
                units = 1
            
            if quantity <= 0:
                return None
            
            # Calculate stop loss if not provided
            stop_loss = signal.stop_loss
            if not stop_loss:
                stop_loss = await self.position_service.calculate_stop_loss(
                    signal.price, signal.trade_type, market.atr, self.strategy_config.config
                )
            
            # Create trade request
            from app.models.trade import TradeRequest
            request = TradeRequest(
                symbol=signal.symbol,
                trade_type=signal.trade_type,
                quantity=quantity,
                price=signal.price,
                stop_loss=stop_loss,
                take_profit=signal.take_profit,
                strategy_name=self.strategy_config.name if self.strategy_config else "turtle"
            )
            
            # Execute trade
            response = await self.trading_service.create_trade(request)
            if response.success and response.trade:
                # Store additional metadata
                response.trade.units = units
                setattr(response.trade, 'entry_reason', signal.reason)
                return response.trade
        
        return None
    
    async def get_current_signals(self, symbol: str) -> List[TradingSignalData]:
        """Get current active signals for a symbol."""
        if symbol not in self.position_service.market_data:
            return []
        
        return [
            signal for signal in self.signals_history[-10:]  # Last 10 signals
            if signal.symbol == symbol and 
            (datetime.now() - signal.timestamp).total_seconds() < 3600  # Last hour
        ]
    
    async def get_portfolio_summary(self) -> Dict:
        """Get portfolio summary."""
        stats = await self.trading_service.get_performance_stats()
        
        summary = {
            **stats,
            'strategy_name': self.strategy_config.name if self.strategy_config else 'None',
            'trading_enabled': self.is_enabled,
            'signals_count': len(self.signals_history),
            'recent_signals': len([
                s for s in self.signals_history 
                if (datetime.now() - s.timestamp).total_seconds() < 3600
            ])
        }
        
        return summary
    
    async def get_position_summary(self, symbol: str) -> Dict:
        """Get position summary for a symbol."""
        market_summary = await self.position_service.get_market_summary(symbol)
        open_positions = await self.trading_service.get_open_positions(symbol)
        
        # Calculate unrealized PnL
        total_unrealized_pnl = 0
        total_units = 0
        if symbol in self.position_service.market_data:
            current_price = self.position_service.market_data[symbol].current_price
            for trade in open_positions:
                pnl = trade.calculate_pnl(current_price)
                trade.unrealized_pnl = pnl
                total_unrealized_pnl += pnl
                total_units += getattr(trade, 'units', 1)
        
        return {
            **market_summary,
            'open_positions': len(open_positions),
            'total_units': total_units,
            'unrealized_pnl': total_unrealized_pnl,
            'current_signals': len(await self.get_current_signals(symbol))
        }
    
    async def reset_portfolio(self, initial_balance: float = 100000.0):
        """Reset portfolio to initial state."""
        self.trading_service = TradingService(initial_balance)
        self.position_service = PositionService(self.trading_service)
        self.signals_history.clear()
    
    async def backtest_mode(self, enabled: bool = True):
        """Enable backtest mode (paper trading)."""
        # In a real implementation, this would switch to paper trading
        # For now, all trading is simulated anyway
        pass
    
    async def get_strategy_performance(self, symbol: str = None) -> Dict:
        """Get detailed strategy performance metrics."""
        stats = await self.trading_service.get_performance_stats()
        
        # Filter trades by symbol if specified
        if symbol:
            all_trades = [t for t in self.trading_service.portfolio.closed_trades if t.symbol == symbol]
        else:
            all_trades = self.trading_service.portfolio.closed_trades
        
        if not all_trades:
            return stats
        
        # Calculate additional strategy-specific metrics
        sys1_trades = [t for t in all_trades if 'sys1' in getattr(t, 'entry_reason', '')]
        sys2_trades = [t for t in all_trades if 'sys2' in getattr(t, 'entry_reason', '')]
        
        sys1_wins = [t for t in sys1_trades if t.realized_pnl > 0]
        sys2_wins = [t for t in sys2_trades if t.realized_pnl > 0]
        
        strategy_stats = {
            **stats,
            'sys1_trades': len(sys1_trades),
            'sys2_trades': len(sys2_trades),
            'sys1_win_rate': len(sys1_wins) / len(sys1_trades) if sys1_trades else 0,
            'sys2_win_rate': len(sys2_wins) / len(sys2_trades) if sys2_trades else 0,
            'sys1_total_pnl': sum(t.realized_pnl for t in sys1_trades),
            'sys2_total_pnl': sum(t.realized_pnl for t in sys2_trades),
            'avg_holding_days': sum((t.exit_time - t.entry_time).days for t in all_trades) / len(all_trades),
            'max_consecutive_losses': self._calculate_max_consecutive_losses(all_trades),
            'max_drawdown': self._calculate_max_drawdown(all_trades)
        }
        
        return strategy_stats
    
    def _calculate_max_consecutive_losses(self, trades: List[Trade]) -> int:
        """Calculate maximum consecutive losing trades."""
        max_consecutive = 0
        current_consecutive = 0
        
        for trade in sorted(trades, key=lambda t: t.entry_time):
            if trade.realized_pnl < 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        return max_consecutive
    
    def _calculate_max_drawdown(self, trades: List[Trade]) -> float:
        """Calculate maximum drawdown percentage."""
        if not trades:
            return 0.0
        
        running_balance = self.trading_service.portfolio.initial_balance
        peak_balance = running_balance
        max_drawdown = 0.0
        
        for trade in sorted(trades, key=lambda t: t.entry_time):
            running_balance += trade.realized_pnl
            
            if running_balance > peak_balance:
                peak_balance = running_balance
            
            current_drawdown = (peak_balance - running_balance) / peak_balance
            max_drawdown = max(max_drawdown, current_drawdown)
        
        return max_drawdown