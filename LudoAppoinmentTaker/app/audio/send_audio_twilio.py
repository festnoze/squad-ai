import asyncio
import logging
import base64
import json
import time
from typing import Dict, Optional, Any

class TwilioAudioSender:
    """
    Classe dédiée à l'envoi d'audio à Twilio via WebSocket.
    Gère l'envoi des différents types d'items audio (audio chunks, marques, pauses).
    
    Au lieu d'utiliser un mécanisme de back-pressure avec une taille limitée,
    cette classe envoie les éléments audio en se basant sur la durée des chunks précédents,
    assurant une lecture fluide sans interruption.
    """
    
    # Temps d'attente en millisecondes avant la fin du chunk précédent pour commencer le prochain
    # Augmenter cette valeur pour un meilleur chevauchement et une lecture plus fluide
    # Une valeur négative signifie que le prochain chunk sera envoyé AVANT la fin du précédent chunk
    SEND_TIME_BEFORE_PREVIOUS_ENDS_MS = -20  # Chevauchement des chunks pour éviter les coupures
    
    # Dictionnaire pour suivre les derniers chunks envoyés et leurs durées
    last_chunk_info = {
        'timestamp': 0,  # Quand le dernier chunk a été envoyé
        'duration_ms': 0,  # Durée du dernier chunk en millisecondes
        'stream_sid': None  # SID du stream actuel
    }
    
    @staticmethod
    async def send_chunk_to_twilio(websocket, chunk_item: dict, logger=None) -> bool:
        """
        Envoie un chunk audio à Twilio via WebSocket.
        
        Args:
            websocket: La connexion WebSocket à utiliser
            chunk_item: L'élément de la file d'attente à envoyer
            logger: Logger à utiliser pour les messages
            
        Returns:
            bool: True si l'envoi a réussi, False sinon
        """
        if logger is None:
            logger = logging.getLogger(__name__)
            
        if websocket is None:
            logger.warning("WebSocket is None")
            return False
            
        # Vérifier l'état du websocket
        if not TwilioAudioSender.is_websocket_connected(websocket, logger):
            logger.warning("WebSocket disconnected")
            return False
            
        try:
            if chunk_item['type'] == 'audio_chunk':
                await TwilioAudioSender._send_audio_data(websocket, chunk_item, logger)
            elif chunk_item['type'] == 'mark':
                await TwilioAudioSender._send_mark(websocket, chunk_item, logger)
            elif chunk_item['type'] == 'pause':
                await asyncio.sleep(chunk_item.get('duration', 0.1))
            else:
                logger.warning(f"Unknown chunk type: {chunk_item['type']}")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Error sending chunk to Twilio: {e}")
            return False
    
    @staticmethod
    async def _send_audio_data(websocket, chunk_item: dict, logger) -> None:
        """
        Envoie des données audio brutes à Twilio.
        """
        try:
            # Préparer le message à envoyer
            message = {
                "event": "media",
                "streamSid": chunk_item.get('stream_sid'),
                "media": {
                    "payload": base64.b64encode(chunk_item['data']).decode('utf-8')
                }
            }
            
            # Limiter le temps d'envoi pour éviter le blocage indéfini
            await asyncio.wait_for(websocket.send_text(json.dumps(message)), timeout=2.0)
            
        except asyncio.TimeoutError:
            logger.error("Timeout sending to Twilio WebSocket")
            raise
        except Exception as e:
            logger.error(f"Error sending audio data: {e}")
            raise
    
    @staticmethod
    async def _send_mark(websocket, chunk_item: dict, logger) -> None:
        """
        Envoie une marque (événement) à Twilio.
        """
        try:
            message = {
                "event": "mark",
                "streamSid": chunk_item.get('stream_sid'),
                "mark": {
                    "name": chunk_item.get('name', 'generic_mark')
                }
            }
            
            await asyncio.wait_for(websocket.send_text(json.dumps(message)), timeout=2.0)
            
        except asyncio.TimeoutError:
            logger.error("Timeout sending mark to Twilio WebSocket")
            raise
        except Exception as e:
            logger.error(f"Error sending mark: {e}")
            raise
    
    @staticmethod
    def is_websocket_connected(websocket, logger=None) -> bool:
        """
        Vérifie si le WebSocket est toujours connecté avec une surveillance améliorée.
        """
        if logger is None:
            logger = logging.getLogger(__name__)
            
        if not websocket:
            logger.debug("No websocket object available")
            return False
            
        try:
            # Vérifier les indicateurs de déconnexion courants
            # 1. Vérifier si la connexion a été explicitement fermée
            if hasattr(websocket, 'closed') and websocket.closed:
                logger.debug("WebSocket reports closed=True")
                return False
                
            # 2. Vérifier l'attribut client_state dans les WebSockets Starlette/FastAPI
            if hasattr(websocket, 'client_state'):
                state_str = str(websocket.client_state)
                logger.debug(f"WebSocket client_state: {state_str}")
                
                # Si client_state est un enum avec attribut CONNECTED (Starlette) 
                if hasattr(websocket.client_state, 'CONNECTED'):
                    is_connected = (websocket.client_state == websocket.client_state.CONNECTED)
                    logger.debug(f"WebSocket CONNECTED enum check: {is_connected}")
                    return is_connected
                    
                # Si client_state est une chaîne, vérifier la présence de 'connect'
                if isinstance(websocket.client_state, str):
                    is_connected = 'connect' in state_str.lower() and 'disconnect' not in state_str.lower()
                    logger.debug(f"WebSocket string state check: {is_connected} (state='{state_str}')")
                    return is_connected
            
            # 3. Pour les implémentations WebSocket spécifiques à Twilio, essayer des vérifications supplémentaires
            if hasattr(websocket, 'application_state'):
                logger.debug(f"WebSocket application_state: {websocket.application_state}")
            
            # 4. Vérifier la connexion au niveau du transport si disponible
            if hasattr(websocket, 'transport') and hasattr(websocket.transport, 'is_closing'):
                if websocket.transport.is_closing():
                    logger.debug("WebSocket transport is closing")
                    return False
            
            # Si nous sommes arrivés jusqu'ici sans réponse définitive, essayer une vérification très basique
            # Ce n'est peut-être pas fiable à 100%, mais c'est une bonne solution de repli
            if hasattr(websocket, '_send_lock'):
                # La présence d'un _send_lock indique souvent une connexion active
                logger.debug("WebSocket has _send_lock, assuming connected")
                return True
                
            # Par défaut, supposer qu'il est connecté si nous ne pouvons pas déterminer l'état de manière définitive
            logger.debug("No definitive connection state found, assuming connected")
            return True
            
        except Exception as e:
            logger.warning(f"Error checking websocket connection: {e}")
            # Enregistrer les attributs WebSocket pour le débogage
            if websocket:
                logger.debug(f"WebSocket attributes: {[attr for attr in dir(websocket) if not attr.startswith('_')]}")
            # Pour la sécurité, si nous avons eu une exception lors de la vérification, supposer connecté
            return True
    
    @staticmethod
    async def process_audio_queue_item(websocket, audio_item: dict, logger=None) -> bool:
        """
        Traite un élément de la file d'attente audio et l'envoie à Twilio.
        Utilise la durée du chunk précédent pour déterminer quand envoyer le prochain item.
        
        Args:
            websocket: La connexion WebSocket à utiliser
            audio_item: L'élément de la file d'attente à traiter
            logger: Logger à utiliser pour les messages
            
        Returns:
            bool: True si l'élément a été traité avec succès, False sinon
        """
        if logger is None:
            logger = logging.getLogger(__name__)
        
        # Valider l'élément de la file d'attente
        if not isinstance(audio_item, dict) or 'type' not in audio_item:
            logger.error(f"Invalid queue item: {audio_item}")
            return False
        
        stream_sid = audio_item.get('stream_sid')
        current_time = time.time() * 1000  # Convertir en ms
        
        # Si le stream a changé, réinitialiser les informations de suivi
        if TwilioAudioSender.last_chunk_info['stream_sid'] != stream_sid:
            logger.debug(f"New stream detected: {stream_sid}")
            TwilioAudioSender.last_chunk_info['stream_sid'] = stream_sid
            TwilioAudioSender.last_chunk_info['timestamp'] = 0
            TwilioAudioSender.last_chunk_info['duration_ms'] = 0
        
        # Calculer quand nous devrions envoyer le prochain chunk
        # Nous devons l'envoyer SEND_TIME_BEFORE_PREVIOUS_ENDS_MS ms avant la fin du précédent
        if TwilioAudioSender.last_chunk_info['timestamp'] > 0:
            last_chunk_end_time = TwilioAudioSender.last_chunk_info['timestamp'] + TwilioAudioSender.last_chunk_info['duration_ms']
            next_send_time = last_chunk_end_time - TwilioAudioSender.SEND_TIME_BEFORE_PREVIOUS_ENDS_MS
            
            # Si le prochain temps d'envoi est dans le futur, attendre
            wait_time_ms = next_send_time - current_time
            if wait_time_ms > 0:
                # Limiter le temps d'attente à un maximum raisonnable pour éviter de bloquer trop longtemps
                wait_time_ms = min(wait_time_ms, 500)  # Maximum 500ms d'attente
                logger.debug(f"Waiting {wait_time_ms:.2f}ms before sending next chunk")
                await asyncio.sleep(wait_time_ms / 1000)  # Convertir en secondes
            else:
                # Pas besoin d'attendre, mais on donne une petite chance aux autres tâches
                await asyncio.sleep(0.001)  # 1ms de pause pour éviter la surcharge CPU
        
        # Envoyer le chunk à Twilio
        try:
            send_start_time = time.time() * 1000
            success = await TwilioAudioSender.send_chunk_to_twilio(websocket, audio_item, logger)
            
            # Mettre à jour les informations du dernier chunk envoyé
            if success:
                TwilioAudioSender.last_chunk_info['timestamp'] = send_start_time
                
                # Calculer la durée du chunk en fonction de son type
                if audio_item['type'] == 'audio_chunk':
                    # Pour les chunks audio, calculer la durée basée sur la taille des données
                    chunk_size = len(audio_item.get('data', b''))
                    frame_rate = audio_item.get('frame_rate', 8000)  # Par défaut 8kHz
                    sample_width = audio_item.get('sample_width', 2)  # 2 octets par échantillon pour PCM 16-bit
                    
                    # Durée en ms = (taille en octets / octets par échantillon) / (échantillons par seconde) * 1000
                    # Pour les données µ-law, le sample_width est 1 octet
                    bytes_per_sample = 1  # µ-law est toujours 1 octet par échantillon (après conversion)
                    
                    # Calcul précis de la durée du chunk audio
                    chunk_duration_ms = (chunk_size / bytes_per_sample) / frame_rate * 1000
                    
                    # Ajouter un petit facteur de sécurité (5% de plus) pour éviter les coupures 
                    chunk_duration_ms = chunk_duration_ms * 1.05
                    TwilioAudioSender.last_chunk_info['duration_ms'] = chunk_duration_ms
                    logger.debug(f"Audio chunk duration: {chunk_duration_ms:.2f}ms, size: {chunk_size} bytes")
                elif audio_item['type'] == 'pause':
                    # Pour les pauses, utiliser la durée spécifiée
                    pause_duration_ms = audio_item.get('duration', 0.1) * 1000  # Convertir en ms
                    TwilioAudioSender.last_chunk_info['duration_ms'] = pause_duration_ms
                    logger.debug(f"Pause duration: {pause_duration_ms:.2f}ms")
                elif audio_item['type'] == 'mark':
                    # Les marques n'ont pas de durée
                    TwilioAudioSender.last_chunk_info['duration_ms'] = 0
                    logger.debug(f"Mark sent: {audio_item.get('name', 'unnamed')}")
            
            return success
        except Exception as e:
            logger.error(f"Error processing audio queue item: {e}")
            return False
            
    @staticmethod
    async def streaming_worker(websocket, audio_queue: asyncio.Queue, is_streaming: bool = True, logger=None):
        """
        Worker qui traite les éléments de la file d'attente audio et les envoie à Twilio.
        Utilise la durée des chunks audio pour assurer une lecture fluide sans interruption.
        
        Args:
            websocket: La connexion WebSocket à utiliser
            audio_queue: La file d'attente contenant les éléments audio à envoyer (taille illimitée)
            is_streaming: Flag indiquant si le streaming est actif
            logger: Logger à utiliser pour les messages
        """
        if logger is None:
            logger = logging.getLogger(__name__)
            
        # Paramètres pour la gestion des erreurs et des redémarrages
        consecutive_errors = 0
        max_consecutive_errors = 5
        restart_count = 0
        max_restart_attempts = 3
        
        # Réinitialiser les infos de suivi des chunks au démarrage du worker
        TwilioAudioSender.last_chunk_info = {
            'timestamp': 0,
            'duration_ms': 0,
            'stream_sid': None
        }
        
        logger.info("Starting audio streaming worker with timing-based flow control")
        
        while is_streaming:
            try:
                # Vérifier l'état du WebSocket avant de traiter la file d'attente
                if not TwilioAudioSender.is_websocket_connected(websocket, logger):
                    logger.error("WebSocket disconnected, stopping streaming worker")
                    break
                
                # Si la file est vide, attendre un peu et vérifier à nouveau
                if audio_queue.empty():
                    # Yield control to other tasks using a short sleep
                    await asyncio.sleep(0.01)  # 10ms yield
                    continue
                
                # Get item with a timeout to prevent blocking indefinitely
                try:
                    audio_item = await asyncio.wait_for(audio_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    await asyncio.sleep(0.01)  # Si timeout, juste attendre et continuer
                    continue
                
                # Process the queue item (avec la logique de timing pour assurer une lecture fluide)
                success = await TwilioAudioSender.process_audio_queue_item(websocket, audio_item, logger)
                
                # Mark the task as done regardless of success
                audio_queue.task_done()
                
                if success:
                    consecutive_errors = 0  # Réinitialiser le compteur quand tout va bien
                else:
                    consecutive_errors += 1
                    logger.warning(f"Error processing queue item ({consecutive_errors}/{max_consecutive_errors}), but continuing worker")
                    
                    # Si trop d'erreurs consécutives, on arrête temporairement
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f"Too many consecutive errors ({consecutive_errors}), restarting streaming worker")
                        restart_count += 1
                        
                        # Si trop de redémarrages, abandonner complètement
                        if restart_count > max_restart_attempts:
                            logger.error(f"Max restart attempts ({max_restart_attempts}) reached, stopping streaming worker")
                            break
                        
                        # Pause avant de réessayer pour donner une chance au système de se stabiliser
                        await asyncio.sleep(1.0)
                        consecutive_errors = 0
                        
                        # Réinitialiser les infos de suivi après une erreur
                        TwilioAudioSender.last_chunk_info = {
                            'timestamp': 0,
                            'duration_ms': 0,
                            'stream_sid': None
                        }

            
            except asyncio.CancelledError:
                logger.info("Streaming worker task cancelled")
                break
            except Exception as e:
                logger.error(f"Unhandled error in streaming worker: {e}", exc_info=True)
                consecutive_errors += 1
                await asyncio.sleep(0.5)  # Pause avant de réessayer
                
                # Si trop d'erreurs, abandonner complètement
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("Too many errors in streaming worker, stopping")
                    break
        
        logger.info("Audio streaming worker stopped")
