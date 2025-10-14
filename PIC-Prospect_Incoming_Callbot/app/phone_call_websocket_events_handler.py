import json
import logging
import os
import time

from agents.agents_graph import AgentsGraph

# from managers.transcription_manager import TranscriptionManager
#
from fastapi import WebSocket, WebSocketDisconnect
from managers.incoming_audio_manager import IncomingAudioManager
from managers.outgoing_audio_manager import OutgoingAudioManager

#
from openai import OpenAI
from providers.phone_provider_base import PhoneProvider
from providers.twilio_provider import TwilioProvider
from services.analytics_service import AnalyticsService
from speech.speech_to_text import get_speech_to_text_provider
from speech.text_to_speech import get_text_to_speech_provider
from utils.envvar import EnvHelper
from utils.latency_decorator import measure_latency_context

#
from utils.latency_metric import LatencyMetric, OperationStatus, OperationType
from utils.latency_tracker import latency_tracker


class PhoneCallWebsocketEventsHandler:
    # Class variables shared across instances
    compiled_graph = None  # LangGraph workflow compilation
    outgoing_audio_processing: OutgoingAudioManager
    incoming_audio_processing: IncomingAudioManager

    def __init__(self, websocket: WebSocket | None = None, phone_provider: PhoneProvider | None = None, is_outgoing: bool = False):
        # Instance variables
        self.websocket = websocket
        self.is_outgoing_call = is_outgoing
        self.logger = logging.getLogger(__name__)
        self.logger.info("IncomingPhoneCallHandler logger started")

        # Initialize phone provider
        if phone_provider is None:
            phone_provider = TwilioProvider()
        self.phone_provider = phone_provider

        call_type_str = "outgoing" if is_outgoing else "incoming"
        self.logger.info(f"Initialized with provider: {self.phone_provider.provider_type.value}, call type: {call_type_str}")

        # State tracking for this instance
        self.openai_client = None
        self.stream_states = {}
        self.active_streams = {}
        # Flags to track speaking state
        self.is_speaking = False  # Flag to track if system is currently speaking
        self.rag_interrupt_flag = {"interrupted": False}  # Flag to interrupt RAG streaming

        # Call duration tracking
        self.call_duration_context = None
        self.current_call_sid = None
        self.current_phone_number = None
        self.media_event_counter = 0  # Counter for periodic call duration checks

        # Analytics service
        self.analytics_service = AnalyticsService()

        # Set audio processing parameters as instance variables
        self.frame_rate = 8000  # Sample rate in Hz (8kHz is standard for telephony)
        self.sample_width = 2  # mu-law in 16 bits
        self.channels = 1  # Mono channel audio
        self.speech_threshold = 250  # Threshold for silence vs. speech
        self.min_audio_bytes_for_processing = 6400  # Minimum buffer size = ~400ms at 8kHz
        self.max_audio_bytes_for_processing = 150000  # Maximum buffer size = ~15s at 8kHz
        self.consecutive_silence_duration_ms = 0.0  # Count consecutive silence duration in milliseconds
        self.required_silence_ms_to_answer = 300  # Require 300ms of silence to process audio
        self.speech_chunk_duration_ms = 500  # Duration of each audio chunk in milliseconds

        self.audio_buffer = b""
        self.current_stream = None
        self.start_time = None
        self.websocket_creation_time = None

        # Environment and configuration settings
        self.OPENAI_API_KEY = EnvHelper.get_openai_api_key()
        os.environ["OPENAI_API_KEY"] = self.OPENAI_API_KEY

        # Load Google credentials used for STT
        self.project_root = os.path.dirname(os.path.dirname(__file__))
        self.google_credentials_filepath = EnvHelper.get_google_credentials_filepath()
        self.google_credentials_absolute_path = os.path.join(self.project_root, self.google_credentials_filepath)

        if os.path.exists(self.google_credentials_absolute_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.google_credentials_absolute_path
            self.logger.info(f"Set GOOGLE_APPLICATION_CREDENTIALS to: {self.google_credentials_absolute_path}")
        else:
            self.logger.error(f"/!\\ Google calendar credentials file not found at {self.google_credentials_absolute_path}")

        # Initialize dependencies
        tts_provider_name = EnvHelper.get_text_to_speech_provider()
        stt_provider_name = EnvHelper.get_speech_to_text_provider()
        can_speech_be_interupted = EnvHelper.get_can_speech_be_interupted()
        self.tts_provider = get_text_to_speech_provider(
            tts_provider_name=tts_provider_name,
            frame_rate=self.frame_rate,
            channels=self.channels,
            sample_width=self.sample_width,
        )
        self.stt_provider = get_speech_to_text_provider(stt_provider_name=stt_provider_name, language_code="fr-FR", frame_rate=self.frame_rate)

        self.outgoing_audio_processing = OutgoingAudioManager(
            websocket=self.websocket,
            tts_provider=self.tts_provider,
            phone_provider=self.phone_provider,
            stream_sid=None,
            min_chunk_interval=0.05,
            can_speech_be_interupted=can_speech_be_interupted,
            sample_width=self.sample_width,
            frame_rate=self.frame_rate,
            channels=self.channels,
        )

        self.agents_graph = AgentsGraph(self.outgoing_audio_processing)
        self.compiled_graph = self.agents_graph.graph
        self.stt_provider.conversation_persistence = self.agents_graph.conversation_persistence
        self.tts_provider.conversation_persistence = self.agents_graph.conversation_persistence

        self.incoming_audio_processing = IncomingAudioManager(
            websocket=self.websocket,
            stt_provider=self.stt_provider,
            outgoing_manager=self.outgoing_audio_processing,
            agents_graph=self.agents_graph,
            sample_width=self.sample_width,
            frame_rate=self.frame_rate,
            vad_aggressiveness=3,
        )

        if self.openai_client is None:
            self.openai_client = OpenAI(api_key=self.OPENAI_API_KEY)

        self.logger.info("IncomingPhoneCallHandler initialized successfully.")

    def set_websocket(self, websocket: WebSocket):
        self.websocket = websocket
        self.websocket_creation_time = time.time()  # Start the timer when websocket is set
        self.incoming_audio_processing.set_websocket(websocket)
        self.outgoing_audio_processing.set_websocket(websocket)
        self.incoming_audio_processing.set_websocket_creation_time(self.websocket_creation_time)

        # Prepare call duration tracking (will be started when we have call_sid and phone_number)
        self._prepare_call_duration_tracking()

    def _prepare_call_duration_tracking(self):
        """Prepare call duration tracking context manager."""
        if not self.call_duration_context:
            self.call_duration_context = measure_latency_context(
                operation_type=OperationType.CALL_DURATION,
                operation_name="websocket_call_duration",
                provider=self.phone_provider.provider_type.value,
                call_sid=self.current_call_sid,
                phone_number=self.current_phone_number,
                metadata={"tracking_method": "websocket_lifecycle"},
            )

    def _start_call_duration_tracking(self, call_sid: str, phone_number: str):
        """Start call duration tracking with complete call information."""
        self.current_call_sid = call_sid
        self.current_phone_number = phone_number

        # Update existing context manager with call information or create new one
        if self.call_duration_context:
            self.call_duration_context.call_sid = call_sid
            self.call_duration_context.phone_number = phone_number
        else:
            self.call_duration_context = measure_latency_context(
                operation_type=OperationType.CALL_DURATION,
                operation_name="websocket_call_duration",
                provider=self.phone_provider.provider_type.value,
                call_sid=call_sid,
                phone_number=phone_number,
                metadata={"tracking_method": "websocket_lifecycle"},
            )

        # Enter the context if not already entered
        if not hasattr(self.call_duration_context, "start_time") or self.call_duration_context.start_time is None:
            self.call_duration_context.__enter__()
            self.logger.debug(f"[{call_sid}] Started call duration tracking")

    def _finish_call_duration_tracking(self, disconnect_reason: str = "normal"):
        """Finish call duration tracking and record the metric."""
        if self.call_duration_context:
            try:
                # Calculate duration before exiting context
                import time
                duration_seconds = 0
                if hasattr(self.call_duration_context, "start_time") and self.call_duration_context.start_time:
                    duration_seconds = time.time() - self.call_duration_context.start_time

                # Update metadata with disconnect reason
                if hasattr(self.call_duration_context, "metadata"):
                    self.call_duration_context.metadata["disconnect_reason"] = disconnect_reason

                # Exit the context manager to record the metric
                self.call_duration_context.__exit__(None, None, None)
                self.logger.debug(f"[{self.current_call_sid or 'N/A'}] Finished call duration tracking - {disconnect_reason}")

                # Track call ended event
                if self.current_call_sid and self.current_phone_number:
                    import asyncio
                    asyncio.create_task(
                        self.analytics_service.track_call_ended_async(
                            call_sid=self.current_call_sid,
                            phone_number=self.current_phone_number,
                            duration_seconds=duration_seconds,
                            disconnect_reason=disconnect_reason
                        )
                    )
            except Exception as e:
                self.logger.error(f"Error finishing call duration tracking: {e}")
            finally:
                self.call_duration_context = None

    async def _check_call_duration_and_hangup_if_critical(self):
        """Check if call duration has exceeded critical threshold and hangup if necessary."""
        if self.websocket_creation_time and self.current_call_sid:
            import time

            current_duration_ms = (time.time() - self.websocket_creation_time) * 1000
            critical_threshold = latency_tracker.thresholds.get_critical_threshold(OperationType.CALL_DURATION)

            if current_duration_ms >= critical_threshold:
                self.logger.warning(f"[{self.current_call_sid}] Call duration {current_duration_ms:.0f}ms exceeded critical threshold {critical_threshold:.0f}ms. Hanging up automatically.")

                metric = LatencyMetric(
                    operation_type=OperationType.CALL_DURATION,
                    operation_name="critical_duration_hangup",
                    latency_ms=current_duration_ms,
                    status=OperationStatus.SUCCESS,
                    call_sid=self.current_call_sid,
                    phone_number=self.current_phone_number,
                    provider="twilio",
                    error_message=None,
                    metadata={"tracking_method": "critical_threshold_check", "disconnect_reason": "critical_duration_exceeded", "threshold_exceeded": critical_threshold},
                )
                metric.criticality = "critical"
                latency_tracker.add_metric(metric)

                # Trigger hangup through the incoming audio manager
                if self.incoming_audio_processing:
                    await self.incoming_audio_processing._hangup_call_async()

                return True
        return False

    async def handle_websocket_all_receieved_events_async(self, calling_phone_number: str, call_sid: str) -> None:
        """Main method: handle a full audio conversation with I/O Twilio streams on a WebSocket."""
        if not self.websocket:
            self.logger.error("WebSocket not set, cannot handle WebSocket connection.")
            return

        self.logger.info(f"WebSocket handler started for {self.websocket.client.host}:{self.websocket.client.port}")

        # Store the caller's phone number and call SID so we can retrieve them later
        self.incoming_audio_processing.set_call_sid(call_sid)
        self.incoming_audio_processing.set_phone_number(calling_phone_number, call_sid)
        self._start_call_duration_tracking(call_sid, calling_phone_number)

        # Track call started event
        call_type = "outgoing" if self.is_outgoing_call else "incoming"
        await self.analytics_service.track_call_started_async(
            call_sid=call_sid,
            phone_number=calling_phone_number,
            call_type=call_type,
            provider=self.phone_provider.provider_type.value
        )

        self.outgoing_audio_processing.run_background_streaming_worker()
        self.logger.info("Audio stream manager initialized and started with optimized parameters")

        # Main loop to handle WebSocket events
        try:
            while True:
                try:
                    msg = await self.websocket.receive_text()
                    data = json.loads(msg)
                    if data is None:
                        continue
                except WebSocketDisconnect as disconnect_err:
                    self.logger.info(f"WebSocket disconnected: {self.websocket.client.host}:{self.websocket.client.port} - Code: {disconnect_err.code}")
                    self._finish_call_duration_tracking("websocket_disconnect")
                    break

                # Parse event using provider
                parsed_event = self.phone_provider.parse_websocket_event(data)
                event = parsed_event.get("event")

                if event == "connected":
                    self._handle_connected_event()
                elif event == "start":
                    await self._handle_start_event_async(parsed_event)
                elif event == "media":
                    await self._handle_media_event_async(parsed_event)
                elif event == "stop":
                    await self._handle_stop_event_async()
                    return
                elif event == "mark":
                    self._handle_mark_event(parsed_event)
                else:
                    self.logger.warning(f"Received unknown event type: {event}")

        except Exception as e:
            self.logger.error(f"Unhandled error in WebSocket handler: {e}", exc_info=True)
            self._finish_call_duration_tracking("websocket_error")
        finally:
            await self.outgoing_audio_processing.stop_background_streaming_worker_async()
            if self.current_stream and self.current_stream in self.stream_states:
                self.logger.warning(f"Cleaning up state for stream {self.current_stream} due to handler exit/error.")
                del self.stream_states[self.current_stream]
            # Ensure call duration tracking is finished in case it wasn't already
            if self.call_duration_context:
                self._finish_call_duration_tracking("websocket_cleanup")
            self.logger.info(f"WebSocket handler finished for {self.websocket.client.host}:{self.websocket.client.port} (Stream: {self.current_stream})")

    def _handle_connected_event(self):
        """Handle the 'connected' event from phone provider."""
        self.logger.info(f"{self.phone_provider.provider_type.value.title()} WebSocket connected")

    async def _handle_start_event_async(self, parsed_start_data: dict) -> str:
        """Handle the 'start' event from phone provider which begins a new call."""
        call_id = parsed_start_data.get("call_id", "N.C")
        stream_id = parsed_start_data.get("stream_id", "N.C")

        if self.is_outgoing_call:
            # For outgoing calls, play welcome message immediately
            await self._handle_outgoing_call_start_async(call_id, stream_id)
        else:
            # For incoming calls, use normal graph-based initialization
            await self.incoming_audio_processing.init_conversation_async(call_id, stream_id)

        self.outgoing_audio_processing.update_stream_sid(stream_id)
        return stream_id

    async def _handle_outgoing_call_start_async(self, call_id: str, stream_id: str) -> None:
        """Handle the start of an outgoing call by playing the welcome message."""
        from agents.text_registry import TextRegistry

        self.logger.info(f"Starting outgoing call - CallSid: {call_id}, StreamSid: {stream_id}")

        # Set basic call info
        self.incoming_audio_processing.set_call_sid(call_id)
        self.incoming_audio_processing.set_stream_sid(stream_id)

        # Play the outgoing call welcome message
        welcome_text = TextRegistry.outgoing_call_welcome_text
        self.logger.info(f"Playing outgoing call welcome message: {welcome_text}")

        # Queue the welcome message for TTS and playback
        await self.outgoing_audio_processing.queue_text_to_speech_async(welcome_text)

    async def _handle_media_event_async(self, parsed_media_data: dict) -> None:
        """Handle the 'media' event from phone provider which contains audio data."""
        # Process the media event - pass the raw data to maintain compatibility
        await self.incoming_audio_processing.process_incoming_data_async(parsed_media_data.get("raw_data", parsed_media_data))

        # Periodically check call duration (every 100 media events ~= every 2-3 seconds)
        self.media_event_counter += 1
        if self.media_event_counter % 100 == 0:
            hangup_triggered = await self._check_call_duration_and_hangup_if_critical()
            if hangup_triggered:
                return  # Stop processing if hangup was triggered

    def _is_websocket_connected(self) -> bool:
        """Check if the websocket is still connected"""
        if not self.websocket:
            return False
        try:
            if hasattr(self.websocket, "client_state"):
                if hasattr(self.websocket.client_state, "CONNECTED"):
                    return True
                if isinstance(self.websocket.client_state, str):
                    return "connect" in self.websocket.client_state.lower()
                return True
            if hasattr(self.websocket, "closed"):
                return not self.websocket.closed
            return True
        except Exception as e:
            self.logger.error(f"Error checking websocket connection: {e}")
            return True

    async def _handle_stop_event_async(self):
        """Handle the stop event from Twilio which ends a call"""
        if not self.current_stream:
            self.logger.error("Received stop event but no active stream")
            return

        self.logger.info(f"Received stop event for stream: {self.current_stream}")

        # Finish call duration tracking for normal stop event
        self._finish_call_duration_tracking("twilio_stop_event")

        if self.current_stream in self.stream_states:
            del self.stream_states[self.current_stream]
            self.logger.info(f"Cleaned up state for stream {self.current_stream}")
        else:
            self.logger.error(f"Received stop for unknown or already cleaned stream: {self.current_stream}")

        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                self.logger.error(f"Error closing websocket: {e}")

        self.current_stream = None
        self.incoming_audio_processing.set_call_sid(None)
        self.logger.info("Reset AudioProcessing stream SID as call ended")

    def _handle_mark_event(self, parsed_mark_data):
        mark_name = parsed_mark_data.get("name")
        self.logger.debug(f"Received mark event: {mark_name} for stream {self.current_stream}")


class PhoneCallWebsocketEventsHandlerFactory:
    websocket_events_handler_instance: PhoneCallWebsocketEventsHandler | None = None

    def __init__(self):
        self.build_new_phone_call_websocket_events_handler()

    def build_new_phone_call_websocket_events_handler(self, websocket: WebSocket | None = None, provider: PhoneProvider | None = None, is_outgoing: bool = False):
        if not self.websocket_events_handler_instance:
            self.websocket_events_handler_instance = PhoneCallWebsocketEventsHandler(websocket=websocket, phone_provider=provider, is_outgoing=is_outgoing)

    def get_new_phone_call_websocket_events_handler(self, websocket: WebSocket | None = None, provider: PhoneProvider | None = None, is_outgoing: bool = False):
        self.build_new_phone_call_websocket_events_handler(provider=provider, is_outgoing=is_outgoing)
        websocket_events_handler_to_return: PhoneCallWebsocketEventsHandler = self.websocket_events_handler_instance
        # Set the websocket for the handler
        websocket_events_handler_to_return.set_websocket(websocket)
        self.websocket_events_handler_instance = None
        return websocket_events_handler_to_return
