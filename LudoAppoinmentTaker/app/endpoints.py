import os
import logging

from fastapi import APIRouter, WebSocket, Request, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from twilio.twiml.voice_response import VoiceResponse, Connect
from logic import BusinessLogic

logger: logging.Logger = logging.getLogger(__name__)

router = APIRouter()
static_audio_path: str = "static/audio/"

@router.get("/audio/{filename}")
async def audio(filename: str) -> FileResponse:
    full_path = os.path.abspath(os.path.join(static_audio_path, filename))
    if not full_path.startswith(os.path.abspath(static_audio_path)):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    if not os.path.exists(full_path):
        return JSONResponse(status_code=404, content={"detail": "File not found"})
    return FileResponse(full_path)

@router.post("/")
async def voice_webhook(request: Request) -> HTMLResponse:
    logger.info("Received POST request on / (voice webhook)")
    try:
        form = await request.form()
        from_number: str = form.get("From", "Unknown From")
        call_sid: str = form.get("CallSid", "Unknown CallSid")
        logger.info(f"Call from: {from_number}, CallSid: {call_sid}")

        ws_scheme = "wss" if request.url.scheme == "https" else "ws"
        ws_url = f"{ws_scheme}://{request.url.netloc}/ws/phone/{from_number}/sid/{call_sid}"
        logger.info(f"Connecting Twilio stream to WebSocket: {ws_url}")

        response = VoiceResponse()
        
        host = request.url.hostname
        connect = Connect()
        
        form = await request.form()
        from_number: str = form.get("From", "Undisclosed phone number")
        call_sid: str = form.get("CallSid", "Undisclosed Call Sid")
        
        connect.stream(url=ws_url)
        response.append(connect)

        return HTMLResponse(content=str(response), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error processing voice webhook: {e}", exc_info=True)
        response = VoiceResponse()
        response.say("An error occurred processing your call. Please try again later.")
        return HTMLResponse(content=str(response), media_type="application/xml", status_code=500)

@router.websocket("/ws/phone/{calling_phone_number}/sid/{call_sid}")
async def websocket_endpoint(ws: WebSocket, calling_phone_number: str, call_sid: str) -> None:
    await ws.accept()
    logger.info(f"WebSocket connection accepted from: {ws.client.host}:{ws.client.port}")
    try:
        await BusinessLogic().handler_websocket(ws, calling_phone_number, call_sid)
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
