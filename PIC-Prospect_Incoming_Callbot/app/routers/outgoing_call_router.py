import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from providers.twilio_provider import TwilioProvider
from pydantic import BaseModel, Field
from services.outgoing_call_service import OutgoingCallService
from twilio.base.exceptions import TwilioRestException
from utils.endpoints_api_key_required_decorator import api_key_required

logger = logging.getLogger(__name__)

outgoing_call_router = APIRouter(prefix="/outgoing-call", tags=["Outgoing Calls"])


# Request/Response Models
class InitiateCallRequest(BaseModel):
    """Request model for initiating an outgoing call"""
    to_phone_number: str = Field(
        "+33668422388",
        description="Target phone number in E.164 format (e.g., +33123456789)",
        example="+33668422388"
    )
    from_phone_number: str | None = Field(
        None,
        description="Optional caller ID in E.164 format (defaults to TWILIO_PHONE_NUMBER)",
        example="+33987654321"
    )


class InitiateCallResponse(BaseModel):
    """Response model for initiated call"""
    success: bool
    call_sid: str
    to_phone_number: str
    from_phone_number: str
    message: str


class SendSmsRequest(BaseModel):
    """Request model for sending an outgoing SMS"""
    to_phone_number: str = Field(
        ...,
        description="Target phone number in E.164 format (e.g., +33123456789)",
        example="+33668422388"
    )
    message: str = Field(
        ...,
        description="SMS message content to send",
        example="Hello, this is a test message"
    )


class SendSmsResponse(BaseModel):
    """Response model for sent SMS"""
    success: bool
    message_sid: str
    to_phone_number: str
    from_phone_number: str
    message: str


