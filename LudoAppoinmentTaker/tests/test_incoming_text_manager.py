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
class TestIncomingTextManager:
    
    @pytest.fixture
    def incoming_text_manager(self):
        """Fixture to create a mock IncomingTextManager with mocked dependencies."""
        # Create mocks
        self.mock_outgoing_manager = AsyncMock(spec=OutgoingTextManager)
        self.mock_agents_graph = AsyncMock()
        self.call_sid = 'test_call_sid'
        self.calling_phone_number = '+123456789'
        
        # Create IncomingTextManager instance with mocked dependencies
        incoming_text_manager = IncomingTextManager(
            outgoing_manager=self.mock_outgoing_manager,
            agents_graph=self.mock_agents_graph,
            call_sid=None
        )
        
        # Equivalent to "set_call_sid" call: avoid it to be counted as a test call
        incoming_text_manager.call_sid = self.call_sid
        incoming_text_manager.outgoing_manager.call_sid = self.call_sid
        incoming_text_manager.set_phone_number(self.calling_phone_number, self.call_sid)
        
        # Return the manager and its mocks for tests to use
        return incoming_text_manager
    
    def test_incoming_text_manager_initialization(self, incoming_text_manager : IncomingTextManager):
        """Test that IncomingTextManager initializes correctly."""
        
        # Assert initial state
        incoming_text_manager.call_sid | should.equal(self.call_sid)
        incoming_text_manager.outgoing_manager | should.equal(self.mock_outgoing_manager)
        incoming_text_manager.is_processing | should.be_false()  # Should be initialized as False
    
    def test_set_stream_sid(self, incoming_text_manager : IncomingTextManager):
        """Test setting stream SID updates both the manager and its outgoing manager."""
        
        # Call the method with a new stream SID
        test_call_sid = 'new_call_sid'
        incoming_text_manager.set_call_sid(test_call_sid)
        
        # Assert stream SID was updated
        incoming_text_manager.call_sid | should.equal(test_call_sid)
        
        # Assert outgoing manager was notified
        incoming_text_manager.outgoing_manager.update_call_sid.have_been_called_once_with(test_call_sid)
    
    def test_set_phone_number(self, incoming_text_manager  : IncomingTextManager):
        """Test setting phone number correctly updates internal state."""
        
        # Call the method with a test phone number and stream SID
        test_phone = '+123456789'
        test_stream_sid = 'test_stream_sid'
        incoming_text_manager.set_phone_number(test_phone, test_stream_sid)
        
        # Assert phone number was stored
        incoming_text_manager.phone_number | should.equal(test_phone)
        incoming_text_manager.phones_by_call_sid[test_stream_sid] | should.equal(test_phone)
    
    @pytest.mark.asyncio
    async def test_process_incoming_data_not_processing(self, incoming_text_manager : IncomingTextManager):
        """Test that process_incoming_data_async doesn't process data when is_processing is False."""
        
        # Ensure is_processing is False (default)
        incoming_text_manager.is_processing | should.be_false()
        
        # Call the method with some text
        await incoming_text_manager.process_incoming_data_async("Test message")
        
        # Assert that agents_graph was not called
        incoming_text_manager.agents_graph.ainvoke.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_process_incoming_data_is_processing(self, incoming_text_manager : IncomingTextManager):
        """Test that process_incoming_data_async processes data when is_processing is True."""
        
        # Set is_processing to True
        incoming_text_manager.is_processing = True
        
        # Define expected data
        test_message = "Test message"
        
        # Call the method
        await incoming_text_manager.process_incoming_data_async(test_message)
        
        # Assert agents_graph was called with expected parameters
        incoming_text_manager.agents_graph.ainvoke.have_been_called_once_with(test_message)
        state_graph = incoming_text_manager.agents_graph.ainvoke.call_args[0][0]

        state_graph['user_input'] | should.equal(test_message)
        #state_graph['phone_number'] | should.equal(incoming_text_manager.phones_by_call_sid[incoming_text_manager.call_sid])
        state_graph['call_sid'] | should.equal(incoming_text_manager.call_sid)
        state_graph['history'] | should.equal([])
        state_graph['agent_scratchpad'] | should.equal({})
    
    @pytest.mark.asyncio
    async def test_process_incoming_data_exception(self, incoming_text_manager : IncomingTextManager):
        """Test that process_incoming_data_async handles exceptions gracefully."""
        
        # Set is_processing to True
        incoming_text_manager.is_processing = True
        
        # Make agents_graph.ainvoke raise an exception
        incoming_text_manager.agents_graph.ainvoke.side_effect = Exception("Test exception")
        
        # Call the method - should not raise an exception to the caller
        await incoming_text_manager.process_incoming_data_async("Test message")
        
        # Assert agents_graph was called
        incoming_text_manager.agents_graph.ainvoke.assert_called_once()
        
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
    async def test_validation_of_user_input(self, incoming_text_manager : IncomingTextManager):
        """Test that input validation works correctly."""
        
        # Enable processing
        incoming_text_manager.is_processing = True
        
        # Test with empty input
        await incoming_text_manager.process_incoming_data_async("")
        # Test with very long input
        long_text = "A" * 1000  # 1000 character string
        await incoming_text_manager.process_incoming_data_async(long_text)
        # Test with special characters
        special_chars = "Test with special chars: !@#$%^&*()_+"
        await incoming_text_manager.process_incoming_data_async(special_chars)
        
        # Assert that agents_graph.ainvoke was called 3 times (once for each input)
        #incoming_text_manager.agents_graph.ainvoke.call_count | should.equal(3)
        assert incoming_text_manager.agents_graph.ainvoke.call_count == 3