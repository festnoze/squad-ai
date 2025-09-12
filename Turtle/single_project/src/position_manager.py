from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import pandas as pd
import sys
sys.path.append('..')
from models import Candle, Trade, TradeType
from trading_service import TradingService


@dataclass
class MarketData:
    symbol: str
    candles: List[Candle]
    current_price: float
    atr: float
    high_20: float
    low_20: float
    high_55: float
    low_55: float
    last_trade_winner: Optional[bool] = None


class PositionManager:
    """Manages positions and risk for turtle trading strategy"""
    
    def __init__(self, trading_service: TradingService):
        self.trading_service = trading_service
        self.market_data: Dict[str, MarketData] = {}
        
    def update_market_data(self, symbol: str, candles: List[Candle]) -> MarketData:
        """Update market data for a symbol and calculate indicators"""
        if len(candles) < 55:
            # Not enough data for turtle strategy
            return None
        
        df = pd.DataFrame([
            {
                'timestamp': candle.timestamp,
                'open': candle.open,
                'high': candle.high,
                'low': candle.low,
                'close': candle.close
            }
            for candle in candles
        ])
        
        # Calculate ATR (Average True Range)
        df['prev_close'] = df['close'].shift(1)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = abs(df['high'] - df['prev_close'])
        df['tr3'] = abs(df['low'] - df['prev_close'])
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        df['atr'] = df['tr'].rolling(window=14).mean()
        
        # Calculate breakout levels
        df['high_20'] = df['high'].rolling(window=20).max()
        df['low_20'] = df['low'].rolling(window=20).min()
        df['high_55'] = df['high'].rolling(window=55).max()
        df['low_55'] = df['low'].rolling(window=55).min()
        
        latest = df.iloc[-1]
        
        # Get last trade result for this symbol
        last_trade_winner = self._get_last_trade_result(symbol)
        
        market_data = MarketData(
            symbol=symbol,
            candles=candles,
            current_price=latest['close'],
            atr=latest['atr'] if pd.notna(latest['atr']) else 0.0,
            high_20=latest['high_20'] if pd.notna(latest['high_20']) else latest['close'],
            low_20=latest['low_20'] if pd.notna(latest['low_20']) else latest['close'],
            high_55=latest['high_55'] if pd.notna(latest['high_55']) else latest['close'],
            low_55=latest['low_55'] if pd.notna(latest['low_55']) else latest['close'],
            last_trade_winner=last_trade_winner
        )
        
        self.market_data[symbol] = market_data
        return market_data
    
    def _get_last_trade_result(self, symbol: str) -> Optional[bool]:
        """Get the result of the last closed trade for this symbol"""
        symbol_trades = [
            trade for trade in self.trading_service.portfolio.closed_trades
            if trade.symbol == symbol
        ]
        
        if symbol_trades:
            last_trade = max(symbol_trades, key=lambda t: t.exit_time)
            return last_trade.pnl > 0
        
        return None
    
    def check_entry_signals(self, symbol: str, strategy_config: Dict) -> Optional[Tuple[TradeType, str]]:
        """Check for turtle entry signals"""
        if symbol not in self.market_data:
            return None
        
        market = self.market_data[symbol]
        
        if market.atr == 0:
            return None
        
        # Volatility gate check
        vol_gate_mult = strategy_config.get('entries', {}).get('vol_gate_atr_mult', 1.2)
        if market.atr < vol_gate_mult * market.atr:  # This needs historical ATR comparison
            return None
        
        # Check if price is too close to breakout level (avoid marginal signals)
        noise_threshold = 0.25 * market.atr
        
        # System 1: 20-day breakout (only if last trade was loser)
        sys1_days = strategy_config.get('entries', {}).get('sys1_breakout_days', 20)
        if market.last_trade_winner is False or market.last_trade_winner is None:
            # Long signal on 20-day high breakout
            if (market.current_price > market.high_20 and 
                market.current_price - market.high_20 > noise_threshold):
                return (TradeType.LONG, "sys1_long")
            
            # Short signal on 20-day low breakout
            if (market.current_price < market.low_20 and 
                market.low_20 - market.current_price > noise_threshold):
                return (TradeType.SHORT, "sys1_short")
        
        # System 2: 55-day breakout (always active)
        sys2_days = strategy_config.get('entries', {}).get('sys2_breakout_days', 55)
        # Long signal on 55-day high breakout
        if (market.current_price > market.high_55 and 
            market.current_price - market.high_55 > noise_threshold):
            return (TradeType.LONG, "sys2_long")
        
        # Short signal on 55-day low breakout
        if (market.current_price < market.low_55 and 
            market.low_55 - market.current_price > noise_threshold):
            return (TradeType.SHORT, "sys2_short")
        
        return None
    
    def calculate_stop_loss(self, entry_price: float, trade_type: TradeType, 
                          atr: float, strategy_config: Dict) -> float:
        """Calculate initial stop loss based on ATR"""
        stop_mult = strategy_config.get('exits', {}).get('stop_init_atr_mult', 2.0)
        stop_distance = atr * stop_mult
        
        if trade_type == TradeType.LONG:
            return entry_price - stop_distance
        else:  # SHORT
            return entry_price + stop_distance
    
    def check_trailing_stops(self, symbol: str, strategy_config: Dict) -> List[Trade]:
        """Check for trailing stop exits"""
        if symbol not in self.market_data:
            return []
        
        market = self.market_data[symbol]
        open_trades = self.trading_service.get_open_positions(symbol)
        triggered_trades = []
        
        for trade in open_trades:
            should_exit = False
            exit_reason = ""
            
            # Check time stop (80 trading days)
            time_stop_days = strategy_config.get('exits', {}).get('time_stop_days', 80)
            if (datetime.now() - trade.entry_time).days >= time_stop_days:
                should_exit = True
                exit_reason = "time_stop"
            
            # Check trailing stops based on system
            elif "sys1" in getattr(trade, 'entry_reason', ''):
                trail_days = strategy_config.get('exits', {}).get('trail_sys1_days', 10)
                if trade.trade_type == TradeType.LONG and market.current_price <= market.low_20:
                    should_exit = True
                    exit_reason = "trail_sys1"
                elif trade.trade_type == TradeType.SHORT and market.current_price >= market.high_20:
                    should_exit = True
                    exit_reason = "trail_sys1"
            
            elif "sys2" in getattr(trade, 'entry_reason', ''):
                trail_days = strategy_config.get('exits', {}).get('trail_sys2_days', 20)
                if trade.trade_type == TradeType.LONG and market.current_price <= market.low_20:
                    should_exit = True
                    exit_reason = "trail_sys2"
                elif trade.trade_type == TradeType.SHORT and market.current_price >= market.high_20:
                    should_exit = True
                    exit_reason = "trail_sys2"
            
            if should_exit:
                self.trading_service.exit_trade(trade, market.current_price, exit_reason)
                triggered_trades.append(trade)
        
        return triggered_trades
    
    def update_breakeven_stops(self, symbol: str, strategy_config: Dict) -> int:
        """Move stops to breakeven when trade gains enough"""
        if symbol not in self.market_data:
            return 0
        
        market = self.market_data[symbol]
        open_trades = self.trading_service.get_open_positions(symbol)
        updated_count = 0
        
        breakeven_trigger = strategy_config.get('exits', {}).get('breakeven_trigger_atr', 1.0)
        trigger_distance = market.atr * breakeven_trigger
        
        for trade in open_trades:
            if trade.trade_type == TradeType.LONG:
                profit = market.current_price - trade.entry_price
                if profit >= trigger_distance and trade.stop_loss < trade.entry_price:
                    self.trading_service.update_stop_loss(trade, trade.entry_price)
                    updated_count += 1
            else:  # SHORT
                profit = trade.entry_price - market.current_price
                if profit >= trigger_distance and trade.stop_loss > trade.entry_price:
                    self.trading_service.update_stop_loss(trade, trade.entry_price)
                    updated_count += 1
        
        return updated_count
    
    def check_pyramiding_opportunity(self, symbol: str, strategy_config: Dict) -> bool:
        """Check if we can add to existing position (pyramiding)"""
        if symbol not in self.market_data:
            return False
        
        market = self.market_data[symbol]
        open_trades = self.trading_service.get_open_positions(symbol)
        
        if not open_trades:
            return False
        
        max_addons = strategy_config.get('pyramiding', {}).get('max_addons', 4)
        addon_step_atr = strategy_config.get('pyramiding', {}).get('addon_step_atr', 0.5)
        
        # Count existing units
        total_units = sum(trade.units for trade in open_trades)
        
        if total_units >= max_addons + 1:  # +1 for initial position
            return False
        
        # Check whipsaw brake
        whipsaw_losses = strategy_config.get('pyramiding', {}).get('whipsaw_brake_losses', 2)
        recent_trades = [
            trade for trade in self.trading_service.portfolio.closed_trades[-5:]
            if trade.symbol == symbol and trade.pnl < 0
        ]
        
        if len(recent_trades) >= whipsaw_losses:
            return False
        
        # Check if price has moved favorably enough for add-on
        base_trade = open_trades[0]  # Assume first trade is base position
        step_size = market.atr * addon_step_atr
        
        if base_trade.trade_type == TradeType.LONG:
            required_price = base_trade.entry_price + (total_units * step_size)
            return market.current_price >= required_price
        else:  # SHORT
            required_price = base_trade.entry_price - (total_units * step_size)
            return market.current_price <= required_price
        
        return False
    
    def get_portfolio_heat(self) -> float:
        """Get current portfolio heat percentage"""
        return self.trading_service.portfolio.portfolio_heat
    
    def get_market_summary(self, symbol: str) -> Dict:
        """Get market data summary for display"""
        if symbol not in self.market_data:
            return {}
        
        market = self.market_data[symbol]
        return {
            'symbol': symbol,
            'current_price': market.current_price,
            'atr': market.atr,
            'high_20': market.high_20,
            'low_20': market.low_20,
            'high_55': market.high_55,
            'low_55': market.low_55,
            'breakout_20_long': market.current_price > market.high_20,
            'breakout_20_short': market.current_price < market.low_20,
            'breakout_55_long': market.current_price > market.high_55,
            'breakout_55_short': market.current_price < market.low_55,
            'last_trade_winner': market.last_trade_winner
        }