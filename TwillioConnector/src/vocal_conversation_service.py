
import os
from dotenv import load_dotenv
import json
import base64
import asyncio
import websockets
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from src.helper import Helper
from src.api_client.studi_rag_inference_client import StudiRAGInferenceClient
from src.api_client.request_models.user_request_model import UserRequestModel, DeviceInfoRequestModel
from src.api_client.request_models.conversation_request_model import ConversationRequestModel

# Constants moved from twilio_controller.py
display_timing = True
events_types_to_log = [
    'error', 'response.content.done', 'rate_limits.updated',
    'response.done', 'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped', 'input_audio_buffer.speech_started',
    'session.created'
]

class VocalConversationService:
    """Handles WebSocket connections between Twilio and OpenAI."""
    
    def __init__(self, twilio_websocket: WebSocket):
        """Initialize WebSocketHandler with Twilio and OpenAI WebSocket connections."""
        self.twilio_websocket = twilio_websocket
        
        # Connection specific infos
        self.stream_sid = None
        self.latest_media_timestamp = 0
        self.last_assistant_item = None
        self.mark_queue = []
        self.response_start_timestamp_twilio = None
        self.voice_to_voice_llm_ws = None
        self.studi_rag_inference_client = StudiRAGInferenceClient()
    
    async def initialize_llm_websocket_async(self):
        load_dotenv()
        llm_api_key = os.getenv('OPENAI_API_KEY')
        if not llm_api_key:
            raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')
        
        self.voice_to_voice_llm_ws = await websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
            additional_headers={ "Authorization": f"Bearer {llm_api_key}", "OpenAI-Beta": "realtime=v1"}
        )
    
    async def handle_conversation_async(self, calling_phone_number: str, call_sid: str):
        """Main method to handle the WebSocket connections."""
        try:
            await self.init_user_session(calling_phone_number, call_sid)
            await asyncio.gather(self.received_vocal_input(), self.send_vocal_output())
        finally:
            if self.voice_to_voice_llm_ws and self.voice_to_voice_llm_ws.state is websockets.State.OPEN:
                await self.voice_to_voice_llm_ws.close()

    async def init_user_session(self, calling_phone_number: str, call_sid: str):
        """ Initialize the user session: create user and conversation and send a welcome message """
        user_RM = UserRequestModel(user_id=None, user_name=None, IP=calling_phone_number, device_info=DeviceInfoRequestModel(user_agent="twilio", platform="phone", app_version="", os="", browser="", is_mobile=False))
        user = await self.studi_rag_inference_client.create_or_retrieve_user(user_RM)
        conversation_RM = ConversationRequestModel(user_id=user['user_id'], call_sid=call_sid)
        conversation = await self.studi_rag_inference_client.create_new_conversation(conversation_RM)
        
        await self.send_conversation_greetings()        

    async def send_conversation_greetings(self):
        """Control initial session with OpenAI."""
        language = "fr"
        welcome_message = Helper.read_file(f"src/prompts/welcome_message.{language}.txt").format(company_name="Studi")
        voice_type = 'alloy'

        session_update = {
            "type": "session.update",
            "session": {
                "turn_detection": {"type": "server_vad"},
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "voice": voice_type,
                "instructions": welcome_message,
                "modalities": ["text", "audio"],
                "temperature": 0.8,
            }
        }
        await self.voice_to_voice_llm_ws.send(json.dumps(session_update))

    async def send_conversation_greetings_2(self):
        """Send initial conversation item if AI talks first."""
        initial_conversation_item = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": Helper.read_file("src/prompts/welcome.txt")
                    }
                ]
            }
        }
        await self.voice_to_voice_llm_ws.send(json.dumps(initial_conversation_item))
        await self.voice_to_voice_llm_ws.send(json.dumps({"type": "response.create"}))
    
    async def received_vocal_input(self):
        """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
        try:
            async for message in self.twilio_websocket.iter_text():
                data = json.loads(message)
                if data['event'] == 'media' and self.voice_to_voice_llm_ws.state is websockets.State.OPEN:
                    self.latest_media_timestamp = int(data['media']['timestamp'])
                    audio_append = {
                        "type": "input_audio_buffer.append",
                        "audio": data['media']['payload']
                    }
                    await self.voice_to_voice_llm_ws.send(json.dumps(audio_append))
                elif data['event'] == 'start':
                    self.stream_sid = data['start']['streamSid']
                    print(f"!!! Incoming stream has started (stream sid: {self.stream_sid}) !!!")
                    
                    self.response_start_timestamp_twilio = None
                    self.latest_media_timestamp = 0
                    self.last_assistant_item = None
                elif data['event'] == 'mark':
                    if self.mark_queue:
                        self.mark_queue.pop(0)
        except WebSocketDisconnect:
            print("Client disconnected.")
            raise

    async def send_vocal_output(self):
        """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
        try:
            async for llm_answer_message in self.voice_to_voice_llm_ws:
                llm_answer_json = json.loads(llm_answer_message)
                if llm_answer_json['type'] in events_types_to_log:
                    print(f"Received event: {llm_answer_json['type']}", llm_answer_json)

                if llm_answer_json.get('type') == 'response.audio.delta' and 'delta' in llm_answer_json:
                    audio_payload = base64.b64encode(base64.b64decode(llm_answer_json['delta'])).decode('utf-8')
                    audio_delta = {
                        "event": "media",
                        "streamSid": self.stream_sid,
                        "media": {
                            "payload": audio_payload
                        }
                    }
                    await self.twilio_websocket.send_json(audio_delta)

                    if self.response_start_timestamp_twilio is None:
                        self.response_start_timestamp_twilio = self.latest_media_timestamp
                        if display_timing:
                            print(f"Setting start timestamp for new response: {self.response_start_timestamp_twilio}ms")

                    # Update last_assistant_item safely
                    if llm_answer_json.get('item_id'):
                        self.last_assistant_item = llm_answer_json['item_id']

                    await self.send_mark()

                # Trigger an interruption when speech is detected
                if llm_answer_json.get('type') == 'input_audio_buffer.speech_started':
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
            if display_timing:
                print(f"Elapsed time for truncation: {self.latest_media_timestamp} - {self.response_start_timestamp_twilio} = {elapsed_time}ms")

            if self.last_assistant_item:
                if display_timing:
                    print(f"Truncating item with ID: {self.last_assistant_item}, Truncated at: {elapsed_time}ms")

                truncate_event = {
                    "type": "conversation.item.truncate",
                    "item_id": self.last_assistant_item,
                    "content_index": 0,
                    "audio_end_ms": elapsed_time
                }
                await self.voice_to_voice_llm_ws.send(json.dumps(truncate_event))

            await self.twilio_websocket.send_json({
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
            await self.twilio_websocket.send_json(mark_event)
            self.mark_queue.append('responsePart')
