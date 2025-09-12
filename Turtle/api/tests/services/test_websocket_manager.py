"""Tests for WebSocketManager."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import asyncio
import json
from fastapi import WebSocket

from app.services.websocket_manager import WebSocketManager


class TestWebSocketManager:
    """Test cases for WebSocketManager."""
    
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
        mock_websocket = Mock(spec=WebSocket)
        mock_websocket.accept = AsyncMock()
        
        await manager.connect(mock_websocket)
        
        mock_websocket.accept.assert_called_once()
        assert mock_websocket in manager.active_connections
        
    def test_disconnect(self):
        """Test WebSocket disconnection."""
        manager = WebSocketManager()
        
        # Mock WebSocket
        mock_websocket = Mock(spec=WebSocket)
        manager.active_connections.append(mock_websocket)
        manager.subscriptions[mock_websocket] = {"trades", "signals"}
        
        manager.disconnect(mock_websocket)
        
        assert mock_websocket not in manager.active_connections
        assert mock_websocket not in manager.subscriptions
        
    @pytest.mark.asyncio
    async def test_send_personal_message(self):
        """Test sending personal message to specific connection."""
        manager = WebSocketManager()
        
        # Mock WebSocket
        mock_websocket = Mock(spec=WebSocket)
        mock_websocket.send_text = AsyncMock()
        
        message = {"type": "test", "data": "hello"}
        await manager.send_personal_message(message, mock_websocket)
        
        expected_json = json.dumps(message)
        mock_websocket.send_text.assert_called_once_with(expected_json)
        
    @pytest.mark.asyncio
    async def test_send_personal_message_error(self):
        """Test sending personal message with connection error."""
        manager = WebSocketManager()
        
        # Mock WebSocket that raises exception
        mock_websocket = Mock(spec=WebSocket)
        mock_websocket.send_text = AsyncMock(side_effect=Exception("Connection lost"))
        manager.active_connections.append(mock_websocket)
        
        message = {"type": "test", "data": "hello"}
        await manager.send_personal_message(message, mock_websocket)
        
        # Connection should be removed after error
        assert mock_websocket not in manager.active_connections
        
    @pytest.mark.asyncio
    async def test_broadcast(self):
        """Test broadcasting message to all connections."""
        manager = WebSocketManager()
        
        # Create mock connections
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_text = AsyncMock()
        mock_ws2 = Mock(spec=WebSocket)
        mock_ws2.send_text = AsyncMock()
        
        manager.active_connections.extend([mock_ws1, mock_ws2])
        
        message = {"type": "broadcast", "data": "hello all"}
        await manager.broadcast(message)
        
        expected_json = json.dumps(message)
        mock_ws1.send_text.assert_called_once_with(expected_json)
        mock_ws2.send_text.assert_called_once_with(expected_json)
        
    @pytest.mark.asyncio
    async def test_broadcast_to_subscribers(self):
        """Test broadcasting to specific subscribers."""
        manager = WebSocketManager()
        
        # Create mock connections with subscriptions
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_text = AsyncMock()
        mock_ws2 = Mock(spec=WebSocket)
        mock_ws2.send_text = AsyncMock()
        mock_ws3 = Mock(spec=WebSocket)
        mock_ws3.send_text = AsyncMock()
        
        manager.active_connections.extend([mock_ws1, mock_ws2, mock_ws3])
        manager.subscriptions[mock_ws1] = {"trades", "signals"}
        manager.subscriptions[mock_ws2] = {"signals"}
        manager.subscriptions[mock_ws3] = {"portfolio"}
        
        message = {"type": "trade_update", "data": "trade data"}
        await manager.broadcast_to_subscribers(message, topic="trades")
        
        expected_json = json.dumps(message)
        # Only mock_ws1 should receive the message (subscribed to trades)
        mock_ws1.send_text.assert_called_once_with(expected_json)
        mock_ws2.send_text.assert_not_called()
        mock_ws3.send_text.assert_not_called()
        
    @pytest.mark.asyncio
    async def test_broadcast_trade_update(self):
        """Test broadcasting trade updates."""
        manager = WebSocketManager()
        
        mock_websocket = Mock(spec=WebSocket)
        mock_websocket.send_text = AsyncMock()
        manager.active_connections.append(mock_websocket)
        manager.subscriptions[mock_websocket] = {"trades"}
        
        trade_data = {"id": "123", "symbol": "AAPL", "status": "filled"}
        
        with patch.object(manager, 'broadcast_to_subscribers') as mock_broadcast:
            await manager.broadcast_trade_update(trade_data)
            
            mock_broadcast.assert_called_once()
            call_args = mock_broadcast.call_args
            assert call_args[1]["topic"] == "trades"
            assert call_args[0][0]["type"] == "trade_update"
            assert call_args[0][0]["data"] == trade_data
            
    @pytest.mark.asyncio
    async def test_broadcast_signal(self):
        """Test broadcasting trading signals."""
        manager = WebSocketManager()
        
        signal_data = {"symbol": "AAPL", "signal": "BUY", "strength": 0.8}
        
        with patch.object(manager, 'broadcast_to_subscribers') as mock_broadcast:
            await manager.broadcast_signal(signal_data)
            
            mock_broadcast.assert_called_once()
            call_args = mock_broadcast.call_args
            assert call_args[1]["topic"] == "signals"
            assert call_args[0][0]["type"] == "trading_signal"
            assert call_args[0][0]["data"] == signal_data
            
    @pytest.mark.asyncio
    async def test_broadcast_portfolio_update(self):
        """Test broadcasting portfolio updates."""
        manager = WebSocketManager()
        
        portfolio_data = {"balance": 100000, "equity": 105000, "pnl": 5000}
        
        with patch.object(manager, 'broadcast_to_subscribers') as mock_broadcast:
            await manager.broadcast_portfolio_update(portfolio_data)
            
            mock_broadcast.assert_called_once()
            call_args = mock_broadcast.call_args
            assert call_args[1]["topic"] == "portfolio"
            assert call_args[0][0]["type"] == "portfolio_update"
            assert call_args[0][0]["data"] == portfolio_data
            
    def test_subscribe(self):
        """Test subscribing to topics."""
        manager = WebSocketManager()
        
        mock_websocket = Mock(spec=WebSocket)
        topics = ["trades", "signals"]
        
        manager.subscribe(mock_websocket, topics)
        
        assert mock_websocket in manager.subscriptions
        assert manager.subscriptions[mock_websocket] == set(topics)
        
    def test_unsubscribe(self):
        """Test unsubscribing from topics."""
        manager = WebSocketManager()
        
        mock_websocket = Mock(spec=WebSocket)
        manager.subscriptions[mock_websocket] = {"trades", "signals", "portfolio"}
        
        manager.unsubscribe(mock_websocket, ["trades"])
        
        assert manager.subscriptions[mock_websocket] == {"signals", "portfolio"}
        
    def test_unsubscribe_nonexistent(self):
        """Test unsubscribing from non-existent subscription."""
        manager = WebSocketManager()
        
        mock_websocket = Mock(spec=WebSocket)
        # No existing subscription
        
        # Should not raise exception
        manager.unsubscribe(mock_websocket, ["trades"])
        
    def test_get_connection_count(self):
        """Test getting active connection count."""
        manager = WebSocketManager()
        
        assert manager.get_connection_count() == 0
        
        # Add some connections
        manager.active_connections.extend([Mock(), Mock(), Mock()])
        
        assert manager.get_connection_count() == 3
        
    def test_get_subscription_count(self):
        """Test getting subscription count."""
        manager = WebSocketManager()
        
        mock_ws1 = Mock()
        mock_ws2 = Mock()
        
        manager.subscriptions[mock_ws1] = {"trades", "signals"}
        manager.subscriptions[mock_ws2] = {"portfolio"}
        
        assert manager.get_subscription_count("trades") == 1
        assert manager.get_subscription_count("signals") == 1  
        assert manager.get_subscription_count("portfolio") == 1
        assert manager.get_subscription_count("nonexistent") == 0