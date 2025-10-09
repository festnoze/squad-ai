from abc import ABC, abstractmethod
from typing import Any

from fastapi import Request, WebSocket
from fastapi.responses import HTMLResponse
from utils.phone_provider_type import PhoneProviderType


class PhoneProvider(ABC):
    """Abstract base class for phone providers (Twilio, Telnyx, etc.)"""
    
    def __init__(self, provider_type: PhoneProviderType):
        self.provider_type = provider_type
    
    @abstractmethod
    async def authenticate_request(self, request: Request | WebSocket) -> None:
        """Authenticate incoming request from provider"""
        pass
    
    @abstractmethod
    async def verify_call(self, call_id: str, from_number: str) -> None:
        """Verify that the call is valid and in progress"""
        pass
    
    @abstractmethod
    async def create_websocket_response(self, request: Request) -> HTMLResponse:
        """Create the response that sets up WebSocket streaming for incoming call"""
        pass
    
    @abstractmethod
    async def extract_call_data(self, request: Request) -> tuple[str, str, str]:
        """Extract phone number, call ID, and body from request"""
        pass
    
    @abstractmethod
    def get_websocket_url(self, request: Request, phone_number: str, call_id: str) -> str:
        """Generate WebSocket URL for the provider"""
        pass
    
    @abstractmethod
    def parse_websocket_event(self, data: dict[str, Any]) -> dict[str, Any]:
        """Parse incoming websocket event and normalize to common format"""
        pass
    
    @abstractmethod
    def create_media_message(self, stream_id: str, payload: str) -> dict[str, Any]:
        """Create a media message for sending audio back to the provider"""
        pass
    
    @abstractmethod
    def get_audio_format(self) -> dict[str, Any]:
        """Get audio format specifications for this provider"""
        pass
    
    @abstractmethod
    def get_call_identifier_field(self) -> str:
        """Get the field name used for call identification (e.g., 'CallSid' for Twilio, 'call_control_id' for Telnyx)"""
        pass
    
    @abstractmethod
    def get_stream_identifier_field(self) -> str:
        """Get the field name used for stream identification (e.g., 'streamSid' for Twilio, 'stream_id' for Telnyx)"""
        pass
