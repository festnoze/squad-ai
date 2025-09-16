# Testing

The PIC Prospect Incoming Callbot includes comprehensive testing strategies covering unit tests, integration tests, and load testing. This document describes the testing approach, frameworks, and best practices.

## Testing Strategy

### Test Structure
```
tests/
├── agents/                 # Agent system tests
│   ├── test_lead_agent.py
│   ├── test_calendar_agent.py
│   ├── test_sf_agent.py
│   └── test_agent_integration.py
├── api_client/            # External API client tests
│   ├── test_salesforce_api_client.py
│   ├── test_google_calendar_client.py
│   └── test_studi_rag_client.py
├── managers/              # Manager component tests
│   ├── test_incoming_audio_manager.py
│   ├── test_outgoing_audio_manager.py
│   └── test_conversation_manager.py
├── speech/                # Speech processing tests
│   ├── test_speech_to_text.py
│   └── test_text_to_speech.py
├── utils/                 # Utility function tests
│   ├── test_envvar.py
│   └── test_google_calendar_auth.py
├── fixtures/              # Test fixtures and data
└── conftest.py           # Pytest configuration
```

## Testing Frameworks

### Core Testing Stack
- **pytest**: Primary testing framework
- **pytest-asyncio**: Async test support
- **pytest-mock**: Mocking capabilities
- **parameterized**: Parameterized test cases
- **httpx**: HTTP client testing
- **websockets**: WebSocket testing

### Installation
```bash
pip install pytest pytest-asyncio pytest-mock parameterized httpx websockets
```

## Running Tests

### Basic Test Commands
```bash
# Run all tests
pytest

# Run specific test directory
pytest tests/agents/

# Run specific test file
pytest tests/agents/test_lead_agent.py

# Run specific test method
pytest tests/agents/test_lead_agent.py::TestLeadAgent::test_qualify_prospect

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=app tests/

# Run with coverage report
pytest --cov=app --cov-report=html tests/
```

### Test Configuration
**File**: `pytest.ini`
```ini
[tool:pytest]
testpaths = tests
python_paths = app
asyncio_mode = auto
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Tests that take longer to run
    requires_external: Tests requiring external services

filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
```

## Unit Testing

### Agent Testing

**File**: `tests/agents/test_lead_agent.py`

```python
import pytest
from unittest.mock import AsyncMock, Mock, patch
from parameterized import parameterized

from app.agents.lead_agent import LeadAgent
from app.agents.phone_conversation_state_model import PhoneConversationState, ProspectInfo


class TestLeadAgent:
    @pytest.fixture
    async def lead_agent(self):
        """Create LeadAgent instance for testing"""
        config = Mock()
        config.llm_config = Mock()
        return LeadAgent(config)

    @pytest.fixture
    def sample_state(self):
        """Create sample conversation state"""
        return PhoneConversationState(
            call_id="test_call_123",
            caller_phone="+33123456789",
            start_time=datetime.utcnow(),
            current_phase=ConversationPhase.QUALIFICATION,
            conversation_history=[],
            current_user_input="Hello, I'm interested in your services",
            prospect_info=ProspectInfo(),
            qualification_score=0.0,
            qualification_complete=False,
            current_agent=AgentType.LEAD_AGENT,
            agent_context={}
        )

    @pytest.mark.asyncio
    async def test_qualify_prospect_success(self, lead_agent, sample_state):
        """Test successful prospect qualification"""
        # Mock LLM response
        with patch.object(lead_agent.llm, 'agenerate') as mock_llm:
            mock_llm.return_value = Mock()
            mock_llm.return_value.generations = [[Mock(text="High quality lead")]]

            # Test qualification
            result = await lead_agent.qualify_prospect_async(sample_state)

            assert result.qualification_complete == True
            assert result.qualification_score > 0
            mock_llm.assert_called_once()

    @parameterized.expand([
        ("CEO", "Tech Company", "urgent", 9.0),
        ("Manager", "Small Business", "this month", 7.0),
        ("Employee", "Unknown", "someday", 3.0),
    ])
    @pytest.mark.asyncio
    async def test_qualification_scoring(self, lead_agent, job_title, company, timeline, expected_score):
        """Test qualification scoring with various inputs"""
        prospect_info = ProspectInfo(
            job_title=job_title,
            company=company,
            timeline=timeline,
            budget_indicated=True
        )

        score = await lead_agent.calculate_qualification_score_async(prospect_info)
        assert abs(score - expected_score) < 1.0  # Allow some variance

    @pytest.mark.asyncio
    async def test_extract_prospect_info(self, lead_agent):
        """Test prospect information extraction from conversation"""
        conversation_text = """
        Hello, my name is Jean Dupont from Acme Corp.
        I'm the CTO and we're looking for a solution urgently.
        You can reach me at jean@acme.com or 01.23.45.67.89.
        """

        with patch.object(lead_agent.llm, 'agenerate') as mock_llm:
            mock_response = {
                "name": "Jean Dupont",
                "company": "Acme Corp",
                "job_title": "CTO",
                "email": "jean@acme.com",
                "phone": "01.23.45.67.89",
                "timeline": "urgent"
            }
            mock_llm.return_value.generations = [[Mock(text=json.dumps(mock_response))]]

            result = await lead_agent.extract_prospect_info_async(conversation_text)

            assert result.name == "Jean Dupont"
            assert result.company == "Acme Corp"
            assert result.job_title == "CTO"
            assert result.email == "jean@acme.com"
```

