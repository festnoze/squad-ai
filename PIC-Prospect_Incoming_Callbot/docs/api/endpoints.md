# API Endpoints

The PIC Prospect Incoming Callbot exposes several FastAPI endpoints for handling phone calls, WebSocket connections, testing, and accessing logs. This document details all available endpoints and their usage.

## API Router Structure

The application uses FastAPI routers to organize endpoints:

- **Callbot Router** (`app/routers/callbot_router.py`) - Main Twilio webhooks and WebSocket connections
- **Logs Router** (`app/routers/logs_router.py`) - Access to application logs
- **Test Router** (`app/routers/test_router.py`) - Testing endpoints for parallel call simulation

## Callbot Endpoints

### Incoming Call Webhook

**Endpoint**: `POST /api/callbot/incoming-call`

**Purpose**: Handle incoming calls from Twilio

**Request Format** (Twilio TwiML):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://your-domain.com/api/callbot/audio-stream" />
    </Connect>
</Response>
```

**Response**: TwiML response with WebSocket stream connection

**Implementation**:
```python
@router.post("/incoming-call")
async def handle_incoming_call(request: Request) -> Response:
    # Parse Twilio webhook data
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    from_number = form_data.get("From")
    to_number = form_data.get("To")

    # Generate TwiML response with WebSocket stream
    twiml_response = generate_stream_twiml_response(call_sid)
    return Response(content=twiml_response, media_type="application/xml")
```

### Call Status Webhook

**Endpoint**: `POST /api/callbot/call-status`

**Purpose**: Receive call status updates from Twilio

**Parameters**:
- `CallSid`: Unique call identifier
- `CallStatus`: Current call status (ringing, in-progress, completed, etc.)
- `Duration`: Call duration in seconds (if completed)

**Response**: HTTP 200 OK

### Audio Stream WebSocket

**Endpoint**: `WS /api/callbot/audio-stream`

**Purpose**: Handle real-time audio streaming with Twilio

**Connection Flow**:
1. Twilio establishes WebSocket connection
2. Bi-directional audio streaming begins
3. Audio processed through speech pipeline
4. Responses generated and streamed back

**Message Types**:
```json
// Incoming audio from Twilio
{
    "event": "media",
    "streamSid": "MZ123...",
    "media": {
        "track": "inbound",
        "chunk": "1",
        "timestamp": "1234567890",
        "payload": "base64_audio_data"
    }
}

// Outgoing audio to Twilio
{
    "event": "media",
    "streamSid": "MZ123...",
    "media": {
        "payload": "base64_audio_data"
    }
}
```

**Implementation**:
```python
@router.websocket("/audio-stream")
async def audio_stream_websocket(websocket: WebSocket):
    await websocket.accept()

    # Initialize audio managers
    incoming_manager = IncomingAudioManager(websocket)
    outgoing_manager = OutgoingAudioManager(websocket)

    # Start audio processing loop
    await process_audio_stream_async(websocket, incoming_manager, outgoing_manager)
```

## Logs Endpoints

### Latest Logs

**Endpoint**: `GET /api/logs/latest`

**Purpose**: Retrieve the most recent application logs

**Parameters**:
- `lines`: Number of log lines to return (default: 100, max: 1000)
- `level`: Filter by log level (DEBUG, INFO, WARNING, ERROR)
- `since`: Return logs since timestamp (ISO 8601 format)

**Response**:
```json
{
    "logs": [
        {
            "timestamp": "2024-01-01T12:00:00Z",
            "level": "INFO",
            "message": "Call initiated from +1234567890",
            "call_id": "call_123",
            "module": "callbot_router"
        }
    ],
    "total_lines": 45,
    "filtered_lines": 45
}
```

**Usage Example**:
```bash
# Get latest 50 log entries
curl "http://localhost:8080/api/logs/latest?lines=50"

# Get only ERROR level logs
curl "http://localhost:8080/api/logs/latest?level=ERROR"

