import json
import base64
import asyncio
import websockets
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

# Constants moved from twilio_controller.py
SHOW_TIMING_MATH = False
LOG_EVENT_TYPES = [
    'error', 'response.content.done', 'rate_limits.updated',
    'response.done', 'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped', 'input_audio_buffer.speech_started',
    'session.created'
]

class VocalConversationService:
    """Handles WebSocket connections between Twilio and OpenAI."""
    
    def __init__(self, twilio_websocket: WebSocket, openai_websocket):
        """Initialize WebSocketHandler with Twilio and OpenAI WebSocket connections."""
        self.websocket = twilio_websocket
        self.openai_ws = openai_websocket
        
        # Connection specific infos
        self.stream_sid = None
        self.latest_media_timestamp = 0
        self.last_assistant_item = None
        self.mark_queue = []
        self.response_start_timestamp_twilio = None
    
    async def handle_conversation(self):
        """Main method to handle the WebSocket connections."""
        await asyncio.gather(self.received_vocal_input(), self.send_vocal_output())
    
    async def received_vocal_input(self):
        """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
        try:
            async for message in self.websocket.iter_text():
                data = json.loads(message)
                if data['event'] == 'media' and self.openai_ws.state is websockets.State.OPEN:
                    self.latest_media_timestamp = int(data['media']['timestamp'])
                    audio_append = {
                        "type": "input_audio_buffer.append",
                        "audio": data['media']['payload']
                    }
                    await self.openai_ws.send(json.dumps(audio_append))
                elif data['event'] == 'start':
                    self.stream_sid = data['start']['streamSid']
                    print(f"Incoming stream has started {self.stream_sid}")
                    self.response_start_timestamp_twilio = None
                    self.latest_media_timestamp = 0
                    self.last_assistant_item = None
                elif data['event'] == 'mark':
                    if self.mark_queue:
                        self.mark_queue.pop(0)
        except WebSocketDisconnect:
            print("Client disconnected.")
            if self.openai_ws.open:
                await self.openai_ws.close()

    async def send_vocal_output(self):
        """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
        try:
            async for openai_message in self.openai_ws:
                response = json.loads(openai_message)
                if response['type'] in LOG_EVENT_TYPES:
                    print(f"Received event: {response['type']}", response)

                if response.get('type') == 'response.audio.delta' and 'delta' in response:
                    audio_payload = base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                    audio_delta = {
                        "event": "media",
                        "streamSid": self.stream_sid,
                        "media": {
                            "payload": audio_payload
                        }
                    }
                    await self.websocket.send_json(audio_delta)

                    if self.response_start_timestamp_twilio is None:
                        self.response_start_timestamp_twilio = self.latest_media_timestamp
                        if SHOW_TIMING_MATH:
                            print(f"Setting start timestamp for new response: {self.response_start_timestamp_twilio}ms")

                    # Update last_assistant_item safely
                    if response.get('item_id'):
                        self.last_assistant_item = response['item_id']

                    await self.send_mark()

                # Trigger an interruption when speech is detected
                if response.get('type') == 'input_audio_buffer.speech_started':
                    print("Speech started detected.")
                    if self.last_assistant_item:
                        print(f"Interrupting response with id: {self.last_assistant_item}")
                        await self.handle_speech_started_event()
        except Exception as e:
            print(f"Error in send_to_twilio: {e}")

    async def handle_speech_started_event(self):
        """Handle interruption when the caller's speech starts."""
        print("Handling speech started event.")
        if self.mark_queue and self.response_start_timestamp_twilio is not None:
            elapsed_time = self.latest_media_timestamp - self.response_start_timestamp_twilio
            if SHOW_TIMING_MATH:
                print(f"Calculating elapsed time for truncation: {self.latest_media_timestamp} - {self.response_start_timestamp_twilio} = {elapsed_time}ms")

            if self.last_assistant_item:
                if SHOW_TIMING_MATH:
                    print(f"Truncating item with ID: {self.last_assistant_item}, Truncated at: {elapsed_time}ms")

                truncate_event = {
                    "type": "conversation.item.truncate",
                    "item_id": self.last_assistant_item,
                    "content_index": 0,
                    "audio_end_ms": elapsed_time
                }
                await self.openai_ws.send(json.dumps(truncate_event))

            await self.websocket.send_json({
                "event": "clear",
                "streamSid": self.stream_sid
            })

            self.mark_queue.clear()
            self.last_assistant_item = None
            self.response_start_timestamp_twilio = None

    async def send_mark(self):
        """Send a mark event to Twilio."""
        if self.stream_sid:
            mark_event = {
                "event": "mark",
                "streamSid": self.stream_sid,
                "mark": {"name": "responsePart"}
            }
            await self.websocket.send_json(mark_event)
            self.mark_queue.append('responsePart')
