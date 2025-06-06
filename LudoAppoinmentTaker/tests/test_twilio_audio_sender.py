import pytest
import asyncio
import json
import base64
import audioop
import time
from unittest.mock import AsyncMock, MagicMock, patch

from app.speech.twilio_audio_sender import TwilioAudioSender

@pytest.fixture
def mock_websocket():
    ws = AsyncMock()
    ws.closed = False
    ws.send_text = AsyncMock()
    return ws

@pytest.fixture
def audio_sender(mock_websocket):
    # Ensure the import path for TwilioAudioSender matches its actual location
    # If TwilioAudioSender is in app.speech.twilio_audio_sender, the import is correct.
    return TwilioAudioSender(websocket=mock_websocket, stream_sid="test_stream_sid_123")

# Helper to generate PCM audio data
def generate_pcm_audio(duration_ms, sample_rate=16000, bit_depth=16):
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    # Each sample is 2 bytes for 16-bit PCM
    return b'\x00\x00' * num_samples 

@pytest.mark.asyncio
async def test_initialization(audio_sender, mock_websocket):
    assert audio_sender.websocket == mock_websocket
    assert audio_sender.stream_sid == "test_stream_sid_123"
    assert not audio_sender.streaming_interruption_asked
    assert isinstance(audio_sender.send_lock, asyncio.Lock)

@pytest.mark.asyncio
async def test_send_audio_chunk_empty_audio(audio_sender, caplog):
    assert not await audio_sender.send_audio_chunk(b'')
    assert "send_audio_chunk called with empty audio_chunk" in caplog.text

@pytest.mark.asyncio
async def test_send_audio_chunk_no_stream_sid(mock_websocket, caplog):
    sender = TwilioAudioSender(websocket=mock_websocket, stream_sid=None)
    assert not await sender.send_audio_chunk(generate_pcm_audio(100))
    assert "No stream_sid provided" in caplog.text

@pytest.mark.asyncio
async def test_send_audio_chunk_no_websocket(caplog):
    sender = TwilioAudioSender(websocket=None, stream_sid="test_sid")
    assert not await sender.send_audio_chunk(generate_pcm_audio(100))
    assert "WebSocket is not set" in caplog.text

@pytest.mark.asyncio
async def test_send_audio_chunk_websocket_closed(audio_sender, mock_websocket, caplog):
    mock_websocket.closed = True
    assert not await audio_sender.send_audio_chunk(generate_pcm_audio(100))
    assert "WebSocket is closed" in caplog.text

@pytest.mark.asyncio
@patch('audioop.lin2ulaw')
async def test_send_audio_chunk_lin2ulaw_error(mock_lin2ulaw, audio_sender, caplog):
    mock_lin2ulaw.side_effect = audioop.error("conversion failed")
    audio_data = generate_pcm_audio(100)
    assert not await audio_sender.send_audio_chunk(audio_data)
    assert "Error converting PCM to μ-law" in caplog.text
    mock_lin2ulaw.assert_called_once_with(audio_data, 2)

