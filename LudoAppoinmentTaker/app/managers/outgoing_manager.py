import abc

class OutgoingManager(abc.ABC):
    """
    Abstract base class for managing outgoing data streams (audio, text, etc).
    Implementations of this class handle queueing and delivering data to the appropriate
    output channel.
    """
    
    def __init__(self, output_channel: any):
        """
        Initialize the outgoing data manager.
        
        Args:
            output_channel: The channel to send data through (e.g., WebSocket, file, etc.)
        """
        self.output_channel = output_channel
        self.is_running = False
    
    @abc.abstractmethod
    def enqueue_text(self, text: str) -> None:
        """
        Queue text for delivery.
        
        Args:
            text: Text to be queued for output
        """
        pass
    
    @abc.abstractmethod
    def run_background_streaming_worker(self) -> None:
        """Start the data delivery process."""
        self.is_running = True
    
    @abc.abstractmethod
    def stop_background_streaming_worker_async(self) -> None:
        """Stop the data delivery process."""
        self.is_running = False

    @abc.abstractmethod
    def _background_streaming_worker(self) -> None:
        """Worker task to process the queue and send data."""
        pass