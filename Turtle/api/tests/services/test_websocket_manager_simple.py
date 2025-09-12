"""Simple tests for WebSocketManager to verify basic functionality."""

import pytest
from unittest.mock import Mock, AsyncMock
import asyncio

from app.services.websocket_manager import WebSocketManager


class TestWebSocketManagerSimple:
    """Basic test cases for WebSocketManager."""
    
    def test_init(self):
        """Test manager initialization."""
        manager = WebSocketManager()
        assert len(manager.active_connections) == 0
        assert len(manager.subscriptions) == 0
        
    @pytest.mark.asyncio
    async def test_connect(self):
        """Test WebSocket connection."""
        manager = WebSocketManager()
        
        # Mock WebSocket
        mock_websocket = Mock()
        mock_websocket.accept = AsyncMock()
        
        await manager.connect(mock_websocket)
        
        mock_websocket.accept.assert_called_once()
        assert mock_websocket in manager.active_connections
        
    def test_disconnect(self):
        """Test WebSocket disconnection."""
        manager = WebSocketManager()
        
        # Mock WebSocket
        mock_websocket = Mock()
        manager.active_connections.append(mock_websocket)
        manager.subscriptions[mock_websocket] = {"trades", "signals"}
        
        manager.disconnect(mock_websocket)
        
        assert mock_websocket not in manager.active_connections
        assert mock_websocket not in manager.subscriptions
        
    def test_subscribe(self):
        """Test subscribing to topics."""
        manager = WebSocketManager()
        
        mock_websocket = Mock()
        topics = ["trades", "signals"]
        
        manager.subscribe(mock_websocket, topics)
        
        assert mock_websocket in manager.subscriptions
        assert manager.subscriptions[mock_websocket] == set(topics)
        
    def test_get_connection_count(self):
        """Test getting active connection count."""
        manager = WebSocketManager()
        
        assert manager.get_connection_count() == 0
        
        # Add some connections
        manager.active_connections.extend([Mock(), Mock(), Mock()])
        
        assert manager.get_connection_count() == 3
        
    @pytest.mark.asyncio
    async def test_broadcast_trade_update(self):
        """Test broadcasting trade updates."""
        manager = WebSocketManager()
        
        trade_data = {"id": "123", "symbol": "AAPL", "status": "filled"}
        
        # Should not raise exception even with no connections
        await manager.broadcast_trade_update(trade_data)