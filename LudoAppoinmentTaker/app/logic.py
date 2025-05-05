import base64
import os
import io
import uuid
import json
import audioop
import asyncio
import logging
import wave
import tempfile
import requests
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
from google.cloud import speech, texttospeech
from openai import OpenAI
from typing import Any, Dict, Optional
from fastapi import WebSocket
from agents_graph import create_graph, ConversationState

class BusinessLogic:
    logger: logging.Logger = None

    # Environment and configuration settings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ELEVEN_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    VOICE_ID: str = os.getenv("VOICE_ID", "")
    TEMP_DIR: str = "static/audio"
    PUBLIC_HOST: str = os.getenv("PUBLIC_HOST", "http://localhost:8000")
    TWILIO_SID: str = os.getenv("TWILIO_SID", "")
    TWILIO_AUTH: str = os.getenv("TWILIO_AUTH", "")
    
    # Create temp directory if it doesn't exist
    os.makedirs(TEMP_DIR, exist_ok=True)

    # API clients
    client_oa = OpenAI(api_key=OPENAI_API_KEY)
    
    # LangGraph workflow
    compiled_graph = None
    
    # State tracking dictionaries
    stream_states: Dict[str, ConversationState] = {}
    phones: Dict[str, str] = {}  # Map call_sid to phone numbers
    
    def init_graph():
        """Initialize the LangGraph workflow compilation."""
        try:
            BusinessLogic.compiled_graph = create_graph()
            BusinessLogic.logger.info("LangGraph compiled successfully.")
        except Exception as graph_init_error:
            BusinessLogic.logger.error(f"FATAL: Failed to compile LangGraph: {graph_init_error}", exc_info=True)

    @staticmethod
    def _init_stream_vars():
        """Initialize variables needed for audio stream processing."""
        return (
            b"",  # audio_buffer
            0,    # silence_counter_bytes
            None, # current_stream_sid
            {
                "sample_width": 2,  # 16-bit PCM 
                "silence_threshold": 2000,  # RMS threshold for silence detection
                "max_silence_bytes": 30 * 320,  # ~600ms at 8kHz
                "min_audio_bytes_for_processing": 5000  # Minimum buffer size to process
            }
        )
        
    @staticmethod
    def _decode_json(message: str) -> Optional[Dict]:
        """Safely decode JSON message from WebSocket."""
        try:
            return json.loads(message)
        except json.JSONDecodeError as e:
            BusinessLogic.logger.error(f"Failed to decode JSON message: {e}")
            return None
    
    @staticmethod
    def _handle_connected_event(ws: WebSocket):
        """Handle the 'connected' event from Twilio."""
        BusinessLogic.logger.info("Twilio WebSocket connected")

    @staticmethod
    async def _handle_start_event(ws: WebSocket, start_data: Dict) -> str:
        """Handle the 'start' event from Twilio which begins a new call."""
        call_sid = start_data.get("callSid")
        stream_sid = start_data.get("streamSid")
        
        BusinessLogic.logger.info(f"Call started - CallSid: {call_sid}, StreamSid: {stream_sid}")
        
        # Initialize conversation state for this stream
        phone_number = BusinessLogic.phones.get(call_sid, "Unknown")
        
        # Create initial state for the graph
        initial_state: ConversationState = {
            "call_sid": call_sid,
            "caller_phone": phone_number,
            "user_input": "",
            "history": [],
            "agent_scratchpad": {}
        }
        
        # Store the state
        BusinessLogic.stream_states[stream_sid] = initial_state
        
        # Invoke the graph with initial state to get welcome message
        try:
            if BusinessLogic.compiled_graph:
                updated_state = await BusinessLogic.compiled_graph.ainvoke(initial_state)
                BusinessLogic.stream_states[stream_sid] = updated_state
                
                # Check if there's an initial AI message to send
                if updated_state.get('history') and updated_state['history'][0][0] == 'AI':
                    initial_message = updated_state['history'][0][1]
                    await BusinessLogic._speak_and_send(ws, initial_message, stream_sid)
            else:
                BusinessLogic.logger.error("Graph not compiled, cannot generate welcome message")
                # Default welcome message
                default_welcome = "Bienvenue chez Studi. Comment puis-je vous aider ?"
                await BusinessLogic._speak_and_send(ws, default_welcome, stream_sid)
        
        except Exception as e:
            BusinessLogic.logger.error(f"Error in initial graph invocation: {e}", exc_info=True)
            # Fallback welcome message
            await BusinessLogic._speak_and_send(ws, "Bonjour, bienvenue chez Studi.", stream_sid)
        
        return stream_sid
    
    async def handler_websocket(ws: WebSocket) -> None:
        """Main WebSocket handler for Twilio streams."""
        if not BusinessLogic.compiled_graph:
            BusinessLogic.logger.error("Graph not compiled, cannot handle WebSocket connection.")
            await ws.close(code=1011, reason="Server configuration error")
            return

        # Initialize audio processing variables
        audio_buffer, silence_counter_bytes, current_stream, params = BusinessLogic._init_stream_vars()
        BusinessLogic.logger.info(f"WebSocket handler started for {ws.client.host}:{ws.client.port}")

        try:
            while True:
                msg = await ws.receive_text()
                data = BusinessLogic._decode_json(msg)
                if data is None:
                    continue
                    
                event = data.get("event")
                if event == "connected":
                    BusinessLogic._handle_connected_event(ws)
                elif event == "start":
                    current_stream = await BusinessLogic._handle_start_event(ws, data.get("start", {}))
                elif event == "media":
                    if not current_stream:
                        BusinessLogic.logger.warning("Received media before start event")
                        continue
                    audio_buffer, silence_counter_bytes = await BusinessLogic._handle_media_event(
                        ws, data, audio_buffer, silence_counter_bytes, params, current_stream
                    )
                elif event == "stop":
                    await BusinessLogic._handle_stop_event(ws, current_stream)
                    return
                elif event == "mark":
                    BusinessLogic._handle_mark_event(data, current_stream)
                else:
                    BusinessLogic.logger.warning(f"Received unknown event type: {event}")

        except Exception as e:
            BusinessLogic.logger.error(f"Unhandled error in WebSocket handler: {e}", exc_info=True)
        finally:
            if current_stream and current_stream in BusinessLogic.stream_states:
                BusinessLogic.logger.warning(f"Cleaning up state for stream {current_stream} due to handler exit/error.")
                del BusinessLogic.stream_states[current_stream]
            BusinessLogic.logger.info(f"WebSocket handler finished for {ws.client.host}:{ws.client.port} (Stream: {current_stream})" )

    @staticmethod
    async def _handle_media_event(ws, data, audio_buffer, silence_counter_bytes, params, current_stream):
        # 1. Decode audio chunk
        chunk = BusinessLogic._decode_audio_chunk(data, params["sample_width"])
        if chunk is None: return audio_buffer, silence_counter_bytes
        
        audio_buffer += chunk

        # 2. Silence detection
        silence_counter_bytes = BusinessLogic._update_silence_counter(
            chunk,
            silence_counter_bytes,
            params["sample_width"],
            params["silence_threshold"]
        )

        # 3. Process audio if: prolonged silence & buffer is large enough
        if silence_counter_bytes >= params["max_silence_bytes"] and len(audio_buffer) > params["min_audio_bytes_for_processing"]:
            BusinessLogic.logger.info(f"Silence detected for stream {current_stream}, processing audio (buffer: {len(audio_buffer)} bytes).")
            buffer_to_process = audio_buffer
            audio_buffer = b""
            silence_counter_bytes = 0

            transcript = BusinessLogic._transcribe_buffer(buffer_to_process)
            if transcript is None:
                return audio_buffer, silence_counter_bytes

            # 4. Orchestrate the conversation graph and generate a response
            response_text = await BusinessLogic._process_conversation(ws, current_stream, transcript)
            if response_text:
                await BusinessLogic._speak_and_send(ws, response_text, current_stream)
        return audio_buffer, silence_counter_bytes

    @staticmethod
    def _decode_audio_chunk(data, sample_width):
        media_data = data.get("media", {})
        payload = media_data.get("payload")
        if not payload:
            BusinessLogic.logger.warning("Received media event without payload")
            return None
        try:
            return audioop.ulaw2lin(base64.b64decode(payload), sample_width)
        except Exception as decode_err:
            BusinessLogic.logger.error(f"Error decoding/converting audio chunk: {decode_err}")
            return None

    @staticmethod
    def _update_silence_counter(chunk, silence_counter_bytes, sample_width, silence_threshold):
        rms: int = audioop.rms(chunk, sample_width)
        if rms < silence_threshold:
            return silence_counter_bytes + len(chunk)
        else:
            return 0

    @staticmethod
    def _transcribe_buffer(buffer_to_process):
        try:
            wav_path = BusinessLogic.save_wav(buffer_to_process)
            transcript: str = BusinessLogic.transcribe_audio(wav_path)
            BusinessLogic.logger.info(f"Transcript: {transcript}")
            os.remove(wav_path)
            return transcript
        except Exception as speech_err:
            BusinessLogic.logger.error(f"Error during transcription: {speech_err}", exc_info=True)
            return None

    @staticmethod
    async def _process_conversation(ws, current_stream, transcript):
        """Process user input through the conversation graph and get a response."""
        response_text = "Désolé, une erreur interne s'est produite."
        
        if current_stream in BusinessLogic.stream_states:
            # Get current state and update with user input
            current_state = BusinessLogic.stream_states[current_stream]
            current_state['user_input'] = transcript
            
            try:
                # Log the conversation for debugging
                BusinessLogic.logger.info(f"User [{current_stream[:8]}]: '{transcript[:50]}...'")
                
                # Invoke the graph with the updated state
                updated_state: ConversationState = await BusinessLogic.compiled_graph.ainvoke(
                    current_state,
                    {"recursion_limit": 15}  # Prevent infinite loops
                )
                
                # Save the updated state
                BusinessLogic.stream_states[current_stream] = updated_state
                
                # Extract the AI response from history
                if updated_state.get('history') and updated_state['history'][-1][0] == 'AI':
                    response_text = updated_state['history'][-1][1]
                    BusinessLogic.logger.info(f"AI [{current_stream[:8]}]: '{response_text[:50]}...'")
                else:
                    BusinessLogic.logger.warning(f"No AI response found in history after graph invocation.")
            except Exception as graph_err:
                BusinessLogic.logger.error(f"Error invoking graph: {graph_err}", exc_info=True)
            
            return response_text
        else:
            BusinessLogic.logger.error(f"Stream {current_stream} not found in states, cannot invoke graph.")
            return None

    @staticmethod
    async def _speak_and_send(ws, response_text, current_stream):
        try:
            path: str = BusinessLogic.synthesize_speech_google(response_text)
            await BusinessLogic.send_audio_to_twilio(ws, path, current_stream)
            BusinessLogic.logger.info(f"Sent graph response to stream {current_stream}: '{response_text[:50]}...'")
        except Exception as e:
            BusinessLogic.logger.error(f"Error sending graph response for stream {current_stream}: {e}", exc_info=True)

    @staticmethod
    async def _handle_stop_event(ws, current_stream):
        BusinessLogic.logger.info(f"Received stop event for stream: {current_stream}")
        if current_stream in BusinessLogic.stream_states:
            del BusinessLogic.stream_states[current_stream]
            BusinessLogic.logger.info(f"Cleaned up state for stream {current_stream}")
        else:
            BusinessLogic.logger.warning(f"Received stop for unknown or already cleaned stream: {current_stream}")
        await ws.close()

    @staticmethod
    def _handle_mark_event(data, current_stream):
        mark_name = data.get("mark", {}).get("name")
        BusinessLogic.logger.debug(f"Received mark event: {mark_name} for stream {current_stream}")

    @staticmethod
    def save_pcm_as_file(pcm_data: bytes, path: str):
        """Save PCM data (16-bit, 8kHz, mono) to a WAV file at the specified path."""
        with wave.open(path, "wb") as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(8000)
            wav_file.writeframes(pcm_data)

    @staticmethod
    def transcribe_audio(wav_path: str, language_code: str = "fr-FR") -> str:
        """Transcribe audio file using Google Cloud Speech-to-Text API."""
        try:
            # First try with OpenAI Whisper if available
            if BusinessLogic.OPENAI_API_KEY:
                try:
                    with open(wav_path, "rb") as audio_file:
                        response = BusinessLogic.client_oa.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language="fr"
                        )
                        return response.text
                except Exception as whisper_err:
                    BusinessLogic.logger.warning(f"Error with Whisper transcription, falling back to Google: {whisper_err}")
            
            # Fallback to Google Speech-to-Text
            client = speech.SpeechClient()
            with open(wav_path, "rb") as audio_file:
                content = audio_file.read()

            audio = speech.RecognitionAudio(content=content)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=8000,
                language_code=language_code,
            )

            response = client.recognize(config=config, audio=audio)

            transcript = ""
            for result in response.results:
                transcript += result.alternatives[0].transcript

            return transcript
        except Exception as e:
            BusinessLogic.logger.error(f"Error transcribing audio: {e}", exc_info=True)
            return ""

    @staticmethod
    def synthesize_speech_google(text: str, language_code: str = "fr-FR") -> str:
        """Synthesize speech using Google Cloud Text-to-Speech API."""
        try:
            client = texttospeech.TextToSpeechClient()

            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(
                language_code=language_code,
                ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
            )

            response = client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )

            # Save to file
            filename = f"{uuid.uuid4()}.mp3"
            filepath = os.path.join(BusinessLogic.TEMP_DIR, filename)
            with open(filepath, "wb") as out:
                out.write(response.audio_content)

            return filepath
        except Exception as e:
            BusinessLogic.logger.error(f"Error synthesizing speech with Google: {e}", exc_info=True)
            return ""

    @staticmethod
    def synthesize_speech_elevenlabs(text: str) -> str:
        """Synthesize speech using ElevenLabs API."""
        try:
            if not BusinessLogic.ELEVEN_API_KEY or not BusinessLogic.VOICE_ID:
                raise ValueError("ElevenLabs API key or Voice ID not set")
                
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{BusinessLogic.VOICE_ID}"
            headers = {
                "xi-api-key": BusinessLogic.ELEVEN_API_KEY,
                "xi-api-language": "fr",  # Force French language
                "Content-Type": "application/json"
            }
            data = {
                "text": text,
                "model_id": "eleven_turbo_v2",
                "voice_settings": {
                    "stability": 0.9,
                    "similarity_boost": 0.9
                }
            }

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as mp3_file:
                response = requests.post(url, json=data, headers=headers)
                if response.status_code != 200:
                    raise Exception(f"ElevenLabs error: {response.status_code} - {response.text}")
                    
                mp3_file.write(response.content)
                filepath = mp3_file.name
                
            # Copy to public directory
            filename = f"{uuid.uuid4()}.mp3"
            public_path = os.path.join(BusinessLogic.TEMP_DIR, filename)
            with open(filepath, "rb") as src, open(public_path, "wb") as dst:
                dst.write(src.read())
                
            # Remove temp file
            os.unlink(filepath)
            
            return public_path
        except Exception as e:
            BusinessLogic.logger.error(f"Error synthesizing speech with ElevenLabs: {e}", exc_info=True)
            return ""

    @staticmethod
    async def send_audio_to_twilio(ws: WebSocket, audio_path: str, stream_sid: str):
        """Convert mp3 to μ-law and send to Twilio over WebSocket."""
        try:
            # Load audio and convert to appropriate format for Twilio (8kHz μ-law)
            audio = AudioSegment.from_file(audio_path).set_frame_rate(8000).set_channels(1).set_sample_width(2)
            pcm_data = audio.raw_data
            ulaw_data = audioop.lin2ulaw(pcm_data, 2)  # 2 = 16 bits

            # Send in chunks with slight delay to simulate real-time streaming
            chunk_size = 320  # ~20ms at 8kHz
            for i in range(0, len(ulaw_data), chunk_size):
                chunk = ulaw_data[i:i + chunk_size]
                payload = base64.b64encode(chunk).decode()

                msg = {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {
                        "payload": payload
                    }
                }

                await ws.send_text(json.dumps(msg))
                await asyncio.sleep(0.02)  # 20ms for real-time simulation

            # Send mark to indicate end of message
            mark_msg = {
                "event": "mark",
                "streamSid": stream_sid,
                "mark": {
                    "name": "msg_retour"
                }
            }
            await ws.send_text(json.dumps(mark_msg))

            BusinessLogic.logger.info(f"Audio sent to Twilio for stream {stream_sid}")
            return True
        except Exception as e:
            BusinessLogic.logger.error(f"Error sending audio to Twilio: {e}", exc_info=True)
            return False
