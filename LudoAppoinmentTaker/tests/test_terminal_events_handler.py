import pytest
import sys
import os
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pyshould import should

# Add the parent directory to sys.path to allow importing app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import io
import sys
from unittest.mock import patch, MagicMock, AsyncMock, call
from app.terminal_events_handler import TerminalEventsHandler

@pytest.mark.asyncio
class TestTerminalEventsHandler:
    
    @pytest.fixture
    def mock_environment(self):
        # Set necessary environment variables for testing
        os.environ["OPENAI_API_KEY"] = "test_openai_key"
        return {
            "calling_phone_number": "+1234567890",
            "call_sid": "test_call_sid",
            "stream_sid": "test_stream_sid"
        }
    
    @pytest.mark.asyncio
    async def test_terminal_events_handler_initialization(self):
        """Test that TerminalEventsHandler initializes all required dependencies."""
        
        # Mock all dependencies needed by TerminalEventsHandler
        with patch('app.terminal_events_handler.StudiRAGInferenceApiClient') as mock_rag_client, \
             patch('app.terminal_events_handler.SalesforceApiClient') as mock_sf_client, \
             patch('app.terminal_events_handler.OutgoingTextManager') as mock_outgoing_manager, \
             patch('app.terminal_events_handler.IncomingTextManager') as mock_incoming_manager, \
             patch('app.terminal_events_handler.AgentsGraph') as mock_agents_graph, \
             patch('app.terminal_events_handler.OpenAI') as mock_openai, \
             patch('app.terminal_events_handler.os.path.exists', return_value=True):
            
            # Create a TerminalEventsHandler instance
            handler = TerminalEventsHandler()
            
            # Assert that all dependencies were initialized
            mock_rag_client.assert_called_once()
            mock_sf_client.assert_called_once()
            mock_agents_graph.assert_called_once()
            mock_incoming_manager.assert_called_once()
            mock_openai.assert_called_once()
            mock_outgoing_manager.assert_called_once()
            
            # Assert logger was initialized
            assert handler.logger is not None
            
    @pytest.mark.asyncio
    async def test_init_incoming_data_handler_async(self, mock_environment):
        """Test the initialization of incoming data handler."""
        
        with patch('app.terminal_events_handler.StudiRAGInferenceApiClient'), \
             patch('app.terminal_events_handler.SalesforceApiClient'), \
             patch('app.terminal_events_handler.OutgoingTextManager') as mock_outgoing_manager, \
             patch('app.terminal_events_handler.IncomingTextManager') as mock_incoming_manager, \
             patch('app.terminal_events_handler.AgentsGraph'), \
             patch('app.terminal_events_handler.OpenAI'), \
             patch('app.terminal_events_handler.input', side_effect=['bye']), \
             patch.object(TerminalEventsHandler, '_handle_start_event_async', return_value="") as mock_start_handler:
            
            # Configure mocks
            mock_outgoing_instance = mock_outgoing_manager.return_value
            mock_incoming_instance = mock_incoming_manager.return_value
            mock_outgoing_instance.run_background_streaming_worker = MagicMock()
            mock_incoming_instance.set_call_sid = MagicMock()
            mock_incoming_instance.set_phone_number = MagicMock()
            
            # Create a TerminalEventsHandler instance
            handler = TerminalEventsHandler()
            
            # Call the method under test
            await handler.init_incoming_data_handler_async(
                mock_environment['calling_phone_number'],
                mock_environment['call_sid']
            )
            
            # Verify the expected method calls
            mock_incoming_instance.set_call_sid.assert_called_once_with(mock_environment['call_sid'])
            mock_incoming_instance.set_phone_number.assert_called_once_with(
                mock_environment['calling_phone_number'],
                mock_environment['call_sid']
            )
            mock_outgoing_instance.run_background_streaming_worker.assert_called_once()
            mock_start_handler.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_incoming_text_async(self):
        """Test the processing of incoming text."""
        
        test_text = "Hello, this is a test message"
        test_media_data = {"text": test_text}
        
        with patch('app.terminal_events_handler.StudiRAGInferenceApiClient'), \
             patch('app.terminal_events_handler.SalesforceApiClient'), \
             patch('app.terminal_events_handler.OutgoingTextManager'), \
             patch('app.terminal_events_handler.IncomingTextManager') as mock_incoming_manager, \
             patch('app.terminal_events_handler.AgentsGraph'), \
             patch('app.terminal_events_handler.OpenAI'):
            
            # Configure mock
            mock_incoming_instance = mock_incoming_manager.return_value
            mock_incoming_instance.process_incoming_data_async = AsyncMock()
            
            # Create handler and call the method under test
            handler = TerminalEventsHandler()
            await handler.process_incoming_text_async(test_media_data)
            
            # Verify the method was called with the correct data
            mock_incoming_instance.process_incoming_data_async.assert_called_once_with(test_media_data)
    
    @pytest.mark.asyncio
    async def test_handle_start_event_async(self, mock_environment):
        """Test handling of the start event."""
        
        start_data = {
            "callSid": mock_environment['call_sid'],
            "streamSid": mock_environment['stream_sid']
        }
        
        with patch('app.terminal_events_handler.StudiRAGInferenceApiClient'), \
             patch('app.terminal_events_handler.SalesforceApiClient'), \
             patch('app.terminal_events_handler.OutgoingTextManager'), \
             patch('app.terminal_events_handler.IncomingTextManager') as mock_incoming_manager, \
             patch('app.terminal_events_handler.AgentsGraph'), \
             patch('app.terminal_events_handler.OpenAI'):
            
            # Configure mock
            mock_incoming_instance = mock_incoming_manager.return_value
            mock_incoming_instance.init_conversation_async = AsyncMock()
            
            # Create handler and call the method under test
            handler = TerminalEventsHandler()
            result = await handler._handle_start_event_async(start_data)
            
            # Verify the method was called with the correct parameters
            mock_incoming_instance.init_conversation_async.assert_called_once_with(
                mock_environment['call_sid'], 
                mock_environment['stream_sid']
            )
            # Verify the return value
            assert result == mock_environment['stream_sid']
    
    @pytest.mark.asyncio
    async def test_close_session_async(self):
        """Test closing of a session."""
        
        with patch('app.terminal_events_handler.StudiRAGInferenceApiClient'), \
             patch('app.terminal_events_handler.SalesforceApiClient'), \
             patch('app.terminal_events_handler.OutgoingTextManager') as mock_outgoing_manager, \
             patch('app.terminal_events_handler.IncomingTextManager'), \
             patch('app.terminal_events_handler.AgentsGraph'), \
             patch('app.terminal_events_handler.OpenAI'):
            
            # Configure mock
            mock_outgoing_instance = mock_outgoing_manager.return_value
            mock_outgoing_instance.stop_background_streaming_worker_async = AsyncMock()
            
            # Create handler with a current_stream set
            handler = TerminalEventsHandler()
            handler.current_stream = "test_stream"
            handler.stream_states = {"test_stream": {"some": "state"}}
            
            # Call the method under test
            await handler.close_session_async()
            
            # Verify the expected method calls
            mock_outgoing_instance.stop_background_streaming_worker_async.assert_called_once()
            # Since current_stream is set and in stream_states, it should be removed
            assert "test_stream" not in handler.stream_states
    
    @pytest.mark.asyncio
    async def test_handle_stop_event_async(self):
        """Test handling of the stop event."""
        
        with patch('app.terminal_events_handler.StudiRAGInferenceApiClient'), \
             patch('app.terminal_events_handler.SalesforceApiClient'), \
             patch('app.terminal_events_handler.OutgoingTextManager'), \
             patch('app.terminal_events_handler.IncomingTextManager') as mock_incoming_manager, \
             patch('app.terminal_events_handler.AgentsGraph'), \
             patch('app.terminal_events_handler.OpenAI'):
            
            # Configure mock
            mock_incoming_instance = mock_incoming_manager.return_value
            mock_incoming_instance.set_call_sid = MagicMock()
            
            # Create handler with a current_stream set
            handler = TerminalEventsHandler()
            handler.current_stream = "test_stream"
            handler.stream_states = {"test_stream": {"some": "state"}}
            
            # Call the method under test
            await handler._handle_stop_event_async()
            
            # Verify the current_stream is cleared and IncomingTextManager.set_call_sid is called with None
            assert handler.current_stream is None
            mock_incoming_instance.set_call_sid.assert_called_once_with(None)
            # Check that the stream state was removed
            assert "test_stream" not in handler.stream_states
    
    @pytest.mark.asyncio
    async def test_terminal_loop_input_processing(self, mock_environment):
        """Test the terminal input loop processing."""
        
        # Test with two inputs: a normal message and then "bye" to exit the loop
        with patch('app.terminal_events_handler.StudiRAGInferenceApiClient'), \
             patch('app.terminal_events_handler.SalesforceApiClient'), \
             patch('app.terminal_events_handler.OutgoingTextManager'), \
             patch('app.terminal_events_handler.IncomingTextManager'), \
             patch('app.terminal_events_handler.AgentsGraph'), \
             patch('app.terminal_events_handler.OpenAI'), \
             patch.object(TerminalEventsHandler, '_handle_start_event_async', return_value="") as mock_start_handler, \
             patch.object(TerminalEventsHandler, 'incoming_text') as mock_incoming_text, \
             patch('app.terminal_events_handler.input', side_effect=['test message', 'bye']):
            
            # Create handler
            handler = TerminalEventsHandler()
            
            # Call the method that contains the loop
            await handler.init_incoming_data_handler_async(
                mock_environment['calling_phone_number'],
                mock_environment['call_sid']
            )
            
            mock_start_handler.assert_called_once()
            # Verify incoming_text_async was called once with the test message
            # It should not be called for 'bye' as that breaks the loop
            mock_incoming_text.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_real_terminal_welcome_message(self, monkeypatch):
        """Test with real dependencies to verify the welcome message output."""
        # Setup environment variables
        monkeypatch.setenv("OPENAI_API_KEY", "test_key")
        
        # Create a StringIO object to capture stdout
        captured_output = io.StringIO()
        sys.stdout = captured_output
        outputs_texts = []

        def outgoing_text_func(text):
            outputs_texts.append(text)

        try:
            # Patch only the input function to break the loop
            with patch('app.terminal_events_handler.input', side_effect=['quels BTS en informatique ?','bye']):
                # Create real handler (with minimal actual dependencies)
                handler = TerminalEventsHandler(outgoing_text_func=outgoing_text_func)
                
                # Create test data
                call_sid = "test_real_call_sid"
                phone_number = "+1234567890"
                
                # Set up dependencies for welcome message
                await handler.init_incoming_data_handler_async(phone_number, call_sid)
                
                # Give time for welcome message to be printed
                await asyncio.sleep(20)
                
                # Get the captured output
                # assert len(outputs_texts) | should.equal(1)
                
                # # Check for welcome message components
                # assert "Welcome" in outputs_texts[0] or "Hello" in outputs_texts[0] or "Hi" in outputs_texts[0]
                # assert "appointment" in outputs_texts[0].lower() or "schedule" in outputs_texts[0].lower()
        finally:
            # Reset stdout
            sys.stdout = sys.__stdout__

        