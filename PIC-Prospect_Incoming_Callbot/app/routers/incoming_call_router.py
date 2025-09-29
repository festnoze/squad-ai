import logging
import os

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from incoming_sms_handler import IncomingSMSHandler

#
from phone_call_websocket_events_handler import PhoneCallWebsocketEventsHandler, PhoneCallWebsocketEventsHandlerFactory
from providers.phone_provider_base import PhoneProvider
from providers.telnyx_provider import TelnyxProvider
from providers.twilio_provider import TwilioProvider
from twilio.request_validator import RequestValidator
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse
from utils.endpoints_api_key_required_decorator import api_key_required
from utils.envvar import EnvHelper
from utils.phone_provider_type import PhoneProviderType

logger: logging.Logger = logging.getLogger(__name__)

incoming_call_router = APIRouter()

# Instanciate after app startup
phone_call_websocket_events_handler_factory: PhoneCallWebsocketEventsHandlerFactory = PhoneCallWebsocketEventsHandlerFactory()
allowed_signatures: list[str] = []
twilio_authenticate = RequestValidator(EnvHelper.get_twilio_auth())


def get_phone_provider(provider_type: PhoneProviderType) -> PhoneProvider:
    """Get phone provider instance based on configuration or parameter"""
    if provider_type == PhoneProviderType.TELNYX:
        return TelnyxProvider()
    else:
        return TwilioProvider()


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
    if not EnvHelper.get_allow_test_fake_incoming_calls():
        call = twilio_client.calls(call_sid).fetch()
        if call.status not in ("in-progress", "in-queue", "ringing"):
            err_msg = f"Call status is neither in-progress, in-queue nor ringing. Call status is: {call.status}"
            logger.error(err_msg)
            raise HTTPException(status_code=403, detail=err_msg)
        if call.from_formatted != from_number:
            err_msg = f"Wrong phone number: {from_number} different from {call.from_formatted}"
            logger.error(err_msg)
            raise HTTPException(status_code=403, detail=err_msg)


# ========= Incoming phone call endpoints ========= #
@incoming_call_router.post("/")
@incoming_call_router.post("/twilio")
async def twilio_voice_incoming_call_endpoint(request: Request) -> HTMLResponse:
    logger.info("Received POST request for Twilio voice endpoint")
    return await create_websocket_for_incoming_call_async(request, PhoneProviderType.TWILIO)


@incoming_call_router.post("/telnyx")
async def telnyx_voice_incoming_call_endpoint(request: Request) -> HTMLResponse:
    logger.info("Received POST request for Telnyx voice endpoint")
    return await create_websocket_for_incoming_call_async(request, PhoneProviderType.TELNYX)


@incoming_call_router.get("/websocket-url")
@api_key_required
async def get_websocket_url_for_incoming_call(request: Request) -> HTMLResponse:
    logger.info("Received GET request for websocket URL endpoint")
    provider = get_phone_provider(PhoneProviderType.TWILIO)
    ws_url, phone_number, call_id = await get_websocket_url_for_incoming_call_async(request, provider)
    logger.info(f"Returning websocket URL: {ws_url} for {phone_number}/{call_id}")
    return HTMLResponse(content=ws_url, media_type="text/plain")


async def get_websocket_url_for_incoming_call_async(request: Request, provider: PhoneProvider) -> tuple[str, str, str]:
    """Handle incoming phone calls from any provider"""
    phone_number, call_id, _ = await provider.extract_call_data(request)
    ws_url = provider.get_websocket_url(request, phone_number, call_id)
    return ws_url, phone_number, call_id


async def create_websocket_for_incoming_call_async(request: Request, phone_provider_type: PhoneProviderType) -> HTMLResponse:
    """Handle incoming phone calls from any provider"""

    phone_provider = get_phone_provider(phone_provider_type)
    logger.info(f"Received POST request for {phone_provider.provider_type.value} voice webhook")
    try:
        return await phone_provider.create_websocket_response(request)

    except Exception as e:
        logger.error(f"Error processing {phone_provider.provider_type.value} voice webhook: {e}", exc_info=True)
        # Create provider-specific error response
        if phone_provider.provider_type == PhoneProviderType.TWILIO:
            response = VoiceResponse()
            response.say("An error occurred processing your call. Please try again later.")
            return HTMLResponse(content=str(response), media_type="application/xml", status_code=500)
        else:
            # For Telnyx, return TeXML error response
            texml_error = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>An error occurred processing your call. Please try again later.</Say>
