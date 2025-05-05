from dotenv import load_dotenv
import os
import io
import requests
import uuid
import base64
import json
import tempfile
import asyncio
import logging
from pathlib import Path
import wave
from flask import Flask, send_file, request, Response,send_from_directory
import websockets
from openai import OpenAI
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream, Start
from gevent.pywsgi import WSGIServer
from lead_agent import LeadAgent
from calendar_agent import CalendarAgent
#from studicom_agent import StudiComAgent
from sf_agent import SFAgent
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import openai
import tempfile
import audioop
from google.cloud import speech
from google.cloud import texttospeech
from urllib.parse import urlparse, parse_qs

# Chemin du fichier de credentials (modifie ce chemin avec le bon fichier JSON sur ta machine)
credentials_path = "secrets/google-calendar-credentials.json"

# Charger les credentials dans le code directement
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# === Config ===
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY
agents = {}
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
PUBLIC_HOST = os.getenv("PUBLIC_HOST")
ELEVEN_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = os.getenv("VOICE_ID")
API_PORT = 8344
TEMP_DIR = "static/audio"
websocket_url: str = "127.0.0.1:2021"

os.makedirs(TEMP_DIR, exist_ok=True)

client = OpenAI(api_key=OPENAI_API_KEY)
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

audio_buffers = {}  # { streamSid: byte_data }

# Initialiser Flask
app = Flask(__name__)
phones = {}
sf_agents = {}

# === Flask audio serving ===
@app.route("/audio/<filename>")
def audio(filename):
    return send_from_directory(TEMP_DIR, filename)

@app.route("/webhook", methods=["POST"])
def voice_webhook():
    logger.info("Passage par le webhook")
    from_number = request.form.get("From")
    call_sid = request.form.get("CallSid")
    phones[call_sid] = from_number
    to_number = request.form.get("To")
   
    response = VoiceResponse()
    
    #start = Start()
    connect = Connect()
    connect.stream(url=websocket_url)
    response.append(connect)
    #start.stream(url=websocket_url, track="inbound")
    #response.append(start)
    
    text=f"""
        Bonjour et bienvenue chez Studi. L'école 100% en ligne !
        Je suis l'assistant virtuel Stud'IA, je prends le relais lorsque nos conseillers en formation ne sont pas présents.
        Pouvez vous me laissez vos coordonnées : nom, prénom, email et numéro de téléphone afin qu'un conseiller en formation puisse vous contacter dés son retour ?
        """
    
   
    #response.pause(length=600)  # Ne raccroche pas, laisse la ligne active

    return Response(str(response), mimetype="text/xml")

def synthesize_speech_elevenlabs(text):
    # Étape 1 : Synthèse vocale (format PCM WAV)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "xi-api-language": "fr",  # 👈 C’est ce champ qui force la langue
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

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as wav_file:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code != 200:
            raise Exception("Erreur synthèse ElevenLabs")
        wav_file.write(response.content)
        wav_path = wav_file.name

    return wav_path
   

def synthesize_speech_google(text: str, language_code="fr-FR"):
    # Créer un client pour l'API Google Cloud Text-to-Speech
    client = texttospeech.TextToSpeechClient()

    # Spécifie le texte à vocaliser
    synthesis_input = texttospeech.SynthesisInput(text=text)

    # Configure la voix
    voice = texttospeech.VoiceSelectionParams(
        language_code=language_code,  # Langue en français
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,  # Choix du genre de voix (FEMALE, MALE, NEUTRAL)
    )

    # Configuration du format audio de la sortie (ici, MP3)
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3  # Format audio
    )

    # Appel de l'API pour synthétiser la parole
    response = client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )

    # Sauvegarder le fichier MP3 temporairement
    filename = f"{uuid.uuid4()}.mp3"
    filepath = os.path.join(TEMP_DIR, filename)
    # Sauvegarder le fichier audio (MP3)
    with open(filepath, "wb") as out:
        out.write(response.audio_content)

    
    return filepath


