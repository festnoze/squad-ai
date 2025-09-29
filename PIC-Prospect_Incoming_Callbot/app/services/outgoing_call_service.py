import logging
import re
from typing import Optional

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from utils.envvar import EnvHelper


logger = logging.getLogger(__name__)


class OutgoingCallService:
    """Service for initiating outgoing phone calls via Twilio REST API"""

    def __init__(self):
        self.twilio_sid = EnvHelper.get_twilio_sid()
        self.twilio_auth = EnvHelper.get_twilio_auth()
        self.twilio_phone_number = EnvHelper.get_twilio_phone_number()

        if not self.twilio_sid or not self.twilio_auth:
            raise ValueError("Twilio credentials (TWILIO_SID, TWILIO_AUTH) must be configured")

        self.client = Client(self.twilio_sid, self.twilio_auth)
        logger.info("OutgoingCallService initialized")

    def _validate_phone_number(self, phone_number: str) -> bool:
        """
        Validate phone number is in E.164 format.
        E.164 format: +[country code][number] (e.g., +33123456789, +16175551212)
        """
        e164_pattern = r'^\+[1-9]\d{1,14}$'
        return re.match(e164_pattern, phone_number) is not None

    async def make_call_async(
        self,
        to_phone_number: str,
        twiml_callback_url: str,
        from_phone_number: Optional[str] = None
    ) -> str:
        """
        Initiate an outgoing call via Twilio REST API.

        Args:
            to_phone_number: Target phone number in E.164 format (e.g., +33123456789)
            twiml_callback_url: URL that Twilio will request when call is answered
            from_phone_number: Optional caller ID (defaults to TWILIO_PHONE_NUMBER env var)

        Returns:
            call_sid: Twilio Call SID for the initiated call

        Raises:
            ValueError: If phone numbers are invalid or missing
            TwilioRestException: If Twilio API call fails
        """
        # Validate to_phone_number
        if not to_phone_number:
            raise ValueError("to_phone_number is required")

        if not self._validate_phone_number(to_phone_number):
            raise ValueError(f"Invalid phone number format: {to_phone_number}. Must be E.164 format (e.g., +33123456789)")

        # Determine from_phone_number
        if from_phone_number:
            if not self._validate_phone_number(from_phone_number):
                raise ValueError(f"Invalid from_phone_number format: {from_phone_number}. Must be E.164 format")
        else:
            from_phone_number = self.twilio_phone_number
            if not from_phone_number:
                raise ValueError("from_phone_number not provided and TWILIO_PHONE_NUMBER not configured")

        # Validate callback URL
        if not twiml_callback_url:
            raise ValueError("twiml_callback_url is required")

        logger.info(f"Initiating outgoing call from {from_phone_number} to {to_phone_number}")
        logger.debug(f"TwiML callback URL: {twiml_callback_url}")

        try:
            call = self.client.calls.create(
                to=to_phone_number,
                from_=from_phone_number,
                url=twiml_callback_url
            )

            logger.info(f"Outgoing call initiated successfully. Call SID: {call.sid}")
            return call.sid

        except TwilioRestException as e:
            logger.error(f"Twilio API error initiating call: {e.msg} (Code: {e.code})")
            raise
        except Exception as e:
            logger.error(f"Unexpected error initiating call: {e}", exc_info=True)
            raise