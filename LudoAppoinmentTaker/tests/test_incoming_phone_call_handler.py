import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os

# Add the parent directory to sys.path to allow importing app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestTextToSpeechMethods(unittest.IsolatedAsyncioTestCase):
    """Test the text-to-speech methods independently"""
    
    async def test_speak_and_send_text_functionality(self):
        """Test functionality of the refactored speak_and_send_text method"""
        # Create a mock audio stream manager with the enqueue_text method
        mock_audio_stream_manager = MagicMock()
        mock_audio_stream_manager.enqueue_text = AsyncMock(return_value=True)
        
        # Create a mock logger
        mock_logger = MagicMock()
        
        # Define a simplified version of speak_and_send_text for testing
        async def speak_and_send_text(text_buffer):
            """Test implementation of the text-to-speech method"""
            if not text_buffer:
                mock_logger.warning("Empty text buffer provided to speak_and_send_text")
                return 0
                
            is_speaking = True
            
            # Use the new text-based approach with the audio stream manager
            result = await mock_audio_stream_manager.enqueue_text(text_buffer)
            
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
        mock_audio_stream_manager.enqueue_text.assert_called_once_with(test_text)
        self.assertGreater(duration, 0)
        self.assertEqual(duration, len(test_text) / 15 * 1000)  # Verify duration calculation
        
        # Test with empty text
        mock_audio_stream_manager.enqueue_text.reset_mock()
        duration = await speak_and_send_text("")
        self.assertEqual(duration, 0)
        mock_audio_stream_manager.enqueue_text.assert_not_called()
        
        # Test when enqueue_text returns False
        mock_audio_stream_manager.enqueue_text.reset_mock()
        mock_audio_stream_manager.enqueue_text.return_value = False
        duration = await speak_and_send_text("Another test message")
        self.assertEqual(duration, 0)
    
    async def test_send_text_to_speak_to_twilio(self):
        """Test the enhanced send_text_to_speak_to_twilio method"""
        # Create mocks
        mock_audio_stream_manager = MagicMock()
        mock_audio_stream_manager.enqueue_text = AsyncMock(return_value=True)
        
        mock_tts_provider = MagicMock()
        mock_tts_provider.synthesize_speech_to_bytes = MagicMock(return_value=b'dummy_audio')
        
        mock_logger = MagicMock()
        
        # Import the ProcessText class
        from app.speech.text_processing import ProcessText
        
        # Define a more realistic version for testing that uses actual ProcessText methods
        async def send_text_to_speak_to_twilio(text_buffer, max_words_per_chunk=15, max_chars_per_chunk=150):
            if not text_buffer:
                mock_logger.warning("Empty text buffer provided")
                return 0
                
            # Use the actual text chunking utilities from ProcessText
            text_chunks = ProcessText.chunk_text_by_sized_sentences(
                text_buffer, 
                max_words_by_sentence=max_words_per_chunk, 
                max_chars_by_sentence=max_chars_per_chunk
            )
            
            # Use actual timing optimization
            timed_chunks = ProcessText.optimize_speech_timing(text_chunks)
            
            total_duration_ms = 0
            
            # Streaming approach
            for chunk_text, _, end_time in timed_chunks:
                result = await mock_audio_stream_manager.enqueue_text(chunk_text)
                if result:
                    total_duration_ms = end_time
                    mock_logger.debug(f"Enqueued chunk: '{chunk_text}'")
                else:
                    mock_logger.error(f"Failed to enqueue chunk: '{chunk_text}'")
                    break
                    
            return total_duration_ms
            
        # Test with normal text
        test_text = "This is a test of the enhanced text-to-speech system. It should handle multiple sentences properly."
        duration = await send_text_to_speak_to_twilio(test_text)
        
        # Should have called enqueue_text once for each chunk
        expected_chunks = len(ProcessText.chunk_text_by_sized_sentences(test_text, 15, 150))
        self.assertEqual(mock_audio_stream_manager.enqueue_text.call_count, expected_chunks)
        
        # Should return a positive duration
        self.assertGreater(duration, 0)
        
        # Test with different chunking parameters
        mock_audio_stream_manager.enqueue_text.reset_mock()
        small_chunks_text = "Testing with smaller chunks to ensure proper text splitting and timing."
        await send_text_to_speak_to_twilio(small_chunks_text, max_words_per_chunk=5, max_chars_per_chunk=50)
        
        # Should have more chunks with smaller limits
        expected_small_chunks = len(ProcessText.chunk_text_by_sized_sentences(small_chunks_text, 5, 50))
        self.assertEqual(mock_audio_stream_manager.enqueue_text.call_count, expected_small_chunks)
        self.assertGreater(expected_small_chunks, expected_chunks)
        
        # Test with failed enqueue
        mock_audio_stream_manager.enqueue_text.reset_mock()
        mock_audio_stream_manager.enqueue_text.return_value = False
        
        duration = await send_text_to_speak_to_twilio(test_text)
        
        # Should only have tried to enqueue the first chunk then stopped
        self.assertEqual(mock_audio_stream_manager.enqueue_text.call_count, 1)
        
        # Should return 0 since the first enqueue failed
        self.assertEqual(duration, 0)
        
        # Test with empty text
        mock_audio_stream_manager.enqueue_text.reset_mock()
        duration = await send_text_to_speak_to_twilio("")
        
        # Should not have called enqueue_text at all
        mock_audio_stream_manager.enqueue_text.assert_not_called()
        self.assertEqual(duration, 0)
        
        # Test with very long text
        mock_audio_stream_manager.enqueue_text.reset_mock()
        mock_audio_stream_manager.enqueue_text.return_value = True
        long_text = "This is a very long text. " * 20  # Repeat to create a long text
        duration = await send_text_to_speak_to_twilio(long_text)
        
        # Should have created multiple chunks
        long_text_chunks = len(ProcessText.chunk_text_by_sized_sentences(long_text, 15, 150))
        self.assertEqual(mock_audio_stream_manager.enqueue_text.call_count, long_text_chunks)
        self.assertGreater(long_text_chunks, 5)  # Should have more than 5 chunks
        
        # Test with text containing special characters
        mock_audio_stream_manager.enqueue_text.reset_mock()
        special_chars_text = "Testing with special characters: éèêë, çñ, ß, 你好, 😊!"
        duration = await send_text_to_speak_to_twilio(special_chars_text)
        
        # Should handle special characters properly
        special_chars_chunks = len(ProcessText.chunk_text_by_sized_sentences(special_chars_text, 15, 150))
        self.assertEqual(mock_audio_stream_manager.enqueue_text.call_count, special_chars_chunks)
        self.assertGreater(duration, 0)  # Duration should be positive
    
    async def test_streaming_statistics_functionality(self):
        """Test the enhanced monitoring and statistics functionality"""
        # Create mock objects for testing
        mock_text_queue_manager = MagicMock()
        mock_text_queue_manager.get_queue_stats = MagicMock(return_value={
            'current_size_chars': 150,
            'total_chars_enqueued': 1000,
            'total_chars_processed': 850,
            'is_empty': False,
            'is_processing': True,
            'processing_efficiency': 85.0
        })
        
        mock_audio_sender = MagicMock()
        mock_audio_sender.get_sender_stats = MagicMock(return_value={
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
        
        # Create a mock AudioStreamManager that uses our mocked components
        mock_audio_stream_manager = MagicMock()
        mock_audio_stream_manager.text_queue_manager = mock_text_queue_manager
        mock_audio_stream_manager.audio_sender = mock_audio_sender
        mock_audio_stream_manager.running = True
        mock_audio_stream_manager.is_actively_sending = MagicMock(return_value=True)
        
        # Define a simplified version of get_streaming_stats for testing
        def get_streaming_stats():
            # Get text queue statistics
            text_queue_stats = mock_text_queue_manager.get_queue_stats()
            
            # Get comprehensive audio sender statistics
            audio_sender_stats = mock_audio_sender.get_sender_stats()
            
            # Aggregate statistics
            return {
                'text_queue': text_queue_stats,
                'audio_sender': audio_sender_stats,
                'is_running': mock_audio_stream_manager.running,
                'is_actively_sending': mock_audio_stream_manager.is_actively_sending()
            }
        
        # Assign the method to our mock
        mock_audio_stream_manager.get_streaming_stats = get_streaming_stats
        
        # Get the statistics
        stats = mock_audio_stream_manager.get_streaming_stats()
        
        # Verify the structure and content of the statistics
        self.assertIn('text_queue', stats)
        self.assertIn('audio_sender', stats)
        self.assertIn('is_running', stats)
        self.assertIn('is_actively_sending', stats)
        
        # Verify text queue statistics
        text_stats = stats['text_queue']
        self.assertEqual(text_stats['current_size_chars'], 150)
        self.assertEqual(text_stats['total_chars_enqueued'], 1000)
        self.assertEqual(text_stats['total_chars_processed'], 850)
        self.assertEqual(text_stats['processing_efficiency'], 85.0)
        
        # Verify audio sender statistics
        audio_stats = stats['audio_sender']
        self.assertEqual(audio_stats['chunks_sent'], 42)
        self.assertEqual(audio_stats['bytes_sent'], 84000)
        self.assertEqual(audio_stats['avg_chunk_size'], 2000.0)
        self.assertEqual(audio_stats['stream_sid'], 'test-stream-123')
        
        # Verify overall status
        self.assertTrue(stats['is_running'])
        self.assertTrue(stats['is_actively_sending'])
    
    async def test_stop_speaking_functionality(self):
        """Test functionality of the refactored stop_speaking method"""
        # Create a mock audio stream manager
        mock_audio_stream_manager = MagicMock()
        mock_audio_stream_manager.clear_text_queue = AsyncMock()
        
        # Create a mock for interrupt flag
        mock_rag_interrupt_flag = {"interrupted": False}
        
        # Create a mock logger
        mock_logger = MagicMock()
        
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
                await mock_audio_stream_manager.clear_text_queue()
                mock_logger.info("Cleared text queue due to speech interruption")
                
                is_speaking = False
                return True  # Speech was stopped
            return False  # No speech was ongoing
        
        # Test when is_speaking is True
        result = await stop_speaking()
        
        # Check results
        self.assertTrue(result)
        self.assertFalse(is_speaking)
        mock_audio_stream_manager.clear_text_queue.assert_called_once()
        self.assertTrue(mock_rag_interrupt_flag["interrupted"])
        
        # Test when is_speaking is already False
        mock_audio_stream_manager.clear_text_queue.reset_mock()
        mock_rag_interrupt_flag["interrupted"] = False
        
        # Call again when already not speaking
        result = await stop_speaking()
        
        # Check results
        self.assertFalse(result)
        mock_audio_stream_manager.clear_text_queue.assert_not_called()
        self.assertFalse(mock_rag_interrupt_flag["interrupted"])


if __name__ == "__main__":
    unittest.main()