### Audio Manager Testing

**File**: `tests/managers/test_incoming_audio_manager.py`

```python
import pytest
import asyncio
import base64
from unittest.mock import AsyncMock, Mock, patch

from app.managers.incoming_audio_manager import IncomingAudioManager
from app.speech.speech_to_text import AudioProcessingResult


class TestIncomingAudioManager:
    @pytest.fixture
    def audio_config(self):
        """Create audio configuration for testing"""
        config = Mock()
        config.sample_rate = 16000
        config.chunk_size = 1024
        config.language_code = "fr-FR"
        config.speech_model = "chirp_3_hd"
        return config

    @pytest.fixture
    async def audio_manager(self, audio_config):
        """Create IncomingAudioManager instance"""
        websocket = AsyncMock()
        return IncomingAudioManager(websocket, audio_config)

    @pytest.fixture
    def sample_audio_data(self):
        """Create sample audio data for testing"""
        # Generate sample PCM audio data (silence)
        sample_rate = 16000
        duration_ms = 100
        samples = int(sample_rate * duration_ms / 1000)
        audio_bytes = b'\x00\x00' * samples  # 16-bit silence
        return base64.b64encode(audio_bytes).decode('utf-8')

    @pytest.mark.asyncio
    async def test_process_audio_chunk_with_speech(self, audio_manager, sample_audio_data):
        """Test processing audio chunk with speech detected"""
        with patch.object(audio_manager.vad, 'detect_speech', return_value=True), \
             patch.object(audio_manager.stt_client, 'transcribe_streaming_async') as mock_stt:

            mock_stt.return_value = AudioProcessingResult(
                transcribed_text="Bonjour",
                confidence=0.95,
                is_final=True,
                audio_duration_ms=1000
            )

            result = await audio_manager.handle_audio_chunk_async(
                base64.b64decode(sample_audio_data)
            )

            assert result == "Bonjour"
            mock_stt.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_audio_chunk_no_speech(self, audio_manager, sample_audio_data):
        """Test processing audio chunk with no speech detected"""
        with patch.object(audio_manager.vad, 'detect_speech', return_value=False):
            result = await audio_manager.handle_audio_chunk_async(
                base64.b64decode(sample_audio_data)
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_audio_buffer_management(self, audio_manager):
        """Test audio buffer management"""
        # Add multiple audio chunks
        for i in range(10):
            chunk = b'\x00\x01' * 100
            audio_manager.audio_buffer.add_chunk(chunk)

        # Test buffer size management
        assert len(audio_manager.audio_buffer.chunks) <= audio_manager.audio_buffer.max_chunks

        # Test buffer cleanup
        audio_manager.audio_buffer.clear()
        assert len(audio_manager.audio_buffer.chunks) == 0
```

### API Client Testing

**File**: `tests/api_client/test_salesforce_api_client.py`

