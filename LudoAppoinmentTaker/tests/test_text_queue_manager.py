import asyncio
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
from parameterized import parameterized

# Add the parent directory to sys.path to allow importing app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.speech.text_queue_manager import TextQueueManager


class TestTextQueueManager(unittest.IsolatedAsyncioTestCase):
    """Test cases for the TextQueueManager class"""
    
    async def asyncSetUp(self):
        """Set up the test case"""
        self.text_queue_manager = TextQueueManager()
    
    @parameterized.expand([
        (["This is a test message.", "Another part.", "And a third part."],),
        (["Hello world!", "This is another test.", "With three parts."],),
        (["A short text.", "With some punctuation,", "commas, and a period."],)
    ])
    async def test_enqueue_text(self, texts_to_add):
        """Test enqueueing multiple text chunks to the queue"""
        # Reset the queue for each test case
        await self.text_queue_manager.clear_queue()
        self.text_queue_manager.total_enqueued_chars = 0
        
        # Track expected values
        total_expected_length = 0
        expected_combined_text = ""
        
        # Process each text chunk in the list
        for text in texts_to_add:
            # Measure the length of this chunk
            chunk_length = len(text)
            total_expected_length += chunk_length
            expected_combined_text += text
            
            # Enqueue the text chunk
            result = await self.text_queue_manager.enqueue_text(text)
            
            # Verify the chunk was correctly enqueued
            self.assertTrue(result, f"Enqueue should return True for valid text: '{text}'")
            
        # Verify the final state after all chunks are added
        self.assertEqual(self.text_queue_manager.text_queue, expected_combined_text, 
                       f"Queue content mismatch for dataset with texts: {texts_to_add}")
        self.assertEqual(self.text_queue_manager.total_enqueued_chars, total_expected_length, 
                       f"Character count mismatch for dataset with texts: {texts_to_add}")
    
    async def test_enqueue_empty_text(self):
        """Test that enqueueing empty text returns False"""
        result = await self.text_queue_manager.enqueue_text("")
        self.assertFalse(result, "Enqueue should return False for empty text")
    
    async def test_get_text_chunk_sentence_end(self):
        """Test getting a text chunk that ends with a sentence"""
        # Enqueue text with a sentence end
        await self.text_queue_manager.enqueue_text("This is a short sentence. This is another sentence.")
        
        # Get a chunk - should return the first sentence
        chunk, duration = await self.text_queue_manager.get_text_chunk()
        self.assertEqual(chunk, "This is a short sentence.")
        self.assertTrue(duration > 0, "Duration should be greater than 0")
        
        # Queue should now only contain the second sentence
        self.assertEqual(self.text_queue_manager.text_queue, "This is another sentence.")
    
    async def test_get_text_chunk_word_limit(self):
        """Test getting a text chunk based on word limit"""
        # Enqueue text with more than 10 words but no sentence end
        await self.text_queue_manager.enqueue_text("One two three four five six seven eight nine ten eleven twelve thirteen")
        
        # Get a chunk - should return the first 10 words
        chunk, duration = await self.text_queue_manager.get_text_chunk()
        self.assertEqual(chunk, "One two three four five six seven eight nine ten")
        
        # Queue should now only contain the remaining words
        self.assertEqual(self.text_queue_manager.text_queue, "eleven twelve thirteen")
    
    async def test_get_text_chunk_empty_queue(self):
        """Test getting a chunk from an empty queue"""
        # Queue is empty
        chunk, duration = await self.text_queue_manager.get_text_chunk()
        self.assertEqual(chunk, "")
        self.assertEqual(duration, 0)
    
    async def test_is_empty(self):
        """Test is_empty method"""
        self.assertTrue(self.text_queue_manager.is_empty(), "Queue should be empty initially")
        
        await self.text_queue_manager.enqueue_text("Some text")
        self.assertFalse(self.text_queue_manager.is_empty(), "Queue should not be empty after enqueuing")
        
        await self.text_queue_manager.get_text_chunk()
        self.assertTrue(self.text_queue_manager.is_empty(), "Queue should be empty after getting all text")
    
    async def test_clear_queue(self):
        """Test clearing the queue"""
        await self.text_queue_manager.enqueue_text("Text to be cleared")
        await self.text_queue_manager.clear_queue()
        self.assertEqual(self.text_queue_manager.text_queue, "")
        self.assertTrue(self.text_queue_manager.is_empty())
    
    async def test_get_queue_stats(self):
        """Test getting queue statistics"""
        await self.text_queue_manager.enqueue_text("Stats test")
        stats = self.text_queue_manager.get_queue_stats()
        
        self.assertIn("current_size_chars", stats)
        self.assertIn("total_enqueued_chars", stats)
        self.assertIn("total_processed_chars", stats)
        self.assertIn("is_processing", stats)
        self.assertIn("is_empty", stats)
        
        self.assertEqual(stats["current_size_chars"], 10)
        self.assertEqual(stats["total_enqueued_chars"], 10)
        self.assertEqual(stats["total_processed_chars"], 0)
        self.assertFalse(stats["is_empty"])


if __name__ == "__main__":
    unittest.main()
