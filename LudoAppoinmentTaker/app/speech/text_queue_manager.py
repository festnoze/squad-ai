import logging
import asyncio
from typing import Optional
from app.speech.text_processing import ProcessText

class TextQueueManager:
    """
    Manages text queues for TTS processing.
    Stores text as a simple string and processes it in chunks based on
    sentence boundaries or word count limits.
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.text_queue = ""
        self.total_enqueued_chars = 0
        self.total_processed_chars = 0
        # Use a lock to ensure thread-safety when modifying the queue content
        self.lock = asyncio.Lock()  
        
    async def enqueue_text(self, text: str) -> bool:
        """
        Appends text to the queue.
        Returns True if the text was successfully enqueued.
        """
        if not text:
            return False
            
        async with self.lock:
            # Add space if last char isn't
            if self.text_queue and not self.text_queue.endswith(" "):
                self.text_queue += " " 
                self.total_enqueued_chars += 1
            
            self.text_queue += text
            self.total_enqueued_chars += len(text)

            self.logger.debug(f"Enqueued {len(text)} characters. Queue length: {len(self.text_queue)} characters")
            return True
            
    async def get_next_text_chunk(self, max_words_by_sentence: int = 15, max_chars_by_sentence: int = 120) -> Optional[str]:
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
            return None
            
        async with self.lock:
            splitted_text = ProcessText.chunk_text_by_sentences_size(self.text_queue, max_words_by_sentence, max_chars_by_sentence)
            self.text_queue = "".join(splitted_text[1:])
            self.total_processed_chars += len(splitted_text[0])
            return splitted_text[0]
            
    def get_next_text_chunk_sync(self, max_words_by_sentence: int = 15, max_chars_by_sentence: int = 120) -> Optional[str]:
        """
        Synchronous version of get_next_text_chunk.
        Gets a chunk of text from the queue without using async/await.
        Used by the AsyncCallWrapper for thread-based processing.
        
        Returns a text chunk or None if queue is empty.
        """
        if not self.text_queue:
            return None
            
        # No lock usage here since we're using this in a thread-based context
        # The main thread should ensure no concurrent modifications to the queue
        splitted_text = ProcessText.chunk_text_by_sentences_size(self.text_queue, max_words_by_sentence, max_chars_by_sentence)
        if splitted_text:
            self.text_queue = "".join(splitted_text[1:])
            self.total_processed_chars += len(splitted_text[0])
            return splitted_text[0]
        return None            
    
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
            'processing_efficiency': round(self.total_processed_chars / max(1, self.total_enqueued_chars) * 100, 2)
        }
        
    async def clear_queue(self) -> None:
        """
        Clears the text queue
        """
        async with self.lock:
            self.logger.debug(f"Clearing text queue (was {len(self.text_queue)} chars)")
            self.text_queue = ""
            self.total_processed_chars = 0
            self.total_enqueued_chars = 0
