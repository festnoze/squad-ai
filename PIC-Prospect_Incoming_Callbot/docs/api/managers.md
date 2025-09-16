# Managers API Reference

The PIC Prospect Incoming Callbot uses manager classes to handle audio processing, conversation flow, and external service coordination. This document provides detailed API reference for all manager components.

## Audio Managers

### Incoming Audio Manager

**File**: `app/managers/incoming_audio_manager.py`

**Purpose**: Handle real-time audio streams from Twilio WebSocket connections

```python
class IncomingAudioManager:
    def __init__(self, websocket: WebSocket, config: AudioConfig):
        self.websocket = websocket
        self.config = config
        self.audio_buffer = AudioBuffer()
        self.vad = WebRTCVoiceActivityDetector()
        self.stt_client = SpeechToTextClient()

    async def process_audio_stream_async(self) -> None:
        """Main audio processing loop"""

    async def handle_audio_chunk_async(self, audio_data: bytes) -> Optional[str]:
        """Process individual audio chunk"""

    async def detect_speech_end_async(self, audio_chunk: bytes) -> bool:
        """Detect end of speech using VAD"""
```

#### Key Methods

```python
async def initialize_audio_processing_async(self) -> None:
    """Initialize audio processing components"""
    self.audio_buffer.configure(
        sample_rate=self.config.sample_rate,
        chunk_size=self.config.chunk_size,
        max_buffer_duration=self.config.max_buffer_duration
    )

    await self.stt_client.initialize_async(
        language_code=self.config.language_code,
        model=self.config.speech_model
    )

async def process_incoming_audio_async(self, twilio_payload: str) -> AudioProcessingResult:
    """
    Process incoming audio from Twilio WebSocket

    Args:
        twilio_payload: Base64 encoded audio data from Twilio

    Returns:
        AudioProcessingResult containing transcribed text and metadata
    """
    # Decode base64 audio data
    audio_bytes = base64.b64decode(twilio_payload)

    # Add to buffer
    self.audio_buffer.add_chunk(audio_bytes)

    # Voice activity detection
    is_speech = self.vad.detect_speech(audio_bytes)

    if is_speech:
        # Process through speech-to-text
        transcription = await self.stt_client.transcribe_streaming_async(audio_bytes)

        if transcription.is_final:
            return AudioProcessingResult(
                transcribed_text=transcription.text,
                confidence=transcription.confidence,
                is_final=True,
                audio_duration_ms=transcription.audio_duration_ms
            )

    return AudioProcessingResult(is_final=False)

async def cleanup_audio_resources_async(self) -> None:
    """Clean up audio processing resources"""
    await self.stt_client.close_async()
    self.audio_buffer.clear()
    self.vad.reset()
```

#### Audio Buffer Management

```python
class AudioBuffer:
    def __init__(self, max_duration_seconds: int = 30):
        self.max_duration = max_duration_seconds
        self.chunks: List[AudioChunk] = []
        self.total_duration = 0

    def add_chunk(self, audio_data: bytes, timestamp: Optional[datetime] = None) -> None:
        """Add audio chunk to buffer"""
        chunk = AudioChunk(
            data=audio_data,
            timestamp=timestamp or datetime.utcnow(),
            size_bytes=len(audio_data)
        )

        self.chunks.append(chunk)
        self._enforce_max_duration()

    def get_buffered_audio(self, duration_seconds: Optional[float] = None) -> bytes:
        """Get buffered audio data"""
        if duration_seconds:
            return self._get_audio_for_duration(duration_seconds)
        return b''.join(chunk.data for chunk in self.chunks)

    def clear(self) -> None:
        """Clear audio buffer"""
        self.chunks.clear()
        self.total_duration = 0
```

### Outgoing Audio Manager

**File**: `app/managers/outgoing_audio_manager.py`

**Purpose**: Manage audio response generation and delivery to Twilio

```python
class OutgoingAudioManager:
    def __init__(self, websocket: WebSocket, config: AudioConfig):
        self.websocket = websocket
        self.config = config
        self.tts_client = TextToSpeechClient()
        self.audio_cache = PreGeneratedAudioCache()
        self.response_queue = asyncio.Queue()

    async def generate_and_send_response_async(self, text: str, voice_config: VoiceConfig) -> None:
        """Generate audio response and send to Twilio"""

    async def stream_audio_to_twilio_async(self, audio_data: bytes) -> None:
        """Stream audio data to Twilio WebSocket"""

    async def manage_response_queue_async(self) -> None:
        """Manage queue of pending audio responses"""
```

#### Response Generation

