import os
import logging
from fastapi import APIRouter, WebSocket, Request, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from twilio.twiml.voice_response import VoiceResponse, Connect
from twilio.twiml.messaging_response import MessagingResponse
#
from app.phone_call_websocket_events_handler import PhoneCallWebsocketEventsHandlerFactory
from app.incoming_sms_handler import IncomingSMSHandler

logger: logging.Logger = logging.getLogger(__name__)

router = APIRouter()

phone_call_websocket_events_handler_factory = PhoneCallWebsocketEventsHandlerFactory()

@staticmethod
async def _extract_request_data_async(request: Request) -> tuple:
    """Extract common data from the request form"""
    form = await request.form()
    phone_number: str = form.get("From", "Unknown From")
    call_sid: str = form.get("CallSid", "Unknown CallSid")
    body = form.get("Body", "")     
    return phone_number, call_sid, body

# ========= Incoming phone call logic ========= #
@staticmethod
async def create_incoming_call_websocket_async(request: Request) -> HTMLResponse:
    """Handle incoming phone calls from Twilio"""
    logger.info("Received POST request for voice webhook")
    try:
        phone_number, call_sid, _ = await _extract_request_data_async(request)
        logger.info(f"Call from: {phone_number}, CallSid: {call_sid}")

        # Open a websocket to handle the phone call audio I/O
        ws_scheme = "wss" if request.url.scheme == "https" else "ws"
        ws_url = f"{ws_scheme}://{request.url.netloc}/ws/phone/{phone_number}/sid/{call_sid}"
        logger.info(f"[<--->] Connecting Twilio stream to WebSocket: {ws_url}")

        response = VoiceResponse()
        connect = Connect()
        
        # Request higher quality audio from Twilio
        connect.stream(url=ws_url, track="inbound_track", parameters={
            "mediaEncoding": "audio/x-mulaw", 
            "sampleRate": 8000  # Request 8kHz if possible
        })
        response.append(connect)
        return HTMLResponse(content=str(response), media_type="application/xml")
                  
    except Exception as e:
        logger.error(f"Error processing voice webhook: {e}", exc_info=True)
        response = VoiceResponse()
        response.say("An error occurred processing your call. Please try again later.")
        return HTMLResponse(content=str(response), media_type="application/xml", status_code=500)


# ========= Incoming phone call endpoint ========= #
@router.post("/")
async def voice_webhook(request: Request) -> HTMLResponse:
    return await create_incoming_call_websocket_async(request)
    
# ========= Incoming phone call WebSocket endpoint ========= #
@router.websocket("/ws/phone/{calling_phone_number}/sid/{call_sid}")
async def websocket_endpoint(ws: WebSocket, calling_phone_number: str, call_sid: str) -> None:
    await ws.accept()
    logger.info(f"WebSocket connection accepted from: {ws.client.host}:{ws.client.port}")
    try:
        call_handler = phone_call_websocket_events_handler_factory.get_new_phone_call_websocket_events_handler(websocket=ws)
        await call_handler.handle_websocket_events_async(calling_phone_number, call_sid)
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
        phone_call_websocket_events_handler_factory.build_new_phone_call_websocket_events_handler(websocket=None)


# ========= Incoming SMS logic ========= #
@staticmethod
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

# ========= Incoming SMS endpoint ========= #
@router.api_route("/incoming-sms", methods=["GET", "POST"])
async def twilio_incoming_sms(request: Request):
    return await handle_incoming_sms_async(request)
    