import time
import logging
import asyncio
from typing import Optional

class AudioQueueManager:
    """
    Manages audio queues with true back-pressure to prevent overwhelming Twilio.
    Implements a blocking queue system that forces producers to wait when the queue is full.
    """
    def __init__(self, max_queue_size: int = 10):
        self.logger = logging.getLogger(__name__)
        self.max_queue_size = max_queue_size
        self.audio_queue = asyncio.Queue(maxsize=max_queue_size)
        self.is_playing = False
        self.total_enqueued = 0
        self.total_dequeued = 0
        self.total_dropped = 0
        self.last_enqueue_time = time.time()
        self.producer_waiting = False
        self.consumer_waiting = False
        self.drain_event = asyncio.Event()
        self.drain_event.set()  # Initially not blocked
        
    def get_queue_pressure(self) -> float:
        """
        Returns a value between 0 and 1 representing how full the queue is
        """
        return self.audio_queue.qsize() / self.max_queue_size
    
    async def wait_until_space_available(self, timeout: float = 5.0) -> bool:
        """
        Implements true back-pressure by having the producer wait until there's space.
        Returns True if space became available, False if timed out.
        """
        self.producer_waiting = True
        try:
            current_pressure = self.get_queue_pressure()
            
            if current_pressure >= 0.9:  # Near full
                self.logger.warning(f"Queue at high capacity ({current_pressure:.1%}), producer will wait")
                
                # Reset the event when we're nearing capacity
                if self.drain_event.is_set():
                    self.drain_event.clear()
                
                # Wait until the drain event is set (by the consumer when queue drains below threshold)
                try:
                    # Wait with timeout to prevent deadlock
                    await asyncio.wait_for(self.drain_event.wait(), timeout=timeout)
                    self.logger.info(f"Producer resumed after queue pressure decreased to {self.get_queue_pressure():.1%}")
                    return True
                except asyncio.TimeoutError:
                    self.logger.error(f"Timed out waiting for queue to drain after {timeout}s")
                    # Continue anyway but return False
                    return False
            return True
        finally:
            self.producer_waiting = False
    
    async def enqueue_audio(self, audio_chunk: bytes) -> bool:
        """
        Enqueues an audio chunk with true back-pressure.
        Returns True if the chunk was successfully enqueued, False otherwise.
        This is a blocking call that will wait until space is available in the queue.
        """
        if not audio_chunk:
            return False
            
        # Wait until there's space in the queue (true back-pressure)
        await self.wait_until_space_available()
        
        # Always use put (which will block if queue is full) instead of put_nowait
        try:
            # Put with a generous timeout
            await asyncio.wait_for(self.audio_queue.put(audio_chunk), timeout=2.0)
            self.total_enqueued += 1
            self.last_enqueue_time = time.time()
            
            # Log how much of the queue is utilized
            if self.total_enqueued % 10 == 0:  # Log every 10 chunks
                self.logger.debug(f"Queue utilization: {self.get_queue_pressure():.1%} ({self.audio_queue.qsize()}/{self.max_queue_size})")
                
            return True
        except asyncio.TimeoutError:
            self.logger.warning("Timed out trying to enqueue audio chunk")
            self.total_dropped += 1
            return False
        except Exception as e:
            self.logger.error(f"Error enqueuing audio chunk: {e}")
            self.total_dropped += 1
            return False
    
    async def get_audio_chunk(self, timeout: float = 0.1) -> Optional[bytes]:
        """
        Gets an audio chunk from the queue asynchronously.
        Returns the chunk if successful, None otherwise.
        """
        self.consumer_waiting = True
        try:
            # Use asyncio.wait_for to implement timeout
            try:
                chunk = await asyncio.wait_for(self.audio_queue.get(), timeout=timeout)
                self.total_dequeued += 1
                
                # CRITICAL: Signal producers when queue drains below threshold
                # This is the key to implementing back-pressure correctly
                current_pressure = self.get_queue_pressure()
                if current_pressure < 0.5 and not self.drain_event.is_set():  # Once we're below 50% capacity
                    self.logger.info(f"Queue drained to {current_pressure:.1%}, signaling producers")
                    self.drain_event.set()  # Signal that producers can continue
                
                # Always acknowledge that we've processed this task
                self.audio_queue.task_done()
                
                return chunk
            except asyncio.TimeoutError:
                return None
        except Exception as e:
            self.logger.error(f"Error getting audio chunk: {e}")
            return None
        finally:
            self.consumer_waiting = False
    
    def is_actively_sending(self) -> bool:
        """
        Returns True if there are items in the queue still being processed
        or if we're actively playing audio
        """
        is_speaking = self.audio_queue.qsize() > 0 or self.is_playing
        return is_speaking
    
    def get_queue_stats(self) -> dict[str, any]:
        """
        Returns statistics about the queue for monitoring
        """
        return {
            "current_size": self.audio_queue.qsize(),
            "max_size": self.max_queue_size,
            "pressure": self.get_queue_pressure(),
            "total_enqueued": self.total_enqueued,
            "total_dequeued": self.total_dequeued,
            "total_dropped": self.total_dropped,
            "is_playing": self.is_playing,
            "producer_waiting": self.producer_waiting,
            "consumer_waiting": self.consumer_waiting,
            "drain_event_set": self.drain_event.is_set(),
            "is_actively_sending": self.is_actively_sending()
        }
        
    async def clear_queue(self) -> None:
        """
        Clears the audio queue asynchronously
        """
        try:
            while True:
                try:
                    # Try to get items with a short timeout
                    chunk = await asyncio.wait_for(self.audio_queue.get(), timeout=0.01)
                    # Mark as done
                    self.audio_queue.task_done()
                except asyncio.TimeoutError:
                    # Queue is empty
                    break
                    
            # Always make sure the drain event is set after clearing
            if not self.drain_event.is_set():
                self.drain_event.set()
                
            self.logger.debug("Audio queue cleared")
        except Exception as e:
            self.logger.error(f"Error clearing audio queue: {e}")
