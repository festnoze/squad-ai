from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import sys
sys.path.append('..')
from models import ChartData, Candle, TradeType, Trade
from trading_service import TradingService
from position_manager import PositionManager, MarketData
from strategy_loader import StrategyConfig


@dataclass
class TradingSignal:
    symbol: str
    signal_type: str  # 'entry', 'exit', 'pyramid'
    trade_type: TradeType
    price: float
    confidence: float
    reason: str
    timestamp: datetime


class StrategyEngine:
    """Main strategy engine implementing turtle trading rules"""
    
    def __init__(self, initial_balance: float = 100000.0):
        self.trading_service = TradingService(initial_balance)
        self.position_manager = PositionManager(self.trading_service)
        self.strategy_config: Optional[StrategyConfig] = None
        self.is_enabled = False
        self.signals_history: List[TradingSignal] = []
        
    def load_strategy(self, strategy_config: StrategyConfig):
        """Load strategy configuration"""
        self.strategy_config = strategy_config
        
    def enable_trading(self, enabled: bool = True):
        """Enable/disable trading"""
        self.is_enabled = enabled
        
    def process_market_data(self, symbol: str, chart_data: ChartData) -> List[TradingSignal]:
        """Process new market data and generate signals"""
        if not self.strategy_config or not self.is_enabled:
            return []
        
        # Update market data
        market_data = self.position_manager.update_market_data(symbol, chart_data.candles)
        if not market_data:
            return []
        
        signals = []
        
        # Check for exit signals first (stops, trailing stops)
        exit_signals = self._check_exit_signals(symbol)
        signals.extend(exit_signals)
        
        # Check for new entry signals
        entry_signals = self._check_entry_signals(symbol)
        signals.extend(entry_signals)
        
        # Check for pyramiding opportunities
        pyramid_signals = self._check_pyramid_signals(symbol)
        signals.extend(pyramid_signals)
        
        # Store signals in history
        self.signals_history.extend(signals)
        
        return signals
    
    def _check_exit_signals(self, symbol: str) -> List[TradingSignal]:
        """Check for exit signals"""
        signals = []
        
        if not self.strategy_config:
            return signals
        
        # Check trailing stops
        trailing_trades = self.position_manager.check_trailing_stops(symbol, self.strategy_config.config)
        for trade in trailing_trades:
            signal = TradingSignal(
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
        updated_count = self.position_manager.update_breakeven_stops(symbol, self.strategy_config.config)
        if updated_count > 0:
            signal = TradingSignal(
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
        current_prices = {symbol: self.position_manager.market_data[symbol].current_price}
        stopped_trades = self.trading_service.check_stops_and_targets(current_prices)
        for trade in stopped_trades:
            signal = TradingSignal(
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
    
    def _check_entry_signals(self, symbol: str) -> List[TradingSignal]:
        """Check for new entry signals"""
        signals = []
        
        if not self.strategy_config:
            return signals
        
        # Check if we can add more positions (heat limit)
        max_heat = self.strategy_config.config.get('risk', {}).get('max_heat_pct', 0.25)
        if not self.position_manager.trading_service.can_add_position(symbol, max_heat):
            return signals
        
        # Check for entry signals
        entry_signal = self.position_manager.check_entry_signals(symbol, self.strategy_config.config)
        if not entry_signal:
            return signals
        
        trade_type, reason = entry_signal
        market = self.position_manager.market_data[symbol]
        
        # Calculate position size
        risk_pct = self.strategy_config.config.get('risk', {}).get('unit_pct', 0.01)
        stop_mult = self.strategy_config.config.get('exits', {}).get('stop_init_atr_mult', 2.0)
        
        quantity, units = self.trading_service.calculate_position_size(
            market.current_price, market.atr, risk_pct, stop_mult
        )
        
        if quantity > 0:
            signal = TradingSignal(
                symbol=symbol,
                signal_type='entry',
                trade_type=trade_type,
                price=market.current_price,
                confidence=0.8,
                reason=reason,
                timestamp=datetime.now()
            )
            signals.append(signal)
        
        return signals
    
    def _check_pyramid_signals(self, symbol: str) -> List[TradingSignal]:
        """Check for pyramiding opportunities"""
        signals = []
        
        if not self.strategy_config:
            return signals
        
        # Check if pyramiding is allowed
        if not self.position_manager.check_pyramiding_opportunity(symbol, self.strategy_config.config):
            return signals
        
        market = self.position_manager.market_data[symbol]
        open_trades = self.trading_service.get_open_positions(symbol)
        
        if open_trades:
            base_trade = open_trades[0]
            
            # Calculate add-on size (typically smaller than initial)
            risk_pct = self.strategy_config.config.get('risk', {}).get('unit_pct', 0.01) * 0.5  # Half size
            stop_mult = self.strategy_config.config.get('exits', {}).get('stop_init_atr_mult', 2.0)
            
            quantity, units = self.trading_service.calculate_position_size(
                market.current_price, market.atr, risk_pct, stop_mult
            )
            
            if quantity > 0:
                signal = TradingSignal(
                    symbol=symbol,
                    signal_type='pyramid',
                    trade_type=base_trade.trade_type,
                    price=market.current_price,
                    confidence=0.6,
                    reason=f"Pyramid add-on (unit {len(open_trades) + 1})",
                    timestamp=datetime.now()
                )
                signals.append(signal)
        
        return signals
    
    def execute_signal(self, signal: TradingSignal) -> Optional[Trade]:
        """Execute a trading signal"""
        if not self.is_enabled or not self.strategy_config:
            return None
        
        if signal.symbol not in self.position_manager.market_data:
            return None
        
        market = self.position_manager.market_data[signal.symbol]
        
        if signal.signal_type == 'entry' or signal.signal_type == 'pyramid':
            # Calculate position size
            risk_pct = self.strategy_config.config.get('risk', {}).get('unit_pct', 0.01)
            stop_mult = self.strategy_config.config.get('exits', {}).get('stop_init_atr_mult', 2.0)
            
            if signal.signal_type == 'pyramid':
                risk_pct *= 0.5  # Smaller size for add-ons
            
            quantity, units = self.trading_service.calculate_position_size(
                signal.price, market.atr, risk_pct, stop_mult
            )
            
            if quantity <= 0:
                return None
            
            # Calculate stop loss
            stop_loss = self.position_manager.calculate_stop_loss(
                signal.price, signal.trade_type, market.atr, self.strategy_config.config
            )
            
            # Enter trade
            trade = self.trading_service.enter_trade(
                symbol=signal.symbol,
                trade_type=signal.trade_type,
                price=signal.price,
                quantity=quantity,
                stop_loss=stop_loss
            )
            
            if trade:
                trade.units = units
                # Store entry reason for later reference
                setattr(trade, 'entry_reason', signal.reason)
            
            return trade
        
        return None
    
    def get_current_signals(self, symbol: str) -> List[TradingSignal]:
        """Get current active signals for a symbol"""
        if symbol not in self.position_manager.market_data:
            return []
        
        return [
            signal for signal in self.signals_history[-10:]  # Last 10 signals
            if signal.symbol == symbol and 
            (datetime.now() - signal.timestamp).total_seconds() < 3600  # Last hour
        ]
    
    def get_portfolio_summary(self) -> Dict:
        """Get portfolio summary"""
        stats = self.trading_service.get_performance_stats()
        
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
    
    def get_position_summary(self, symbol: str) -> Dict:
        """Get position summary for a symbol"""
        market_summary = self.position_manager.get_market_summary(symbol)
        open_positions = self.trading_service.get_open_positions(symbol)
        
        return {
            **market_summary,
            'open_positions': len(open_positions),
            'total_units': sum(trade.units for trade in open_positions),
            'unrealized_pnl': sum(trade.current_pnl for trade in open_positions),
            'current_signals': len(self.get_current_signals(symbol))
        }
    
    def reset_portfolio(self, initial_balance: float = 100000.0):
        """Reset portfolio to initial state"""
        self.trading_service = TradingService(initial_balance)
        self.position_manager = PositionManager(self.trading_service)
        self.signals_history.clear()
    
    def backtest_mode(self, enabled: bool = True):
        """Enable backtest mode (paper trading)"""
        # In a real implementation, this would switch to paper trading
        # For now, all trading is simulated anyway
        pass