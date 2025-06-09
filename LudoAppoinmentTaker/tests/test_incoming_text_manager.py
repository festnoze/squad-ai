import pytest
import sys
import os
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pyshould import should

# Add the parent directory to sys.path to allow importing app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.agents.agents_graph import AgentsGraph
from app.managers.incoming_text_manager import IncomingTextManager
from app.managers.outgoing_text_manager import OutgoingTextManager

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
        test_stream_sid = 'new_stream_sid'
        incoming_text_manager.set_stream_sid(test_stream_sid)
        
        # Assert stream SID was updated
        incoming_text_manager.stream_sid | should.equal(test_stream_sid)
        
        # Assert outgoing manager was notified
        incoming_text_manager.outgoing_manager.update_stream_sid.have_been_called_once_with(test_stream_sid)
    
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
    async def test_process_incoming_data_is_processing(self, incoming_text_manager : IncomingTextManager):
        """Test that process_incoming_data_async processes data when is_processing is True."""        
        # Arrange
        test_message = "Test message"
        
        # Act
        await incoming_text_manager.process_incoming_data_async(test_message)
        
        # Assert
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
        # Arrange
        incoming_text_manager.is_processing = True
        incoming_text_manager.agents_graph.ainvoke.side_effect = Exception("Test exception")
        
        # Act
        await incoming_text_manager.process_incoming_data_async("Test message")
        
        # Assert
        incoming_text_manager.agents_graph.ainvoke.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_process_incoming_data_with_different_user_input(self, incoming_text_manager : IncomingTextManager):
        """Test that process_incoming_data_async handles different user inputs correctly."""        
        # Test with empty input
        await incoming_text_manager.process_incoming_data_async("")
        # Test with very long input
        long_text = "A" * 1000  # 1000 character string
        await incoming_text_manager.process_incoming_data_async(long_text)
        # Test with special characters
        special_chars = "Test with special chars: !@#$%^&*()_+"
        await incoming_text_manager.process_incoming_data_async(special_chars)
        
        # Assert that agents_graph.ainvoke was called 3 times (once for each input)
        incoming_text_manager.agents_graph.ainvoke.call_count | should.equal(3)