def transcribe_audio(file_path: str, language_code="fr-FR") -> str:
    # Créer un client Google Cloud Speech-to-Text
    client = speech.SpeechClient()

    # Lire le fichier audio
    with io.open(file_path, "rb") as audio_file:
        content = audio_file.read()

    # Configurer la demande pour l'API
    audio = speech.RecognitionAudio(content=content)

    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,  # Format audio (ici pour un fichier WAV)
        sample_rate_hertz=8000,  # Taux d'échantillonnage (doit correspondre à celui de l'audio)
        language_code=language_code,  # Langue du texte
    )

    # Envoyer la requête à l'API
    response = client.recognize(config=config, audio=audio)

    # Récupérer la transcription du premier résultat
    for result in response.results:
        # La transcription du texte
        return result.alternatives[0].transcript

# WebSocket handler
async def handler3(websocket):
    print("Connexion Twilio établie")
    audio_buffer = b""
    silence_threshold = 2000         # RMS en dessous = silence
    max_silence_chunks = 30          # nombre de silences consécutifs (~500-600ms)
    silence_counter = 0          # Environ 20ms à 8kHz, mu-law
    sample_width = 2  # 16 bits PCM
    async for message in websocket:
        data = json.loads(message)
        print("📞 Nouveau message entrant :", data)
        if data.get("event") == "start":
            print("📞 Nouveau message Start ...")
            call_sid = data["start"]["callSid"]
            tel = phones[call_sid]
            print(f"📞 Appel de : {tel}")

            current_stream_sid = data["start"]["streamSid"]
            
            print(f"📞 Call SID : {current_stream_sid}")
            
            text = f"""
            Bonjour. Bienvenue chez Studi, l'école 100% en ligne !
            Je suis l'assistant virtuel Stud'IA, je prends le relais lorsque nos conseillers en formation ne sont pas présents.
            """
            filepath = synthesize_speech_google(text)
            await send_audio_to_twilio(websocket, filepath, current_stream_sid)

            #Je cherche si deja connu dans SF
            sf_agent = SFAgent()
            sf_agent.get_account_info(tel)
            sf_agents[call_sid] = sf_agent
            if sf_agent.account is not None:
                agents[current_stream_sid] = CalendarAgent(sf_agent.account["FirstName"],sf_agent.account["LastName"],sf_agent.account["Email"],sf_agent.account["OwnerFirstName"],sf_agent.account["OwnerLastName"],sf_agent.account["OwnerEmail"] ,"calendar_agent.yaml") 
                text = f"""
                Je suis ravi que vous nous contactiez à nouveau {sf_agent.account["FirstName"]}. {sf_agent.account["OwnerFirstName"]} qui vous accompagne d'habitude n'est pas disponible.
                Je vais donc m'occuper de prendre un rendez-vous avec vous afin que {sf_agent.account["OwnerFirstName"]} puisse vous contacter à son retour.
                Pouvez-vous me donner le jour et le moment de la journée qui vous convient le mieux pour ce rendez-vous ?
                 """
                
            else:
                agents[current_stream_sid] = LeadAgent("lid_api_config.yaml")
                text = f"""
                Pouvez vous me laissez vos coordonnées : nom, prénom, email et numéro de téléphone afin qu'un conseiller en formation puisse vous contacter dés son retour ?
                """
            filepath = synthesize_speech_google(text)
            await send_audio_to_twilio(websocket, filepath, current_stream_sid)
        if data.get("event") == "media":
            
            agent = agents[current_stream_sid]
            # 1. Décode le chunk μ-law
            chunk_ulaw = base64.b64decode(data["media"]["payload"])

            # 2. Convertit en PCM 16-bit
            pcm_chunk = audioop.ulaw2lin(chunk_ulaw, sample_width)

            # 3. Bufferise en PCM
            audio_buffer += pcm_chunk

            # Détection de silence
        
            # 4. Analyse du silence
            rms = audioop.rms(pcm_chunk, sample_width)
            if rms < silence_threshold:
                silence_counter += 1
            else:
                silence_counter = 0
            #print(f"Len audio buffer : {len(audio_buffer)}")
            if silence_counter >= max_silence_chunks and len(audio_buffer) > 5000:
                pcm_audio = audioop.ulaw2lin(audio_buffer, 2)
                rms_total = audioop.rms(pcm_audio, 2)

                # Vérifie que le buffer n'est pas tout silencieux
                rms_total = audioop.rms(audio_buffer, sample_width)
                if rms_total > silence_threshold:
                    filepath = synthesize_speech_google("Merci pour ces informations. Un instant s'il vous plait.")
                    await send_audio_to_twilio(websocket, filepath, current_stream_sid)
                    # Sauvegarde temporaire WAV
                    filename = f"temp_{uuid.uuid4().hex}.mp3"
                    save_pcm_to_wav(audio_buffer, filename)
                    #transcript = transcribe_audio(filename)
                    
                    with open(filename, "rb") as audio_file:
                        response = agent.client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language="fr"
                        )
                        transcript = response.text
                        
                    print("Utilisateur :", transcript)
                    print(str(agent))
                    responseText = agent.analyze_text(transcript)
                    filepath = synthesize_speech_google(responseText)
                    await send_audio_to_twilio(websocket, filepath, current_stream_sid)
                    
                audio_buffer = b""  # reset buffer
                silence_counter = 0

