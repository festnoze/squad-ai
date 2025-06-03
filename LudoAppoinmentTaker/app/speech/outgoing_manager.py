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
    def queue_data(self, data: any) -> None:
        """
        Queue data for delivery.
        
        Args:
            data: Data to be queued (text, audio bytes, etc.)
        """
        pass
    
    @abc.abstractmethod
    def start(self) -> None:
        """Start the data delivery process."""
        self.is_running = True
    
    @abc.abstractmethod
    def stop(self) -> None:
        """Stop the data delivery process."""
        self.is_running = False