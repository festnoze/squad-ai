import abc


class OutgoingManager(abc.ABC):
    """
    Abstract base class for managing outgoing data streams (audio, text, etc).
    Implementations of this class handle queueing and delivering data to the appropriate
    output channel.
    """

    def __init__(self, output_channel: any, can_speech_be_interupted: bool = True):
        """
        Initialize the outgoing data manager.

        Args:
            output_channel: The channel to send data through (e.g., WebSocket, file, etc.)
        """
        self.output_channel = output_channel
        self.can_speech_be_interupted = can_speech_be_interupted
        self.is_running = False
        self.audio_sender = None

    @abc.abstractmethod
    async def enqueue_text_async(self, text: str) -> bool:
        """
        Queue text for delivery.

        Args:
            text: Text to be queued for output
        """
        pass

    @abc.abstractmethod
    async def clear_text_queue_async(self) -> str:
        """Clear the text queue."""
        pass

    @abc.abstractmethod
    def run_background_streaming_worker(self) -> None:
        """Start the data delivery process."""
        pass

    @abc.abstractmethod
    async def stop_background_streaming_worker_async(self) -> None:
        """Stop the data delivery process."""
        pass

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

    @abc.abstractmethod
    def has_text_to_be_sent(self) -> bool:
        """
        Returns True if there is still text to be sent.
        """
        pass
