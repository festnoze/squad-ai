import abc
from typing import Any, Callable

class IncomingManager(abc.ABC):
    """
    Abstract base class for managing incoming data streams (audio, text, etc).
    Implementations of this class handle receiving, processing, and providing callbacks
    when new data is available.
    """
    
    def __init__(self, data_callback: Callable[[str], None]):
        """
        Initialize the incoming data manager.
        
        Args:
            data_callback: Function to call when processed data is available
                          (e.g., transcribed text from audio or plain text from text input)
        """
        self.data_callback = data_callback
        self.is_processing = False
    
    @abc.abstractmethod
    def process_data(self, data: Any) -> None:
        """
        Process incoming data and call the data callback when results are available.
        
        Args:
            data: Raw data to process (audio bytes, text string, etc.)
        """
        pass
    
    @abc.abstractmethod
    def start_processing(self) -> None:
        """Start the data processing pipeline."""
        self.is_processing = True
    
    @abc.abstractmethod
    def stop_processing(self) -> None:
        """Stop the data processing pipeline."""
        self.is_processing = False