```python
async def create_audio_response_async(
    self,
    response_text: str,
    priority: ResponsePriority = ResponsePriority.NORMAL,
    use_cache: bool = True
) -> AudioResponse:
    """
    Create audio response from text

    Args:
        response_text: Text to convert to speech
        priority: Response priority for queue management
        use_cache: Whether to use pre-generated audio cache

    Returns:
        AudioResponse object with audio data and metadata
    """
    # Check pre-generated audio cache first
    if use_cache:
        cached_audio = await self.audio_cache.get_audio_async(response_text)
        if cached_audio:
            logger.info(f"Using cached audio for: {response_text[:50]}...")
            return AudioResponse(
                audio_data=cached_audio.data,
                format=cached_audio.format,
                duration_ms=cached_audio.duration_ms,
                source=AudioSource.CACHE
            )

    # Generate using TTS
    tts_result = await self.tts_client.synthesize_async(
        text=response_text,
        voice_config=self.config.voice_config
    )

    return AudioResponse(
        audio_data=tts_result.audio_data,
        format=tts_result.audio_format,
        duration_ms=tts_result.duration_ms,
        source=AudioSource.TTS
    )

async def send_audio_to_twilio_async(self, audio_response: AudioResponse) -> None:
    """Send audio response to Twilio WebSocket"""
    # Convert to Twilio format
    twilio_audio = self._convert_to_twilio_format(audio_response.audio_data)

    # Chunk audio for streaming
    chunks = self._chunk_audio_data(twilio_audio, chunk_size_ms=100)

    for chunk in chunks:
        twilio_message = {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {
                "payload": base64.b64encode(chunk).decode('utf-8')
            }
        }

        await self.websocket.send_text(json.dumps(twilio_message))

        # Small delay for streaming
        await asyncio.sleep(0.1)
```

#### Pre-generated Audio Cache

```python
class PreGeneratedAudioCache:
    def __init__(self, cache_directory: str):
        self.cache_directory = Path(cache_directory)
        self.index = self._load_audio_index()

    async def get_audio_async(self, text: str) -> Optional[CachedAudio]:
        """Get pre-generated audio for text"""
        text_hash = self._generate_text_hash(text)

        if text_hash in self.index:
            audio_file = self.cache_directory / self.index[text_hash]['file']
            if audio_file.exists():
                audio_data = audio_file.read_bytes()
                return CachedAudio(
                    data=audio_data,
                    format=AudioFormat.PCM,
                    duration_ms=self.index[text_hash]['duration_ms']
                )

        return None

    async def cache_audio_async(self, text: str, audio_data: bytes, duration_ms: int) -> None:
        """Cache audio data for future use"""
        text_hash = self._generate_text_hash(text)
        filename = f"{text_hash}.pcm"
        file_path = self.cache_directory / filename

        # Save audio file
        file_path.write_bytes(audio_data)

        # Update index
        self.index[text_hash] = {
            'text': text,
            'file': filename,
            'duration_ms': duration_ms,
            'created_at': datetime.utcnow().isoformat()
        }

        await self._save_audio_index_async()
```

## Conversation Manager

**File**: `app/managers/conversation_manager.py`

**Purpose**: Coordinate conversation flow between agents and manage state

```python
class ConversationManager:
    def __init__(self, config: ConversationConfig):
        self.config = config
        self.agent_graph = AgentGraph(config.agent_config)
        self.state_manager = StateManager()
        self.active_conversations: Dict[str, PhoneConversationState] = {}

    async def start_conversation_async(self, call_id: str, caller_info: CallerInfo) -> PhoneConversationState:
        """Initialize new conversation"""

    async def process_user_input_async(self, call_id: str, user_input: str) -> ConversationResponse:
        """Process user input through agent workflow"""

    async def end_conversation_async(self, call_id: str, reason: str) -> ConversationSummary:
        """End conversation and generate summary"""
```

### Conversation Flow

```python
async def handle_conversation_turn_async(
    self,
    call_id: str,
    user_input: str,
    audio_metadata: AudioMetadata
) -> ConversationResponse:
    """
    Handle a single conversation turn

    Args:
        call_id: Unique identifier for the call
        user_input: Transcribed user input
        audio_metadata: Audio processing metadata

    Returns:
        ConversationResponse with agent response and actions
    """
    # Get current conversation state
    state = await self.get_conversation_state_async(call_id)

    # Update state with user input
    state = self._update_state_with_user_input(state, user_input, audio_metadata)

    # Process through agent graph
    updated_state = await self.agent_graph.execute_async(state)

    # Store updated state
    await self.state_manager.save_state_async(call_id, updated_state)

    # Generate response
    response = ConversationResponse(
        agent_response=updated_state["current_agent_response"],
        next_action=updated_state.get("next_action"),
        conversation_phase=updated_state["current_phase"],
        confidence_score=updated_state.get("confidence_score", 1.0),
        requires_followup=updated_state.get("requires_followup", False)
    )

    return response

async def handle_conversation_interruption_async(
    self,
    call_id: str,
    interruption_type: InterruptionType
) -> InterruptionResponse:
    """Handle conversation interruptions (silence, background noise, etc.)"""
    state = await self.get_conversation_state_async(call_id)

    if interruption_type == InterruptionType.LONG_SILENCE:
        # Handle long silence - prompt user
        return InterruptionResponse(
            action=InterruptionAction.PROMPT_USER,
            message="Are you still there? How can I help you?"
        )
    elif interruption_type == InterruptionType.BACKGROUND_NOISE:
        # Handle background noise - request clarification
        return InterruptionResponse(
            action=InterruptionAction.REQUEST_CLARIFICATION,
            message="I'm having trouble hearing you. Could you repeat that?"
        )

    return InterruptionResponse(action=InterruptionAction.CONTINUE)
```

