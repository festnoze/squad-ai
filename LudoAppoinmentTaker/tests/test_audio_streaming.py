import asyncio
import pytest
from app.speech.audio_streaming import AudioStreamManager


# Define the fixture at the module level
@pytest.fixture
def fixture(mocker):
    """Set up the test fixture with mocked dependencies"""
    # Create mock objects
    mock_websocket = mocker.Mock()
    mock_tts_provider = mocker.Mock()
    mock_tts_provider.synthesize_speech_to_bytes = mocker.Mock(return_value=b'dummy_audio_bytes' * 100)
    mock_tts_provider.text_queue_manager = mocker.Mock()
    mock_tts_provider.text_queue_manager.get_next_text_chunk = mocker.Mock(return_value="dummy_text")
    
    # Create the AudioStreamManager instance with mocks
    audio_stream_manager = AudioStreamManager(
        websocket=mock_websocket,
        tts_provider=mock_tts_provider,
        streamSid="test_stream_sid"
    )
    
    # Patch the send_audio_chunk method of audio_sender
    audio_stream_manager.audio_sender.send_audio_chunk = mocker.AsyncMock(return_value=True)
    
    return {
        'websocket': mock_websocket,
        'tts_provider': mock_tts_provider,
        'audio_stream_manager': audio_stream_manager
    }

@pytest.mark.asyncio
class TestAudioStreamManager:
    """Test cases for the AudioStreamManager class"""
    
    @pytest.mark.asyncio
    async def test_enqueue_text(self, fixture):
        """Test enqueueing text to the AudioStreamManager"""
        audio_stream_manager: AudioStreamManager = fixture['audio_stream_manager']
        
        # Test with valid text
        result = await audio_stream_manager.enqueue_text("Hello, this is a test")
        assert result is True
        assert audio_stream_manager.text_queue_manager.is_empty() is False
        
        # Test with empty text
        result = await audio_stream_manager.enqueue_text("")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_clear_text_queue(self, fixture):
        """Test clearing the text queue"""
        audio_stream_manager: AudioStreamManager = fixture['audio_stream_manager']
        
        # Add text to the queue
        await audio_stream_manager.enqueue_text("Text to be cleared")
        assert audio_stream_manager.text_queue_manager.is_empty() is False
        
        # Clear the queue
        await audio_stream_manager.clear_text_queue()
        assert audio_stream_manager.text_queue_manager.is_empty() is True
    
    @pytest.mark.asyncio
    async def test_is_actively_sending(self, fixture):
        """Test is_actively_sending method"""
        audio_stream_manager: AudioStreamManager = fixture['audio_stream_manager']
        
        # When queue is empty and not running
        audio_stream_manager.running = False
        assert audio_stream_manager.text_queue_manager.is_empty() is True
        assert audio_stream_manager.is_sending_speech() is False
        
        # When queue has text but not running
        await audio_stream_manager.enqueue_text("Some text")
        assert audio_stream_manager.text_queue_manager.is_empty() is False
        assert audio_stream_manager.is_sending_speech() is True
        
        # When queue is empty but running
        await audio_stream_manager.clear_text_queue()
        audio_stream_manager.audio_sender.is_sending = True
        assert audio_stream_manager.is_sending_speech() is True
    
    @pytest.mark.asyncio
    async def test_streaming_text_to_speech(self, fixture):
        """Test the full text-to-speech streaming flow"""
        audio_stream_manager: AudioStreamManager = fixture['audio_stream_manager']
        
        # Start streaming
        audio_stream_manager.run_background_streaming_worker()
        assert audio_stream_manager.is_sending_speech() is False
        assert audio_stream_manager.sender_task is not None
        
        # Enqueue some text
        test_text = "This is a test message for streaming."
        await audio_stream_manager.enqueue_text(test_text)
        assert audio_stream_manager.is_sending_speech() is True
        
        # Give time for the streaming worker to process the text
        await asyncio.sleep(0.5)
        
        # Stop streaming
        await audio_stream_manager.stop_background_streaming_worker_async()
        assert audio_stream_manager.is_sending_speech() is False
        
        # Verify TTS and send_audio_chunk were called
        audio_stream_manager.audio_sender.send_audio_chunk.assert_called()
    
    @pytest.mark.asyncio
    async def test_get_streaming_stats(self, fixture):
        """Test getting streaming statistics"""
        audio_stream_manager: AudioStreamManager = fixture['audio_stream_manager']
        
        stats = audio_stream_manager.get_streaming_stats()
        
        assert "text_queue" in stats
        assert "audio_sender" in stats
        assert "is_sending_speech" in stats

    @pytest.mark.asyncio
    async def test_run_stream_then_stop_audio_streaming_worker(self, fixture):
        """Test the async versions of run and stop background streaming worker"""
        audio_stream_manager: AudioStreamManager = fixture['audio_stream_manager']
        
        # Test running the worker asynchronously
        audio_stream_manager.run_background_streaming_worker()
        assert audio_stream_manager.sender_task is not None
        assert audio_stream_manager.is_sending_speech() is False
        
        # Enqueue some text to test activity
        test_text = "Testing async streaming worker."
        await audio_stream_manager.enqueue_text(test_text)
        assert audio_stream_manager.is_sending_speech() is True
        
        # Allow some time for processing
        await asyncio.sleep(0.5)
        assert audio_stream_manager.is_sending_speech() is False
        
        # Test stopping the worker asynchronously
        await audio_stream_manager.stop_background_streaming_worker_async()
        assert audio_stream_manager.sender_task is None
        assert audio_stream_manager.is_sending_speech() is False
        assert audio_stream_manager.ask_to_stop_streaming_worker is True
        
        # Verify the text queue was cleared
        assert audio_stream_manager.text_queue_manager.is_empty()
