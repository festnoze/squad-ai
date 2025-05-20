import re
import logging
import asyncio
from typing import Optional, Tuple


class TextQueueManager:
    """
    Manages text queues for TTS processing.
    Stores text as a simple string and processes it in chunks based on
    sentence boundaries or word count limits.
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.text_queue = ""
        self.is_processing = False
        self.total_enqueued_chars = 0
        self.total_processed_chars = 0
        self.lock = asyncio.Lock()  # To ensure thread-safety when modifying the queue
        
    async def enqueue_text(self, text: str) -> bool:
        """
        Appends text to the queue.
        Returns True if the text was successfully enqueued.
        """
        if not text:
            return False
            
        async with self.lock:
            self.text_queue += text
            self.total_enqueued_chars += len(text)
            self.logger.debug(f"Enqueued {len(text)} characters. Queue length: {len(self.text_queue)} characters")
            return True
            
    async def get_text_chunk(self) -> Tuple[str, float]:
        """
        Gets a chunk of text from the queue.
        Returns a tuple of (text_chunk, estimated_duration_ms)
        The chunk will be either:
        - The first 10 words
        - Text up to the end of a sentence (if within the first 15 words)
        - Empty string if queue is empty
        
        Also returns an estimated duration in milliseconds based on
        a simple heuristic (characters per second).
        """
        if not self.text_queue:
            return "", 0.0
            
        async with self.lock:
            # Simple heuristic: 15 characters per second (average speech rate)
            # This will be replaced by actual TTS duration in the streaming worker
            chars_per_second = 15
            ms_per_char = 1000 / chars_per_second
            
            # First, try to find a sentence end within the first 15 words
            words = self.text_queue.split()
            first_15_words = " ".join(words[:15]) if words else ""
            
            # Look for sentence endings (period, question mark, exclamation point followed by space or end)
            sentence_end_match = re.search(r'[.!?](\s|$)', first_15_words)
            
            if sentence_end_match:
                # Found sentence end, extract up to that point (including the punctuation)
                end_index = sentence_end_match.end()
                chunk = self.text_queue[:end_index].strip()
            elif len(words) > 0:
                # No sentence end found, take first 10 words (or all if less than 10)
                word_limit = min(10, len(words))
                chunk = " ".join(words[:word_limit])
                # Find the exact position in the original string to properly slice
                end_index = len(chunk)
                # Make sure we're not cutting in the middle of a word
                if end_index < len(self.text_queue) and end_index > 0 and self.text_queue[end_index] != ' ':
                    # Find the next space or end of string
                    next_space = self.text_queue.find(' ', end_index)
                    if next_space != -1:
                        end_index = next_space
                    else:
                        end_index = len(self.text_queue)
                chunk = self.text_queue[:end_index].strip()
            else:
                # Empty queue
                return "", 0.0
                
            # Remove the chunk from the queue
            self.text_queue = self.text_queue[end_index:].lstrip()
            self.total_processed_chars += len(chunk)
            
            # Estimate duration based on character count
            estimated_duration_ms = len(chunk) * ms_per_char
            
            self.logger.debug(f"Retrieved chunk of {len(chunk)} chars. Remaining: {len(self.text_queue)} chars")
            return chunk, estimated_duration_ms
    
    def is_empty(self) -> bool:
        """
        Returns True if the text queue is empty.
        """
        return len(self.text_queue) == 0
        
    def get_queue_stats(self) -> dict:
        """
        Get comprehensive statistics about the text queue for monitoring.
        
        Returns:
            Dictionary with detailed statistics about text processing
        """
        return {
            'current_size_chars': len(self.text_queue),
            'total_chars_enqueued': self.total_enqueued_chars,
            'total_chars_processed': self.total_processed_chars,
            'is_empty': self.is_empty(),
            'is_processing': self.is_processing,
            'processing_efficiency': round(self.total_processed_chars / max(1, self.total_enqueued_chars) * 100, 2)
        }
        
    async def clear_queue(self) -> None:
        """
        Clears the text queue
        """
        async with self.lock:
            self.logger.debug(f"Clearing text queue (was {len(self.text_queue)} chars)")
            self.text_queue = ""
