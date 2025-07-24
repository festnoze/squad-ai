import os
import logging
from fastapi import APIRouter, WebSocket, Request, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
#
from phone_call_websocket_events_handler import PhoneCallWebsocketEventsHandler, PhoneCallWebsocketEventsHandlerFactory
from incoming_sms_handler import IncomingSMSHandler
from utils.envvar import EnvHelper
from fastapi import HTTPException

logger: logging.Logger = logging.getLogger(__name__)

router = APIRouter()

# Instanciate after app startup
phone_call_websocket_events_handler_factory: PhoneCallWebsocketEventsHandlerFactory = None
allowed_signatures :list[str] = []
twilio_authenticate = RequestValidator(EnvHelper.get_twilio_auth())

async def authenticate_twilio_request(request: Request | WebSocket) -> None:
    signature = request.headers.get("X-Twilio-Signature", "")
    allowed_signatures.append(signature)
    if isinstance(request, Request):
        url = str(request.url)
        form = await request.form()
        if not twilio_authenticate.validate(url, dict(form), signature):
            raise HTTPException(status_code=403)
    elif isinstance(request, WebSocket):
        if signature not in allowed_signatures:
            raise HTTPException(status_code=403)

twilio_client = Client(EnvHelper.get_twilio_sid(), EnvHelper.get_twilio_auth())

async def verify_twilio_call_sid(call_sid: str, from_number: str) -> None:
    call = twilio_client.calls(call_sid).fetch()
    if call.status not in ("in-progress", "in-queue", "ringing"):
        err_msg = f"Call status is neither in-progress, in-queue nor ringing. Call status is: {call.status}"
        logger.error(err_msg)
        raise HTTPException(status_code=403, detail=err_msg)
    if call.from_formatted != from_number:
        err_msg = f"Wrong phone number: {from_number} different from {call.from_formatted}"
        logger.error(err_msg)
        raise HTTPException(status_code=403, detail=err_msg)

# ========= Incoming phone call endpoint ========= #
@router.post("/")
async def voice_incoming_call_endpoint(request: Request) -> HTMLResponse:
    logger.info("Received POST request for voice endpoint")
    #await authenticate_twilio_request(request)
    return await create_websocket_for_incoming_call_async(request)

async def create_websocket_for_incoming_call_async(request: Request) -> HTMLResponse:
    """Handle incoming phone calls from Twilio"""
    logger.info("Received POST request for voice webhook")
    try:
        phone_number, call_sid, _ = await _extract_request_data_async(request)
        await verify_twilio_call_sid(call_sid, phone_number)
        logger.info(f"Call from: {phone_number}, CallSid: {call_sid}")

        x_forwarded_proto = request.headers.get("x-forwarded-proto")
        is_secure = x_forwarded_proto == "https" or request.url.scheme == "https"
        ws_scheme = "wss" if is_secure else "ws"
        ws_url = f"{ws_scheme}://{request.url.netloc}/ws/phone/{phone_number}/sid/{call_sid}"
        logger.info(f"[<--->] Connecting Twilio stream to WebSocket: {ws_url}")

        response = VoiceResponse()

        connect = Connect()
        #connect.stream(url=ws_url, track="both_tracks", parameters={
        connect.stream(url=ws_url, track="inbound_track", parameters={
            "mediaEncoding": "audio/x-mulaw", 
            "sampleRate": 8000  # Request 8kHz audio (max. on phone lines)
        })
        response.append(connect)
        return HTMLResponse(content=str(response), media_type="application/xml")
                  
    except Exception as e:
        logger.error(f"Error processing voice webhook: {e}", exc_info=True)
        response = VoiceResponse()
        response.say("An error occurred processing your call. Please try again later.")
        return HTMLResponse(content=str(response), media_type="application/xml", status_code=500)

async def _extract_request_data_async(request: Request) -> tuple:
    """Extract common data from the request form"""
    form = await request.form()
    phone_number: str = form.get("From", "Unknown From")
    call_sid: str = form.get("CallSid", "Unknown CallSid")
    body = form.get("Body", "")     
    return phone_number, call_sid, body

