import asyncio
import json
import logging
import os
import re
import uuid
import wave

import aiohttp
from api_client.salesforce_api_client import SalesforceApiClient
from speech.twilio_audio_sender import TwilioAudioSender
from utils.envvar import EnvHelper


class WebSocketWrapper:
    """Wrapper pour uniformiser l'interface WebSocket entre aiohttp client et FastAPI server"""

    def __init__(self, aiohttp_ws):
        self.ws = aiohttp_ws

    async def send_text(self, data: str):
        """Wrapper pour send_text qui utilise send_str d'aiohttp"""
        await self.ws.send_str(data)

    def __getattr__(self, name):
        """Délègue tous les autres attributs au WebSocket aiohttp"""
        return getattr(self.ws, name)


class AudioTestSimulator:
    """
    Simule des appels téléphoniques en utilisant les fichiers audio existants
    dans le dossier static/incoming_audio pour tester l'API en parallèle.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8344"):
        self.logger = logging.getLogger(__name__)
        self.base_url = base_url
        self.test_audio_dir = "static/test_audio"
        self.active_sessions: dict[str, dict] = {}
        self.session_counter = 0

        # Paramètres audio Twilio
        self.sample_rate = 8000  # 8kHz
        self.sample_width = 2  # 16-bit
        self.channels = 1  # Mono
        self.chunk_duration_ms = 20  # 20ms chunks comme Twilio

    async def start_simulation(self, concurrent_calls_count: int):
        """Démarre la simulation avec plusieurs appels simultanés"""
        self.logger.info(f"Démarrage de la simulation audio avec {concurrent_calls_count} appels simultanés")

        # Obtenir la liste des fichiers audio
        audio_files = await self._get_audio_files()
        if not audio_files:
            self.logger.warning("Aucun fichier audio trouvé dans static/incoming_audio")
            return

        # Get true existing phone numbers from SF client
        client = SalesforceApiClient()
        phone_numbers = await client.get_phone_numbers_async(concurrent_calls_count)
        # Créer les tâches pour les appels simultanés
        tasks = []
        for i in range(concurrent_calls_count):
            call_id = f"test-call-{self.session_counter}-{phone_numbers[i]['phone_number']}"
            self.session_counter += 1

            # Chaque appel concurrent va jouer TOUS les fichiers audio dans l'ordre chronologique
            task = asyncio.create_task(self._simulate_single_call(call_id, audio_files, delay_start=i * 2))
            tasks.append(task)

        # Attendre que tous les appels se terminent
        await asyncio.gather(*tasks, return_exceptions=True)
        self.logger.info("Simulation terminée")

    async def _simulate_single_call(self, call_id: str, audio_files: list[str], delay_start: int = 0):
        """Simule un seul appel téléphonique avec tous les fichiers audio"""
        if delay_start > 0:
            await asyncio.sleep(delay_start)

        self.logger.info(f"Démarrage de l'appel simulé {call_id} avec {len(audio_files)} fichiers audio")

        try:
            # 1. Initier l'appel (POST endpoint)
            calling_phone = f"+336{call_id[-8:]}"  # Numéro fictif
            call_sid = f"CA{uuid.uuid4().hex[:32]}"

            self.logger.info(f"Simulation d'appel: {calling_phone} -> {call_sid}")

            # Pour les tests, on skip l'appel POST et va directement au WebSocket
            # await self._initiate_call(calling_phone, call_sid)

            # 2. Obtenir l'URL WebSocket via l'endpoint dédié
            websocket_url = await self._get_websocket_url(calling_phone, call_sid)
            if not websocket_url:
                self.logger.error(f"Impossible d'obtenir l'URL WebSocket pour {call_id}")
                return

            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(websocket_url) as aiohttp_ws:
                    # Wrapper pour uniformiser l'interface WebSocket
                    ws = WebSocketWrapper(aiohttp_ws)

                    # 3. Envoyer l'événement 'connected'
                    await self._send_connected_event(ws)

                    # 4. Envoyer l'événement 'start'
                    stream_sid = f"MZ{uuid.uuid4().hex[:32]}"
                    await self._send_start_event(ws, call_sid, stream_sid)

                    # 5. Créer le TwilioAudioSender et envoyer tous les fichiers audio
                    audio_sender = TwilioAudioSender(
                        websocket=ws,
                        stream_sid=stream_sid,
                        sample_rate=self.sample_rate,
                        min_chunk_interval=self.chunk_duration_ms / 1000.0,
                    )
                    await self._send_all_incoming_audio_events(audio_sender, audio_files)

                    # 6. Envoyer l'événement 'stop'
                    await self._send_stop_event(ws)

        except Exception as e:
            self.logger.error(f"Erreur dans l'appel simulé {call_id}: {e}", exc_info=True)

    async def _initiate_call(self, calling_phone: str, call_sid: str):
        """Initie l'appel via l'endpoint POST"""
        url = f"{self.base_url}/"
        data = {"From": calling_phone, "CallSid": call_sid, "CallStatus": "ringing"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        self.logger.warning(f"Réponse inattendue de l'endpoint: {response.status}")
                        response_text = await response.text()
                        self.logger.debug(f"Réponse: {response_text}")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initiation de l'appel: {e}")
            raise

    async def _get_websocket_url(self, calling_phone: str, call_sid: str) -> str | None:
        """Obtient l'URL WebSocket via l'endpoint dédié"""
        url = f"{self.base_url}/websocket-url"
        params = {"From": calling_phone, "CallSid": call_sid, "CallStatus": "ringing", "api_key": EnvHelper.get_admin_api_keys()[0]}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        # L'endpoint retourne l'URL WebSocket dans le contenu
                        websocket_url = await response.text()
                        self.logger.info(f"URL WebSocket obtenue: {websocket_url}")
                        return websocket_url.strip()
                    else:
                        self.logger.error(f"Erreur lors de l'obtention de l'URL WebSocket: {response.status}")
                        response_text = await response.text()
                        self.logger.debug(f"Réponse: {response_text}")
                        return None
        except Exception as e:
            self.logger.error(f"Erreur lors de l'obtention de l'URL WebSocket: {e}")
            return None

    async def _send_connected_event(self, ws):
        """Envoie l'événement 'connected' Twilio"""
        event = {"event": "connected", "protocol": "Call", "version": "1.0.0"}
        await ws.send_text(json.dumps(event))
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
                "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
            },
            "streamSid": stream_sid,
        }
        await ws.send_text(json.dumps(event))
        self.logger.debug(f"Événement 'start' envoyé pour stream {stream_sid}")

    async def _send_stop_event(self, ws):
        """Envoie l'événement 'stop' Twilio"""
        event = {"event": "stop", "sequenceNumber": "2"}
        await ws.send_text(json.dumps(event))
        self.logger.debug("Événement 'stop' envoyé")

    async def _send_all_incoming_audio_events(self, audio_sender: TwilioAudioSender, audio_files: list[str]):
        """Envoie tous les fichiers audio dans l'ordre chronologique"""
        self.logger.info(f"Envoi de {len(audio_files)} fichiers audio dans l'ordre chronologique")

        for audio_file in audio_files:
            await self._send_incoming_audio_event(audio_sender, audio_file)

        self.logger.info("Tous les fichiers audio ont été envoyés")

    async def _send_incoming_audio_event(self, audio_sender: TwilioAudioSender, audio_file: str):
        """Lit un fichier audio et l'envoie via TwilioAudioSender"""
        file_path = os.path.join(self.test_audio_dir, audio_file)

        if not os.path.exists(file_path):
            self.logger.error(f"Fichier audio non trouvé: {file_path}")
            return

        # Extraire le timing du nom de fichier (format: uuid-milliseconds.wav)
        timing_ms = self._extract_timing_from_filename(audio_file)
        start_delay = timing_ms / 1000.0 if timing_ms else 0

        self.logger.info(f"Envoi du fichier audio {audio_file} avec délai initial de {start_delay:.2f}s")
        if start_delay > 0:
            await asyncio.sleep(start_delay)

        try:
            with wave.open(file_path, "rb") as wav_file:
                if wav_file.getframerate() != self.sample_rate:
                    self.logger.warning(f"Taux d'échantillonnage inattendu: {wav_file.getframerate()} (attendu: {self.sample_rate})")

                # Lire tout le fichier audio en une fois
                all_frames = wav_file.readframes(wav_file.getnframes())

                # Envoyer l'audio via TwilioAudioSender qui gère le chunking automatiquement
                success = await audio_sender.send_audio_chunk_async(all_frames)

                if success:
                    self.logger.info(f"Fichier audio {audio_file} envoyé avec succès")
                else:
                    self.logger.error(f"Erreur lors de l'envoi du fichier audio {audio_file}")

        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi du fichier audio {audio_file}: {e}", exc_info=True)

    def _extract_timing_from_filename(self, filename: str) -> int | None:
        """Extrait le timing en millisecondes du nom de fichier"""
        # Format attendu: uuid-milliseconds.wav
        match = re.search(r"-(\d+)\.wav$", filename)
        if match:
            return int(match.group(1))
        return None

    async def _get_audio_files(self) -> list[str]:
        """Récupère la liste des fichiers audio dans le dossier static/incoming_audio"""
        if not os.path.exists(self.test_audio_dir):
            self.logger.error(f"Dossier audio non trouvé: {self.test_audio_dir}")
            return []

        audio_files = []
        for filename in os.listdir(self.test_audio_dir):
            if filename.endswith(".wav"):
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

    async def run_fake_incoming_calls(self, concurrent_calls_count: int):
        """Lance les tests si TEST_AUDIO=true"""
        if not EnvHelper.get_allow_test_fake_incoming_calls():
            return

        self.logger.info("Mode test audio activé - Démarrage de la simulation")

        # Lancer la simulation avec plusieurs appels simultanés
        await self.simulator.start_simulation(concurrent_calls_count)

    async def _wait_for_api_ready(self, max_attempts: int = 10, delay: float = 2.0):
        """Attend que l'API soit prête à recevoir des connexions"""
        for attempt in range(max_attempts):
            try:
                async with aiohttp.ClientSession() as session:
                    # Test de santé simple
                    async with session.get(f"{self.simulator.base_url}/ping", timeout=aiohttp.ClientTimeout(total=5)) as response:
                        if response.status == 200:
                            self.logger.info(f"API prête après {attempt + 1} tentative(s)")
                            return
            except Exception as e:
                self.logger.debug(f"Tentative {attempt + 1}/{max_attempts} échouée: {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(delay)

        self.logger.error("L'API n'est pas prête après toutes les tentatives. Abandon de la simulation.")
        raise ConnectionError("Impossible de se connecter à l'API")
