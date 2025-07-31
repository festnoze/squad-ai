import os
import json
import wave
import base64
import asyncio
import logging
import audioop
import uuid
import re
from typing import List, Dict, Optional
from datetime import datetime
import aiohttp

from utils.envvar import EnvHelper


class AudioTestSimulator:
    """
    Simule des appels téléphoniques en utilisant les fichiers audio existants
    dans le dossier static/incoming_audio pour tester l'API en parallèle.
    """
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.logger = logging.getLogger(__name__)
        self.base_url = base_url
        self.test_audio_dir = "static/test_audio"
        self.active_sessions: Dict[str, dict] = {}
        self.session_counter = 0
        
        # Paramètres audio Twilio
        self.sample_rate = 8000  # 8kHz
        self.sample_width = 2    # 16-bit
        self.channels = 1        # Mono
        self.chunk_duration_ms = 20  # 20ms chunks comme Twilio
        
    async def start_simulation(self, num_concurrent_calls: int = 1):
        """Démarre la simulation avec plusieurs appels simultanés"""
        self.logger.info(f"Démarrage de la simulation audio avec {num_concurrent_calls} appels simultanés")
        
        # Obtenir la liste des fichiers audio
        audio_files = await self._get_audio_files()
        if not audio_files:
            self.logger.warning("Aucun fichier audio trouvé dans static/incoming_audio")
            return
            
        # Créer les tâches pour les appels simultanés
        tasks = []
        for i in range(num_concurrent_calls):
            # Choisir un fichier audio (rotation circulaire)
            audio_file = audio_files[i % len(audio_files)]
            call_id = f"test-call-{self.session_counter}-{i}"
            self.session_counter += 1
            
            task = asyncio.create_task(
                self._simulate_single_call(call_id, audio_file, delay_start=i * 2)
            )
            tasks.append(task)
            
        # Attendre que tous les appels se terminent
        await asyncio.gather(*tasks, return_exceptions=True)
        self.logger.info("Simulation terminée")
        
    async def _simulate_single_call(self, call_id: str, audio_file: str, delay_start: int = 0):
        """Simule un seul appel téléphonique"""
        if delay_start > 0:
            await asyncio.sleep(delay_start)
            
        self.logger.info(f"Démarrage de l'appel simulé {call_id} avec le fichier {audio_file}")
        
        try:
            # 1. Initier l'appel (POST endpoint)
            calling_phone = f"+336{call_id[-8:]}"  # Numéro fictif
            call_sid = f"CA{uuid.uuid4().hex[:32]}"
            
            await self._initiate_call(calling_phone, call_sid)
            
            # 2. Établir la connexion WebSocket
            websocket_url = f"ws://localhost:8000/call/{calling_phone}/{call_sid}"
            
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(websocket_url) as ws:
                    
                    # 3. Envoyer l'événement 'connected'
                    await self._send_connected_event(ws)
                    
                    # 4. Envoyer l'événement 'start'
                    stream_sid = f"MZ{uuid.uuid4().hex[:32]}"
                    await self._send_start_event(ws, call_sid, stream_sid)
                    
                    # 5. Lire et envoyer le fichier audio
                    await self._send_audio_from_file(ws, audio_file, stream_sid)
                    
                    # 6. Envoyer l'événement 'stop'
                    await self._send_stop_event(ws)
                    
        except Exception as e:
            self.logger.error(f"Erreur dans l'appel simulé {call_id}: {e}", exc_info=True)
            
    async def _initiate_call(self, calling_phone: str, call_sid: str):
        """Initie l'appel via l'endpoint POST"""
        url = f"{self.base_url}/twilio/incoming-call"
        data = {
            "From": calling_phone,
            "CallSid": call_sid,
            "CallStatus": "ringing"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                if response.status != 200:
                    self.logger.warning(f"Réponse inattendue de l'endpoint: {response.status}")
                    
    async def _send_connected_event(self, ws):
        """Envoie l'événement 'connected' Twilio"""
        event = {
            "event": "connected",
            "protocol": "Call",
            "version": "1.0.0"
        }
        await ws.send_str(json.dumps(event))
        self.logger.debug("Événement 'connected' envoyé")
        
    async def _send_start_event(self, ws, call_sid: str, stream_sid: str):
        """Envoie l'événement 'start' Twilio"""
        event = {
            "event": "start",
            "sequenceNumber": "1",
            "start": {
                "accountSid": "AC" + "0" * 32,
                "streamSid": stream_sid,
                "callSid": call_sid,
                "tracks": ["inbound"],
                "mediaFormat": {
                    "encoding": "audio/x-mulaw",
                    "sampleRate": 8000,
                    "channels": 1
                }
            },
            "streamSid": stream_sid
        }
        await ws.send_str(json.dumps(event))
        self.logger.debug(f"Événement 'start' envoyé pour stream {stream_sid}")
        
    async def _send_stop_event(self, ws):
        """Envoie l'événement 'stop' Twilio"""
        event = {
            "event": "stop",
            "sequenceNumber": "2"
        }
        await ws.send_str(json.dumps(event))
        self.logger.debug("Événement 'stop' envoyé")
        
    async def _send_audio_from_file(self, ws, audio_file: str, stream_sid: str):
        """Lit un fichier audio et l'envoie par chunks comme Twilio"""
        file_path = os.path.join(self.test_audio_dir, audio_file)
        
        if not os.path.exists(file_path):
            self.logger.error(f"Fichier audio non trouvé: {file_path}")
            return
            
        # Extraire le timing du nom de fichier (format: uuid-milliseconds.wav)
        timing_ms = self._extract_timing_from_filename(audio_file)
        start_delay = timing_ms / 1000.0 if timing_ms else 0
        
        self.logger.info(f"Envoi du fichier audio {audio_file} avec délai initial de {start_delay:.2f}s")
        
        # Attendre le délai initial basé sur le timing du fichier
        if start_delay > 0:
            await asyncio.sleep(start_delay)
            
        try:
            # Lire le fichier WAV
            with wave.open(file_path, 'rb') as wav_file:
                # Vérifier le format
                if wav_file.getframerate() != self.sample_rate:
                    self.logger.warning(f"Taux d'échantillonnage inattendu: {wav_file.getframerate()} (attendu: {self.sample_rate})")
                    
                # Calculer la taille des chunks
                frames_per_chunk = int(self.sample_rate * self.chunk_duration_ms / 1000)
                bytes_per_chunk = frames_per_chunk * wav_file.getsampwidth() * wav_file.getnchannels()
                
                sequence_number = 1
                
                # Lire et envoyer le fichier par chunks
                while True:
                    frames = wav_file.readframes(frames_per_chunk)
                    if not frames:
                        break
                        
                    # Convertir PCM en μ-law comme Twilio
                    mulaw_data = audioop.lin2ulaw(frames, wav_file.getsampwidth())
                    
                    # Encoder en base64
                    payload = base64.b64encode(mulaw_data).decode('utf-8')
                    
                    # Créer l'événement media
                    media_event = {
                        "event": "media",
                        "sequenceNumber": str(sequence_number),
                        "media": {
                            "track": "inbound",
                            "chunk": str(sequence_number), 
                            "timestamp": str(sequence_number * self.chunk_duration_ms),
                            "payload": payload
                        },
                        "streamSid": stream_sid
                    }
                    
                    await ws.send_str(json.dumps(media_event))
                    sequence_number += 1
                    
                    # Respecter le timing réel (20ms par chunk)
                    await asyncio.sleep(self.chunk_duration_ms / 1000.0)
                    
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi du fichier audio {audio_file}: {e}", exc_info=True)
            
    def _extract_timing_from_filename(self, filename: str) -> Optional[int]:
        """Extrait le timing en millisecondes du nom de fichier"""
        # Format attendu: uuid-milliseconds.wav
        match = re.search(r'-(\d+)\.wav$', filename)
        if match:
            return int(match.group(1))
        return None
        
    async def _get_audio_files(self) -> List[str]:
        """Récupère la liste des fichiers audio dans le dossier static/incoming_audio"""
        if not os.path.exists(self.test_audio_dir):
            self.logger.error(f"Dossier audio non trouvé: {self.test_audio_dir}")
            return []
            
        audio_files = []
        for filename in os.listdir(self.test_audio_dir):
            if filename.endswith('.wav'):
                audio_files.append(filename)
                
        # Trier les fichiers par timing (basé sur le nom de fichier)
        def get_timing(filename):
            timing = self._extract_timing_from_filename(filename)
            return timing if timing is not None else 0
            
        audio_files.sort(key=get_timing)
        
        self.logger.info(f"Fichiers audio trouvés: {len(audio_files)}")
        return audio_files


class AudioTestManager:
    """Gestionnaire principal pour les tests audio automatiques"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.simulator = AudioTestSimulator()
        
    async def run_if_enabled(self):
        """Lance les tests si TEST_AUDIO=true"""
        if not EnvHelper.get_test_audio():
            return
            
        self.logger.info("Mode test audio activé - Démarrage de la simulation")
        
        # Attendre que l'application soit prête
        await asyncio.sleep(2)
        
        # Lancer la simulation avec plusieurs appels simultanés
        await self.simulator.start_simulation(num_concurrent_calls=3)