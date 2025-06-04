import abc

class IncomingManager(abc.ABC):
    """
    Abstract base class for managing incoming data streams (audio, text, etc).
    Implementations of this class handle receiving, processing, and providing callbacks
    when new data is available.
    """    
    def __init__(self):
        self.is_processing = False
    
    @abc.abstractmethod
    async def process_incoming_data_async(self, data: any) -> None:
        """
        Process incoming data
        
        Args: data: Raw data to process (audio bytes, text string, etc.)
        """
        pass

    @abc.abstractmethod
    def set_stream_sid(self, stream_sid: str) -> None:
        pass

    @abc.abstractmethod
    def set_phone_number(self, phone_number: str, stream_sid: str) -> None:
        pass
