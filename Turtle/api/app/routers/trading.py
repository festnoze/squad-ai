"""Trading operations API endpoints."""

from typing import List
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.models.trade import Trade, TradeRequest, TradeResponse
from app.models.strategy import TradingSignal
from app.services.trading_service import TradingService
from app.services.websocket_manager import WebSocketManager

router = APIRouter()
trading_service = TradingService()
websocket_manager = WebSocketManager()


@router.get("/trades", response_model=List[Trade])
async def get_trades(
    symbol: str = None,
    status: str = None,
    limit: int = 100
):
    """Get trades with optional filtering."""
    try:
        trades = await trading_service.get_trades(
            symbol=symbol,
            status=status,
            limit=limit
        )
        return trades
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades/{trade_id}", response_model=Trade)
async def get_trade(trade_id: str):
    """Get trade by ID."""
    try:
        trade = await trading_service.get_trade(trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found")
        return trade
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trades", response_model=TradeResponse)
async def create_trade(request: TradeRequest):
    """Create a new trade."""
    try:
        result = await trading_service.create_trade(request)
        
        # Notify WebSocket clients
        await websocket_manager.broadcast_trade_update(result.trade)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/trades/{trade_id}/close", response_model=TradeResponse)
async def close_trade(trade_id: str, exit_price: float = None):
    """Close an open trade."""
    try:
        result = await trading_service.close_trade(trade_id, exit_price)
        
        # Notify WebSocket clients
        await websocket_manager.broadcast_trade_update(result.trade)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/trades/{trade_id}")
async def cancel_trade(trade_id: str):
    """Cancel a pending trade."""
    try:
        success = await trading_service.cancel_trade(trade_id)
        if not success:
            raise HTTPException(status_code=404, detail="Trade not found")
        return {"message": "Trade cancelled successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals", response_model=List[TradingSignal])
async def get_signals(
    symbol: str = None,
    strategy: str = None,
    limit: int = 50
):
    """Get trading signals with optional filtering."""
    try:
        signals = await trading_service.get_signals(
            symbol=symbol,
            strategy=strategy,
            limit=limit
        )
        return signals
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals/process")
async def process_market_data(
    symbol: str,
    strategy_name: str = None
):
    """Process market data and generate trading signals."""
    try:
        signals = await trading_service.process_market_data(symbol, strategy_name)
        
        # Notify WebSocket clients
        for signal in signals:
            await websocket_manager.broadcast_signal(signal)
        
        return {"signals": signals, "count": len(signals)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_positions(symbol: str = None):
    """Get current positions."""
    try:
        positions = await trading_service.get_positions(symbol)
        return positions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time trading updates."""
    await websocket_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        print(f"Received message: {data}")
        websocket_manager.disconnect(websocket)


@router.post("/auto-trade/{strategy_name}")
async def enable_auto_trading(strategy_name: str, symbol: str):
    """Enable automatic trading for a strategy."""
    try:
        success = await trading_service.enable_auto_trading(strategy_name, symbol)
        return {"message": f"Auto-trading enabled for {strategy_name} on {symbol}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/auto-trade/{strategy_name}")
async def disable_auto_trading(strategy_name: str, symbol: str = None):
    """Disable automatic trading for a strategy."""
    try:
        success = await trading_service.disable_auto_trading(strategy_name, symbol)
        return {"message": f"Auto-trading disabled for {strategy_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))