import logging
import hashlib
import os
import json
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
        from agents.calendar_agent import CalendarAgent
        
        texts_to_pregenerate = [
            # AgentsGraph static texts
            AgentsGraph.start_welcome_text,
            AgentsGraph.other_text,
            AgentsGraph.thank_you_text,
            AgentsGraph.appointment_text,
            AgentsGraph.questions_text,
            AgentsGraph.what_do_you_want_text,
            AgentsGraph.technical_error_text,
            AgentsGraph.lead_agent_error_text,
            AgentsGraph.rag_communication_error_text,
            
            # CalendarAgent static texts
            CalendarAgent.availability_request_text,
            CalendarAgent.no_timeframes_text,
            CalendarAgent.slot_unavailable_text,
            CalendarAgent.confirmation_prefix_text,
            CalendarAgent.confirmation_suffix_text,
            CalendarAgent.date_not_found_text,
            CalendarAgent.appointment_confirmed_prefix_text,
            CalendarAgent.appointment_confirmed_suffix_text,
            CalendarAgent.appointment_failed_text,
            CalendarAgent.modification_not_supported_text,
            CalendarAgent.cancellation_not_supported_text
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
            
            # Load the pregenerated audio index (text -> hash mapping)
            audio_index = PreGeneratedAudio.load_pregenerated_audio_index(tts_provider_name, tts_provider.voice)
            PreGeneratedAudio.logger.info(f"Loaded index with {len(audio_index)} existing pregenerated audio files")
            
            # Process each text
            for text in texts_to_pregenerate:
                if not text or not text.strip():
                    continue
                
                pregenerated_audio = None
                
                # Check if text exists in index (no hash recalculation needed)
                if text in audio_index:
                    # Load the existing audio file using the hash from index
                    text_hash = audio_index[text]
                    file_path = PreGeneratedAudio._get_pregenerated_file_path_from_hash(text_hash, tts_provider_name, tts_provider.voice)
                    
                    if os.path.exists(file_path):
                        try:
                            with open(file_path, 'rb') as f:
                                pregenerated_audio = f.read()
                            results["loaded_count"] += 1
                            PreGeneratedAudio.logger.debug(f"Loaded pregenerated audio from index: {text[:50]}...")
                        except Exception as e:
                            PreGeneratedAudio.logger.warning(f"Failed to load pregenerated audio for '{text[:50]}...': {e}")
                    else:
                        PreGeneratedAudio.logger.warning(f"Index references missing file for '{text[:50]}...': {file_path}")
                
                # If not found in index or file missing, synthesize new audio
                if not pregenerated_audio:
                    PreGeneratedAudio.logger.info(f"Synthesizing and saving: {text[:50]}...")
                    try:
                        audio_bytes = await tts_provider.synthesize_speech_to_bytes_async(text)
                        if audio_bytes:
                            # Save to pregenerated file and update index
                            PreGeneratedAudio.save_pregenerated_audio(text, tts_provider_name, tts_provider.voice, audio_bytes)
                            results["synthesized_count"] += 1
                            PreGeneratedAudio.logger.debug(f"Successfully pregenerated audio for: {text[:50]}...")
                        else:
                            results["failed_count"] += 1
                            PreGeneratedAudio.logger.warning(f"Failed to synthesize audio for: {text[:50]}...")
                    except Exception as e:
                        results["failed_count"] += 1
                        PreGeneratedAudio.logger.error(f"Error synthesizing audio for '{text[:50]}...': {e}")

                # Add to OutgoingAudioManager cache
                OutgoingAudioManager.add_synthesized_audio_to_cache(text, pregenerated_audio or audio_bytes, permanent=True)

            PreGeneratedAudio.logger.info(f"Pregenerated audio population completed. Already existed: {results['loaded_count']}, Newly synthesized: {results['synthesized_count']}, Failed: {results['failed_count']}")
            
        except Exception as e:
            PreGeneratedAudio.logger.error(f"Error during pregenerated audio population: {e}", exc_info=True)
            
        return results
    
    @staticmethod
    def load_pregenerated_audio_index(provider_name: str, voice: str) -> dict[str, str]:
        """
        Load the pregenerated audio index for a provider/voice combination.
        
        Args:
            provider_name: TTS provider name (e.g., "openai", "google")
            voice: Voice name used for synthesis
            
        Returns:
            Dictionary mapping text -> hash for all pregenerated audio files
        """
        return PreGeneratedAudio._load_index(provider_name, voice)
    
    @staticmethod
    def save_pregenerated_audio(text: str, provider_name: str, voice: str, audio_bytes: bytes) -> None:
        """
        Save audio bytes to pregenerated file and update the index.
        
        Args:
            text: The text the audio was generated for
            provider_name: TTS provider name (e.g., "openai", "google")
            voice: Voice name used for synthesis
            audio_bytes: The audio data to save
        """
        if not audio_bytes:
            return
        
        try:
            # Generate hash for the text
            text_hash = PreGeneratedAudio._get_text_hash(text)
            
            # Ensure directory exists
            PreGeneratedAudio._ensure_pregenerated_dir_exists(text, provider_name, voice)
            
            # Save the audio file
            file_path = PreGeneratedAudio._get_pregenerated_file_path_from_hash(text_hash, provider_name, voice)
            with open(file_path, 'wb') as f:
                f.write(audio_bytes)
            
            # Update the index (text -> hash mapping)
            index = PreGeneratedAudio._load_index(provider_name, voice)
            index[text] = text_hash
            PreGeneratedAudio._save_index(provider_name, voice, index)
            
            PreGeneratedAudio.logger.debug(f"Saved pregenerated audio and updated index: {file_path}")
            
        except Exception as e:
            PreGeneratedAudio.logger.warning(f"Failed to save pregenerated audio: {e}")

    @staticmethod
    def get_pregenerated_audio_stats() -> dict:
        """
        Get comprehensive statistics about pregenerated audio files.
        
        Returns:
            Dictionary with detailed stats including text information
        """
        if not os.path.exists(PreGeneratedAudio.pregenerated_dir):
            return {
                "total_files": 0, 
                "providers": [], 
                "voices": [], 
                "total_size_bytes": 0,
                "indexed_texts": 0,
                "orphaned_files": 0,
                "provider_stats": {}
            }
        
        total_files = 0
        total_size = 0
        indexed_texts = 0
        orphaned_files = 0
        providers = set()
        voices = set()
        provider_stats = {}
        
        try:
            for root, dirs, files in os.walk(PreGeneratedAudio.pregenerated_dir):
                pcm_files = [f for f in files if f.endswith('.pcm')]
                if not pcm_files:
                    continue
                    
                # Extract provider and voice from path
                rel_path = os.path.relpath(root, PreGeneratedAudio.pregenerated_dir)
                path_parts = rel_path.split(os.sep)
                
                if len(path_parts) >= 2:
                    provider = path_parts[0]
                    voice = path_parts[1]
                    providers.add(provider)
                    voices.add(voice)
                    
                    # Load index for this provider/voice
                    index = PreGeneratedAudio._load_index(provider, voice)
                    
                    # Count files and sizes
                    provider_files = 0
                    provider_size = 0
                    provider_indexed = 0
                    provider_orphaned = 0
                    
                    for file in pcm_files:
                        file_path = os.path.join(root, file)
                        file_size = os.path.getsize(file_path)
                        
                        total_files += 1
                        total_size += file_size
                        provider_files += 1
                        provider_size += file_size
                        
                        # Check if file is in index (hash should exist as a value in text -> hash mapping)
                        file_hash = file[:-4]  # Remove .pcm extension
                        hash_found = any(stored_hash == file_hash for stored_hash in index.values())
                        if hash_found:
                            indexed_texts += 1
                            provider_indexed += 1
                        else:
                            orphaned_files += 1
                            provider_orphaned += 1
                    
                    # Store provider-specific stats
                    if provider not in provider_stats:
                        provider_stats[provider] = {}
                    
                    provider_stats[provider][voice] = {
                        "files": provider_files,
                        "size_bytes": provider_size,
                        "indexed_texts": provider_indexed,
                        "orphaned_files": provider_orphaned,
                        "texts": list(index.keys())[:5] if index else []  # First 5 texts as sample
                    }
        
        except Exception as e:
            PreGeneratedAudio.logger.warning(f"Error getting pregenerated audio stats: {e}")
        
        return {
            "total_files": total_files,
            "providers": sorted(list(providers)),
            "voices": sorted(list(voices)),
            "total_size_bytes": total_size,
            "indexed_texts": indexed_texts,
            "orphaned_files": orphaned_files,
            "provider_stats": provider_stats
        }
    
    # Public introspection methods
    @staticmethod
    def get_text_from_hash(hash_key: str, provider_name: str, voice: str) -> Optional[str]:
        """
        Get the original text from a hash using the index.
        
        Args:
            hash_key: The hash to look up
            provider_name: TTS provider name
            voice: Voice name
            
        Returns:
            Original text if found, None otherwise
        """
        index = PreGeneratedAudio._load_index(provider_name, voice)
        # Search through text -> hash mappings to find the text
        for text, stored_hash in index.items():
            if stored_hash == hash_key:
                return text
        return None
    
    @staticmethod
    def get_hash_from_text(text: str, provider_name: str, voice: str) -> Optional[str]:
        """
        Get the hash for a text using the index.
        
        Args:
            text: The text to look up
            provider_name: TTS provider name
            voice: Voice name
            
        Returns:
            Hash if found, None otherwise
        """
        index = PreGeneratedAudio._load_index(provider_name, voice)
        return index.get(text)
    
    @staticmethod
    def list_pregenerated_texts(provider_name: str, voice: str) -> list[str]:
        """
        List all pregenerated texts for a provider/voice combination.
        
        Args:
            provider_name: TTS provider name
            voice: Voice name
            
        Returns:
            List of all pregenerated texts
        """
        index = PreGeneratedAudio._load_index(provider_name, voice)
        return list(index.keys())
    
    @staticmethod
    def cleanup_orphaned_files(provider_name: str = None, voice: str = None) -> dict:
        """
        Remove .pcm files that have no corresponding entry in the index.
        
        Args:
            provider_name: Specific provider to clean (optional)
            voice: Specific voice to clean (optional)
            
        Returns:
            Dictionary with cleanup results
        """
        if not os.path.exists(PreGeneratedAudio.pregenerated_dir):
            return {"cleaned_files": 0, "errors": 0}
        
        cleaned_files = 0
        errors = 0
        
        try:
            # If specific provider/voice specified, clean only that
            if provider_name and voice:
                providers_voices = [(provider_name, voice)]
            else:
                # Find all provider/voice combinations
                providers_voices = []
                for provider_dir in os.listdir(PreGeneratedAudio.pregenerated_dir):
                    provider_path = os.path.join(PreGeneratedAudio.pregenerated_dir, provider_dir)
                    if os.path.isdir(provider_path):
                        for voice_dir in os.listdir(provider_path):
                            voice_path = os.path.join(provider_path, voice_dir)
                            if os.path.isdir(voice_path):
                                providers_voices.append((provider_dir, voice_dir))
            
            # Clean each provider/voice combination
            for prov, v in providers_voices:
                try:
                    index = PreGeneratedAudio._load_index(prov, v)
                    voice_dir = os.path.join(PreGeneratedAudio.pregenerated_dir, prov, v)
                    
                    if os.path.exists(voice_dir):
                        for file in os.listdir(voice_dir):
                            if file.endswith('.pcm'):
                                file_hash = file[:-4]  # Remove .pcm extension
                                # Check if this hash exists as a value in the index (text -> hash mapping)
                                hash_found = any(stored_hash == file_hash for stored_hash in index.values())
                                if not hash_found:
                                    # Orphaned file, remove it
                                    file_path = os.path.join(voice_dir, file)
                                    os.remove(file_path)
                                    cleaned_files += 1
                                    PreGeneratedAudio.logger.info(f"Removed orphaned file: {file_path}")
                                    
                except Exception as e:
                    PreGeneratedAudio.logger.error(f"Error cleaning {prov}/{v}: {e}")
                    errors += 1
                    
        except Exception as e:
            PreGeneratedAudio.logger.error(f"Error during cleanup: {e}")
            errors += 1
        
        return {"cleaned_files": cleaned_files, "errors": errors}
    
    @staticmethod
    def rebuild_index(provider_name: str, voice: str) -> dict:
        """
        Rebuild the index from existing .pcm files (emergency recovery).
        WARNING: This will lose the original text and use generated hashes.
        
        Args:
            provider_name: TTS provider name
            voice: Voice name
            
        Returns:
            Dictionary with rebuild results
        """
        voice_dir = os.path.join(PreGeneratedAudio.pregenerated_dir, provider_name, voice)
        if not os.path.exists(voice_dir):
            return {"rebuilt_entries": 0, "errors": 1, "message": "Directory not found"}
        
        rebuilt_entries = 0
        errors = 0
        new_index = {}
        
        try:
            for file in os.listdir(voice_dir):
                if file.endswith('.pcm'):
                    try:
                        file_hash = file[:-4]  # Remove .pcm extension
                        # We can't recover the original text, so use a placeholder (text -> hash mapping)
                        placeholder_text = f"[RECOVERED_{file_hash}]"
                        new_index[placeholder_text] = file_hash
                        rebuilt_entries += 1
                    except Exception as e:
                        PreGeneratedAudio.logger.error(f"Error processing file {file}: {e}")
                        errors += 1
            
            # Save the rebuilt index
            PreGeneratedAudio._save_index(provider_name, voice, new_index)
            
        except Exception as e:
            PreGeneratedAudio.logger.error(f"Error rebuilding index: {e}")
            errors += 1
        
        return {
            "rebuilt_entries": rebuilt_entries, 
            "errors": errors,
            "message": f"Rebuilt index with {rebuilt_entries} entries"
        }
    
    # Internal helper methods
    @staticmethod
    def _get_text_hash(text: str) -> str:
        """Generate a short unique hash for the given text"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]
    
    @staticmethod
    def _get_index_file_path(provider_name: str, voice: str) -> str:
        """Get the index file path for a given provider and voice"""
        index_path = Path(PreGeneratedAudio.pregenerated_dir) / provider_name / voice / "index.json"
        return str(index_path)
    
    @staticmethod
    def _load_index(provider_name: str, voice: str) -> dict:
        """Load the text-to-hash index for a given provider and voice"""
        index_file_path = PreGeneratedAudio._get_index_file_path(provider_name, voice)
        if os.path.exists(index_file_path):
            try:
                with open(index_file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                PreGeneratedAudio.logger.warning(f"Failed to load index file {index_file_path}: {e}")
        return {}
    
    @staticmethod
    def _save_index(provider_name: str, voice: str, index_data: dict) -> None:
        """Save the text-to-hash index for a given provider and voice"""
        try:
            index_file_path = PreGeneratedAudio._get_index_file_path(provider_name, voice)
            index_dir = Path(index_file_path).parent
            index_dir.mkdir(parents=True, exist_ok=True)
            
            with open(index_file_path, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            PreGeneratedAudio.logger.warning(f"Failed to save index file: {e}")
    
    
    @staticmethod
    def _get_pregenerated_file_path_from_hash(hash_key: str, provider_name: str, voice: str) -> str:
        """Get the pregenerated file path from a hash"""
        file_path = Path(PreGeneratedAudio.pregenerated_dir) / provider_name / voice / f"{hash_key}.pcm"
        return str(file_path)
    
    @staticmethod
    def _ensure_pregenerated_dir_exists(text: str, provider_name: str, voice: str) -> None:
        """Create pregenerated directory if it doesn't exist"""
        text_hash = PreGeneratedAudio._get_text_hash(text)
        file_path = PreGeneratedAudio._get_pregenerated_file_path_from_hash(text_hash, provider_name, voice)
        dir_path = Path(file_path).parent
        dir_path.mkdir(parents=True, exist_ok=True)