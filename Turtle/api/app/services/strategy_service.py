"""Strategy management service."""

import json
import os
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from app.models.strategy import (
    StrategyConfig, StrategyRequest, StrategyResponse,
    BacktestRequest, BacktestResult, StrategyPerformance
)
from app.core.config import settings


class StrategyService:
    """Service for managing trading strategies."""
    
    def __init__(self):
        self.strategies_dir = Path(settings.STRATEGY_DATA_DIR)
        self.strategies_dir.mkdir(parents=True, exist_ok=True)
        self._strategies: dict = {}  # In-memory strategy cache
    
    async def list_strategies(self) -> List[StrategyConfig]:
        """List all available strategies."""
        try:
            strategies = []
            
            # Load from files
            for file_path in self.strategies_dir.glob("*.json"):
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                    strategy = StrategyConfig(**data)
                    strategies.append(strategy)
                    self._strategies[strategy.name] = strategy
                except Exception as e:
                    print(f"Error loading strategy {file_path}: {e}")
                    continue
            
            return strategies
        
        except Exception as e:
            raise Exception(f"Failed to list strategies: {str(e)}")
    
    async def get_strategy(self, strategy_name: str) -> Optional[StrategyConfig]:
        """Get strategy by name."""
        try:
            # Check cache first
            if strategy_name in self._strategies:
                return self._strategies[strategy_name]
            
            # Load from file
            file_path = self.strategies_dir / f"{strategy_name}.json"
            if not file_path.exists():
                return None
            
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            strategy = StrategyConfig(**data)
            self._strategies[strategy_name] = strategy
            return strategy
        
        except Exception as e:
            raise Exception(f"Failed to get strategy: {str(e)}")
    
    async def create_strategy(self, request: StrategyRequest) -> StrategyResponse:
        """Create a new strategy."""
        try:
            # Check if strategy already exists
            existing = await self.get_strategy(request.name)
            if existing:
                return StrategyResponse(
                    success=False,
                    message=f"Strategy '{request.name}' already exists"
                )
            
            # Create strategy config
            strategy = StrategyConfig(
                name=request.name,
                description=request.description,
                parameters=request.parameters,
                max_position_size=request.max_position_size,
                stop_loss_pct=request.stop_loss_pct,
                take_profit_pct=request.take_profit_pct,
                created_at=datetime.now()
            )
            
            # Save to file
            await self._save_strategy(strategy)
            
            # Update cache
            self._strategies[strategy.name] = strategy
            
            return StrategyResponse(
                success=True,
                message="Strategy created successfully",
                strategy=strategy
            )
        
        except Exception as e:
            return StrategyResponse(
                success=False,
                message=f"Failed to create strategy: {str(e)}"
            )
    
    async def update_strategy(self, strategy_name: str, request: StrategyRequest) -> StrategyResponse:
        """Update an existing strategy."""
        try:
            existing = await self.get_strategy(strategy_name)
            if not existing:
                return StrategyResponse(
                    success=False,
                    message=f"Strategy '{strategy_name}' not found"
                )
            
            # Update strategy
            updated_strategy = existing.copy()
            updated_strategy.description = request.description
            updated_strategy.parameters = request.parameters
            updated_strategy.max_position_size = request.max_position_size
            updated_strategy.stop_loss_pct = request.stop_loss_pct
            updated_strategy.take_profit_pct = request.take_profit_pct
            
            # Save to file
            await self._save_strategy(updated_strategy)
            
            # Update cache
            self._strategies[strategy_name] = updated_strategy
            
            return StrategyResponse(
                success=True,
                message="Strategy updated successfully",
                strategy=updated_strategy
            )
        
        except Exception as e:
            return StrategyResponse(
                success=False,
                message=f"Failed to update strategy: {str(e)}"
            )
    
    async def delete_strategy(self, strategy_name: str) -> bool:
        """Delete a strategy."""
        try:
            file_path = self.strategies_dir / f"{strategy_name}.json"
            if file_path.exists():
                file_path.unlink()
                
                # Remove from cache
                if strategy_name in self._strategies:
                    del self._strategies[strategy_name]
                
                return True
            return False
        
        except Exception as e:
            raise Exception(f"Failed to delete strategy: {str(e)}")
    
    async def activate_strategy(self, strategy_name: str) -> bool:
        """Activate a strategy."""
        try:
            strategy = await self.get_strategy(strategy_name)
            if not strategy:
                return False
            
            strategy.is_active = True
            await self._save_strategy(strategy)
            self._strategies[strategy_name] = strategy
            
            return True
        
        except Exception as e:
            raise Exception(f"Failed to activate strategy: {str(e)}")
    
    async def deactivate_strategy(self, strategy_name: str) -> bool:
        """Deactivate a strategy."""
        try:
            strategy = await self.get_strategy(strategy_name)
            if not strategy:
                return False
            
            strategy.is_active = False
            await self._save_strategy(strategy)
            self._strategies[strategy_name] = strategy
            
            return True
        
        except Exception as e:
            raise Exception(f"Failed to deactivate strategy: {str(e)}")
    
    async def backtest_strategy(self, strategy_name: str, request: BacktestRequest) -> BacktestResult:
        """Run strategy backtest."""
        try:
            strategy = await self.get_strategy(strategy_name)
            if not strategy:
                raise Exception(f"Strategy '{strategy_name}' not found")
            
            # Placeholder backtest implementation
            # This would integrate with the existing strategy engine
            result = BacktestResult(
                strategy_name=strategy_name,
                symbol=request.symbol,
                start_date=request.start_date,
                end_date=request.end_date,
                initial_balance=request.initial_balance,
                final_balance=request.initial_balance * 1.15,  # Placeholder
                total_return=15.0,  # Placeholder
                total_trades=25,
                winning_trades=15,
                losing_trades=10,
                win_rate=60.0,
                max_drawdown=8.5,
                sharpe_ratio=1.2
            )
            
            return result
        
        except Exception as e:
            raise Exception(f"Failed to run backtest: {str(e)}")
    
    async def get_strategy_performance(self, strategy_name: str) -> Optional[StrategyPerformance]:
        """Get strategy performance metrics."""
        try:
            strategy = await self.get_strategy(strategy_name)
            if not strategy:
                return None
            
            # Placeholder performance data
            performance = StrategyPerformance(
                strategy_name=strategy_name,
                total_signals=50,
                successful_signals=30,
                signal_accuracy=60.0,
                avg_return_per_trade=2.5,
                best_trade=12.3,
                worst_trade=-5.1,
                active_since=strategy.created_at,
                last_signal=datetime.now()
            )
            
            return performance
        
        except Exception as e:
            raise Exception(f"Failed to get strategy performance: {str(e)}")
    
    async def _save_strategy(self, strategy: StrategyConfig) -> None:
        """Save strategy to file."""
        file_path = self.strategies_dir / f"{strategy.name}.json"
        
        with open(file_path, 'w') as f:
            json.dump(strategy.dict(), f, indent=2, default=str)