# Get logs since specific timestamp
curl "http://localhost:8080/api/logs/latest?since=2024-01-01T10:00:00Z"
```

### Log Stream

**Endpoint**: `WS /api/logs/stream`

**Purpose**: Real-time log streaming via WebSocket

**Connection**: WebSocket connection for live log monitoring

**Message Format**:
```json
{
    "timestamp": "2024-01-01T12:00:00Z",
    "level": "INFO",
    "message": "Processing audio chunk",
    "call_id": "call_123",
    "module": "audio_manager"
}
```

**Usage**:
```javascript
const ws = new WebSocket('ws://localhost:8080/api/logs/stream');
ws.onmessage = function(event) {
    const logEntry = JSON.parse(event.data);
    console.log(`[${logEntry.level}] ${logEntry.message}`);
};
```

## Test Endpoints

### Simulate Parallel Calls

**Endpoint**: `POST /api/test/simulate-calls`

**Purpose**: Simulate multiple parallel incoming calls for load testing

**Request Body**:
```json
{
    "call_count": 5,
    "duration_seconds": 30,
    "concurrent": true,
    "call_scenario": "lead_qualification",
    "caller_profiles": [
        {
            "phone_number": "+1234567890",
            "name": "John Doe",
            "company": "Acme Corp"
        }
    ]
}
```

**Response**:
```json
{
    "simulation_id": "sim_123",
    "calls_initiated": 5,
    "estimated_duration": 30,
    "status": "running"
}
```

### Simulation Status

**Endpoint**: `GET /api/test/simulation/{simulation_id}`

**Purpose**: Check status of running call simulation

**Response**:
```json
{
    "simulation_id": "sim_123",
    "status": "completed",
    "calls_completed": 5,
    "calls_failed": 0,
    "average_duration": 28.5,
    "metrics": {
        "successful_qualifications": 3,
        "appointments_scheduled": 2,
        "average_response_time": 1.2
    }
}
```

### Load Test Results

**Endpoint**: `GET /api/test/load-results`

**Purpose**: Retrieve load testing results and performance metrics

**Response**:
```json
{
    "test_runs": [
        {
            "test_id": "load_001",
            "timestamp": "2024-01-01T12:00:00Z",
            "concurrent_calls": 10,
            "duration_minutes": 5,
            "success_rate": 0.95,
            "average_latency_ms": 250,
            "error_count": 2
        }
    ],
    "summary": {
        "max_concurrent_calls": 15,
        "best_success_rate": 0.98,
        "average_latency_ms": 275
    }
}
```

## Health and Status Endpoints

### Application Health

**Endpoint**: `GET /health`

**Purpose**: Application health check

**Response**:
```json
{
    "status": "healthy",
    "timestamp": "2024-01-01T12:00:00Z",
    "version": "1.0.0",
    "uptime_seconds": 3600,
    "active_calls": 2
}
```

### Service Status

**Endpoint**: `GET /status`

**Purpose**: Detailed service status including external integrations

**Response**:
```json
{
    "application": {
        "status": "running",
        "version": "1.0.0",
        "environment": "production"
    },
    "services": {
        "twilio": {
            "status": "connected",
            "last_check": "2024-01-01T12:00:00Z"
        },
        "google_cloud": {
            "status": "connected",
            "speech_api": "available",
            "tts_api": "available"
        },
        "salesforce": {
            "status": "connected",
            "api_version": "58.0"
        },
        "calendar": {
            "provider": "salesforce",
            "status": "connected"
        }
    },
    "metrics": {
        "active_calls": 3,
        "total_calls_today": 127,
        "average_call_duration": 180,
        "success_rate": 0.94
    }
}
```

## WebSocket Event Handling

### Connection Management

**Implementation**: `app/phone_call_websocket_events_handler.py`

**Key Features**:
- Connection lifecycle management
- Audio stream processing
- Error handling and recovery
- State synchronization

**Event Types**:
```python
class WebSocketEvent:
    CONNECTED = "connected"
    START = "start"
    MEDIA = "media"
    STOP = "stop"
    ERROR = "error"
    MARK = "mark"
```

**Event Handlers**:
```python
async def handle_websocket_event_async(event_type: str, event_data: dict, websocket: WebSocket):
    if event_type == WebSocketEvent.START:
        await handle_stream_start_async(event_data, websocket)
    elif event_type == WebSocketEvent.MEDIA:
        await handle_audio_media_async(event_data, websocket)
    elif event_type == WebSocketEvent.STOP:
        await handle_stream_stop_async(event_data, websocket)
```

## Error Handling

### Standard Error Responses

**HTTP Error Format**:
```json
{
    "error": {
        "code": "INVALID_REQUEST",
        "message": "Missing required parameter: CallSid",
        "details": {
            "parameter": "CallSid",
            "expected_type": "string"
        }
    },
    "timestamp": "2024-01-01T12:00:00Z",
    "request_id": "req_123"
}
```

**Common Error Codes**:
- `INVALID_REQUEST`: Malformed request data
- `AUTHENTICATION_FAILED`: Invalid credentials
- `RATE_LIMIT_EXCEEDED`: Too many requests
- `SERVICE_UNAVAILABLE`: External service failure
- `INTERNAL_ERROR`: Unexpected server error

### WebSocket Error Handling

**Error Message Format**:
```json
{
    "event": "error",
    "error": {
        "code": "AUDIO_PROCESSING_FAILED",
        "message": "Failed to process audio chunk",
        "recoverable": true
    }
}
```

## Rate Limiting

**Implementation**: Applied to all endpoints with different limits

**Limits**:
- `/api/callbot/*`: 100 requests per minute per IP
- `/api/logs/*`: 60 requests per minute per IP
- `/api/test/*`: 10 requests per minute per IP

**Rate Limit Headers**:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640995200
```

## Authentication

### Webhook Authentication

**Twilio Webhooks**: Validated using Twilio signature verification

```python
def validate_twilio_signature(request: Request) -> bool:
    signature = request.headers.get('X-Twilio-Signature')
    url = str(request.url)
    body = request.body

    return twilio_validator.validate(url, body, signature)
```

### API Authentication

**Development**: No authentication required
**Production**: Bearer token authentication for sensitive endpoints

## OpenAPI Documentation

**Swagger UI**: Available at `http://localhost:8080/docs`
**ReDoc**: Available at `http://localhost:8080/redoc`
**OpenAPI JSON**: Available at `http://localhost:8080/openapi.json`

The interactive documentation includes:
- Endpoint descriptions and examples
- Request/response schemas
- Authentication requirements
- Rate limiting information
- WebSocket connection details

This comprehensive API provides all necessary endpoints for operating the callbot system, monitoring its performance, and testing its functionality.