@pytest.mark.asyncio
@patch('asyncio.sleep', new_callable=AsyncMock)
@patch('audioop.lin2ulaw')
@patch('time.time') 
async def test_send_audio_chunk_single_segment_success(mock_time, mock_lin2ulaw, mock_async_sleep, audio_sender, mock_websocket):
    mock_current_time = 1000.0
    audio_sender.start_time = mock_current_time # Align start time for duration metrics
    # Simulate time advancing for last_send_time, last_chunk_time, total_send_duration
    mock_time.side_effect = [mock_current_time, mock_current_time + 0.05, mock_current_time + 0.1]

    pcm_audio = generate_pcm_audio(50) # 50ms -> 1600 bytes PCM -> 800 bytes mulaw (1 segment)
    mulaw_audio = b'\x7F' * (len(pcm_audio) // 2)
    mock_lin2ulaw.return_value = mulaw_audio

    result = await audio_sender.send_audio_chunk(pcm_audio)
    assert result

    mock_lin2ulaw.assert_called_once_with(pcm_audio, 2)
    mock_websocket.send_text.assert_called_once()
    args, _ = mock_websocket.send_text.call_args
    sent_message = json.loads(args[0])
    assert sent_message["event"] == "media"
    assert sent_message["streamSid"] == "test_stream_sid_123"
    assert sent_message["media"]["payload"] == base64.b64encode(mulaw_audio).decode('utf-8')

    expected_delay = len(mulaw_audio) / 8000.0
    mock_async_sleep.assert_called_once_with(expected_delay)

    assert audio_sender.total_bytes_sent == len(pcm_audio)
    assert audio_sender.chunks_sent == 1
    assert audio_sender.consecutive_errors == 0

@pytest.mark.asyncio
@patch('asyncio.sleep', new_callable=AsyncMock)
@patch('audioop.lin2ulaw')
@patch('time.time')
async def test_send_audio_chunk_multiple_segments_success(mock_time, mock_lin2ulaw, mock_async_sleep, audio_sender, mock_websocket):
    mock_current_time = 2000.0
    audio_sender.start_time = mock_current_time
    # Provide enough time values for each segment + initial + final
    time_sequence = [mock_current_time] + [mock_current_time + 0.05 * (i+1) for i in range(8)] 
    mock_time.side_effect = time_sequence

    pcm_audio = generate_pcm_audio(250) # 250ms -> 8000 bytes PCM -> 4000 bytes mulaw -> 8 segments
    mulaw_audio_full = b'\xAA' * (len(pcm_audio) // 2)
    mock_lin2ulaw.return_value = mulaw_audio_full

    result = await audio_sender.send_audio_chunk(pcm_audio)
    assert result

    mock_lin2ulaw.assert_called_once_with(pcm_audio, 2)
    
    num_expected_segments = (len(mulaw_audio_full) + 511) // 512
    assert mock_websocket.send_text.call_count == num_expected_segments
    assert mock_async_sleep.call_count == num_expected_segments

    for i in range(num_expected_segments):
        start_idx = i * 512
        end_idx = min((i + 1) * 512, len(mulaw_audio_full))
        segment_mulaw = mulaw_audio_full[start_idx:end_idx]
        
        args, _ = mock_websocket.send_text.call_args_list[i]
        sent_message = json.loads(args[0])
        assert sent_message["media"]["payload"] == base64.b64encode(segment_mulaw).decode('utf-8')
        
        sleep_args, _ = mock_async_sleep.call_args_list[i]
        assert abs(sleep_args[0] - (len(segment_mulaw) / 8000.0)) < 1e-9 # Compare floats with tolerance

    assert audio_sender.total_bytes_sent == len(pcm_audio)
    assert audio_sender.chunks_sent == 1
    assert audio_sender.consecutive_errors == 0

@pytest.mark.asyncio
@patch('asyncio.sleep', new_callable=AsyncMock)
@patch('audioop.lin2ulaw')
async def test_send_audio_chunk_interruption(mock_lin2ulaw, mock_async_sleep, audio_sender, mock_websocket, caplog):
    pcm_audio = generate_pcm_audio(250) # Multi-segment
    mulaw_audio_full = b'\xBB' * (len(pcm_audio) // 2)
    mock_lin2ulaw.return_value = mulaw_audio_full
    audio_sender.streaming_interruption_asked = False # Ensure it starts false

    # Interrupt after the first segment
    original_send_text = mock_websocket.send_text
    async def side_effect_send_text(*args, **kwargs):
        # Call original to maintain AsyncMock properties like call_count
        res = await original_send_text(*args, **kwargs) 
        if mock_websocket.send_text.call_count == 1:
            audio_sender.streaming_interruption_asked = True
        return res
    mock_websocket.send_text.side_effect = side_effect_send_text

    result = await audio_sender.send_audio_chunk(pcm_audio)
    assert result # True as first segment was sent

    assert mock_websocket.send_text.call_count == 1 # Only first segment sent
    assert mock_async_sleep.call_count == 1
    assert "Streaming interruption asked by flag" in caplog.text
    assert audio_sender.total_bytes_sent == len(pcm_audio)
    assert audio_sender.chunks_sent == 1
    audio_sender.streaming_interruption_asked = False # Reset

@pytest.mark.asyncio
@patch('asyncio.sleep', new_callable=AsyncMock)
@patch('audioop.lin2ulaw')
async def test_send_audio_chunk_websocket_send_error_once(mock_lin2ulaw, mock_async_sleep, audio_sender, mock_websocket, caplog):
    pcm_audio = generate_pcm_audio(50) 
    mulaw_audio = b'\xCC' * (len(pcm_audio) // 2)
    mock_lin2ulaw.return_value = mulaw_audio
    audio_sender.consecutive_errors = 0 # Reset for test

    mock_websocket.send_text.side_effect = Exception("Send failed!")

    result = await audio_sender.send_audio_chunk(pcm_audio)
    assert not result

    assert mock_websocket.send_text.call_count == 1
    assert "Error sending audio segment to Twilio: Send failed!" in caplog.text
    assert audio_sender.consecutive_errors == 1
    assert audio_sender.total_bytes_sent == 0 
    assert audio_sender.chunks_sent == 0
    audio_sender.consecutive_errors = 0 # Reset

@pytest.mark.asyncio
@patch('asyncio.sleep', new_callable=AsyncMock)
@patch('audioop.lin2ulaw')
async def test_send_audio_chunk_websocket_send_error_max_attempts_in_chunk(mock_lin2ulaw, mock_async_sleep, audio_sender, mock_websocket, caplog):
    pcm_audio = generate_pcm_audio(250) 
    mulaw_audio_full = b'\xDD' * (len(pcm_audio) // 2)
    mock_lin2ulaw.return_value = mulaw_audio_full

    audio_sender.max_consecutive_errors = 3 
    audio_sender.consecutive_errors = 0 # Start fresh for this test logic
    
    mock_websocket.send_text.side_effect = Exception("Network error on first segment")

    result = await audio_sender.send_audio_chunk(pcm_audio)
    assert not result 

    assert mock_websocket.send_text.call_count == 1 
    assert "Error sending audio segment to Twilio: Network error on first segment" in caplog.text
    assert audio_sender.consecutive_errors == 1 
    assert "Max consecutive errors (3) reached" not in caplog.text 

    audio_sender.consecutive_errors = 0 
    audio_sender.max_consecutive_errors = 5 

@pytest.mark.asyncio
@patch('asyncio.sleep', new_callable=AsyncMock)
@patch('audioop.lin2ulaw')
async def test_send_audio_chunk_max_errors_across_calls(mock_lin2ulaw, mock_async_sleep, audio_sender, mock_websocket, caplog):
    pcm_audio = generate_pcm_audio(50)
    mulaw_audio = b'\xEE' * (len(pcm_audio) // 2)
    mock_lin2ulaw.return_value = mulaw_audio
    mock_websocket.send_text.side_effect = Exception("Persistent failure")
    audio_sender.max_consecutive_errors = 2
    audio_sender.consecutive_errors = 0 

    await audio_sender.send_audio_chunk(pcm_audio) 
    assert audio_sender.consecutive_errors == 1
    assert "Max consecutive errors (2) reached" not in caplog.text 

    await audio_sender.send_audio_chunk(pcm_audio) 
    assert audio_sender.consecutive_errors == 2
    assert "Max consecutive errors (2) reached while sending segment" in caplog.text
    
    assert mock_websocket.send_text.call_count == 2 

    audio_sender.consecutive_errors = 0 
    audio_sender.max_consecutive_errors = 5 


def test_get_sender_stats(audio_sender):
    current_t = time.time()
    audio_sender.total_bytes_sent = 10240
    audio_sender.chunks_sent = 5
    audio_sender.avg_chunk_size = 10240 / 5
    audio_sender.consecutive_errors = 1
    audio_sender.is_sending = True
    audio_sender.last_chunk_time = current_t - 10
    audio_sender.start_time = current_t - 60
    audio_sender.total_send_duration = 5.0 

    with patch('time.time', return_value=current_t):
        stats = audio_sender.get_sender_stats()
    
    assert stats['chunks_sent'] == 5
    assert stats['bytes_sent'] == 10240
    assert stats['bytes_sent_kb'] == 10.0
    assert abs(stats['avg_chunk_size'] - 2048.0) < 1e-9
    assert stats['consecutive_errors'] == 1
    assert stats['is_sending'] == True
    assert stats['stream_sid'] == "test_stream_sid_123"
    assert abs(stats['time_since_last_chunk'] - 10) < 0.1 
    assert abs(stats['total_duration'] - 60) < 0.1 
    assert abs(stats['send_duration'] - 5.0) < 1e-9

def test_get_sending_stats(audio_sender):
    current_t = time.time()
    audio_sender.total_bytes_sent = 5120
    audio_sender.chunks_sent = 2
    audio_sender.consecutive_errors = 0
    audio_sender.is_sending = False
    audio_sender.last_send_time = current_t - 5

    # No need to mock time.time() here as it's not called within get_sending_stats itself
    stats = audio_sender.get_sending_stats()

    assert stats['total_bytes_sent'] == 5120
    assert stats['chunks_sent'] == 2
    assert stats['consecutive_errors'] == 0
    assert stats['is_sending'] == False
    assert abs(audio_sender.last_send_time - (current_t - 5)) < 1e-9

@pytest.mark.asyncio
@patch('asyncio.sleep', new_callable=AsyncMock)
@patch('audioop.lin2ulaw')
async def test_integration_send_sequence_with_interruption(mock_lin2ulaw, mock_async_sleep, audio_sender, mock_websocket, caplog):
    audio_sender.total_bytes_sent = 0
    audio_sender.chunks_sent = 0
    audio_sender.consecutive_errors = 0
    audio_sender.streaming_interruption_asked = False
    audio_sender.start_time = time.time()

    pcm_audio1 = generate_pcm_audio(150)
    mulaw_audio1 = b'\x11' * (len(pcm_audio1) // 2)
    pcm_audio2 = generate_pcm_audio(50)  
    mulaw_audio2 = b'\x22' * (len(pcm_audio2) // 2)

    def lin2ulaw_side_effect(pcm_data, width):
        if pcm_data == pcm_audio1: return mulaw_audio1
        if pcm_data == pcm_audio2: return mulaw_audio2
        return b''
    mock_lin2ulaw.side_effect = lin2ulaw_side_effect

    sent_segments_chunk1 = 0
    send_text_calls_payloads = []
    original_send_text_mock = mock_websocket.send_text # Save original mock
    
    async def interrupt_side_effect(json_str):
        nonlocal sent_segments_chunk1
        send_text_calls_payloads.append(json.loads(json_str)['media']['payload'])
        # Simulate original mock behavior for call counting etc.
        await original_send_text_mock(json_str) 
        payload_content = base64.b64decode(json.loads(json_str)['media']['payload'])
        if payload_content.startswith(b'\x11'): # First chunk's data
            sent_segments_chunk1 += 1
            if sent_segments_chunk1 == 2: # Interrupt after 2nd segment of 1st chunk
                audio_sender.streaming_interruption_asked = True
        return MagicMock() # Return a mock to satisfy await
    mock_websocket.send_text.side_effect = interrupt_side_effect

    res1 = await audio_sender.send_audio_chunk(pcm_audio1)
    assert res1 
    assert sent_segments_chunk1 == 2
    # send_text was called twice for the first chunk before interruption
    assert mock_websocket.send_text.call_count == 2 
    assert "Streaming interruption asked" in caplog.text
    assert audio_sender.total_bytes_sent == len(pcm_audio1)
    assert audio_sender.chunks_sent == 1

    audio_sender.streaming_interruption_asked = False
    mock_websocket.send_text.reset_mock() # Reset call count for the next chunk
    mock_websocket.send_text.side_effect = original_send_text_mock # Restore simple mock or new side_effect for chunk2
    send_text_calls_payloads.clear()
    # If original_send_text_mock was just AsyncMock(), re-assigning is fine.
    # If it had a more complex side_effect for other tests, this needs care.
    # For this test, let's assume subsequent calls are normal successful sends.
    async def normal_send_effect(json_str):
        send_text_calls_payloads.append(json.loads(json_str)['media']['payload'])
        await original_send_text_mock(json_str)
        return MagicMock()
    mock_websocket.send_text.side_effect = normal_send_effect

    res2 = await audio_sender.send_audio_chunk(pcm_audio2)
    assert res2
    num_expected_segments_chunk2 = (len(mulaw_audio2) + 511) // 512
    assert mock_websocket.send_text.call_count == num_expected_segments_chunk2
    
    assert audio_sender.total_bytes_sent == len(pcm_audio1) + len(pcm_audio2)
    assert audio_sender.chunks_sent == 2
    assert audio_sender.consecutive_errors == 0
