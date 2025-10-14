import hashlib
import json
import logging
import os
from pathlib import Path

from managers.outgoing_audio_manager import OutgoingAudioManager
from speech.text_to_speech import TextToSpeechProvider, get_text_to_speech_provider
from utils.envvar import EnvHelper


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
        from agents.text_registry import TextRegistry

        # Get all texts dynamically from the centralized registry
        texts_to_pregenerate = TextRegistry.get_all_texts()

        # Filter out empty texts
        texts_to_pregenerate = [text for text in texts_to_pregenerate if text and text.strip()]

        if not texts_to_pregenerate:
            PreGeneratedAudio.logger.warning("No texts to pregenerate from AgentsGraph")
            return

        results = {
            "loaded_count": 0,
            "synthesized_count": 0,
            "failed_count": 0,
            "obsolete_removed": 0,
        }

        try:
            # Create TTS provider instance
            tts_provider_name = EnvHelper.get_text_to_speech_provider() or "openai"
            PreGeneratedAudio.logger.info(f"Starting pregenerated audio population with {len(texts_to_pregenerate)} texts using {tts_provider_name} provider")

            tts_provider: TextToSpeechProvider = get_text_to_speech_provider(
                tts_provider_name=tts_provider_name,
                frame_rate=8000,
                channels=1,
                sample_width=2,
                temp_dir="static/outgoing_audio",
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
            for obsolete_text in obsolete_texts:
                obsolete_hash = audio_index[obsolete_text]
                obsolete_file_path = PreGeneratedAudio._get_pregenerated_file_path_from_hash(obsolete_hash, tts_provider_name, tts_provider.voice)

                if os.path.exists(obsolete_file_path):
                    try:
                        os.remove(obsolete_file_path)
                    except Exception as e:
                        PreGeneratedAudio.logger.warning(f"Failed to remove obsolete audio file {obsolete_file_path}: {e}")

                del audio_index[obsolete_text]
                results["obsolete_removed"] += 1

            if obsolete_texts:
                PreGeneratedAudio.save_index(tts_provider_name, tts_provider.voice, audio_index)

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
                            with open(file_path, "rb") as f:
                                pregenerated_audio = f.read()
                            results["loaded_count"] += 1
                        except Exception as e:
                            PreGeneratedAudio.logger.warning(f"Failed to load pregenerated audio for '{text[:50]}...': {e}")
                    else:
                        PreGeneratedAudio.logger.error(f"Index references missing file for '{text[:50]}...': {file_path}")

                # If not found in index or file missing, synthesize new audio
                if not pregenerated_audio:
                    PreGeneratedAudio.logger.info(f"Synthesizing and saving: {text[:50]}...")
                    try:
                        audio_bytes, _ = await tts_provider.synthesize_speech_to_bytes_async(text)
                        if audio_bytes:
                            # Save to pregenerated file and update index
                            PreGeneratedAudio.save_pregenerated_audio(text, tts_provider_name, tts_provider.voice, audio_bytes)
                            results["synthesized_count"] += 1
                        else:
                            results["failed_count"] += 1
                            PreGeneratedAudio.logger.warning(f"Failed to synthesize audio for: {text[:50]}...")
                    except Exception as e:
                        results["failed_count"] += 1
                        PreGeneratedAudio.logger.error(f"Error synthesizing audio for '{text[:50]}...': {e}")

                # Add to OutgoingAudioManager cache
                OutgoingAudioManager.add_synthesized_audio_to_cache(text, pregenerated_audio or audio_bytes, permanent=True)

            PreGeneratedAudio.logger.info(
                f"Pregenerated audio population completed. Already existed: {results['loaded_count']}, Newly synthesized: {results['synthesized_count']}, Failed: {results['failed_count']}, Obsolete removed: {results['obsolete_removed']}"
            )

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

            # Save the audio file
            file_path = PreGeneratedAudio._get_pregenerated_file_path_from_hash(text_hash, provider_name, voice)
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(audio_bytes)

            # Update the index (text -> hash mapping)
            index = PreGeneratedAudio.load_index(provider_name, voice)
            index[text] = text_hash
            PreGeneratedAudio.save_index(provider_name, voice, index)

        except Exception as e:
            PreGeneratedAudio.logger.warning(f"Failed to save pregenerated audio: {e}")

    @staticmethod
    def get_pregenerated_audio_stats() -> dict:
        """Get basic statistics about pregenerated audio files."""
        if not os.path.exists(PreGeneratedAudio.pregenerated_dir):
            return {
                "total_files": 0,
                "total_size_bytes": 0,
                "indexed_texts": 0,
                "orphaned_files": 0,
            }

        total_files = 0
        total_size = 0
        indexed_texts = 0
        orphaned_files = 0

        try:
            for root, dirs, files in os.walk(PreGeneratedAudio.pregenerated_dir):
                pcm_files = [f for f in files if f.endswith(".pcm")]
                if not pcm_files:
                    continue

                rel_path = os.path.relpath(root, PreGeneratedAudio.pregenerated_dir)
                path_parts = rel_path.split(os.sep)

                if len(path_parts) >= 2:
                    provider, voice = path_parts[0], path_parts[1]
                    index = PreGeneratedAudio.load_index(provider, voice)
                    indexed_hashes = set(index.values())

                    for file in pcm_files:
                        file_path = os.path.join(root, file)
                        total_files += 1
                        total_size += os.path.getsize(file_path)

                        file_hash = file[:-4]  # Remove .pcm extension
                        if file_hash in indexed_hashes:
                            indexed_texts += 1
                        else:
                            orphaned_files += 1

        except Exception as e:
            PreGeneratedAudio.logger.warning(f"Error getting pregenerated audio stats: {e}")

        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "indexed_texts": indexed_texts,
            "orphaned_files": orphaned_files,
        }

    # Public introspection methods
    @staticmethod
    def _get_index_for_lookup(provider_name: str, voice: str) -> dict:
        """Shared helper for index-based lookups"""
        return PreGeneratedAudio.load_index(provider_name, voice)

    @staticmethod
    def get_text_from_hash(hash_key: str, provider_name: str, voice: str) -> str | None:
        """Get the original text from a hash using the index."""
        index = PreGeneratedAudio._get_index_for_lookup(provider_name, voice)
        for text, stored_hash in index.items():
            if stored_hash == hash_key:
                return text
        return None

    @staticmethod
    def get_hash_from_text(text: str, provider_name: str, voice: str) -> str | None:
        """Get the hash for a text using the index."""
        index = PreGeneratedAudio._get_index_for_lookup(provider_name, voice)
        return index.get(text)

    @staticmethod
    def list_pregenerated_texts(provider_name: str, voice: str) -> list[str]:
        """List all pregenerated texts for a provider/voice combination."""
        index = PreGeneratedAudio._get_index_for_lookup(provider_name, voice)
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
            return {
                "rebuilt_entries": 0,
                "orphaned_files_removed": 0,
                "missing_entries_removed": 0,
                "errors": 1,
                "message": "Directory not found",
            }

        orphaned_files_removed = 0
        missing_entries_removed = 0
        errors = 0

        try:
            # Load current index
            current_index = PreGeneratedAudio.load_index(provider_name, voice)

            # Get actual PCM files
            actual_files = set()
            for file in os.listdir(voice_dir):
                if file.endswith(".pcm"):
                    actual_files.add(file[:-4])  # Remove .pcm extension

            # Get hashes from index
            indexed_hashes = set(current_index.values())

            # Find orphaned files (exist but not in index) and remove them
            orphaned_files = actual_files - indexed_hashes
            for orphan in orphaned_files:
                try:
                    file_path = os.path.join(voice_dir, f"{orphan}.pcm")
                    os.remove(file_path)
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
                    missing_entries_removed += 1

            # Save the cleaned index
            PreGeneratedAudio.save_index(provider_name, voice, cleaned_index)

        except Exception as e:
            PreGeneratedAudio.logger.error(f"Error rebuilding index: {e}")
            errors += 1
            cleaned_index = current_index  # Fall back to original index

        return {
            "rebuilt_entries": len(cleaned_index),
            "orphaned_files_removed": orphaned_files_removed,
            "missing_entries_removed": missing_entries_removed,
            "errors": errors,
            "message": f"Rebuilt index: {len(cleaned_index)} entries, removed {orphaned_files_removed} orphaned files, removed {missing_entries_removed} missing entries",
        }

    @staticmethod
    def _try(operation_func, operation: str, file_path: str):
        """Common error handling for file operations"""
        try:
            return operation_func()
        except Exception as e:
            PreGeneratedAudio.logger.warning(f"Failed to {operation} {file_path}: {e}")
            return None if operation == "load" else None

    @staticmethod
    def load_index(provider_name: str, voice: str) -> dict:
        """Load the text-to-hash index for a given provider and voice"""
        index_file_path = PreGeneratedAudio._get_index_file_path(provider_name, voice)
        if os.path.exists(index_file_path):

            def load_op():
                with open(index_file_path, encoding="utf-8") as f:
                    return json.load(f)

            result = PreGeneratedAudio._try(load_op, "load index file", index_file_path)
            return result if result is not None else {}
        return {}

    @staticmethod
    def save_index(provider_name: str, voice: str, index_data: dict) -> None:
        """Save the text-to-hash index for a given provider and voice"""
        index_file_path = PreGeneratedAudio._get_index_file_path(provider_name, voice)

        def save_op():
            index_dir = Path(index_file_path).parent
            index_dir.mkdir(parents=True, exist_ok=True)
            with open(index_file_path, "w", encoding="utf-8") as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)

        PreGeneratedAudio._try(save_op, "save index file", index_file_path)

    # Internal helper methods
    @staticmethod
    def _get_text_hash(text: str) -> str:
        """Generate a short unique hash for the given text"""
        return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]

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
