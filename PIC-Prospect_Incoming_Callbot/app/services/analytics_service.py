import hashlib
import logging
from typing import Optional
from utils.envvar import EnvHelper
from ga4mp import GtagMP

logger = logging.getLogger(__name__)

class AnalyticsService:
    """Service for tracking events to Google Analytics 4 using Measurement Protocol"""

    _instance: Optional["AnalyticsService"] = None
    _tracker: Optional[GtagMP] = None
    _enabled: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the GA4 tracker (singleton pattern)"""
        if self._tracker is None:
            self._enabled = EnvHelper.get_ga4_tracking_enabled()
            if self._enabled:
                measurement_id = EnvHelper.get_ga4_measurement_id()
                api_secret = EnvHelper.get_ga4_api_secret()

                if not measurement_id or not api_secret:
                    logger.warning("GA4 tracking enabled but credentials not configured. Disabling tracking.")
                    self._enabled = False
                    return

                try:
                    # Initialize the tracker
                    self._tracker = GtagMP(
                        api_secret=api_secret,
                        measurement_id=measurement_id,
                        client_id="callbot_server",
                    )
                    logger.info("Google Analytics 4 tracking initialized successfully")
                except Exception as e:
                    logger.error(f"Failed to initialize GA4 tracker: {e}")
                    self._enabled = False
            else:
                logger.info("Google Analytics 4 tracking is disabled")

    @staticmethod
    def _hash_value(value: str) -> str:
        """Hash sensitive values before sending to GA4"""
        if not value:
            return ""
        return hashlib.sha256(value.encode()).hexdigest()[:16]

    async def track_call_started_async(
        self,
        call_sid: str,
        phone_number: str,
        call_type: str = "incoming",
        provider: str = "twilio"
    ) -> None:
        """Track when a call starts"""
        if not self._enabled or not self._tracker:
            return

        try:
            event = self._tracker.create_new_event(name="call_started")
            event.set_event_param(name="call_sid", value=call_sid)
            event.set_event_param(name="phone_number_hash", value=self._hash_value(phone_number))
            event.set_event_param(name="call_type", value=call_type)
            event.set_event_param(name="provider", value=provider)

            self._tracker.send(events=[event])
            logger.debug(f"Tracked call_started event for call_sid: {call_sid}")
        except Exception as e:
            logger.error(f"Failed to track call_started event: {e}")

    async def track_call_ended_async(
        self,
        call_sid: str,
        phone_number: str,
        duration_seconds: float,
        disconnect_reason: str = "normal"
    ) -> None:
        """Track when a call ends"""
        if not self._enabled or not self._tracker:
            return

        try:
            event = self._tracker.create_new_event(name="call_ended")
            event.set_event_param(name="call_sid", value=call_sid)
            event.set_event_param(name="phone_number_hash", value=self._hash_value(phone_number))
            event.set_event_param(name="duration_seconds", value=int(duration_seconds))
            event.set_event_param(name="disconnect_reason", value=disconnect_reason)

            self._tracker.send(events=[event])
            logger.debug(f"Tracked call_ended event for call_sid: {call_sid}, duration: {duration_seconds}s")
        except Exception as e:
            logger.error(f"Failed to track call_ended event: {e}")

    async def track_user_identified_async(
        self,
        call_sid: str,
        is_recognized: bool,
        user_id: Optional[str] = None,
        owner_name: Optional[str] = None
    ) -> None:
        """Track user identification with recognition status"""
        if not self._enabled or not self._tracker:
            return

        try:
            event = self._tracker.create_new_event(name="user_identified")
            event.set_event_param(name="call_sid", value=call_sid)
            event.set_event_param(name="is_recognized", value="true" if is_recognized else "false")
            if user_id:
                event.set_event_param(name="user_id_hash", value=self._hash_value(user_id))
            if owner_name:
                event.set_event_param(name="owner_name", value=owner_name)

            self._tracker.send(events=[event])
            logger.debug(f"Tracked user_identified event for call_sid: {call_sid}, recognized: {is_recognized}")
        except Exception as e:
            logger.error(f"Failed to track user_identified event: {e}")

    async def track_appointment_consent_response_async(
        self,
        call_sid: str,
        consent_given: bool,
        user_input: Optional[str] = None
    ) -> None:
        """Track user response to appointment consent question"""
        if not self._enabled or not self._tracker:
            return

        try:
            event = self._tracker.create_new_event(name="appointment_consent_response")
            event.set_event_param(name="call_sid", value=call_sid)
            event.set_event_param(name="consent_given", value="true" if consent_given else "false")
            if user_input:
                # Only send first 50 chars to avoid PII
                event.set_event_param(name="response_preview", value=user_input[:50])

            self._tracker.send(events=[event])
            logger.debug(f"Tracked appointment_consent_response event for call_sid: {call_sid}, consent: {consent_given}")
        except Exception as e:
            logger.error(f"Failed to track appointment_consent_response event: {e}")

    async def track_agent_dispatched_async(
        self,
        call_sid: str,
        agent_type: str,
        user_input_category: Optional[str] = None
    ) -> None:
        """Track when user is routed to a specific agent"""
        if not self._enabled or not self._tracker:
            return

        try:
            event = self._tracker.create_new_event(name="agent_dispatched")
            event.set_event_param(name="call_sid", value=call_sid)
            event.set_event_param(name="agent_type", value=agent_type)
            if user_input_category:
                event.set_event_param(name="user_input_category", value=user_input_category)

            self._tracker.send(events=[event])
            logger.debug(f"Tracked agent_dispatched event for call_sid: {call_sid}, agent: {agent_type}")
        except Exception as e:
            logger.error(f"Failed to track agent_dispatched event: {e}")

    async def track_appointment_scheduled_async(
        self,
        call_sid: str,
        user_id: str,
        appointment_date: str,
        calendar_provider: str = "salesforce"
    ) -> None:
        """Track when an appointment is successfully created"""
        if not self._enabled or not self._tracker:
            return

        try:
            event = self._tracker.create_new_event(name="appointment_scheduled")
            event.set_event_param(name="call_sid", value=call_sid)
            event.set_event_param(name="user_id_hash", value=self._hash_value(user_id))
            event.set_event_param(name="appointment_date", value=appointment_date)
            event.set_event_param(name="calendar_provider", value=calendar_provider)

            self._tracker.send(events=[event])
            logger.debug(f"Tracked appointment_scheduled event for call_sid: {call_sid}")
        except Exception as e:
            logger.error(f"Failed to track appointment_scheduled event: {e}")

    async def track_appointment_sms_sent_async(
        self,
        call_sid: str,
        message_sid: str,
        phone_number: str
    ) -> None:
        """Track when appointment confirmation SMS is sent"""
        if not self._enabled or not self._tracker:
            return

        try:
            event = self._tracker.create_new_event(name="appointment_sms_sent")
            event.set_event_param(name="call_sid", value=call_sid)
            event.set_event_param(name="message_sid", value=message_sid)
            event.set_event_param(name="phone_number_hash", value=self._hash_value(phone_number))

            self._tracker.send(events=[event])
            logger.debug(f"Tracked appointment_sms_sent event for call_sid: {call_sid}")
        except Exception as e:
            logger.error(f"Failed to track appointment_sms_sent event: {e}")

    async def track_rag_query_async(
        self,
        call_sid: str,
        query_length: int,
        response_length: Optional[int] = None
    ) -> None:
        """Track RAG query processing"""
        if not self._enabled or not self._tracker:
            return

        try:
            event = self._tracker.create_new_event(name="rag_query")
            event.set_event_param(name="call_sid", value=call_sid)
            event.set_event_param(name="query_length", value=query_length)
            if response_length is not None:
                event.set_event_param(name="response_length", value=response_length)

            self._tracker.send(events=[event])
            logger.debug(f"Tracked rag_query event for call_sid: {call_sid}")
        except Exception as e:
            logger.error(f"Failed to track rag_query event: {e}")

    async def track_consecutive_errors_async(
        self,
        call_sid: str,
        error_count: int,
        error_type: str = "general"
    ) -> None:
        """Track when consecutive error threshold is reached"""
        if not self._enabled or not self._tracker:
            return

        try:
            event = self._tracker.create_new_event(name="consecutive_errors")
            event.set_event_param(name="call_sid", value=call_sid)
            event.set_event_param(name="error_count", value=error_count)
            event.set_event_param(name="error_type", value=error_type)

            self._tracker.send(events=[event])
            logger.debug(f"Tracked consecutive_errors event for call_sid: {call_sid}, count: {error_count}")
        except Exception as e:
            logger.error(f"Failed to track consecutive_errors event: {e}")

    async def track_api_error_async(
        self,
        call_sid: str,
        api_type: str,
        error_message: str
    ) -> None:
        """Track API errors (Salesforce, RAG, Calendar)"""
        if not self._enabled or not self._tracker:
            return

        try:
            event = self._tracker.create_new_event(name="api_error")
            event.set_event_param(name="call_sid", value=call_sid)
            event.set_event_param(name="api_type", value=api_type)
            # Truncate error message to avoid sensitive data
            event.set_event_param(name="error_message", value=error_message[:100])

            self._tracker.send(events=[event])
            logger.debug(f"Tracked api_error event for call_sid: {call_sid}, api: {api_type}")
        except Exception as e:
            logger.error(f"Failed to track api_error event: {e}")

    async def track_outgoing_call_initiated_async(
        self,
        to_phone_number: str,
        from_phone_number: str,
        initiated_via: str = "api"
    ) -> None:
        """Track outgoing call initiation"""
        if not self._enabled or not self._tracker:
            return

        try:
            event = self._tracker.create_new_event(name="outgoing_call_initiated")
            event.set_event_param(name="to_phone_number_hash", value=self._hash_value(to_phone_number))
            event.set_event_param(name="from_phone_number_hash", value=self._hash_value(from_phone_number))
            event.set_event_param(name="initiated_via", value=initiated_via)

            self._tracker.send(events=[event])
            logger.debug(f"Tracked outgoing_call_initiated event")
        except Exception as e:
            logger.error(f"Failed to track outgoing_call_initiated event: {e}")

    async def track_sms_received_async(
        self,
        from_phone_number: str,
        message_length: int
    ) -> None:
        """Track incoming SMS"""
        if not self._enabled or not self._tracker:
            return

        try:
            event = self._tracker.create_new_event(name="sms_received")
            event.set_event_param(name="from_phone_number_hash", value=self._hash_value(from_phone_number))
            event.set_event_param(name="message_length", value=message_length)

            self._tracker.send(events=[event])
            logger.debug(f"Tracked sms_received event")
        except Exception as e:
            logger.error(f"Failed to track sms_received event: {e}")