```python
import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx

from app.api_client.salesforce_api_client import SalesforceApiClient
from app.api_client.salesforce_user_client_interface import LeadRecord


class TestSalesforceApiClient:
    @pytest.fixture
    def sf_config(self):
        """Create Salesforce configuration"""
        return {
            'username': 'test@example.com',
            'password': 'password',
            'security_token': 'token',
            'domain': 'test',
            'api_version': '58.0'
        }

    @pytest.fixture
    async def sf_client(self, sf_config):
        """Create SalesforceApiClient instance"""
        with patch('simple_salesforce.Salesforce') as mock_sf:
            mock_sf.return_value.session_id = 'test_session'
            client = SalesforceApiClient(sf_config)
            await client.authenticate_async()
            return client

    @pytest.mark.asyncio
    async def test_authenticate_success(self, sf_config):
        """Test successful Salesforce authentication"""
        with patch('simple_salesforce.Salesforce') as mock_sf:
            mock_sf.return_value.session_id = 'test_session'

            client = SalesforceApiClient(sf_config)
            result = await client.authenticate_async()

            assert result is True
            assert client.is_authenticated

    @pytest.mark.asyncio
    async def test_create_lead_success(self, sf_client):
        """Test successful lead creation"""
        lead_data = {
            'FirstName': 'John',
            'LastName': 'Doe',
            'Company': 'Acme Corp',
            'Phone': '+33123456789',
            'Email': 'john@acme.com'
        }

        with patch.object(sf_client.sf.Lead, 'create') as mock_create:
            mock_create.return_value = {'id': 'lead_123', 'success': True}

            result = await sf_client.create_lead_async(lead_data)

            assert result.id == 'lead_123'
            assert result.company == 'Acme Corp'
            mock_create.assert_called_once_with(lead_data)

    @pytest.mark.asyncio
    async def test_create_lead_failure(self, sf_client):
        """Test lead creation failure handling"""
        lead_data = {'Company': 'Test Corp'}  # Missing required fields

        with patch.object(sf_client.sf.Lead, 'create') as mock_create:
            mock_create.side_effect = Exception("Required fields missing")

            with pytest.raises(Exception):
                await sf_client.create_lead_async(lead_data)

    @pytest.mark.asyncio
    async def test_find_existing_lead(self, sf_client):
        """Test finding existing lead by phone/email"""
        with patch.object(sf_client.sf, 'query') as mock_query:
            mock_query.return_value = {
                'records': [{
                    'Id': 'lead_456',
                    'FirstName': 'Jane',
                    'LastName': 'Smith',
                    'Company': 'Test Corp'
                }]
            }

            result = await sf_client.find_existing_lead_async(
                phone='+33123456789',
                email='jane@test.com'
            )

            assert result is not None
            assert result.id == 'lead_456'
```

## Integration Testing

### Agent Integration Testing

**File**: `tests/agents/test_agent_integration.py`

```python
import pytest
from unittest.mock import AsyncMock, Mock, patch

from app.agents.agents_graph import AgentGraph
from app.agents.phone_conversation_state_model import PhoneConversationState


class TestAgentIntegration:
    @pytest.fixture
    async def agent_graph(self):
        """Create AgentGraph for integration testing"""
        config = Mock()
        return AgentGraph(config)

    @pytest.mark.asyncio
    async def test_full_conversation_flow(self, agent_graph):
        """Test complete conversation flow through all agents"""
        # Create initial state
        initial_state = PhoneConversationState(
            call_id="integration_test",
            caller_phone="+33123456789",
            current_phase=ConversationPhase.GREETING,
            current_user_input="Hello, I'm interested in your services",
            current_agent=AgentType.LEAD_AGENT
        )

        # Mock external services
        with patch('app.agents.lead_agent.LeadAgent.process_async') as mock_lead, \
             patch('app.agents.calendar_agent.CalendarAgent.process_async') as mock_calendar, \
             patch('app.agents.sf_agent.SalesforceAgent.process_async') as mock_sf:

            # Configure mock responses
            mock_lead.return_value = initial_state.copy()
            mock_lead.return_value.update({
                'qualification_complete': True,
                'qualification_score': 8.0
            })

            mock_calendar.return_value = initial_state.copy()
            mock_calendar.return_value.update({
                'appointment_scheduled': True,
                'calendar_event_id': 'event_123'
            })

            mock_sf.return_value = initial_state.copy()
            mock_sf.return_value.update({
                'salesforce_lead_id': 'lead_456'
            })

            # Execute workflow
            final_state = await agent_graph.execute_async(initial_state)

            # Verify all agents were called
            mock_lead.assert_called_once()
            mock_calendar.assert_called_once()
            mock_sf.assert_called_once()

            # Verify final state
            assert final_state['qualification_complete'] is True
            assert final_state['appointment_scheduled'] is True
            assert final_state['salesforce_lead_id'] == 'lead_456'

    @pytest.mark.asyncio
    async def test_agent_transition_logic(self, agent_graph):
        """Test agent transition logic"""
        # Test transition from lead to calendar agent
        state = PhoneConversationState(
            qualification_complete=True,
            qualification_score=8.0,
            appointment_scheduled=None
        )

        next_agent = agent_graph.route_next_agent(state)
        assert next_agent == "calendar_agent"

        # Test transition from calendar to salesforce agent
        state.update({
            'appointment_scheduled': True,
            'salesforce_lead_id': None
        })

        next_agent = agent_graph.route_next_agent(state)
        assert next_agent == "salesforce_agent"

        # Test end condition
        state.update({'salesforce_lead_id': 'lead_123'})
        next_agent = agent_graph.route_next_agent(state)
        assert next_agent == "END"
```