### State Management

```python
class StateManager:
    def __init__(self, storage_backend: StorageBackend):
        self.storage = storage_backend

    async def create_initial_state_async(self, call_id: str, caller_info: CallerInfo) -> PhoneConversationState:
        """Create initial conversation state"""
        initial_state = PhoneConversationState(
            call_id=call_id,
            caller_phone=caller_info.phone_number,
            start_time=datetime.utcnow(),
            current_phase=ConversationPhase.GREETING,
            conversation_history=[],
            current_user_input="",
            current_agent_response="",
            prospect_info=ProspectInfo(),
            qualification_score=0.0,
            qualification_complete=False,
            appointment_preferences=AppointmentPreferences(),
            appointment_scheduled=None,
            salesforce_lead_id=None,
            calendar_event_id=None,
            current_agent=AgentType.LEAD_AGENT,
            agent_context={},
            next_action=None
        )

        await self.storage.save_state_async(call_id, initial_state)
        return initial_state

    async def update_conversation_phase_async(
        self,
        call_id: str,
        new_phase: ConversationPhase
    ) -> PhoneConversationState:
        """Update conversation phase"""
        state = await self.storage.load_state_async(call_id)
        if state:
            state["current_phase"] = new_phase
            state["agent_context"]["phase_transition_time"] = datetime.utcnow()
            await self.storage.save_state_async(call_id, state)

        return state
```

## Service Managers

### Calendar Manager

**File**: `app/managers/calendar_manager.py`

**Purpose**: Manage calendar operations across multiple providers

```python
class CalendarManager:
    def __init__(self, config: CalendarConfig):
        self.config = config
        self.calendar_client = self._create_calendar_client()

    def _create_calendar_client(self) -> CalendarClientInterface:
        """Create appropriate calendar client based on configuration"""
        if self.config.provider == "google":
            return GoogleCalendarClient(self.config.google_config)
        elif self.config.provider == "salesforce":
            return SalesforceCalendarClient(self.config.salesforce_config)
        else:
            raise ValueError(f"Unsupported calendar provider: {self.config.provider}")

    async def find_available_times_async(
        self,
        start_date: datetime,
        end_date: datetime,
        duration_minutes: int = 30
    ) -> List[AvailableTime]:
        """Find available appointment times"""

    async def schedule_appointment_async(self, appointment_request: AppointmentRequest) -> SchedulingResult:
        """Schedule new appointment"""

    async def cancel_appointment_async(self, appointment_id: str) -> bool:
        """Cancel existing appointment"""
```

### CRM Manager

**File**: `app/managers/crm_manager.py`

**Purpose**: Manage CRM operations and data synchronization

```python
class CRMManager:
    def __init__(self, config: CRMConfig):
        self.config = config
        self.salesforce_client = SalesforceApiClient(config.salesforce_config)

    async def create_or_update_prospect_async(self, prospect_info: ProspectInfo, call_details: CallDetails) -> CRMRecord:
        """Create new prospect or update existing one"""

    async def log_conversation_async(self, call_id: str, conversation_summary: ConversationSummary) -> ActivityRecord:
        """Log conversation in CRM system"""

    async def update_lead_status_async(self, lead_id: str, new_status: LeadStatus, reason: str) -> bool:
        """Update lead status in CRM"""

    async def sync_appointment_to_crm_async(self, appointment: AppointmentDetails, lead_id: str) -> bool:
        """Sync appointment details to CRM"""
```

## Performance and Monitoring

### Performance Manager

```python
class PerformanceManager:
    def __init__(self):
        self.metrics_collector = MetricsCollector()

    async def track_response_time_async(self, operation: str, start_time: float) -> None:
        """Track operation response time"""
        duration = time.time() - start_time
        await self.metrics_collector.record_metric_async(
            "response_time",
            duration,
            tags={"operation": operation}
        )

    async def track_audio_quality_async(self, quality_metrics: AudioQualityMetrics) -> None:
        """Track audio quality metrics"""
        await self.metrics_collector.record_audio_quality_async(quality_metrics)

    async def get_performance_summary_async(self, time_range: TimeRange) -> PerformanceSummary:
        """Get performance summary for time range"""
        return await self.metrics_collector.get_summary_async(time_range)
```

### Error Handling

All managers implement consistent error handling:

```python
class ManagerError(Exception):
    """Base exception for manager errors"""
    pass

class AudioProcessingError(ManagerError):
    """Audio processing related errors"""
    pass

class ConversationError(ManagerError):
    """Conversation management errors"""
    pass

class ExternalServiceError(ManagerError):
    """External service integration errors"""
    pass

# Error handling decorator
def handle_manager_errors(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            # Handle graceful degradation
            raise ManagerError(f"Operation failed: {str(e)}") from e
    return wrapper
```

This comprehensive manager API provides robust, scalable components for handling all aspects of the callbot system, from real-time audio processing to external service coordination.