import time
import logging
from queue import Queue, Full, Empty
from typing import Dict, Optional, Any

class AudioQueueManager:
    """
    Manages audio queues with back-pressure to prevent overwhelming Twilio.
    Implements adaptive throttling based on queue pressure.
    """
    def __init__(self, max_queue_size: int = 20):
        self.logger = logging.getLogger(__name__)
        self.audio_queue = Queue(maxsize=max_queue_size)
        self.is_playing = False
        self.total_enqueued = 0
        self.total_dequeued = 0
        self.last_enqueue_time = time.time()
        self.pressure_coefficient = 0.03  # How much to slow down per queued item (in seconds)
        self.high_pressure_threshold = 0.7  # When queue is at 70% capacity, consider it high pressure
        self.critical_pressure_threshold = 0.9  # When queue is at 90% capacity, take more drastic measures
        
    def get_queue_pressure(self) -> float:
        """
        Returns a value between 0 and 1 representing how full the queue is
        """
        return self.audio_queue.qsize() / self.audio_queue.maxsize
    
    def wait_if_queue_full(self, timeout: float = 2.0) -> bool:
        """
        Implements back-pressure if the queue is too full.
        Returns True if the wait completed without timeout, False otherwise.
        """
        current_pressure = self.get_queue_pressure()
        
        # Apply adaptive throttling based on current queue pressure
        if current_pressure > self.high_pressure_threshold:
            # Calculate adaptive delay based on queue pressure
            delay = current_pressure * self.pressure_coefficient
            
            if current_pressure > self.critical_pressure_threshold:
                # Double the delay for critical pressure
                delay *= 2
                self.logger.warning(f"Queue critically full ({current_pressure:.1%}), applying increased backpressure")
            else:
                self.logger.info(f"Queue filling up ({current_pressure:.1%}), applying backpressure")
                
            # Sleep to allow the queue to drain
            time.sleep(delay)
            
            # Check if we're still under pressure
            return self.get_queue_pressure() < self.high_pressure_threshold
        
        return True
    
    def enqueue_audio(self, audio_chunk: bytes) -> bool:
        """
        Enqueues an audio chunk with adaptive throttling and back-pressure.
        Returns True if the chunk was successfully enqueued, False otherwise.
        """
        if not audio_chunk:
            return False
            
        # Check if we need to apply throttling
        self.wait_if_queue_full()
        
        # Use non-blocking put with timeout to avoid deadlocks
        try:
            self.audio_queue.put(audio_chunk, block=True, timeout=1.0)
            self.total_enqueued += 1
            self.last_enqueue_time = time.time()
            return True
        except Full:
            self.logger.warning("Audio queue full, dropping chunk to prevent saturation")
            return False
    
    def get_audio_chunk(self, block: bool = False, timeout: float = 0.1) -> Optional[bytes]:
        """
        Gets an audio chunk from the queue.
        Returns the chunk if successful, None otherwise.
        """
        try:
            chunk = self.audio_queue.get(block=block, timeout=timeout)
            self.total_dequeued += 1
            return chunk
        except Empty:
            self.is_playing = False
            return None
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Returns statistics about the queue for monitoring
        """
        return {
            "current_size": self.audio_queue.qsize(),
            "max_size": self.audio_queue.maxsize,
            "pressure": self.get_queue_pressure(),
            "total_enqueued": self.total_enqueued,
            "total_dequeued": self.total_dequeued,
            "is_playing": self.is_playing
        }
        
    def clear_queue(self) -> None:
        """
        Clears the queue completely
        """
        try:
            while not self.audio_queue.empty():
                self.audio_queue.get_nowait()
            self.logger.info("Audio queue cleared")
        except Exception as e:
            self.logger.error(f"Error clearing audio queue: {e}")

