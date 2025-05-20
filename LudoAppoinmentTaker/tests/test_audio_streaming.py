import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os

# Add the parent directory to sys.path to allow importing app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.speech.audio_streaming import AudioStreamManager


class TestAudioStreamManager(unittest.IsolatedAsyncioTestCase):
    """Test cases for the AudioStreamManager class"""
    
    async def asyncSetUp(self):
        """Set up the test case"""
        # Create mock objects
        self.mock_websocket = MagicMock()
        self.mock_tts_provider = MagicMock()
        self.mock_tts_provider.synthesize_speech_to_bytes = MagicMock(return_value=b'dummy_audio_bytes' * 100)
        
        # Create the AudioStreamManager instance with mocks
        self.audio_stream_manager = AudioStreamManager(
            websocket=self.mock_websocket,
            tts_provider=self.mock_tts_provider,
            streamSid="test_stream_sid"
        )
        
        # Patch the send_audio_chunk method of audio_sender
        patcher = patch.object(self.audio_stream_manager.audio_sender, 'send_audio_chunk', new_callable=AsyncMock)
        self.mock_send_audio_chunk = patcher.start()
        self.mock_send_audio_chunk.return_value = True
        self.addAsyncCleanup(patcher.stop)
        
    async def test_enqueue_text(self):
        """Test enqueueing text to the AudioStreamManager"""
        # Test with valid text
        result = await self.audio_stream_manager.enqueue_text("Hello, this is a test")
        self.assertTrue(result)
        self.assertFalse(self.audio_stream_manager.text_queue_manager.is_empty())
        
        # Test with empty text
        result = await self.audio_stream_manager.enqueue_text("")
        self.assertFalse(result)
    
    async def test_clear_text_queue(self):
        """Test clearing the text queue"""
        # Add text to the queue
        await self.audio_stream_manager.enqueue_text("Text to be cleared")
        self.assertFalse(self.audio_stream_manager.text_queue_manager.is_empty())
        
        # Clear the queue
        await self.audio_stream_manager.clear_text_queue()
        self.assertTrue(self.audio_stream_manager.text_queue_manager.is_empty())
    
    async def test_is_actively_sending(self):
        """Test is_actively_sending method"""
        # When queue is empty and not running
        self.audio_stream_manager.running = False
        self.assertTrue(self.audio_stream_manager.text_queue_manager.is_empty())
        self.assertFalse(self.audio_stream_manager.is_actively_sending())
        
        # When queue has text but not running
        await self.audio_stream_manager.enqueue_text("Some text")
        self.assertFalse(self.audio_stream_manager.text_queue_manager.is_empty())
        self.assertTrue(self.audio_stream_manager.is_actively_sending())
        
        # When queue is empty but running
        await self.audio_stream_manager.clear_text_queue()
        self.audio_stream_manager.audio_sender.is_sending = True
        self.assertTrue(self.audio_stream_manager.is_actively_sending())
    
    async def test_streaming_text_to_speech(self):
        """Test the full text-to-speech streaming flow"""
        # Start streaming
        self.audio_stream_manager.start_streaming()
        self.assertTrue(self.audio_stream_manager.running)
        self.assertIsNotNone(self.audio_stream_manager.sender_task)
        
        # Enqueue some text
        test_text = "This is a test message for streaming."
        await self.audio_stream_manager.enqueue_text(test_text)
        
        # Give time for the streaming worker to process the text
        await asyncio.sleep(0.5)
        
        # Stop streaming
        await self.audio_stream_manager.stop_streaming()
        self.assertFalse(self.audio_stream_manager.running)
        
        # Verify TTS and send_audio_chunk were called
        self.mock_tts_provider.synthesize_speech_to_bytes.assert_called()
        self.mock_send_audio_chunk.assert_called()
    
    async def test_get_streaming_stats(self):
        """Test getting streaming statistics"""
        stats = self.audio_stream_manager.get_streaming_stats()
        
        self.assertIn("text_queue", stats)
        self.assertIn("audio_sender", stats)
        self.assertIn("running", stats)


if __name__ == "__main__":
    unittest.main()
