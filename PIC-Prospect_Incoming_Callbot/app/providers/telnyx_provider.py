import logging
import json
from typing import Dict, Any, Tuple
from fastapi import Request, WebSocket, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from utils.envvar import EnvHelper
from providers.phone_provider_base import PhoneProvider


class TelnyxProvider(PhoneProvider):
    """Telnyx implementation of phone provider"""
    
    def __init__(self):
        super().__init__("telnyx")
        self.logger = logging.getLogger(__name__)
        self.api_key = EnvHelper.get_telnyx_api_key()
        self.profile_id = EnvHelper.get_telnyx_profile_id()
    
    async def authenticate_request(self, request: Request | WebSocket) -> None:
        """Authenticate incoming request from Telnyx using API key"""
        # For Telnyx, authentication is typically done via API key in Authorization header
        # or through webhook signature validation if configured
        auth_header = request.headers.get("Authorization", "")
        if not auth_header and not EnvHelper.get_allow_test_fake_incoming_calls():
            # In production, you might want to implement Telnyx webhook signature validation
            # For now, we'll be more permissive but log the missing auth
            self.logger.warning("No Authorization header found in Telnyx request")
    
    async def verify_call(self, call_id: str, from_number: str) -> None:
        """Verify that the Telnyx call is valid and in progress"""
        # For Telnyx, call verification would require API call to check call status
        # Implementation would depend on your specific use case and security requirements
        if not EnvHelper.get_allow_test_fake_incoming_calls():
            # TODO: Implement actual call verification via Telnyx API
            self.logger.info(f"Verifying Telnyx call {call_id} from {from_number}")
            pass
    
    async def create_websocket_response(self, request: Request) -> HTMLResponse:
        """Create Telnyx TeXML response that connects to WebSocket for media streaming"""
        phone_number, call_control_id, _ = await self.extract_call_data(request)
        ws_url = self.get_websocket_url(request, phone_number, call_control_id)
        
        await self.verify_call(call_control_id, phone_number)
        self.logger.info(f"Call from: {phone_number}, Call Control ID: {call_control_id}")
        self.logger.info(f"[<--->] Connecting Telnyx stream to WebSocket: {ws_url}")
        
        # Telnyx TeXML response for media streaming
        texml_response = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Stream url="{ws_url}" track="inbound_track">
        <Parameter name="mediaEncoding" value="audio/x-mulaw"/>
        <Parameter name="sampleRate" value="8000"/>
    </Stream>
</Response>'''
        
        return HTMLResponse(content=texml_response, media_type="application/xml")
    
    async def extract_call_data(self, request: Request) -> Tuple[str, str, str]:
        """Extract phone number, call control ID, and body from Telnyx request"""
        phone_number: str = "Unknown From"
        call_control_id: str = "Unknown Call Control ID"
        body: str = ""
        
        if request.method == "GET":
            phone_number = request._query_params.get("From", "Unknown From")
            call_control_id = request._query_params.get("call_control_id", "Unknown Call Control ID")
            body = request._query_params.get("Body", "")
        elif request.method == "POST":
            # Telnyx typically sends JSON payloads
            try:
                json_data = await request.json()
            except:
                # Fallback to form data
                form = await request.form()
                phone_number = str(form.get("From", "Unknown From"))
                call_control_id = str(form.get("call_control_id", "Unknown Call Control ID"))
                body = str(form.get("Body", ""))
            else:
                # Extract from JSON payload
                payload = json_data.get("payload", {})
                phone_number = payload.get("from", "Unknown From")
                call_control_id = payload.get("call_control_id", "Unknown Call Control ID")
                body = payload.get("body", "")
        else:
            raise HTTPException(status_code=405, detail="Method not allowed")
        
        return phone_number, call_control_id, body
    
    def get_websocket_url(self, request: Request, phone_number: str, call_id: str) -> str:
        """Generate WebSocket URL for Telnyx"""
        x_forwarded_proto = request.headers.get("x-forwarded-proto")
        is_secure = x_forwarded_proto == "https" or request.url.scheme == "https"
        ws_scheme = "wss" if is_secure else "ws"
        return f"{ws_scheme}://{request.url.netloc}/ws/phone/{phone_number}/call_control_id/{call_id}"
    
    def parse_websocket_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Telnyx websocket event and normalize to common format"""
        event = data.get("event")
        
        if event == "connected":
            return {"event": "connected"}
        
        elif event == "start":
            return {
                "event": "start",
                "call_id": data.get("call_control_id"),
                "stream_id": data.get("stream_id"),
                "raw_data": data
            }
        
        elif event == "media":
            media_data = data.get("media", {})
            return {
                "event": "media",
                "stream_id": data.get("stream_id"),
                "payload": media_data.get("payload"),
                "timestamp": media_data.get("timestamp"),
                "sequence_number": data.get("sequence_number"),
                "track": media_data.get("track", "inbound"),
                "chunk": media_data.get("chunk"),
                "raw_data": data
            }
        
        elif event == "stop":
            return {"event": "stop", "raw_data": data}
        
        elif event == "mark":
            return {"event": "mark", "name": data.get("mark", {}).get("name"), "raw_data": data}
        
        return {"event": "unknown", "raw_data": data}
    
    def create_media_message(self, stream_id: str, payload: str) -> Dict[str, Any]:
        """Create Telnyx media message for sending audio"""
        return {
            "event": "media",
            "stream_id": stream_id,
            "media": {"payload": payload}
        }
    
    def get_audio_format(self) -> Dict[str, Any]:
        """Get Telnyx audio format specifications"""
        return {
            "encoding": "rtp_pcmu",  # Telnyx uses RTP PCMU by default
            "sample_rate": 8000,  # Can be up to 16000 for HD audio
            "channels": 1,
            "sample_width": 2,
            "format": "audio/x-rtp-pcmu"
        }
    
    def get_call_identifier_field(self) -> str:
        """Get Telnyx call identifier field name"""
        return "call_control_id"
    
    def get_stream_identifier_field(self) -> str:
        """Get Telnyx stream identifier field name"""
        return "stream_id"