@outgoing_call_router.post("", response_model=InitiateCallResponse)
@outgoing_call_router.post("/", response_model=InitiateCallResponse)
@api_key_required
async def outgoing_call_initiate_endpoint(request: Request, call_request: InitiateCallRequest) -> JSONResponse:
    """
    Initiate an outgoing phone call via Twilio.

    This endpoint triggers Twilio to call the specified phone number. When the call
    is answered, Twilio will request TwiML instructions from the callback endpoint,
    which will establish a WebSocket connection for the AI conversation.

    **Authentication**: Requires API key via X-API-Key header or api_key query parameter.

    **Phone Number Format**: All phone numbers must be in E.164 format (e.g., +33123456789)

    **Flow**:
    1. API calls Twilio REST API to initiate call
    2. Twilio dials the target number
    3. When answered, Twilio requests TwiML from callback URL
    4. TwiML establishes WebSocket connection
    5. AI conversation proceeds normally

    **Example Request**:
    ```json
    {
        "to_phone_number": "+33123456789",
        "from_phone_number": "+33987654321"
    }
    ```

    **Example Response**:
    ```json
    {
        "success": true,
        "call_sid": "CAxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "to_phone_number": "+33123456789",
        "from_phone_number": "+33987654321",
        "message": "Outgoing call initiated successfully"
    }
    ```
    """
    logger.info(f"Received request to initiate outgoing call to {call_request.to_phone_number}")

    try:
        # Generate TwiML callback URL
        # This URL will be called by Twilio when the outgoing call is answered
        x_forwarded_proto = request.headers.get("x-forwarded-proto")
        is_secure = x_forwarded_proto == "https" or request.url.scheme == "https"
        scheme = "https" if is_secure else "http"
        twiml_callback_url = f"{scheme}://{request.url.netloc}/outgoing-call/twiml"

        logger.info(f"Generated TwiML callback URL: {twiml_callback_url}")

        # Initiate the call via service layer
        outgoing_call_service = OutgoingCallService()
        call_sid = await outgoing_call_service.make_call_async(
            to_phone_number=call_request.to_phone_number,
            from_phone_number=call_request.from_phone_number,
            twiml_callback_url=twiml_callback_url
        )

        # Determine the actual from_phone_number used
        from_phone_number = call_request.from_phone_number or outgoing_call_service.twilio_phone_number

        logger.info(f"Outgoing call initiated successfully. Call SID: {call_sid}")

        return JSONResponse(
            status_code=200,
            content=InitiateCallResponse(
                success=True,
                call_sid=call_sid,
                to_phone_number=call_request.to_phone_number,
                from_phone_number=from_phone_number,
                message="Outgoing call initiated successfully"
            ).dict()
        )

    except ValueError as ve:
        logger.error(f"Validation error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))

    except TwilioRestException as te:
        logger.error(f"Twilio API error: {te.msg} (Code: {te.code})")
        raise HTTPException(
            status_code=502,
            detail=f"Twilio API error: {te.msg} (Code: {te.code})"
        )

    except Exception as e:
        logger.error(f"Unexpected error initiating outgoing call: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {e!s}"
        )


@outgoing_call_router.api_route("/twiml", methods=["GET", "POST"])
async def outgoing_call_twiml_callback_endpoint(request: Request) -> HTMLResponse:
    """
    TwiML callback endpoint for outgoing calls.

    This endpoint is called by Twilio when an outgoing call is answered.
    It returns TwiML instructions that establish a WebSocket connection
    for the AI-powered conversation.

    **This endpoint is called by Twilio, not by external clients.**

    The TwiML response connects the call to a WebSocket endpoint where the
    conversation is handled by the same infrastructure as incoming calls.
    """
    logger.info("Received TwiML callback request for outgoing call")

    try:
        # Extract call data from Twilio's request
        provider = TwilioProvider()
        phone_number, call_sid, _ = await provider.extract_call_data(request)

        logger.info(f"Outgoing call answered - To: {phone_number}, CallSid: {call_sid}")

        # Generate WebSocket URL with is_outgoing=True flag
        ws_url = provider.get_websocket_url(request, phone_number, call_sid, is_outgoing=True)
        logger.info(f"Connecting outgoing call to WebSocket: {ws_url}")

        # Create TwiML response with WebSocket connection
        # This reuses the same WebSocket infrastructure as incoming calls
        response = await provider.create_websocket_response(request)

        logger.info(f"TwiML response sent for outgoing call {call_sid}")
        return response

    except Exception as e:
        logger.error(f"Error processing TwiML callback for outgoing call: {e}", exc_info=True)

        # Return error TwiML
        from twilio.twiml.voice_response import VoiceResponse
        response = VoiceResponse()
        response.say("An error occurred connecting your call. Please try again later.")

        return HTMLResponse(
            content=str(response),
            media_type="application/xml",
            status_code=500
        )


@outgoing_call_router.post("/sms", response_model=SendSmsResponse)
@api_key_required
async def send_outgoing_sms_endpoint(request: Request, sms_request: SendSmsRequest) -> JSONResponse:
    """
    Send an outgoing SMS via Twilio.

    This endpoint sends an SMS message to the specified phone number using Twilio's
    messaging API.

    **Authentication**: Requires API key via X-API-Key header or api_key query parameter.

    **Phone Number Format**: Phone number must be in E.164 format (e.g., +33123456789)

    **Example Request**:
    ```json
    {
        "to_phone_number": "+33123456789",
        "message": "Hello, this is a test message"
    }
    ```

    **Example Response**:
    ```json
    {
        "success": true,
        "message_sid": "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "to_phone_number": "+33123456789",
        "from_phone_number": "+33987654321",
        "message": "SMS sent successfully"
    }
    ```
    """
    logger.info(f"Received request to send SMS to {sms_request.to_phone_number}")

    try:
        outgoing_call_service = OutgoingCallService()
        message_sid = await outgoing_call_service.send_sms_async(
            to_phone_number=sms_request.to_phone_number,
            message=sms_request.message
        )

        from_phone_number = outgoing_call_service.twilio_phone_number

        logger.info(f"SMS sent successfully. Message SID: {message_sid}")

        return JSONResponse(
            status_code=200,
            content=SendSmsResponse(
                success=True,
                message_sid=message_sid,
                to_phone_number=sms_request.to_phone_number,
                from_phone_number=from_phone_number,
                message="SMS sent successfully"
            ).dict()
        )

    except ValueError as ve:
        logger.error(f"Validation error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))

    except TwilioRestException as te:
        logger.error(f"Twilio API error: {te.msg} (Code: {te.code})")
        raise HTTPException(
            status_code=502,
            detail=f"Twilio API error: {te.msg} (Code: {te.code})"
        )

    except Exception as e:
        logger.error(f"Unexpected error sending SMS: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {e!s}"
        )
