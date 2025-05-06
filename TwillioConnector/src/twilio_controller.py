# Inspired by: https://github.com/twilio-samples/speech-assistant-openai-realtime-api-python/blob/main/main.py

from fastapi import APIRouter, Request, Response, HTTPException
from src.twilio_service import TwilioService
from src.studi_public_website_client import StudiPublicWebsiteClient
from src.vocal_conversation_service import VocalConversationService

import os
import json
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from twilio.twiml.voice_response import VoiceResponse, Connect, Say, Stream
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')

handled_events_channel_and_ts: set = set()
twilio_service = TwilioService()
website_client :StudiPublicWebsiteClient = StudiPublicWebsiteClient("http://localhost:8281")
twilio_router = APIRouter(prefix="", tags=["Twilio"])

SYSTEM_MESSAGE = (
    """\
You're a helpful chatbot assistant named : 'Studia'. You work for a french company named: 'Studi'. You're specialize in guidance counsellor, coaching poeple to  help them make informed decisions about their trainings choices and help them forsee their career planning, and development needs by providing them concrete ad sourced informations and advices.
Your default langague is french, but you may answer in the langague of the user's query. Say to the user, as introduction, that we're out of the opening hours, but that you can help him with his questions. 
You are a guidance and information assistant specialized in helping users find educational programs, funding opportunities, career paths, and related topics.

# Instructions #
Your role is to provide accurate and relevant information on:
- Available training programs and courses
- Various funding sources for education and career development
- Career guidance, including job opportunities and professional growth paths
- Other related subjects such as certifications, diplomas, and vocational programs
- In case of questions related to courses about: real estate, food jobs, or beauty, that the company: 'Studi' don't provide, propose the user to also check for trainings from: 'Academee' at: 'www.academee.com'

To help you guiding the user into choosing an adapted course, you can ask him questions like: its age, its previous acquired degrees, its current professional status, and its general centers of interest (like relationships, mathematics, ...)
You shouldn't answer queries about:
- existential or off-topic questions
- informations not within the 'Knowledge base' section of this prompt.

In the above cases where you shouldn't answer the user's question, acknowledge the significance of their inquiry in a respectful manner. Gently guide the conversation back to topics you can assist with, such as educational programs, career opportunities, funding, and related areas. Use phrases like "I understand that this is an important question, but my role is to help you find information on..." to acknowledge the user's concern while steering the conversation towards relevant subjects.
Encourage the user to reframe their question in a way that relates to education, career paths, or personal development. Ask follow-up questions to help refocus the discussion, such as "Have you considered exploring a career that aligns with your interests?" or "Is there a specific field or training program you would like to know more about?"

Answer the user's question with a supportive response, providing all relevant information related to the query.
    """
)
VOICE = 'alloy'
LOG_EVENT_TYPES = [
    'error', 'response.content.done', 'rate_limits.updated',
    'response.done', 'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped', 'input_audio_buffer.speech_started',
    'session.created'
]
SHOW_TIMING_MATH = False


@twilio_router.get("/ping")
def test_endpoint():
    return "pong"

@twilio_router.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}

@twilio_router.api_route("/incoming-sms", methods=["GET", "POST"])
async def twilio_incoming_SMS(request: Request):
    return HTMLResponse(content=str("Les SMS ne sont pas pris en charge pour le moment"), media_type="application/xml")

@twilio_router.post("/")
async def twilio_incoming_voice_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    response = VoiceResponse()
    # response.say("Please wait while we connect your call to our A.I voice assistant.")
    # response.pause(length=1)
    # response.say("O.K. you can start talking!")
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

@twilio_router.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and LLM."""

    await websocket.accept()
    voice_to_voice_llm_ws = await connect_voice_to_voice_llm_ws()

    try:
        await initialize_session(voice_to_voice_llm_ws)
        vocal_service = VocalConversationService(websocket, voice_to_voice_llm_ws)
        await vocal_service.handle_conversation()
    finally:
        await voice_to_voice_llm_ws.close()

async def connect_voice_to_voice_llm_ws():
    return await websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
        additional_headers={ "Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Beta": "realtime=v1"}
    )

async def initialize_session(openai_ws):
    """Control initial session with OpenAI."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.8,
        }
    }
    await openai_ws.send(json.dumps(session_update))
    await send_conversation_greetings(openai_ws)

async def send_conversation_greetings(openai_ws):
    """Send initial conversation item if AI talks first."""
    initial_conversation_item = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "Greet the user with 'Hello there! I am an AI voice assistant powered by Twilio and the OpenAI Realtime API. You can ask me for facts, jokes, or anything you can imagine. How can I help you?'"
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(initial_conversation_item))
    await openai_ws.send(json.dumps({"type": "response.create"}))