"""Strategy management API endpoints."""

from typing import List
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.models.strategy import (
    StrategyConfig, StrategyRequest, StrategyResponse,
    BacktestRequest, BacktestResult, StrategyPerformance
)
from app.services.strategy_service import StrategyService

router = APIRouter()
strategy_service = StrategyService()


@router.get("/", response_model=List[StrategyConfig])
async def list_strategies():
    """List all available strategies."""
    try:
        strategies = await strategy_service.list_strategies()
        return strategies
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{strategy_name}", response_model=StrategyConfig)
async def get_strategy(strategy_name: str):
    """Get strategy by name."""
    try:
        strategy = await strategy_service.get_strategy(strategy_name)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return strategy
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=StrategyResponse)
async def create_strategy(request: StrategyRequest):
    """Create a new strategy."""
    try:
        result = await strategy_service.create_strategy(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{strategy_name}", response_model=StrategyResponse)
async def update_strategy(strategy_name: str, request: StrategyRequest):
    """Update an existing strategy."""
    try:
        result = await strategy_service.update_strategy(strategy_name, request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{strategy_name}")
async def delete_strategy(strategy_name: str):
    """Delete a strategy."""
    try:
        success = await strategy_service.delete_strategy(strategy_name)
        if not success:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return {"message": "Strategy deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{strategy_name}/activate")
async def activate_strategy(strategy_name: str):
    """Activate a strategy."""
    try:
        success = await strategy_service.activate_strategy(strategy_name)
        if not success:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return {"message": "Strategy activated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{strategy_name}/deactivate")
async def deactivate_strategy(strategy_name: str):
    """Deactivate a strategy."""
    try:
        success = await strategy_service.deactivate_strategy(strategy_name)
        if not success:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return {"message": "Strategy deactivated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{strategy_name}/backtest", response_model=BacktestResult)
async def backtest_strategy(strategy_name: str, request: BacktestRequest):
    """Run strategy backtest."""
    try:
        result = await strategy_service.backtest_strategy(strategy_name, request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{strategy_name}/performance", response_model=StrategyPerformance)
async def get_strategy_performance(strategy_name: str):
    """Get strategy performance metrics."""
    try:
        performance = await strategy_service.get_strategy_performance(strategy_name)
        if not performance:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return performance
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))