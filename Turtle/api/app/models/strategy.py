"""Strategy and trading signal models."""

from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field
from .trade import TradeType


class SignalType(str, Enum):
    """Trading signal types."""
    ENTRY = "entry"
    EXIT = "exit"
    PYRAMID = "pyramid"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class TradingSignal(BaseModel):
    """Trading signal model."""
    
    id: str = Field(..., description="Signal identifier")
    symbol: str = Field(..., description="Trading symbol")
    signal_type: SignalType = Field(..., description="Signal type")
    trade_type: TradeType = Field(..., description="Trade direction")
    
    price: float = Field(..., gt=0, description="Signal price")
    confidence: float = Field(..., ge=0, le=1, description="Signal confidence (0-1)")
    quantity: float = Field(default=0, ge=0, description="Suggested quantity")
    
    reason: str = Field(..., description="Signal reasoning")
    timestamp: datetime = Field(..., description="Signal timestamp")
    strategy_name: str = Field(..., description="Strategy that generated signal")
    
    # Risk management
    stop_loss: Optional[float] = Field(default=None, description="Suggested stop loss")
    take_profit: Optional[float] = Field(default=None, description="Suggested take profit")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default={}, description="Additional signal data")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class StrategyConfig(BaseModel):
    """Strategy configuration model."""
    
    name: str = Field(..., description="Strategy name")
    description: str = Field(default="", description="Strategy description")
    version: str = Field(default="1.0.0", description="Strategy version")
    
    # Strategy parameters
    parameters: Dict[str, Any] = Field(default={}, description="Strategy parameters")
    
    # Entry rules
    entry_rules: List[str] = Field(default=[], description="Entry conditions")
    exit_rules: List[str] = Field(default=[], description="Exit conditions")
    
    # Risk management
    max_position_size: float = Field(default=0.1, description="Maximum position size (% of portfolio)")
    stop_loss_pct: float = Field(default=0.02, description="Stop loss percentage")
    take_profit_pct: float = Field(default=0.06, description="Take profit percentage")
    
    # Timeframes
    timeframes: List[str] = Field(default=["1d"], description="Supported timeframes")
    
    # Status
    is_active: bool = Field(default=True, description="Strategy active status")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class StrategyRequest(BaseModel):
    """Request model for strategy operations."""
    
    name: str = Field(..., description="Strategy name")
    description: str = Field(default="", description="Strategy description")
    parameters: Dict[str, Any] = Field(default={}, description="Strategy parameters")
    max_position_size: float = Field(default=0.1, ge=0, le=1, description="Max position size")
    stop_loss_pct: float = Field(default=0.02, ge=0, le=1, description="Stop loss percentage")
    take_profit_pct: float = Field(default=0.06, ge=0, le=1, description="Take profit percentage")


class StrategyResponse(BaseModel):
    """Response model for strategy operations."""
    
    success: bool = Field(..., description="Operation success")
    message: str = Field(default="", description="Response message")
    strategy: Optional[StrategyConfig] = Field(default=None, description="Strategy data")


class BacktestRequest(BaseModel):
    """Request model for strategy backtesting."""
    
    strategy_name: str = Field(..., description="Strategy to backtest")
    symbol: str = Field(..., description="Trading symbol")
    start_date: str = Field(..., description="Backtest start date")
    end_date: str = Field(..., description="Backtest end date")
    initial_balance: float = Field(default=100000, gt=0, description="Initial balance")
    parameters: Dict[str, Any] = Field(default={}, description="Strategy parameters override")


class BacktestResult(BaseModel):
    """Backtest result model."""
    
    strategy_name: str = Field(..., description="Strategy name")
    symbol: str = Field(..., description="Trading symbol")
    start_date: str = Field(..., description="Backtest start date")
    end_date: str = Field(..., description="Backtest end date")
    
    # Performance metrics
    initial_balance: float = Field(..., description="Initial balance")
    final_balance: float = Field(..., description="Final balance")
    total_return: float = Field(..., description="Total return percentage")
    
    # Trade statistics
    total_trades: int = Field(..., description="Total number of trades")
    winning_trades: int = Field(..., description="Winning trades")
    losing_trades: int = Field(..., description="Losing trades")
    win_rate: float = Field(..., description="Win rate percentage")
    
    # Risk metrics
    max_drawdown: float = Field(..., description="Maximum drawdown")
    sharpe_ratio: float = Field(..., description="Sharpe ratio")
    
    # Trade details
    trades: List[Any] = Field(default=[], description="Trade history")
    signals: List[TradingSignal] = Field(default=[], description="Generated signals")
    
    # Performance over time
    equity_curve: List[float] = Field(default=[], description="Equity curve")
    returns: List[float] = Field(default=[], description="Daily returns")
    dates: List[str] = Field(default=[], description="Corresponding dates")


class StrategyPerformance(BaseModel):
    """Strategy performance metrics."""
    
    strategy_name: str = Field(..., description="Strategy name")
    total_signals: int = Field(default=0, description="Total signals generated")
    successful_signals: int = Field(default=0, description="Successful signals")
    signal_accuracy: float = Field(default=0, description="Signal accuracy percentage")
    
    avg_return_per_trade: float = Field(default=0, description="Average return per trade")
    best_trade: float = Field(default=0, description="Best trade return")
    worst_trade: float = Field(default=0, description="Worst trade return")
    
    active_since: datetime = Field(..., description="Strategy active since")
    last_signal: Optional[datetime] = Field(default=None, description="Last signal timestamp")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }