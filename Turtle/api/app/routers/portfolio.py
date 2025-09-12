"""Portfolio management API endpoints."""

from typing import List
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.models.portfolio import (
    Portfolio, PortfolioSummary, PortfolioRequest, PortfolioResponse,
    PositionSummary, PortfolioPerformance
)
from app.services.portfolio_service import PortfolioService

router = APIRouter()
portfolio_service = PortfolioService()


@router.get("/", response_model=List[Portfolio])
async def list_portfolios():
    """List all portfolios."""
    try:
        portfolios = await portfolio_service.list_portfolios()
        return portfolios
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{portfolio_id}", response_model=Portfolio)
async def get_portfolio(portfolio_id: str):
    """Get portfolio by ID."""
    try:
        portfolio = await portfolio_service.get_portfolio_from_file_async(portfolio_id)
        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        return portfolio
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=PortfolioResponse)
async def create_portfolio(request: PortfolioRequest):
    """Create a new portfolio."""
    try:
        result = await portfolio_service.create_portfolio_async(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(portfolio_id: str, request: PortfolioRequest):
    """Update portfolio settings."""
    try:
        result = await portfolio_service.update_portfolio(portfolio_id, request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{portfolio_id}")
async def delete_portfolio(portfolio_id: str):
    """Delete a portfolio."""
    try:
        success = await portfolio_service.delete_portfolio_async(portfolio_id)
        if not success:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        return {"message": "Portfolio deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{portfolio_id}/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(portfolio_id: str):
    """Get portfolio summary with key metrics."""
    try:
        summary = await portfolio_service.get_portfolio_summary(portfolio_id)
        if not summary:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{portfolio_id}/positions", response_model=List[PositionSummary])
async def get_portfolio_positions(portfolio_id: str):
    """Get portfolio positions."""
    try:
        positions = await portfolio_service.get_portfolio_positions(portfolio_id)
        return positions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{portfolio_id}/positions/{symbol}", response_model=PositionSummary)
async def get_position_summary(portfolio_id: str, symbol: str):
    """Get position summary for a specific symbol."""
    try:
        position = await portfolio_service.get_position_summary_async(portfolio_id, symbol)
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        return position
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{portfolio_id}/performance", response_model=PortfolioPerformance)
async def get_portfolio_performance(portfolio_id: str, days: int = 30):
    """Get portfolio performance metrics over time."""
    try:
        performance = await portfolio_service.get_portfolio_performance_async(portfolio_id, days)
        if not performance:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        return performance
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{portfolio_id}/reset")
async def reset_portfolio(portfolio_id: str):
    """Reset portfolio to initial state."""
    try:
        success = await portfolio_service.reset_portfolio_async(portfolio_id)
        if not success:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        return {"message": "Portfolio reset successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{portfolio_id}/update-balance")
async def update_portfolio_balance(
    portfolio_id: str,
    new_balance: float,
    currency: str = None
):
    """Update portfolio balance and currency."""
    try:
        success = await portfolio_service.update_balance_async(portfolio_id, new_balance, currency)
        if not success:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        return {"message": "Portfolio balance updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{portfolio_id}/risk-metrics")
async def get_risk_metrics(portfolio_id: str):
    """Get portfolio risk metrics."""
    try:
        metrics = await portfolio_service.get_risk_metrics_async(portfolio_id)
        if not metrics:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))