</Response>"""
            return HTMLResponse(content=texml_error, media_type="application/xml", status_code=500)


async def _extract_request_data_async(request: Request) -> tuple:
    """Extract common data from the request form or query parameters"""
    phone_number: str = "Unknown From"
    call_sid: str = "Unknown CallSid"
    body: str = ""
    if request.method == "GET":
        # Pour les requêtes GET, utiliser les paramètres de requête
        phone_number = request._query_params.get("From", "Unknown From")
        call_sid = request._query_params.get("CallSid", "Unknown CallSid")
        body = request._query_params.get("Body", "")
    elif request.method == "POST":
        # Pour les requêtes POST, utiliser les données du formulaire
        form = await request.form()
        phone_number = str(form.get("From", "Unknown From"))
        call_sid = str(form.get("CallSid", "Unknown CallSid"))
        body = str(form.get("Body", ""))
    else:
        raise HTTPException(status_code=405, detail="Method not allowed")
    return phone_number, call_sid, body


# ========= Incoming phone call WebSocket endpoint ========= #
@incoming_call_router.websocket("/ws/phone/{calling_phone_number}/sid/{call_sid}")
async def twilio_websocket_endpoint(ws: WebSocket, calling_phone_number: str, call_sid: str, call_type: str = "incoming") -> None:
    """WebSocket endpoint for Twilio calls"""
    provider = get_phone_provider(PhoneProviderType.TWILIO)
    is_outgoing = call_type == "outgoing"
    await handle_websocket_connection(ws, calling_phone_number, call_sid, provider, is_outgoing)


@incoming_call_router.websocket("/ws/phone/{calling_phone_number}/call_control_id/{call_control_id}")
async def telnyx_websocket_endpoint(ws: WebSocket, calling_phone_number: str, call_control_id: str) -> None:
    """WebSocket endpoint for Telnyx calls"""
    provider = get_phone_provider(PhoneProviderType.TELNYX)
    await handle_websocket_connection(ws, calling_phone_number, call_control_id, provider)


async def handle_websocket_connection(ws: WebSocket, calling_phone_number: str, call_id: str, provider: PhoneProvider, is_outgoing: bool = False) -> None:
    """Generic WebSocket connection handler for any provider"""
    # Provider-specific authentication and verification
    if provider.provider_type == PhoneProviderType.TWILIO:
        await verify_twilio_call_sid(call_id, calling_phone_number)
    else:
        await provider.verify_call(call_id, calling_phone_number)

    call_type_str = "outgoing" if is_outgoing else "incoming"
    logger.info(f"WebSocket connection for {provider.provider_type.value} {call_type_str} call ID {call_id} from {ws.client.host if ws.client else 'unknown websocket client (and host)'}.")
    try:
        await ws.accept()
        logger.info(f"[SUCCESS] WebSocket connection accepted for {provider.provider_type.value} {call_type_str} call ID {call_id}.")
    except Exception as e:
        logger.error(f"[FAIL] Failed to accept WebSocket connection for call ID {call_id}: {e}", exc_info=True)
        return

    call_handler: PhoneCallWebsocketEventsHandler
    try:
        call_handler = phone_call_websocket_events_handler_factory.get_new_phone_call_websocket_events_handler(websocket=ws, provider=provider, is_outgoing=is_outgoing)
        await call_handler.handle_websocket_all_receieved_events_async(calling_phone_number, call_id)
        logger.info(f"WebSocket handler finished for {provider.provider_type.value} call ID {call_id}.")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {ws.client.host if ws.client else 'unknown websocket client (and host)'}:{ws.client.port if ws.client else '(and port)'}")
        # Ensure call duration tracking is finished on disconnect
        if call_handler and call_handler.call_duration_context:
            call_handler._finish_call_duration_tracking("endpoint_websocket_disconnect")
    except Exception as e:
        logger.error(f"Error in WebSocket handler: {e}", exc_info=True)
        # Ensure call duration tracking is finished on error
        if call_handler and call_handler.call_duration_context:
            call_handler._finish_call_duration_tracking("endpoint_error")
        try:
            await ws.close(code=1011)
        except RuntimeError:
            logger.error("Error closing WebSocket connection", exc_info=True)
            pass
    finally:
        # Final safety check to ensure call duration tracking is finished
        if call_handler and call_handler.call_duration_context:
            call_handler._finish_call_duration_tracking("endpoint_cleanup")
        logger.info(f"WebSocket endpoint finished for: {ws.client.host if ws.client else 'unknown websocket client (and host)'}:{ws.client.port if ws.client else '(and port)'}")
        # Pre-build a new handler for the next call
        phone_call_websocket_events_handler_factory.build_new_phone_call_websocket_events_handler()


# ========= Incoming SMS endpoint ========= #
@incoming_call_router.api_route("/incoming-sms", methods=["GET", "POST"])
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
        if conversation_id:
            rag_answer = await incoming_sms_handler.get_rag_response_to_sms_query_async(conversation_id, body)
        else:
            rag_answer = "Je suis désolé, je ne peux pas répondre à votre message."

        logger.info(f'Original RAG answer: "{rag_answer}"')

        # Clean the RAG answer for SMS - basic cleaning
        logger.info(f'Basic cleaned RAG answer: "{rag_answer}"')

        # Ensure GSM-7 encoding for SMS compatibility
        gsm_rag_answer = rag_answer.encode("utf-8", errors="ignore").decode("utf-8")
        logger.info(f'GSM-7 encoded RAG answer: "{gsm_rag_answer}"')

        gsm_rag_answer = gsm_rag_answer.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").replace("—", "-").replace("–", "-").replace("…", "...").replace(",", " ")
        gsm_rag_answer = "".join(c for c in gsm_rag_answer if c in " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~\n€£¥¤§¿¡ÄÅÆÇÉÑÖØÜßàäåæçèéìñòöøùü")

        # gsm_rag_answer = "Merci pour votre message, un conseiller vous contactera prochainement. Il s'appelle étienne et est très sympa. Il est disponible sur WhatsApp et Telegram.\n\n A très 'vite'!"
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


# ========= Hot Change of Environment Variables Endpoint ========= #
@incoming_call_router.get("/change_env_var")
@api_key_required
async def change_env_var_endpoint(request: Request):
    """Change environment variable value via query parameter"""
    query_params = dict(request.query_params)
    return await change_env_var_values(query_params)


async def change_env_var_values(var_to_update: dict):
    """Change environment variable value via query parameter"""
    logger.info("Received request to change environment variable")

    if not var_to_update:
        raise HTTPException(status_code=400, detail="No query parameters provided")

    try:
        # Process each query parameter as a potential env var change
        updated_vars = []
        missing_vars = []

        for var_name, new_value in var_to_update.items():
            # Check if the environment variable already exists
            if var_name not in os.environ:
                missing_vars.append(var_name)
                continue

            # Update the environment variable only if it exists
            os.environ[var_name] = new_value
            updated_vars.append(f"{var_name}={new_value}")
            logger.info(f"Updated environment variable: {var_name} = {new_value}")

        # If any variables don't exist, return an error
        if missing_vars:
            error_msg = f"Environment variable(s) do not exist: {', '.join(missing_vars)}"
            logger.error(error_msg)
            raise HTTPException(status_code=404, detail=error_msg)

        return {"message": f"Successfully updated environment variables: {', '.join(updated_vars)}"}

    except Exception as e:
        logger.error(f"Error changing environment variable: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating environment variables: {e!s}")


async def reload_env_var(var_to_reload: dict):
    """Reload environment variables"""
    if not var_to_reload:
        raise HTTPException(status_code=400, detail="No query parameters provided")

    try:
        # Process each query parameter as a potential env var change
        updated_vars = []
        missing_vars = []

        for var_name, new_value in var_to_reload.items():
            # Check if the environment variable already exists
            if var_name not in os.environ:
                missing_vars.append(var_name)
                continue
            os.environ[var_name] = EnvHelper.get_env_variable_value_by_name(var_name) or ""

    except Exception as e:
        logger.error(f"Error reloading environment variable: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error reloading environment variables: {e!s}")
