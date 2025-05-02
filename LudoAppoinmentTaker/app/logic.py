import base64
import os
import io
import uuid
import json
import audioop
import asyncio
import logging
import wave
from pydub import AudioSegment
from google.cloud import speech, texttospeech
from openai import OpenAI
from typing import Any, Dict
from fastapi import WebSocket
from graph import create_graph, ConversationState

class BusinessLogic:
    logger: logging.Logger = None

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ELEVEN_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    VOICE_ID: str = os.getenv("VOICE_ID", "")
    TEMP_DIR: str = "static/audio"
    os.makedirs(TEMP_DIR, exist_ok=True)

    client_oa = OpenAI(api_key=OPENAI_API_KEY)
    compiled_graph = None
    
    stream_states: Dict[str, ConversationState] = {}
    
    def init_graph():
        try:
            BusinessLogic.compiled_graph = create_graph()
            BusinessLogic.logger.info("LangGraph compiled successfully.")
        except Exception as graph_init_error:
            BusinessLogic.logger.error(f"FATAL: Failed to compile LangGraph: {graph_init_error}", exc_info=True)

    async def handler_websocket(ws: WebSocket) -> None:
        if not BusinessLogic.compiled_graph:
            BusinessLogic.logger.error("Graph not compiled, cannot handle WebSocket connection.")
            await ws.close(code=1011, reason="Server configuration error")
            return

        # Initialisation des variables audio et contexte
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
                    pass

                else:
                    BusinessLogic.logger.warning(f"Received unknown event type: {event}")

        except Exception as e:
            BusinessLogic.logger.error(f"Unhandled error in WebSocket handler loop for stream {current_stream}: {e}", exc_info=True)
        finally:
            if current_stream and current_stream in BusinessLogic.stream_states:
                BusinessLogic.logger.warning(f"Cleaning up state for stream {current_stream} due to handler exit/error.")
                del BusinessLogic.stream_states[current_stream]
            BusinessLogic.logger.info(f"WebSocket handler finished processing for {ws.client.host}:{ws.client.port} (Stream: {current_stream})" )

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
        response_text = "Désolé, une erreur interne s'est produite."
        if current_stream in BusinessLogic.stream_states:
            current_state = BusinessLogic.stream_states[current_stream]
            current_state['user_input'] = transcript
            try:
                BusinessLogic.logger.info(f"Invoking graph for stream {current_stream} with input: '{transcript[:50]}...'")
                updated_state: ConversationState = await BusinessLogic.compiled_graph.ainvoke(
                    current_state,
                    {"recursion_limit": 15}
                )
                BusinessLogic.stream_states[current_stream] = updated_state
                BusinessLogic.logger.info(f"Graph finished for stream {current_stream}. Updated state: {updated_state}")
                if updated_state.get('history') and updated_state['history'][-1][0] == 'AI':
                    response_text = updated_state['history'][-1][1]
                else:
                    BusinessLogic.logger.warning(f"No AI response found in history for stream {current_stream} after graph invocation.")
            except Exception as graph_err:
                BusinessLogic.logger.error(f"Error invoking graph for stream {current_stream}: {graph_err}", exc_info=True)
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

    def save_wav(audio_bytes: bytes) -> str:
        wav_filename = f"temp_audio_{uuid.uuid4()}.wav"
        wav_filepath = os.path.join(BusinessLogic.TEMP_DIR, wav_filename)
        
        BusinessLogic.logger.debug(f"Saving {len(audio_bytes)} bytes to WAV: {wav_filepath}")
        
        try:
            with wave.open(wav_filepath, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(audio_bytes)
            BusinessLogic.logger.debug(f"Successfully saved WAV file: {wav_filepath}")
            return wav_filepath
        except Exception as e:
            BusinessLogic.logger.error(f"Error saving WAV file {wav_filepath}: {e}", exc_info=True)
            raise

    def transcribe_audio(file_path: str) -> str:
        BusinessLogic.logger.info(f"Transcribing audio file: {file_path}")
        try:
            client = speech.SpeechClient()
            with io.open(file_path, "rb") as audio_file:
                content = audio_file.read()

            audio = speech.RecognitionAudio(content=content)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=8000,
                language_code="fr-FR",
            )

            response = client.recognize(config=config, audio=audio)
            transcript = "".join([result.alternatives[0].transcript for result in response.results])
            BusinessLogic.logger.info(f"Transcription result: {transcript}")
            return transcript
        except Exception as e:
            BusinessLogic.logger.error(f"Error during Google transcription: {e}", exc_info=True)
            return ""

    def synthesize_speech_google(text: str) -> str:
        BusinessLogic.logger.info(f"Synthesizing speech (Google): '{text[:50]}...'" )
        try:
            client = texttospeech.TextToSpeechClient()
            synthesis_input = texttospeech.SynthesisInput(text=text)

            voice = texttospeech.VoiceSelectionParams(
                language_code="fr-FR",
                ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
            )

            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                sample_rate_hertz=8000
            )

            response = client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )

            raw_filename = f"google_tts_{uuid.uuid4()}.raw"
            raw_filepath = os.path.join(TEMP_DIR, raw_filename)
            with open(raw_filepath, "wb") as out:
                out.write(response.audio_content)
            BusinessLogic.logger.info(f"Saved raw Google TTS audio to {raw_filepath}")

            audio = AudioSegment.from_raw(
                raw_filepath,
                sample_width=2,
                frame_rate=8000,
                channels=1
            )
            
            wav_filename = f"google_tts_{uuid.uuid4()}.wav"
            wav_filepath = os.path.join(TEMP_DIR, wav_filename)
            
            BusinessLogic.logger.debug(f"Converting raw audio to mulaw WAV: {wav_filepath}")
            audio.export(wav_filepath, format="wav", codec="pcm_mulaw")
            
            try:
                os.remove(raw_filepath)
            except OSError as e:
                BusinessLogic.logger.warning(f"Could not remove raw TTS file {raw_filepath}: {e}")
                
            BusinessLogic.logger.info(f"Synthesized and saved mulaw WAV: {wav_filepath}")
            return wav_filepath

        except Exception as e:
            BusinessLogic.logger.error(f"Error during Google speech synthesis: {e}", exc_info=True)
            raise

    async def send_audio_to_twilio(ws: WebSocket, file_path: str, stream_sid: str) -> None:
        BusinessLogic.logger.info(f"Sending audio file {file_path} to stream {stream_sid}")
        try:
            with open(file_path, "rb") as audio_file:
                while True:
                    chunk = audio_file.read(1600)
                    if not chunk:
                        break
                    
                    payload = base64.b64encode(chunk).decode("utf-8")
                    
                    media_message = {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {
                            "payload": payload
                        }
                    }
                    
                    await ws.send_text(json.dumps(media_message))
                    await asyncio.sleep(0.02)

            mark_message = {
                "event": "mark",
                "streamSid": stream_sid,
                "mark": {
                    "name": f"audio_playback_complete_{uuid.uuid4()}"
                }
            }
            await ws.send_text(json.dumps(mark_message))
            BusinessLogic.logger.info(f"Finished sending audio file {file_path} and sent mark event for stream {stream_sid}")

        except FileNotFoundError:
            BusinessLogic.logger.error(f"Audio file not found: {file_path}")
        except Exception as e:
            BusinessLogic.logger.error(f"Error sending audio to Twilio for stream {stream_sid}: {e}", exc_info=True)
        finally:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    BusinessLogic.logger.debug(f"Removed sent audio file: {file_path}")
            except OSError as e:
                BusinessLogic.logger.warning(f"Could not remove sent audio file {file_path}: {e}")
