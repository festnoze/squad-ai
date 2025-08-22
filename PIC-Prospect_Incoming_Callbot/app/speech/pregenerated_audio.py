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
            AgentsGraph.unavailability_for_returning_prospect,
            AgentsGraph.unavailability_for_new_prospect,
            AgentsGraph.other_text,
            AgentsGraph.thanks_to_come_back,
            AgentsGraph.appointment_text,
            AgentsGraph.questions_text,
            AgentsGraph.what_do_you_want_text,
            AgentsGraph.want_to_schedule_appointement,
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
               
        results = {"loaded_count": 0, "synthesized_count": 0, "failed_count": 0, "obsolete_removed": 0}
        
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
            
            # Clean up index before populating cache - remove orphaned files and missing references
            PreGeneratedAudio.logger.info(f"Cleaning up index for {tts_provider_name}/{tts_provider.voice}")
            rebuild_result = PreGeneratedAudio.clean_audio_files_index(tts_provider_name, tts_provider.voice)
            PreGeneratedAudio.logger.info(f"Index cleanup completed: {rebuild_result['message']}")
            
            # Load the pregenerated audio index (text -> hash mapping)
            audio_index = PreGeneratedAudio.load_index(tts_provider_name, tts_provider.voice)
            PreGeneratedAudio.logger.info(f"Loaded index with {len(audio_index)} existing pregenerated audio files")
            
            # Remove obsolete entries from index that are no longer in texts_to_pregenerate
            obsolete_texts = set(audio_index.keys()) - set(texts_to_pregenerate)
            if obsolete_texts:
                PreGeneratedAudio.logger.info(f"Found {len(obsolete_texts)} obsolete entries to remove")
                for obsolete_text in obsolete_texts:
                    obsolete_hash = audio_index[obsolete_text]
                    obsolete_file_path = PreGeneratedAudio._get_pregenerated_file_path_from_hash(obsolete_hash, tts_provider_name, tts_provider.voice)
                    
                    # Remove the file if it exists
                    if os.path.exists(obsolete_file_path):
                        try:
                            os.remove(obsolete_file_path)
                            PreGeneratedAudio.logger.info(f"Removed obsolete audio file: {obsolete_file_path}")
                        except Exception as e:
                            PreGeneratedAudio.logger.warning(f"Failed to remove obsolete audio file {obsolete_file_path}: {e}")
                    
                    # Remove from index
                    del audio_index[obsolete_text]
                    results["obsolete_removed"] += 1
                    PreGeneratedAudio.logger.info(f"Removed obsolete index entry: '{obsolete_text[:50]}...'")
                
                # Save the updated index
                PreGeneratedAudio.save_index(tts_provider_name, tts_provider.voice, audio_index)
                PreGeneratedAudio.logger.info(f"Updated index saved with {len(audio_index)} remaining entries")
            
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
                        PreGeneratedAudio.logger.error(f"Index references missing file for '{text[:50]}...': {file_path}")
                
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

            PreGeneratedAudio.logger.info(f"Pregenerated audio population completed. Already existed: {results['loaded_count']}, Newly synthesized: {results['synthesized_count']}, Failed: {results['failed_count']}, Obsolete removed: {results['obsolete_removed']}")
            
        except Exception as e:
            PreGeneratedAudio.logger.error(f"Error during pregenerated audio population: {e}", exc_info=True)
            
        return results
    
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
            index = PreGeneratedAudio.load_index(provider_name, voice)
            index[text] = text_hash
            PreGeneratedAudio.save_index(provider_name, voice, index)
            
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
                    index = PreGeneratedAudio.load_index(provider, voice)
                    
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
        index = PreGeneratedAudio.load_index(provider_name, voice)
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
        index = PreGeneratedAudio.load_index(provider_name, voice)
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
        index = PreGeneratedAudio.load_index(provider_name, voice)
        return list(index.keys())
    
    @staticmethod
    def clean_audio_files_index(provider_name: str, voice: str) -> dict:
        """
        Rebuild the index by cleaning up orphaned files and removing references to deleted files.
        This method will:
        1. Load current index
        2. Find orphaned files (exist but not in index) and remove them
        3. Find missing files (in index but don't exist) and remove their index entries
        4. Keep existing text mappings for files that still exist
        
        Args:
            provider_name: TTS provider name
            voice: Voice name
            
        Returns:
            Dictionary with rebuild results
        """
        voice_dir = os.path.join(PreGeneratedAudio.pregenerated_dir, provider_name, voice)
        if not os.path.exists(voice_dir):
            return {"rebuilt_entries": 0, "orphaned_files_removed": 0, "missing_entries_removed": 0, "errors": 1, "message": "Directory not found"}
        
        orphaned_files_removed = 0
        missing_entries_removed = 0
        errors = 0
        
        try:
            # Load current index
            current_index = PreGeneratedAudio.load_index(provider_name, voice)
            PreGeneratedAudio.logger.info(f"Loaded current index with {len(current_index)} entries")
            
            # Get actual PCM files
            actual_files = set()
            for file in os.listdir(voice_dir):
                if file.endswith('.pcm'):
                    actual_files.add(file[:-4])  # Remove .pcm extension
            
            # Get hashes from index
            indexed_hashes = set(current_index.values())
            
            # Find orphaned files (exist but not in index) and remove them
            orphaned_files = actual_files - indexed_hashes
            for orphan in orphaned_files:
                try:
                    file_path = os.path.join(voice_dir, f"{orphan}.pcm")
                    os.remove(file_path)
                    PreGeneratedAudio.logger.info(f"Removed orphaned file: {orphan}.pcm")
                    orphaned_files_removed += 1
                except Exception as e:
                    PreGeneratedAudio.logger.error(f"Error removing orphaned file {orphan}.pcm: {e}")
                    errors += 1
            
            # Find missing files (in index but don't exist) and remove their entries
            missing_files = indexed_hashes - actual_files
            cleaned_index = {}
            for text, hash_val in current_index.items():
                if hash_val not in missing_files:
                    cleaned_index[text] = hash_val
                else:
                    PreGeneratedAudio.logger.info(f"Removed index entry for missing file: {hash_val} - '{text[:50]}...'")
                    missing_entries_removed += 1
            
            # Save the cleaned index
            PreGeneratedAudio.save_index(provider_name, voice, cleaned_index)
            
            PreGeneratedAudio.logger.info(f"Index rebuild completed: {len(cleaned_index)} entries remaining")
            
        except Exception as e:
            PreGeneratedAudio.logger.error(f"Error rebuilding index: {e}")
            errors += 1
            cleaned_index = current_index  # Fall back to original index
        
        return {
            "rebuilt_entries": len(cleaned_index),
            "orphaned_files_removed": orphaned_files_removed,
            "missing_entries_removed": missing_entries_removed,
            "errors": errors,
            "message": f"Rebuilt index: {len(cleaned_index)} entries, removed {orphaned_files_removed} orphaned files, removed {missing_entries_removed} missing entries"
        }
    
    @staticmethod
    def load_index(provider_name: str, voice: str) -> dict:
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
    def save_index(provider_name: str, voice: str, index_data: dict) -> None:
        """Save the text-to-hash index for a given provider and voice"""
        try:
            index_file_path = PreGeneratedAudio._get_index_file_path(provider_name, voice)
            index_dir = Path(index_file_path).parent
            index_dir.mkdir(parents=True, exist_ok=True)
            
            with open(index_file_path, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            PreGeneratedAudio.logger.warning(f"Failed to save index file: {e}")
    
    
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