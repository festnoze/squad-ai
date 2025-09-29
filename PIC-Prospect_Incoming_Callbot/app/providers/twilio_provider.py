import logging
from typing import Dict, Any, Tuple
from fastapi import Request, WebSocket, HTTPException
from fastapi.responses import HTMLResponse
from twilio.request_validator import RequestValidator
from twilio.rest import Client
from twilio.twiml.voice_response import Connect, VoiceResponse
from utils.envvar import EnvHelper
from providers.phone_provider_base import PhoneProvider
from utils.phone_provider_type import PhoneProviderType


class TwilioProvider(PhoneProvider):
    """Twilio implementation of phone provider"""
    
    def __init__(self):
        super().__init__(PhoneProviderType.TWILIO)
        self.logger = logging.getLogger(__name__)
        self.twilio_client = Client(EnvHelper.get_twilio_sid(), EnvHelper.get_twilio_auth())
        self.twilio_authenticate = RequestValidator(EnvHelper.get_twilio_auth())
        self.allowed_signatures = []
    
    async def authenticate_request(self, request: Request | WebSocket) -> None:
        """Authenticate incoming request from Twilio using signature validation"""
        signature = request.headers.get("X-Twilio-Signature", "")
        self.allowed_signatures.append(signature)
        if isinstance(request, Request):
            url = str(request.url)
            form = await request.form()
            if not self.twilio_authenticate.validate(url, dict(form), signature):
                raise HTTPException(status_code=403)
        elif isinstance(request, WebSocket):
            if signature not in self.allowed_signatures:
                raise HTTPException(status_code=403)
    
    async def verify_call(self, call_id: str, from_number: str) -> None:
        """Verify that the Twilio call is valid and in progress"""
        if not EnvHelper.get_allow_test_fake_incoming_calls():
            call = self.twilio_client.calls(call_id).fetch()
            if call.status not in ("in-progress", "in-queue", "ringing"):
                err_msg = f"Call status is neither in-progress, in-queue nor ringing. Call status is: {call.status}"
                self.logger.error(err_msg)
                raise HTTPException(status_code=403, detail=err_msg)
            if call.from_formatted != from_number:
                err_msg = f"Wrong phone number: {from_number} different from {call.from_formatted}"
                self.logger.error(err_msg)
                raise HTTPException(status_code=403, detail=err_msg)
    
    async def create_websocket_response(self, request: Request) -> HTMLResponse:
        """Create Twilio TwiML response that connects to WebSocket"""
        phone_number, call_sid, _ = await self.extract_call_data(request)
        ws_url = self.get_websocket_url(request, phone_number, call_sid)
        
        await self.verify_call(call_sid, phone_number)
        self.logger.info(f"Call from: {phone_number}, CallSid: {call_sid}")
        self.logger.info(f"[<--->] Connecting Twilio stream to WebSocket: {ws_url}")
        
        response = VoiceResponse()
        connect = Connect()
        connect.stream(
            url=ws_url,
            track="inbound_track",
            parameters={
                "mediaEncoding": "audio/x-mulaw",
                "sampleRate": 8000,
            },
        )
        response.append(connect)
        return HTMLResponse(content=str(response), media_type="application/xml")
    
    async def extract_call_data(self, request: Request) -> Tuple[str, str, str]:
        """Extract phone number, call SID, and body from Twilio request"""
        phone_number: str = "Unknown From"
        call_sid: str = "Unknown CallSid"
        body: str = ""
        
        if request.method == "GET":
            phone_number = request._query_params.get("From", "Unknown From")
            call_sid = request._query_params.get("CallSid", "Unknown CallSid")
            body = request._query_params.get("Body", "")
        elif request.method == "POST":
            form = await request.form()
            phone_number = str(form.get("From", "Unknown From"))
            call_sid = str(form.get("CallSid", "Unknown CallSid"))
            body = str(form.get("Body", ""))
        else:
            raise HTTPException(status_code=405, detail="Method not allowed")
        
        return phone_number, call_sid, body
    
    def get_websocket_url(self, request: Request, phone_number: str, call_id: str, is_outgoing: bool = False) -> str:
        """Generate WebSocket URL for Twilio"""
        x_forwarded_proto = request.headers.get("x-forwarded-proto")
        is_secure = x_forwarded_proto == "https" or request.url.scheme == "https"
        ws_scheme = "wss" if is_secure else "ws"
        call_type_param = "?call_type=outgoing" if is_outgoing else ""
        return f"{ws_scheme}://{request.url.netloc}/ws/phone/{phone_number}/sid/{call_id}{call_type_param}"
    
    def parse_websocket_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Twilio websocket event and normalize to common format"""
        event = data.get("event")
        
        if event == "connected":
            return {"event": "connected"}
        
        elif event == "start":
            start_data = data.get("start", {})
            return {
                "event": "start",
                "call_id": start_data.get("callSid"),
                "stream_id": start_data.get("streamSid"),
                "raw_data": start_data
            }
        
        elif event == "media":
            media_data = data.get("media", {})
            return {
                "event": "media",
                "stream_id": data.get("streamSid"),
                "payload": media_data.get("payload"),
                "timestamp": media_data.get("timestamp"),
                "raw_data": data
            }
        
        elif event == "stop":
            return {"event": "stop", "raw_data": data}
        
        elif event == "mark":
            return {"event": "mark", "name": data.get("mark", {}).get("name"), "raw_data": data}
        
        return {"event": "unknown", "raw_data": data}
    
    def create_media_message(self, stream_id: str, payload: str) -> Dict[str, Any]:
        """Create Twilio media message for sending audio"""
        return {
            "event": "media",
            "streamSid": stream_id,
            "media": {"payload": payload}
        }
    
    def get_audio_format(self) -> Dict[str, Any]:
        """Get Twilio audio format specifications"""
        return {
            "encoding": "mulaw",
            "sample_rate": 8000,
            "channels": 1,
            "sample_width": 2,
            "format": "audio/x-mulaw"
        }
    
    def get_call_identifier_field(self) -> str:
        """Get Twilio call identifier field name"""
        return "CallSid"
    
    def get_stream_identifier_field(self) -> str:
        """Get Twilio stream identifier field name"""
        return "streamSid"