### WebSocket Integration Testing

**File**: `tests/test_websocket_integration.py`

```python
import pytest
import json
import asyncio
from websockets import connect
from fastapi.testclient import TestClient

from app.api.startup import app


class TestWebSocketIntegration:
    @pytest.fixture
    def test_client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.mark.asyncio
    async def test_websocket_connection(self, test_client):
        """Test WebSocket connection establishment"""
        with test_client.websocket_connect("/api/callbot/audio-stream") as websocket:
            # Test connection
            assert websocket is not None

            # Test initial message
            data = websocket.receive_json()
            assert "event" in data

    @pytest.mark.asyncio
    async def test_audio_streaming(self, test_client):
        """Test audio data streaming"""
        with test_client.websocket_connect("/api/callbot/audio-stream") as websocket:
            # Send start message
            start_message = {
                "event": "start",
                "streamSid": "test_stream",
                "tracks": ["inbound", "outbound"]
            }
            websocket.send_json(start_message)

            # Send audio data
            audio_message = {
                "event": "media",
                "streamSid": "test_stream",
                "media": {
                    "track": "inbound",
                    "chunk": "1",
                    "timestamp": "1234567890",
                    "payload": "base64_audio_data"
                }
            }
            websocket.send_json(audio_message)

            # Receive response (should be processed by audio manager)
            response = websocket.receive_json()
            assert response["event"] in ["media", "mark"]
```

## Load Testing

### Concurrent Call Testing

**File**: `tests/load/test_concurrent_calls.py`

```python
import pytest
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor


class TestLoadTesting:
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_concurrent_websocket_connections(self):
        """Test multiple concurrent WebSocket connections"""
        num_connections = 10
        connection_duration = 30  # seconds

        async def create_connection(session, connection_id):
            """Create single WebSocket connection"""
            try:
                async with session.ws_connect(
                    "ws://localhost:8080/api/callbot/audio-stream"
                ) as ws:
                    # Send start message
                    await ws.send_str(json.dumps({
                        "event": "start",
                        "streamSid": f"test_stream_{connection_id}"
                    }))

                    # Keep connection alive
                    await asyncio.sleep(connection_duration)

                    return True
            except Exception as e:
                print(f"Connection {connection_id} failed: {e}")
                return False

        # Create concurrent connections
        async with aiohttp.ClientSession() as session:
            tasks = [
                create_connection(session, i)
                for i in range(num_connections)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Analyze results
            successful_connections = sum(1 for r in results if r is True)
            success_rate = successful_connections / num_connections

            assert success_rate >= 0.8  # At least 80% success rate

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_api_load_testing(self):
        """Test API endpoint load handling"""
        num_requests = 100
        concurrent_requests = 10

        async def make_request(session):
            """Make single API request"""
            try:
                async with session.get("http://localhost:8080/health") as response:
                    return response.status == 200
            except Exception:
                return False

        async with aiohttp.ClientSession() as session:
            # Create batches of concurrent requests
            success_count = 0
            total_requests = 0

            for batch in range(num_requests // concurrent_requests):
                tasks = [
                    make_request(session)
                    for _ in range(concurrent_requests)
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)
                success_count += sum(1 for r in results if r is True)
                total_requests += len(results)

                # Brief pause between batches
                await asyncio.sleep(0.1)

            success_rate = success_count / total_requests
            assert success_rate >= 0.95  # 95% success rate under load
```

