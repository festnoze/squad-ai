import asyncio
import pytest
from app.managers.outgoing_audio_manager import OutgoingAudioManager


# Define the fixture at the module level
@pytest.fixture
def fixture(mocker):
    """Set up the test fixture with mocked dependencies"""
    # Create mock objects
    mock_websocket = mocker.Mock()
    mock_tts_provider = mocker.Mock()
    mock_tts_provider.synthesize_speech_to_bytes_async = mocker.AsyncMock(return_value=b'dummy_audio_bytes' * 100)
    mock_tts_provider.text_queue_manager = mocker.Mock()
    mock_tts_provider.text_queue_manager.get_next_text_chunk_async = mocker.AsyncMock(return_value="dummy_text")
    
    # Create the OutgoingAudioManager instance with mocks websocket & TTS provider
    outgoing_audio_manager = OutgoingAudioManager(
        websocket=mock_websocket,
        tts_provider=mock_tts_provider,
        stream_sid="test_stream_sid"
    )
    
    # Patch the send_audio_chunk method of audio_sender
    outgoing_audio_manager.audio_sender.send_audio_chunk_async = mocker.AsyncMock(return_value=True)
    
    return {
        'websocket': mock_websocket,
        'tts_provider': mock_tts_provider,
        'outgoing_audio_manager': outgoing_audio_manager
    }


class TestOutgoingAudioManager:
    """Test cases for the OutgoingAudioManager class"""
    
    async def test_enqueue_text(self, fixture):
        """Test enqueueing text to the OutgoingAudioManager"""
        outgoing_audio_manager: OutgoingAudioManager = fixture['outgoing_audio_manager']
        
        # Test with valid text
        result = await outgoing_audio_manager.enqueue_text("Hello, this is a test")
        assert result is True
        assert outgoing_audio_manager.text_queue_manager.is_empty() is False
        
        # Test with empty text
        result = await outgoing_audio_manager.enqueue_text("")
        assert result is False
    
    
    async def test_clear_text_queue(self, fixture):
        """Test clearing the text queue"""
        outgoing_audio_manager: OutgoingAudioManager = fixture['outgoing_audio_manager']
        
        # Add text to the queue
        await outgoing_audio_manager.enqueue_text("Text to be cleared")
        assert outgoing_audio_manager.text_queue_manager.is_empty() is False
        
        # Clear the queue
        await outgoing_audio_manager.clear_text_queue()
        assert outgoing_audio_manager.text_queue_manager.is_empty() is True
    
    
    async def test_is_sending_speech(self, fixture):
        """Test is_sending_speech method"""
        outgoing_audio_manager: OutgoingAudioManager = fixture['outgoing_audio_manager']
        
        # When queue is empty and not running
        outgoing_audio_manager.running = False
        assert outgoing_audio_manager.text_queue_manager.is_empty() is True
        assert outgoing_audio_manager.has_text_to_be_sent() is False
        assert outgoing_audio_manager.is_sending() is False
        
        # When queue has text but not running
        await outgoing_audio_manager.enqueue_text("Text longer than min_chars_for_interruptible_speech value")
        assert outgoing_audio_manager.text_queue_manager.is_empty() is False
        assert outgoing_audio_manager.has_text_to_be_sent() is True
        assert outgoing_audio_manager.is_sending() is False
        
        # When queue is empty but running
        await outgoing_audio_manager.clear_text_queue()
        outgoing_audio_manager.audio_sender.is_sending = True
        assert outgoing_audio_manager.has_text_to_be_sent() is False
        assert outgoing_audio_manager.is_sending() is True
    
    
    async def test_streaming_text_to_speech(self, fixture):
        """Test the full text-to-speech streaming flow"""
        outgoing_audio_manager: OutgoingAudioManager = fixture['outgoing_audio_manager']
        
        # Start streaming
        outgoing_audio_manager.run_background_streaming_worker()
        assert outgoing_audio_manager.has_text_to_be_sent() is False
        assert outgoing_audio_manager.sender_task is not None
        
        # Enqueue some text
        test_text = "This is a test message for streaming."
        await outgoing_audio_manager.enqueue_text(test_text)
        assert outgoing_audio_manager.has_text_to_be_sent() is True
        
        # Give time for the streaming worker to process the text
        await asyncio.sleep(1)
        
        # Stop streaming
        await outgoing_audio_manager.stop_background_streaming_worker_async()
        assert outgoing_audio_manager.has_text_to_be_sent() is False
        
        # Verify TTS and send_audio_chunk were called
        outgoing_audio_manager.audio_sender.send_audio_chunk_async.assert_called()
    
    
    async def test_get_streaming_stats(self, fixture):
        """Test getting streaming statistics"""
        outgoing_audio_manager: OutgoingAudioManager = fixture['outgoing_audio_manager']
        
        stats = outgoing_audio_manager.get_streaming_stats()
        
        assert "text_queue" in stats
        assert "audio_sender" in stats
        assert "is_sending_speech" in stats

    
    async def test_run_stream_then_stop_audio_streaming_worker(self, fixture):
        """Test the async versions of run and stop background streaming worker"""
        outgoing_audio_manager: OutgoingAudioManager = fixture['outgoing_audio_manager']
        
        # Test running the worker asynchronously
        outgoing_audio_manager.run_background_streaming_worker()
        assert outgoing_audio_manager.sender_task is not None
        assert outgoing_audio_manager.has_text_to_be_sent() is False
        
        # Enqueue some text to test activity
        test_text = "Testing async streaming worker."
        await outgoing_audio_manager.enqueue_text(test_text)
        assert outgoing_audio_manager.has_text_to_be_sent() is True
        
        # Allow some time for processing
        await asyncio.sleep(0.5)
        assert outgoing_audio_manager.has_text_to_be_sent() is False
        
        # Test stopping the worker asynchronously
        await outgoing_audio_manager.stop_background_streaming_worker_async()
        assert outgoing_audio_manager.sender_task is None
        assert outgoing_audio_manager.has_text_to_be_sent() is False
        assert outgoing_audio_manager.ask_to_stop_streaming_worker is True
        
        # Verify the text queue was cleared
        assert outgoing_audio_manager.text_queue_manager.is_empty()