# ========= Incoming phone call WebSocket endpoint ========= #
@router.websocket("/ws/phone/{calling_phone_number}/sid/{call_sid}")
async def websocket_endpoint(ws: WebSocket, calling_phone_number: str, call_sid: str) -> None:
    #await authenticate_twilio_request(ws)
    await verify_twilio_call_sid(call_sid, calling_phone_number)
    logger.info(f"WebSocket connection attempted for call SID {call_sid} from {ws.client.host}.")
    try:
        await ws.accept()
        logger.info(f"[SUCCESS] WebSocket connection accepted for call SID {call_sid}.")
    except Exception as e:
        logger.error(f"[FAIL] Failed to accept WebSocket connection for call SID {call_sid}: {e}", exc_info=True)
        return

    try:
        call_handler: PhoneCallWebsocketEventsHandler = phone_call_websocket_events_handler_factory.get_new_phone_call_websocket_events_handler(websocket=ws)
        await call_handler.handle_websocket_all_receieved_events_async(calling_phone_number, call_sid)
        logger.info(f"WebSocket handler finished for call SID {call_sid}.")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {ws.client.host}:{ws.client.port}")
    except Exception as e:
        logger.error(f"Error in WebSocket handler: {e}", exc_info=True)
        try:
            await ws.close(code=1011)
        except RuntimeError:
            logger.error("Error closing WebSocket connection", exc_info=True)
            pass
    finally:
        logger.info(f"WebSocket endpoint finished for: {ws.client.host}:{ws.client.port}")
        # Pre-build a new handler for the next call
        phone_call_websocket_events_handler_factory.build_new_phone_call_websocket_events_handler()


# ========= Incoming SMS endpoint ========= #
@router.api_route("/incoming-sms", methods=["GET", "POST"])
async def twilio_incoming_sms(request: Request):
    return await handle_incoming_sms_async(request)

async def handle_incoming_sms_async(request: Request) -> HTMLResponse:
    """Handle incoming SMS messages from Twilio"""
    logger.info("Received POST request for SMS webhook")
    try:
        phone_number, _, body = await _extract_request_data_async(request)
        logger.info(f'SMS from: {phone_number}. Received message: "{body}"')
        
        incoming_sms_handler = IncomingSMSHandler()
        conversation_id = await incoming_sms_handler.init_user_and_conversation_upon_incoming_sms(phone_number)
        rag_answer = await incoming_sms_handler.get_rag_response_to_sms_query_async(conversation_id, body)
        
        logger.info(f'Original RAG answer: "{rag_answer}"')
        
        # Clean the RAG answer for SMS - basic cleaning
        logger.info(f'Basic cleaned RAG answer: "{rag_answer}"')
        
        # Ensure GSM-7 encoding for SMS compatibility
        gsm_rag_answer = rag_answer.encode('utf-8', errors='ignore').decode('utf-8')
        logger.info(f'GSM-7 encoded RAG answer: "{gsm_rag_answer}"')
        
        gsm_rag_answer = gsm_rag_answer.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'").replace('—', '-').replace('–', '-').replace('…', '...').replace(',', ' ')
        gsm_rag_answer = ''.join(c for c in gsm_rag_answer if c in " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~\n€£¥¤§¿¡ÄÅÆÇÉÑÖØÜßàäåæçèéìñòöøùü")
                
        #gsm_rag_answer = "Merci pour votre message, un conseiller vous contactera prochainement. Il s'appelle étienne et est très sympa. Il est disponible sur WhatsApp et Telegram.\n\n A très 'vite'!"
        logger.info(f'SMS answer: "{gsm_rag_answer}"')

        # Create Twilio response with proper encoding
        response = MessagingResponse()
        response.message(gsm_rag_answer)
        return HTMLResponse(content=str(response), media_type="application/xml") 

    except Exception as e:
        logger.error(f"Error processing SMS webhook: {e}", exc_info=True)
        response = MessagingResponse()
        response.message("Une erreur s'est produite. Veuillez réessayer plus tard.")
        return HTMLResponse(content=str(response), media_type="application/xml", status_code=500)    