## Test Data and Fixtures

### Test Fixtures

**File**: `tests/conftest.py`

```python
import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock

from app.agents.phone_conversation_state_model import PhoneConversationState, ProspectInfo


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_prospect_info():
    """Sample prospect information for testing"""
    return ProspectInfo(
        name="Jean Dupont",
        company="Acme Corp",
        job_title="CTO",
        email="jean@acme.com",
        phone="+33123456789",
        industry="Technology",
        company_size="50-100 employees",
        pain_points=["Scalability issues", "Cost optimization"],
        budget_indicated=True,
        timeline=30  # days
    )


@pytest.fixture
def sample_conversation_state(sample_prospect_info):
    """Sample conversation state for testing"""
    return PhoneConversationState(
        call_id="test_call_123",
        caller_phone="+33123456789",
        start_time=datetime.utcnow(),
        current_phase=ConversationPhase.QUALIFICATION,
        conversation_history=[],
        current_user_input="",
        current_agent_response="",
        prospect_info=sample_prospect_info,
        qualification_score=7.5,
        qualification_complete=True,
        appointment_preferences=AppointmentPreferences(),
        appointment_scheduled=None,
        salesforce_lead_id=None,
        calendar_event_id=None,
        current_agent=AgentType.LEAD_AGENT,
        agent_context={},
        next_action=None
    )


@pytest.fixture
def mock_twilio_websocket():
    """Mock Twilio WebSocket for testing"""
    websocket = AsyncMock()
    websocket.accept = AsyncMock()
    websocket.send_text = AsyncMock()
    websocket.receive_text = AsyncMock()
    websocket.close = AsyncMock()
    return websocket


@pytest.fixture
def mock_external_services():
    """Mock all external services"""
    mocks = {
        'salesforce': AsyncMock(),
        'google_calendar': AsyncMock(),
        'speech_to_text': AsyncMock(),
        'text_to_speech': AsyncMock(),
        'rag_client': AsyncMock()
    }

    # Configure default responses
    mocks['salesforce'].create_lead_async.return_value = Mock(id='lead_123')
    mocks['google_calendar'].create_event_async.return_value = Mock(id='event_456')
    mocks['speech_to_text'].transcribe_async.return_value = "Test transcription"
    mocks['text_to_speech'].synthesize_async.return_value = b'audio_data'

    return mocks
```

## Performance Testing

### Response Time Testing

```python
import time
import pytest
from app.agents.lead_agent import LeadAgent


class TestPerformance:
    @pytest.mark.asyncio
    async def test_agent_response_time(self, lead_agent, sample_conversation_state):
        """Test agent response time meets requirements"""
        start_time = time.time()

        result = await lead_agent.process_async(sample_conversation_state)

        end_time = time.time()
        response_time = end_time - start_time

        # Agent should respond within 2 seconds
        assert response_time < 2.0

    @pytest.mark.asyncio
    async def test_audio_processing_latency(self, audio_manager, sample_audio_data):
        """Test audio processing latency"""
        start_time = time.time()

        result = await audio_manager.process_audio_chunk_async(sample_audio_data)

        end_time = time.time()
        processing_time = end_time - start_time

        # Audio processing should complete within 500ms
        assert processing_time < 0.5
```

## Continuous Integration

### GitHub Actions Configuration

**File**: `.github/workflows/test.yml`

```yaml
name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.11, 3.12]

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e .[dev]

    - name: Run unit tests
      run: |
        pytest tests/ -v --cov=app --cov-report=xml

    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml

    - name: Run integration tests
      run: |
        pytest tests/ -m integration -v

    - name: Run load tests
      run: |
        pytest tests/load/ -m slow -v
```

This comprehensive testing strategy ensures the reliability, performance, and maintainability of the PIC Prospect Incoming Callbot system through automated testing at multiple levels.