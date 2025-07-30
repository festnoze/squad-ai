import logging
import hashlib
import os
from pathlib import Path
from typing import Optional
from utils.envvar import EnvHelper
from speech.text_to_speech import get_text_to_speech_provider, TextToSpeechProvider
from managers.outgoing_audio_manager import OutgoingAudioManager

class PreGeneratedAudio:
    """
    Manages pregenerated audio files for TTS to avoid repeated synthesis of common texts.
    Stores files in directory structure: {pregenerated_dir}/{provider}/{voice}/{hash}.pcm
    """
    pregenerated_dir: str = "static/pregenerated_audio"
    logger = logging.getLogger(__name__)
    
    @staticmethod
    async def populate_permanent_cache_at_startup_async() -> dict:
        """
        Populate cache with permanent pregenerated audio files at startup with commonly used texts.
        First checks if files exist, loads from file if available, otherwise synthesizes and saves.
        Then add to cache - in both cases.
            
        Returns:
            Dictionary with results: loaded_count, synthesized_count, failed_count
        """
         # Import here to avoid circular import
        from agents.agents_graph import AgentsGraph
        
        texts_to_pregenerate = [
            AgentsGraph.start_welcome_text,
            AgentsGraph.other_text
        ]
        
        # Filter out empty texts
        texts_to_pregenerate = [text for text in texts_to_pregenerate if text and text.strip()]
        
        if not texts_to_pregenerate:
            PreGeneratedAudio.logger.warning("No texts to pregenerate from AgentsGraph")
            return
               
        results = {"loaded_count": 0, "synthesized_count": 0, "failed_count": 0}
        
        try:
            # Create TTS provider instance
            tts_provider_name = EnvHelper.get_text_to_speech_provider() or "openai" 
            PreGeneratedAudio.logger.info(f"Starting pregenerated audio population with {len(texts_to_pregenerate)} texts using {tts_provider_name} provider")
            
            tts_provider: TextToSpeechProvider = get_text_to_speech_provider(
                provider_name=tts_provider_name,
                frame_rate=8000,
                channels=1,
                sample_width=2,
                temp_dir="static/outgoing_audio"
            )
            
            # Process each text
            for text in texts_to_pregenerate:
                if not text or not text.strip():
                    continue
                    
                # Check if already exists in pregenerated files
                pregenerated_audio = PreGeneratedAudio.load_pregenerated_audio(text, tts_provider_name, tts_provider.voice)
                if pregenerated_audio:
                    results["loaded_count"] += 1
                    PreGeneratedAudio.logger.debug(f"Text already pregenerated: {text[:50]}...")
                else:
                    # Synthesize using existing TTS provider
                    PreGeneratedAudio.logger.info(f"Synthesizing and saving: {text[:50]}...")
                    try:
                        audio_bytes = await tts_provider.synthesize_speech_to_bytes_async(text)
                        if audio_bytes:
                            # Save to pregenerated file
                            PreGeneratedAudio.save_pregenerated_audio(text, tts_provider_name, tts_provider.voice, audio_bytes)
                            results["synthesized_count"] += 1
                            PreGeneratedAudio.logger.debug(f"Successfully pregenerated audio for: {text[:50]}...")
                        else:
                            results["failed_count"] += 1
                            PreGeneratedAudio.logger.warning(f"Failed to synthesize audio for: {text[:50]}...")
                    except Exception as e:
                        results["failed_count"] += 1
                        PreGeneratedAudio.logger.error(f"Error synthesizing audio for '{text[:50]}...': {e}")

                OutgoingAudioManager.add_synthesized_audio_to_cache(text, pregenerated_audio or audio_bytes, permanent=True)

            PreGeneratedAudio.logger.info(f"Pregenerated audio population completed. Already existed: {results['loaded_count']}, Newly synthesized: {results['synthesized_count']}, Failed: {results['failed_count']}")
            
        except Exception as e:
            PreGeneratedAudio.logger.error(f"Error during pregenerated audio population: {e}", exc_info=True)
            
        return results
    
    @staticmethod
    def load_pregenerated_audio(text: str, provider_name: str, voice: str) -> Optional[bytes]:
        """
        Load pregenerated audio file if it exists.
        
        Args:
            text: The text to load audio for
            provider_name: TTS provider name (e.g., "openai", "google")
            voice: Voice name used for synthesis
            
        Returns:
            Audio bytes if file exists, None otherwise
        """
        file_path = PreGeneratedAudio._get_pregenerated_file_path(text, provider_name, voice)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'rb') as f:
                    audio_bytes = f.read()
                PreGeneratedAudio.logger.debug(f"Loaded pregenerated audio: {file_path}")
                return audio_bytes
            except Exception as e:
                PreGeneratedAudio.logger.warning(f"Failed to load pregenerated audio: {e}")
        return None
    
    @staticmethod
    def save_pregenerated_audio(text: str, provider_name: str, voice: str, audio_bytes: bytes) -> None:
        """
        Save audio bytes to pregenerated file.
        
        Args:
            text: The text the audio was generated for
            provider_name: TTS provider name (e.g., "openai", "google")
            voice: Voice name used for synthesis
            audio_bytes: The audio data to save
        """
        if not audio_bytes:
            return
        
        try:
            PreGeneratedAudio._ensure_pregenerated_dir_exists(text, provider_name, voice)
            file_path = PreGeneratedAudio._get_pregenerated_file_path(text, provider_name, voice)
            
            with open(file_path, 'wb') as f:
                f.write(audio_bytes)
            PreGeneratedAudio.logger.debug(f"Saved pregenerated audio: {file_path}")
        except Exception as e:
            PreGeneratedAudio.logger.warning(f"Failed to save pregenerated audio: {e}")

    @staticmethod
    def get_pregenerated_audio_stats() -> dict:
        """
        Get statistics about pregenerated audio files.
        
        Returns:
            Dictionary with stats: total_files, providers, voices, total_size_bytes
        """
        if not os.path.exists(PreGeneratedAudio.pregenerated_dir):
            return {"total_files": 0, "providers": [], "voices": [], "total_size_bytes": 0}
        
        total_files = 0
        total_size = 0
        providers = set()
        voices = set()
        
        try:
            for root, dirs, files in os.walk(PreGeneratedAudio.pregenerated_dir):
                for file in files:
                    if file.endswith('.pcm'):
                        total_files += 1
                        file_path = os.path.join(root, file)
                        total_size += os.path.getsize(file_path)
                        
                        # Extract provider and voice from path
                        rel_path = os.path.relpath(root, PreGeneratedAudio.pregenerated_dir)
                        path_parts = rel_path.split(os.sep)
                        if len(path_parts) >= 2:
                            providers.add(path_parts[0])
                            voices.add(path_parts[1])
        
        except Exception as e:
            PreGeneratedAudio.logger.warning(f"Error getting pregenerated audio stats: {e}")
        
        return {
            "total_files": total_files,
            "providers": sorted(list(providers)),
            "voices": sorted(list(voices)),
            "total_size_bytes": total_size
        }
    
    # Internal helper methods
    @staticmethod
    def _get_text_hash(text: str) -> str:
        """Generate a short unique hash for the given text"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]
    
    @staticmethod
    def _get_pregenerated_file_path(text: str, provider_name: str, voice: str) -> str:
        """Get the pregenerated file path for a given text"""
        text_hash = PreGeneratedAudio._get_text_hash(text)
        file_path = Path(PreGeneratedAudio.pregenerated_dir) / provider_name / voice / f"{text_hash}.pcm"
        return str(file_path)
    
    @staticmethod
    def _ensure_pregenerated_dir_exists(text: str, provider_name: str, voice: str) -> None:
        """Create pregenerated directory if it doesn't exist"""
        file_path = PreGeneratedAudio._get_pregenerated_file_path(text, provider_name, voice)
        dir_path = Path(file_path).parent
        dir_path.mkdir(parents=True, exist_ok=True)