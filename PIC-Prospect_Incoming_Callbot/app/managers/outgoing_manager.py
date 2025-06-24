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
        self.can_speech_be_interupted = True
    
    @abc.abstractmethod
    def enqueue_text(self, text: str) -> None:
        """
        Queue text for delivery.
        
        Args:
            text: Text to be queued for output
        """
        pass

    @abc.abstractmethod
    async def clear_text_queue(self) -> None:
        """Clear the text queue."""
        pass
    
    @abc.abstractmethod
    def run_background_streaming_worker(self) -> None:
        """Start the data delivery process."""
        pass
    
    @abc.abstractmethod
    def stop_background_streaming_worker_async(self) -> None:
        """Stop the data delivery process."""
        self.is_running = False

    @abc.abstractmethod
    async def _background_streaming_worker_async(self) -> None:
        """Worker task to process the queue and send data."""
        pass

    @abc.abstractmethod
    def update_stream_sid(self, stream_sid: str) -> None:
        """
        Updates the stream SID when it changes (e.g., when a new call starts or ends)
        Allows setting to None when resetting after a call ends
        """
        pass

    @abc.abstractmethod
    def is_sending(self) -> bool:
        """
        Returns True if the data delivery process is currently running.
        """
        pass