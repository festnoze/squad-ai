import pytest
import sys
import os
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pyshould import should

# Add the parent directory to sys.path to allow importing app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.managers.incoming_text_manager import IncomingTextManager
from app.managers.outgoing_text_manager import OutgoingTextManager
from app.agents.agents_graph import AgentsGraph
from app.managers.incoming_manager import IncomingManager
from app.managers.outgoing_manager import OutgoingManager
from app.terminal_events_handler import TerminalEventsHandler
from app.agents.phone_conversation_state_model import PhoneConversationState

@pytest.mark.asyncio
class TestTerminalEventsHandler:
    
    @pytest.mark.asyncio
    async def test_terminal_events_handler_integration_with_incoming_text_manager(self):
        """Test integration with TerminalEventsHandler."""
        
        # Mock dependencies needed by TerminalEventsHandler
        with patch('app.terminal_events_handler.StudiRAGInferenceApiClient'), \
             patch('app.terminal_events_handler.SalesforceApiClient'), \
             patch('app.terminal_events_handler.OutgoingTextManager'), \
             patch('app.terminal_events_handler.AgentsGraph'), \
             patch('app.terminal_events_handler.IncomingTextManager') as mock_incoming_text_manager_class, \
             patch('app.terminal_events_handler.OpenAI'):
            
            # Create a TerminalEventsHandler instance
            handler = TerminalEventsHandler()
            
            # Assert that IncomingTextManager was initialized
            mock_incoming_text_manager_class.assert_called_once()