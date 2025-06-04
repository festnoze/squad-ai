import pytest
import sys
import os
import asyncio
from unittest.mock import Mock, AsyncMock, patch

# Add the parent directory to sys.path to allow importing app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.managers.incoming_text_manager import IncomingTextManager
from app.managers.outgoing_text_manager import OutgoingTextManager
from app.terminal_events_handler import TerminalEventsHandler

@pytest.mark.asyncio
class TestIncomingTextHandler:
    
    @pytest.fixture
    def setup_incoming_text_manager(self):
        """Fixture to create a mock IncomingTextManager with mocked dependencies."""
        # Create mocks
        mock_outgoing_manager = AsyncMock()
        mock_agents_graph = AsyncMock()
        call_sid = 'test_call_sid'
        
        # Create IncomingTextManager instance with mocked dependencies
        incoming_text_manager = IncomingTextManager(
            outgoing_manager=mock_outgoing_manager,
            agents_graph=mock_agents_graph,
            call_sid=call_sid
        )
        
        # Return the manager and its mocks for tests to use
        return {
            'incoming_text_manager': incoming_text_manager,
            'mock_outgoing_manager': mock_outgoing_manager,
            'mock_agents_graph': mock_agents_graph,
            'call_sid': call_sid
        }
    
    def test_incoming_text_manager_initialization(self, setup_incoming_text_manager):
        """Test that IncomingTextManager initializes correctly."""
        manager = setup_incoming_text_manager['incoming_text_manager']
        mock_outgoing_manager = setup_incoming_text_manager['mock_outgoing_manager']
        call_sid = setup_incoming_text_manager['call_sid']
        
        # Assert initial state
        assert manager.call_sid == call_sid
        assert manager.outgoing_manager == mock_outgoing_manager
        assert not manager.is_processing  # Should be initialized as False
    
    def test_set_stream_sid(self, setup_incoming_text_manager):
        """Test setting stream SID updates both the manager and its outgoing manager."""
        manager = setup_incoming_text_manager['incoming_text_manager']
        mock_outgoing_manager = setup_incoming_text_manager['mock_outgoing_manager']
        
        # Call the method with a new stream SID
        test_stream_sid = 'new_stream_sid'
        manager.set_stream_sid(test_stream_sid)
        
        # Assert stream SID was updated
        assert manager.stream_sid == test_stream_sid
        
        # Assert outgoing manager was notified
        mock_outgoing_manager.update_stream_sid.assert_called_once_with(test_stream_sid)
    
    def test_set_phone_number(self, setup_incoming_text_manager):
        """Test setting phone number correctly updates internal state."""
        manager = setup_incoming_text_manager['incoming_text_manager']
        
        # Call the method with a test phone number and stream SID
        test_phone = '+123456789'
        test_stream_sid = 'test_stream_sid'
        manager.set_phone_number(test_phone, test_stream_sid)
        
        # Assert phone number was stored
        assert manager.phone_number == test_phone
        assert manager.phones_by_call_sid[test_stream_sid] == test_phone
    
    @pytest.mark.asyncio
    async def test_process_incoming_data_not_processing(self, setup_incoming_text_manager):
        """Test that process_incoming_data_async doesn't process data when is_processing is False."""
        manager = setup_incoming_text_manager['incoming_text_manager']
        mock_agents_graph = setup_incoming_text_manager['mock_agents_graph']
        
        # Ensure is_processing is False (default)
        assert not manager.is_processing
        
        # Call the method with some text
        await manager.process_incoming_data_async("Test message")
        
        # Assert that agents_graph was not called
        mock_agents_graph.ainvoke.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_process_incoming_data_is_processing(self, setup_incoming_text_manager):
        """Test that process_incoming_data_async processes data when is_processing is True."""
        manager = setup_incoming_text_manager['incoming_text_manager']
        mock_agents_graph = setup_incoming_text_manager['mock_agents_graph']
        
        # Set is_processing to True
        manager.is_processing = True
        
        # Define expected data
        test_message = "Test message"
        
        # Call the method
        await manager.process_incoming_data_async(test_message)
        
        # Assert agents_graph was called with expected parameters
        mock_agents_graph.ainvoke.assert_called_once()
        call_args = mock_agents_graph.ainvoke.call_args[0][0]
        assert call_args['data'] == test_message
        assert call_args['type'] == 'text'
    
    @pytest.mark.asyncio
    async def test_process_incoming_data_exception(self, setup_incoming_text_manager):
        """Test that process_incoming_data_async handles exceptions gracefully."""
        manager = setup_incoming_text_manager['incoming_text_manager']
        mock_agents_graph = setup_incoming_text_manager['mock_agents_graph']
        
        # Set is_processing to True
        manager.is_processing = True
        
        # Make agents_graph.ainvoke raise an exception
        mock_agents_graph.ainvoke.side_effect = Exception("Test exception")
        
        # Call the method - should not raise an exception to the caller
        await manager.process_incoming_data_async("Test message")
        
        # Assert agents_graph was called
        mock_agents_graph.ainvoke.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_terminal_events_handler_integration(self):
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
    
    @pytest.mark.asyncio
    async def test_validation_of_user_input(self, setup_incoming_text_manager):
        """Test that input validation works correctly."""
        manager = setup_incoming_text_manager['incoming_text_manager']
        
        # Enable processing
        manager.is_processing = True
        
        # Test with empty input
        await manager.process_incoming_data_async("")
        # Test with very long input
        long_text = "A" * 1000  # 1000 character string
        await manager.process_incoming_data_async(long_text)
        # Test with special characters
        special_chars = "Test with special chars: !@#$%^&*()_+"
        await manager.process_incoming_data_async(special_chars)
        
        # Assert that agents_graph.ainvoke was called 3 times (once for each input)
        assert setup_incoming_text_manager['mock_agents_graph'].ainvoke.call_count == 3