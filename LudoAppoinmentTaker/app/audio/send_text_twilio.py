import asyncio
import logging
import time
from typing import Dict, Optional, Any
import traceback

# Constantes de configuration pour le streaming audio
DEFAULT_CHUNK_DURATION_MS = 200  # Durée cible pour chaque chunk audio
MAX_SEND_TIMEOUT_SECONDS = 5     # Temps maximum pour envoyer un chunk audio
MAX_RETRY_ATTEMPTS = 3           # Nombre maximum de tentatives en cas d'échec
WEBSOCKET_SEND_RETRY_DELAY_MS = 500  # Délai avant retentative d'envoi


class TwilioTextSender:
    """
    Classe dédiée à la conversion de texte en audio et l'envoi à Twilio.
    Utilise un contrôle de flux basé sur le timing pour assurer
    une lecture fluide et sans interruption.
    """
    
    @staticmethod
    async def process_text_to_audio(
        websocket, 
        text_queue,
        tts_provider,
        stream_sid: str,
        frame_rate: int = 8000,
        sample_width: int = 2,
        is_streaming: bool = True,
        logger = None
    ):
        """
        Processus principal qui gère le flux de texte vers audio.
        Extrait le texte de la file, synthétise l'audio et l'envoie via WebSocket
        à Twilio avec un contrôle de timing précis.
        
        Args:
            websocket: Le WebSocket Twilio
            text_queue: Instance de TextQueueManager contenant le texte à traiter
            tts_provider: Service de synthèse vocale
            stream_sid: Identifiant du stream Twilio
            frame_rate: Taux d'échantillonnage audio
            sample_width: Largeur d'échantillon audio
            is_streaming: Flag indiquant si le streaming est actif
            logger: Logger pour tracer l'exécution
        """
        logger = logger or logging.getLogger(__name__)
        
        logger.info(f"Démarrage du processus de streaming texte-audio pour stream {stream_sid}")
        
        last_chunk_time = time.time()
        last_chunk_duration_ms = 0
        
        # Boucle principale tant que le streaming est actif
        while is_streaming:
            # Récupérer le prochain segment de texte
            text_chunk = await text_queue.get_next_chunk()
            
            # Si pas de texte, attendre un peu et réessayer
            if not text_chunk:
                # S'il reste du texte en attente, continuer à traiter
                if not text_queue.is_empty():
                    logger.debug("Pas de texte complet disponible, mais il en reste à traiter")
                    await asyncio.sleep(0.05)
                    continue
                    
                # Sinon, attendre plus longtemps avant de vérifier à nouveau
                logger.debug("Pas de texte à traiter, attente...")
                await asyncio.sleep(0.2)
                continue
                
            try:
                # Synthétiser l'audio à partir du texte
                logger.debug(f"Synthèse audio pour: '{text_chunk}'")
                audio_bytes = tts_provider.synthesize_speech_to_bytes(text_chunk)
                
                # Créer l'item audio à envoyer
                audio_item = {
                    "payload": audio_bytes,
                    "stream_sid": stream_sid,
                    "frame_rate": frame_rate,
                    "sample_width": sample_width
                }
                
                # Calculer le temps d'attente optimal basé sur la durée du chunk précédent
                # pour assurer une transition fluide entre les chunks
                now = time.time()
                elapsed_since_last_chunk_ms = (now - last_chunk_time) * 1000
                
                # Attendre si nécessaire pour éviter les chevauchements ou gaps
                wait_time_ms = max(0, last_chunk_duration_ms - elapsed_since_last_chunk_ms)
                if wait_time_ms > 0:
                    logger.debug(f"Attente de {wait_time_ms:.0f}ms pour timing optimal")
                    await asyncio.sleep(wait_time_ms / 1000)
                
                # Envoyer l'audio et obtenir la durée estimée
                success, duration_ms = await TwilioTextSender._send_audio_with_retry(
                    websocket, audio_item, logger
                )
                
                if success:
                    last_chunk_time = time.time()
                    last_chunk_duration_ms = duration_ms
                    logger.debug(f"Chunk audio envoyé ({duration_ms:.0f}ms)")
                else:
                    logger.warning("Échec d'envoi audio après plusieurs tentatives")
                    # Petite pause pour éviter de spammer en cas d'erreurs répétées
                    await asyncio.sleep(0.5)
            
            except Exception as e:
                logger.error(f"Erreur de traitement audio: {e}", exc_info=True)
                # Pause pour éviter la boucle d'erreur rapide
                await asyncio.sleep(1)
        
        logger.info("Processus de streaming texte-audio terminé")
    
    @staticmethod
    async def _send_audio_with_retry(websocket, audio_item: Dict[str, Any], logger=None) -> tuple[bool, float]:
        """
        Envoie un item audio via WebSocket avec logique de retry.
        
        Args:
            websocket: Le WebSocket Twilio
            audio_item: Dictionnaire contenant les données audio et métadonnées
            logger: Logger pour tracer l'exécution
            
        Returns:
            Tuple (succès, durée_ms)
        """
        logger = logger or logging.getLogger(__name__)
        
        # Calculer la durée estimée de l'audio en millisecondes
        audio_bytes = audio_item.get("payload", b"")
        frame_rate = audio_item.get("frame_rate", 8000)
        sample_width = audio_item.get("sample_width", 2)
        
        # Calculer la durée du chunk audio (bytes / (sample_width * frame_rate))
        # Multiplier par 1000 pour avoir des millisecondes
        estimated_duration_ms = (len(audio_bytes) / (sample_width * frame_rate)) * 1000
        
        # Tentatives d'envoi avec retry
        attempt = 0
        while attempt < MAX_RETRY_ATTEMPTS:
            attempt += 1
            
            try:
                # Préparer le message pour Twilio
                message = {
                    "event": "media",
                    "streamSid": audio_item.get("stream_sid"),
                    "media": {
                        "payload": audio_bytes.decode('latin1')
                    }
                }
                
                # Envoyer avec timeout pour éviter les blocages
                send_task = asyncio.create_task(websocket.send_json(message))
                
                # Attendre l'envoi avec timeout
                await asyncio.wait_for(send_task, timeout=MAX_SEND_TIMEOUT_SECONDS)
                
                # En cas de succès, retourner la durée estimée
                return True, estimated_duration_ms
                
            except asyncio.TimeoutError:
                logger.warning(f"Timeout lors de l'envoi WebSocket (tentative {attempt}/{MAX_RETRY_ATTEMPTS})")
                
            except Exception as e:
                logger.error(f"Erreur d'envoi WebSocket: {e} (tentative {attempt}/{MAX_RETRY_ATTEMPTS})")
                logger.debug(traceback.format_exc())
                
            # Pause avant retentative
            if attempt < MAX_RETRY_ATTEMPTS:
                await asyncio.sleep(WEBSOCKET_SEND_RETRY_DELAY_MS / 1000)
        
        # Échec après toutes les tentatives
        return False, estimated_duration_ms
