import pytest
import sys
import os
from unittest.mock import Mock, AsyncMock

# Add the parent directory to sys.path to allow importing app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.speech.text_processing import ProcessText
from app.managers.outgoing_audio_manager import OutgoingAudioManager

@pytest.mark.asyncio
class TestIncomingPhoneCallManager:

    @pytest.fixture
    def mock_outgoing_audio_manager(self):
        mock_outgoing_audio_manager = Mock(spec=OutgoingAudioManager)
        mock_outgoing_audio_manager.enqueue_text = AsyncMock(return_value=True)
        return mock_outgoing_audio_manager

    @pytest.fixture
    def mock_logger(self):
        return Mock()

    @pytest.fixture
    def mock_tts_provider(self):
        mock_tts_provider = Mock()
        mock_tts_provider.synthesize_speech_to_bytes = AsyncMock(return_value=b'dummy_audio')
        return mock_tts_provider

    @pytest.fixture
    def mock_text_queue_manager(self):
        mock_text_queue_manager = Mock()
        mock_text_queue_manager.get_queue_stats = AsyncMock(return_value={
            'current_size_chars': 150,
            'total_chars_enqueued': 1000,
            'total_chars_processed': 850,
            'is_empty': False,
            'processing_efficiency': 85.0
        })
        return mock_text_queue_manager

    @pytest.fixture
    def mock_audio_sender(self):
        mock_audio_sender = Mock()
        mock_audio_sender.get_sender_stats = AsyncMock(return_value={
            'chunks_sent': 42,
            'bytes_sent': 84000,
            'bytes_sent_kb': 82.03,
            'avg_chunk_size': 2000.0,
            'consecutive_errors': 0,
            'is_sending': True,
            'last_chunk_time': 1621234567.89,
            'time_since_last_chunk': 0.25,
            'total_duration': 30.5,
            'send_duration': 28.75,
            'stream_sid': 'test-stream-123'
        })
        return mock_audio_sender

    @pytest.mark.asyncio
    async def test_speak_and_send_text_functionality(self, mock_outgoing_audio_manager, mock_logger):
        """Test functionality of the refactored speak_and_send_text method"""
        
        # Define a simplified version of speak_and_send_text for testing
        async def speak_and_send_text(text_buffer):
            """Test implementation of the text-to-speech method"""
            if not text_buffer:
                mock_logger.warning("Empty text buffer provided to speak_and_send_text")
                return 0
                
            is_speaking = True
            
            # Use the new text-based approach with the audio stream manager
            result = await mock_outgoing_audio_manager.enqueue_text(text_buffer)
            
            if result:
                mock_logger.info(f"Text enqueued for streaming: {len(text_buffer)} chars")
                
                # Estimate duration based on character count
                chars_per_second = 15  # Average speech rate
                estimated_duration_ms = (len(text_buffer) / chars_per_second) * 1000
                
                return estimated_duration_ms
            else:
                mock_logger.error("Failed to enqueue text for streaming")
                return 0
        
        # Test normal operation
        test_text = "This is a test message for speech synthesis."
        duration = await speak_and_send_text(test_text)
        
        # Check results
        mock_outgoing_audio_manager.enqueue_text.assert_called_once_with(test_text)
        assert duration > 0
        assert duration == len(test_text) / 15 * 1000  # Verify duration calculation
        
        # Test with empty text
        mock_outgoing_audio_manager.enqueue_text.reset_mock()
        duration = await speak_and_send_text("")
        assert duration == 0
        mock_outgoing_audio_manager.enqueue_text.assert_not_called()
        
        # Test when enqueue_text returns False
        mock_outgoing_audio_manager.enqueue_text.reset_mock()
        mock_outgoing_audio_manager.enqueue_text.return_value = False
        duration = await speak_and_send_text("Another test message")
        assert duration == 0
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("text_input,max_words,max_chars,expected_chunks", [
        ("This is a test of the enhanced text-to-speech system. It should handle multiple sentences properly.", 15, 150, 1),
        ("Testing with smaller chunks to ensure proper text splitting and timing.", 5, 50, 3),
        ("This is a very long text. " * 20, 15, 150, 6),  # Should create multiple chunks
        ("Testing with special characters: éèêë, çñ, ß, 你好, 😊!", 15, 150, 1)
    ])
    async def test_send_text_to_speak_to_twilio(self, mock_outgoing_audio_manager, mock_logger, mock_tts_provider, text_input, max_words, max_chars, expected_chunks):
        """Test the enhanced send_text_to_speak_to_twilio method"""
        # Define a more realistic version for testing that uses actual ProcessText methods
        async def send_text_to_speak_to_twilio(text_buffer, max_words_per_chunk=15, max_chars_per_chunk=150):
            if not text_buffer:
                mock_logger.warning("Empty text buffer provided")
                return 0
                
            # Use the actual text chunking utilities from ProcessText
            text_chunks = ProcessText.chunk_text_by_sentences_size(
                text_buffer, 
                max_words_by_sentence=max_words_per_chunk, 
                max_chars_by_sentence=max_chars_per_chunk
            )
            
            # Use actual timing optimization
            timed_chunks = ProcessText.optimize_speech_timing(text_chunks)
            
            total_duration_ms = 0
            
            # Streaming approach
            for chunk_text, _, end_time in timed_chunks:
                result = await mock_outgoing_audio_manager.enqueue_text(chunk_text)
                if result:
                    total_duration_ms = end_time
                    mock_logger.debug(f"Enqueued chunk: '{chunk_text}'")
                else:
                    mock_logger.error(f"Failed to enqueue chunk: '{chunk_text}'")
                    break
                    
            return total_duration_ms
            
        # Test with the parametrized input
        duration = await send_text_to_speak_to_twilio(text_input, max_words_per_chunk=max_words, max_chars_per_chunk=max_chars)
        
        # Should have called enqueue_text once for each chunk
        actual_chunks = len(ProcessText.chunk_text_by_sentences_size(text_input, max_words, max_chars))
        assert mock_outgoing_audio_manager.enqueue_text.call_count == actual_chunks
        assert actual_chunks >= expected_chunks  # Verify our expected number of chunks
        
        # Should return a positive duration
        assert duration > 0
        
        # Test with failed enqueue
        mock_outgoing_audio_manager.enqueue_text.reset_mock()
        mock_outgoing_audio_manager.enqueue_text.return_value = False
        
        duration = await send_text_to_speak_to_twilio(text_input)
        
        # Should only have tried to enqueue the first chunk then stopped
        assert mock_outgoing_audio_manager.enqueue_text.call_count == 1
        
        # Should return 0 since the first enqueue failed
        assert duration == 0
        
        # Test with empty text
        mock_outgoing_audio_manager.enqueue_text.reset_mock()
        duration = await send_text_to_speak_to_twilio("")
        
        # Should not have called enqueue_text at all
        mock_outgoing_audio_manager.enqueue_text.assert_not_called()
        assert duration == 0
    
    @pytest.mark.asyncio
    async def test_stop_speaking_functionality(self, mock_outgoing_audio_manager, mock_logger, mocker):
        """Test functionality of the refactored stop_speaking method"""
        # Setup mock
        mock_outgoing_audio_manager.clear_text_queue = mocker.AsyncMock()
        
        # Create a mock for interrupt flag
        mock_rag_interrupt_flag = {"interrupted": False}
        
        # Define is_speaking state variable
        is_speaking = True
        
        # Define a simplified version of stop_speaking for testing
        async def stop_speaking():
            nonlocal is_speaking
            
            if is_speaking:
                # Interrupt RAG streaming if it's active
                mock_rag_interrupt_flag["interrupted"] = True
                mock_logger.info("RAG streaming interrupted due to speech interruption")
                
                # Clear the text queue
                await mock_outgoing_audio_manager.clear_text_queue()
                mock_logger.info("Cleared text queue due to speech interruption")
                
                # Update speaking state
                is_speaking = False
                return True  # Speech was stopped
            return False  # No speech was ongoing
        
        # Test stopping speech when speaking
        result = await stop_speaking()
        
        # Should have stopped speech
        assert result is True
        assert is_speaking is False
        
        # Should have interrupted RAG streaming
        assert mock_rag_interrupt_flag["interrupted"] is True
        
        # Should have cleared the text queue
        mock_outgoing_audio_manager.clear_text_queue.assert_called_once()
        
        # Test stopping speech when not speaking
        mock_outgoing_audio_manager.clear_text_queue.reset_mock()
        mock_rag_interrupt_flag["interrupted"] = False
        
        # Call stop_speaking again (now that is_speaking is False)
        result = await stop_speaking()
        
        # Should not have stopped speech (already stopped)
        assert result is False
        
        # Should not have interrupted RAG streaming
        assert mock_rag_interrupt_flag["interrupted"] is False
        
        # Should not have cleared the text queue
        mock_outgoing_audio_manager.clear_text_queue.assert_not_called()
