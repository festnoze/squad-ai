import asyncio
import time
import logging
import os
from typing import Dict, Any, Optional
import io
import uuid
from pydub import AudioSegment
import audioop
import wave
from contextlib import asynccontextmanager

class AudioQueueManager:
    """
    Classe dédiée à la gestion de la file d'attente audio.
    Gère l'ajout et le traitement des éléments audio avant leur envoi à Twilio.
    Intègre un mécanisme de back-pressure pour éviter de surcharger la file d'attente.
    """
    DEFAULT_FRAME_RATE = 8000  # Hz
    DEFAULT_SAMPLE_WIDTH = 2   # bytes (16-bit)
    DEFAULT_CHUNK_DURATION_MS = 200  # ms - Plus petite taille de chunk pour un audio plus fluide
    DEFAULT_BACK_PRESSURE_TIMEOUT = 10.0  # Timeout en secondes pour attendre de la place dans la queue
    
    @staticmethod
    def save_as_wav_file(audio_data: bytes, temp_dir: str, frame_rate: int = DEFAULT_FRAME_RATE, sample_width: int = DEFAULT_SAMPLE_WIDTH):
        """Enregistrer les données PCM dans un fichier WAV."""
        file_name = f"{uuid.uuid4()}.wav"
        with wave.open(os.path.join(temp_dir, file_name), "wb") as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(sample_width)  # 16-bit
            wav_file.setframerate(frame_rate)
            wav_file.writeframes(audio_data)
        return file_name
    
    @staticmethod
    def delete_temp_file(file_name: str, temp_dir: str):
        """Supprimer un fichier temporaire."""
        try:
            os.remove(os.path.join(temp_dir, file_name))
        except Exception as e:
            logging.error(f"Error deleting temp file {file_name}: {e}")
    
    @staticmethod
    def prepare_voice_stream(file_path: str = None, audio_bytes: bytes = None, 
                           frame_rate: int = DEFAULT_FRAME_RATE, channels: int = 1, 
                           sample_width: int = DEFAULT_SAMPLE_WIDTH, convert_to_mulaw: bool = False):
        """Prépare le flux audio à partir d'un fichier ou de bytes directement"""
        if (file_path and audio_bytes) or (not file_path and not audio_bytes):
            raise ValueError("Must provide either file_path or audio_bytes, but not both.")
        
        if file_path:
            audio = AudioSegment.from_file(file_path).set_frame_rate(frame_rate).set_channels(channels).set_sample_width(sample_width)
        else:
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            audio = audio.set_frame_rate(frame_rate).set_channels(channels).set_sample_width(sample_width)
        pcm_data = audio.raw_data
        if convert_to_mulaw:
            mulaw_audio = audioop.lin2ulaw(pcm_data, sample_width)  # Convert to 8-bit μ-law
            return mulaw_audio
        else:
            return pcm_data
    
    @staticmethod
    async def fill_audio_queue(queue: asyncio.Queue, file_path: str = None, audio_bytes: bytes = None, 
                             frame_rate: int = DEFAULT_FRAME_RATE, channels: int = 1, 
                             sample_width: int = DEFAULT_SAMPLE_WIDTH, convert_to_mulaw: bool = False,
                             stream_sid: str = None, chunk_duration_ms: int = DEFAULT_CHUNK_DURATION_MS,
                             temp_dir: str = None, logger=None):
        """
        Remplit la file d'attente audio avec des chunks de taille appropriée.
        Cette méthode est conçue pour être exécutée dans une tâche asyncio séparée.
        """
        if logger is None:
            logger = logging.getLogger(__name__)
            
        start_time = time.time()
        
        try:
            # Charger l'audio et le convertir au format approprié
            ulaw_data = AudioQueueManager.prepare_voice_stream(
                file_path=file_path, 
                audio_bytes=audio_bytes, 
                frame_rate=frame_rate, 
                channels=channels, 
                sample_width=sample_width, 
                convert_to_mulaw=True
            )
            
            # Supprimer le fichier temporaire s'il existe
            if file_path and temp_dir:
                AudioQueueManager.delete_temp_file(file_path, temp_dir)
            
            # Calculer la taille des chunks en fonction de la durée
            chunk_size = int((chunk_duration_ms / 1000) * frame_rate * sample_width)
            
            # Calculer les attributs audio totaux
            total_audio_seconds = (len(ulaw_data) / (frame_rate * sample_width))
            total_chunks = len(ulaw_data) // chunk_size + (1 if len(ulaw_data) % chunk_size else 0)
            
            # Diviser l'audio en petits chunks pour une meilleure gestion
            # Des chunks plus petits se traitent plus rapidement et permettent un contrôle plus précis
            max_chunk_duration_ms = 500  # Maximum 500ms par chunk pour un meilleur contrôle
            chunks_per_group = max(1, int(max_chunk_duration_ms / chunk_duration_ms))
            total_groups = (total_chunks + chunks_per_group - 1) // chunks_per_group
            
            logger.info(f"-> Queueing {total_audio_seconds:.2f}s of audio splitted in {total_chunks} chunks ({total_groups} groups)")
            
            # Mettre tous les chunks audio dans la file d'attente avec de petites pauses entre les groupes
            chunks_queued = 0
            
            for group in range(total_groups):
                group_start = group * chunks_per_group * chunk_size
                group_end = min(group_start + (chunks_per_group * chunk_size), len(ulaw_data))
                group_data = ulaw_data[group_start:group_end]
                
                # Ajouter une pause entre les groupes (sans vérifier si la file est pleine)
                if group > 0:
                    await queue.put({
                        'type': 'pause',
                        'duration': 0.2,  # 200ms pause entre les groupes
                        'stream_sid': stream_sid,
                        'frame_rate': frame_rate,
                        'sample_width': sample_width
                    })
                
                # Traiter le groupe audio en chunks individuels
                for i in range(0, len(group_data), chunk_size):
                    chunk = group_data[i:i + chunk_size]
                    
                    # Ajouter ce chunk à la file d'attente sans restriction de taille
                    await queue.put({
                        'type': 'audio_chunk',
                        'data': chunk,
                        'stream_sid': stream_sid,
                        'frame_rate': frame_rate,
                        'sample_width': sample_width
                    })
                    chunks_queued += 1
                    
                    # Céder le contrôle après chaque chunk pour éviter de bloquer
                    await asyncio.sleep(0)
                    
                    # Tous les N chunks, ajouter une mini pause (sauf pour le dernier chunk)
                    if chunks_queued % 3 == 0 and chunks_queued < total_chunks:
                        # Ajouter une très petite pause tous les 3 chunks
                        await queue.put({
                            'type': 'pause',
                            'duration': 0.02,  # 20ms mini-pause après chaque 3 chunks (réduit pour plus de fluidité)
                            'stream_sid': stream_sid,
                            'frame_rate': frame_rate,
                            'sample_width': sample_width
                        })
            
            # Ajouter la marque finale pour signaler la fin du message
            await queue.put({
                'type': 'mark',
                'name': 'msg_retour',
                'stream_sid': stream_sid
            })
            
            # Enregistrer les statistiques de la file d'attente
            logger.info(f"Successfully queued {chunks_queued} audio chunks (~{total_audio_seconds:.2f}s)")
            return True
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Error preparing audio for queue: {elapsed:.2f}s elapsed: {e}", exc_info=True)
            return False
    
    @staticmethod
    async def clear_audio_queue(queue: asyncio.Queue, logger=None):
        """Vide la file d'attente audio de manière sécurisée."""
        if logger is None:
            logger = logging.getLogger(__name__)
            
        try:
            # Vider proprement la file d'attente en marquant les tâches comme terminées
            while not queue.empty():
                try:
                    # Récupérer un élément sans attendre
                    queue.get_nowait()
                    queue.task_done()  # Important pour éviter les blocages
                except asyncio.QueueEmpty:
                    break  # La file est vide, sortir de la boucle
                except Exception as e:
                    logger.error(f"Error clearing audio queue: {e}")
                    break
            
            logger.info("Audio queue cleared successfully")
            return True
        except Exception as e:
            logger.error(f"Error in clear_audio_queue: {e}")
            return False
    
    # Cette méthode n'est plus nécessaire car nous n'utilisons plus de file d'attente bornée
    # et nous nous basons maintenant sur la durée des chunks audio pour contrôler le flux
    # La méthode est conservée ici pour compatibilité mais n'a plus d'effet
    @staticmethod
    async def wait_if_queue_full(queue: asyncio.Queue, timeout: float = DEFAULT_BACK_PRESSURE_TIMEOUT, logger=None):
        """
        Cette méthode est maintenue pour compatibilité mais n'a plus d'effet.
        Le contrôle de flux est maintenant basé sur la durée des chunks audio, pas sur la taille de la file d'attente.
        """
        # Ne fait rien, retourne simplement True
        return True
    
    # Cette méthode n'est plus nécessaire car nous n'utilisons plus de file d'attente bornée
    # et nous nous basons maintenant sur la durée des chunks audio pour contrôler le flux
    # La méthode est conservée ici pour compatibilité mais n'a plus d'effet
    @staticmethod
    @asynccontextmanager
    async def queue_flow_control(queue: asyncio.Queue, timeout: float = DEFAULT_BACK_PRESSURE_TIMEOUT, logger=None):
        """
        Cette méthode est maintenue pour compatibilité mais n'a plus d'effet.
        Le contrôle de flux est maintenant basé sur la durée des chunks audio, pas sur la taille de la file d'attente.
        
        Usage:
            async with AudioQueueManager.queue_flow_control(audio_queue):
                # Code qui ajoute des éléments à la file
                await audio_queue.put(item)
        """
        try:
            # Céder le contrôle au bloc with sans attente
            yield True
        finally:
            # Rien à faire à la sortie du bloc with
            pass
            
    @staticmethod
    def create_queue(maxsize: int = 0) -> asyncio.Queue:
        """
        Crée une file d'attente sans limite de taille (maxsize=0).
        Le contrôle de flux est maintenant basé sur la durée des chunks audio, pas sur la taille de la file.
        """
        return asyncio.Queue(maxsize=0)
