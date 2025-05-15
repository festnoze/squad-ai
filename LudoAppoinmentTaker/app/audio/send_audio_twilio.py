import asyncio
import logging
import base64
import json

class TwilioAudioSender:
    """
    Classe dédiée à l'envoi d'audio à Twilio via WebSocket.
    Gère l'envoi des différents types d'items audio (audio chunks, marques, pauses).
    """
    
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
        
        # Envoyer le chunk à Twilio
        try:
            success = await TwilioAudioSender.send_chunk_to_twilio(websocket, audio_item, logger)
            return success
        except Exception as e:
            logger.error(f"Error processing audio queue item: {e}")
            return False
            
    @staticmethod
    async def streaming_worker(websocket, audio_queue: asyncio.Queue, is_streaming: bool = True, logger=None):
        """
        Worker qui traite les éléments de la file d'attente audio et les envoie à Twilio.
        Cette méthode est conçue pour être exécutée dans une tâche asyncio séparée.
        
        Args:
            websocket: La connexion WebSocket à utiliser
            audio_queue: La file d'attente contenant les éléments audio à envoyer
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
        
        logger.info("Starting audio streaming worker")
        
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
                
                # Process the queue item
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
