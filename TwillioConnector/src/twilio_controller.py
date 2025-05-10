# Inspired by: https://github.com/twilio-samples/speech-assistant-openai-realtime-api-python/blob/main/main.py

from fastapi import APIRouter, Request
from src.studi_public_website_client import StudiPublicWebsiteClient
from src.vocal_conversation_service import VocalConversationService

from fastapi import WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from twilio.twiml.voice_response import VoiceResponse, Connect

handled_events_channel_and_ts: set = set()
website_client :StudiPublicWebsiteClient = StudiPublicWebsiteClient("http://localhost:8281")
twilio_router = APIRouter(prefix="", tags=["Twilio"])

@twilio_router.get("/ping")
def test_endpoint():
    return "pong"

@twilio_router.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}

@twilio_router.api_route("/incoming-sms", methods=["GET", "POST"])
async def twilio_incoming_SMS(request: Request):
    return HTMLResponse(content=str("Les SMS ne sont pas pris en charge pour le moment"), media_type="application/xml")

@twilio_router.post("/")
async def twilio_incoming_voice_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    response = VoiceResponse()
    #response.say("Bonjour, merci de patienter pendant que nous vous connectons à votre assistant vocal personnel ...", language="fr-FR")

    host = request.url.hostname
    connect = Connect()
    
    form = await request.form()
    from_number: str = form.get("From", "Undisclosed phone number")
    call_sid: str = form.get("CallSid", "Undisclosed Call Sid")

    connect.stream(url=f'wss://{host}/media-stream/phone/{from_number}/sid/{call_sid}')
    response.append(connect)
    
    return HTMLResponse(content=str(response), media_type="application/xml")

@twilio_router.websocket("/media-stream/phone/{calling_phone_number}/sid/{call_sid}")
async def handle_media_stream(websocket: WebSocket, calling_phone_number: str, call_sid: str):
    """Handle WebSocket connections between Twilio and LLM."""
    await websocket.accept()
    print(f"!!! Incoming call from {calling_phone_number}")
    print(f"!!! Call SID: {call_sid}")
    vocal_service = VocalConversationService(websocket)
    await vocal_service.initialize_llm_websocket_async()
    await vocal_service.handle_conversation_async(calling_phone_number, call_sid)