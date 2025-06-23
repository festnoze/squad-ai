import asyncio
import pytest
import logging
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import WebSocket

from speech.text_to_speech import TextToSpeechProvider
from speech.twilio_audio_sender import TwilioAudioSender
from managers.outgoing_audio_manager import OutgoingAudioManager

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)


async def test_all_chunks_processing():
    """Test that all chunks in the queue gets processed and sent."""
    # Arrange        
    audio_sender = MagicMock(spec=TwilioAudioSender)
    audio_sender.send_audio_chunk = AsyncMock(return_value=True)
    audio_sender.stream_sid = "mock_stream_sid"
    audio_sender.is_sending = False

    websocket = MagicMock(spec=WebSocket)
    tts_provider = MagicMock(spec=TextToSpeechProvider)
    mocked_synthesize_audio_bytes = b"mock_audio_bytes"
    tts_provider.synthesize_speech_to_bytes = MagicMock(return_value=mocked_synthesize_audio_bytes)
    outgoing_audio_manager = OutgoingAudioManager(websocket=websocket, tts_provider=tts_provider)
    outgoing_audio_manager.audio_sender = audio_sender
    
    sent_chunks = []
    async def mock_send_audio_chunk_async(audio_bytes):
        sent_chunks.append(audio_bytes)
        return True
    outgoing_audio_manager.audio_sender.send_audio_chunk_async = mock_send_audio_chunk_async
    
    original_synthesize = outgoing_audio_manager.synthesize_next_audio_chunk
    processed_chunks = []
    def mock_synthesize_next_audio_chunk():
        chunk = original_synthesize()
        if chunk:
            processed_chunks.append(chunk)  # Record the text chunk
        return chunk
    outgoing_audio_manager.synthesize_next_audio_chunk = mock_synthesize_next_audio_chunk
    
    # Act
    outgoing_audio_manager.run_background_streaming_worker()
    
    # Enqueue test text chunks
    await outgoing_audio_manager.enqueue_text("First test chunk.")
    await asyncio.sleep(0.3)  # Give time for processing
    
    await outgoing_audio_manager.enqueue_text("Last test chunk.")
    await asyncio.sleep(0.5)
    
    # Assert
    assert len(processed_chunks) == 2, "Expected 2 chunks to be processed"
    for processed_chunk in processed_chunks:
        assert processed_chunk == mocked_synthesize_audio_bytes, "processed chunk not equals to the mocked 'mock_audio_bytes'."
    
    assert len(sent_chunks) == 2, "Expected 2 chunks to be sent"
    for sent_chunk in sent_chunks:
        assert sent_chunk == mocked_synthesize_audio_bytes, "sent chunk not equals to the mocked 'mock_audio_bytes'."
    
    # Clean up
    await outgoing_audio_manager.stop_background_streaming_worker_async()


async def test_single_chunk_processing():
    """Test that a single chunk in the queue gets processed correctly."""
    # Arrange
    websocket = MagicMock(spec=WebSocket)
    tts_provider = MagicMock(spec=TextToSpeechProvider)
    mocked_synthesize_audio_bytes = b"mock_audio_bytes"
    tts_provider.synthesize_speech_to_bytes = MagicMock(return_value=mocked_synthesize_audio_bytes)
    outgoing_audio_manager = OutgoingAudioManager(websocket=websocket, tts_provider=tts_provider)
    #
    mock_audio_sender = MagicMock(spec=TwilioAudioSender)
    mock_audio_sender.send_audio_chunk = AsyncMock(return_value=True)
    mock_audio_sender.stream_sid = "mock_stream_sid"
    mock_audio_sender.is_sending = False
    outgoing_audio_manager.audio_sender = mock_audio_sender
    
    sent_chunks = []
    async def send_audio_chunk_async(audio_bytes):
        sent_chunks.append(audio_bytes)
        return True
        
    outgoing_audio_manager.audio_sender.send_audio_chunk_async = send_audio_chunk_async
    outgoing_audio_manager.run_background_streaming_worker()
    
    # Act
    await outgoing_audio_manager.enqueue_text("Single test chunk.")
    
    # Wait for processing to complete
    await asyncio.sleep(1)
    
    # Assertions
    assert len(sent_chunks) == 1, "Expected the single chunk to be sent"
    assert sent_chunks[0] == mocked_synthesize_audio_bytes, "sent chunk not equals to the mocked 'mock_audio_bytes'."