def convert_mp3_to_mulaw(mp3_bytes):
    audio = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
    audio = audio.set_frame_rate(8000).set_channels(1).set_sample_width(2)  # 16-bit PCM
    pcm_data = audio.raw_data
    mulaw_audio = audioop.lin2ulaw(pcm_data, 2)  # Convert to 8-bit μ-law
    return mulaw_audio

def synthesize_speech(text: str, voice: str = "alloy", model: str = "tts-1-hd") -> str:
    # Génère un fichier vocal avec OpenAI TTS
    response = openai.audio.speech.create(
        model=model,
        voice=voice,
        input=text
    )

    # Sauvegarder le fichier MP3 temporairement
    filename = f"{uuid.uuid4()}.mp3"
    filepath = os.path.join(TEMP_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(response.content)

    return filepath

async def send_audio_to_twilio(websocket, mp3_path, current_stream_sid):
    # Convertir en PCM mono 16-bit 8kHz
    audio = AudioSegment.from_file(mp3_path).set_frame_rate(8000).set_channels(1).set_sample_width(2)
    pcm_data = audio.raw_data

    # Convertir en μ-law
    ulaw_data = audioop.lin2ulaw(pcm_data, 2)  # 2 = 16 bits

    # Découper en petits chunks (20ms = 160 samples * 2 bytes = 320 bytes)
    chunk_size = 320
    for i in range(0, len(ulaw_data), chunk_size):
        chunk = ulaw_data[i:i + chunk_size]
        payload = base64.b64encode(chunk).decode()
        
        msg = {
            "event": "media",
            "streamSid": current_stream_sid ,
            "media": {
                "payload": payload
            }
        }
      
        await websocket.send(json.dumps(msg))
        await asyncio.sleep(0.02)  # 20ms pour simuler temps réel
    msg = {
            "event": "mark",
            "streamSid": current_stream_sid ,
            "mark": {
                "name": "msg_retour"
            }
        }
    
    await websocket.send(json.dumps(msg))
# === Fonction pour sauvegarder le buffer PCM en .wav
def save_pcm_to_wav(pcm_data, filename):

    sample_width = 2 
    sample_rate = 8000

    with wave.open(filename, "wb") as wav_file:
        wav_file.setnchannels(1)  # mono
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)  


# === Fonction principale asynchrone ===
async def run_websocket_server():
    """Démarre le serveur WebSocket de manière asynchrone."""
    server = await websockets.serve(handler3, "127.0.0.1", API_PORT)
    logger.info("Serveur WebSocket démarré")
    print("Serveur WebSocket démarré")
    await server.wait_closed()

# === Fonction pour démarrer Flask et WebSocket ensemble ===
def start_servers():
    """Démarre Flask et le serveur WebSocket dans des threads séparés."""
    # Créer une boucle d'événements asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Démarrer le serveur WebSocket dans un thread séparé
    import threading
    ws_thread = threading.Thread(target=lambda: loop.run_until_complete(run_websocket_server()))
    ws_thread.daemon = True
    ws_thread.start()
    
    # Démarrer Flask avec gevent sur le port 8080
    logger.info("Démarrage du serveur Flask sur http://127.0.0.1:8080")
    http_server = WSGIServer(('127.0.0.1', 8080), app)
    http_server.serve_forever()

if __name__ == "__main__":
    # Démarrer les serveurs
    start_servers() 