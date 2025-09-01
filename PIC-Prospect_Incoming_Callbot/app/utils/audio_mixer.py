import logging
import os
import struct


class AudioMixer:
    """
    Utility class for mixing synthesized speech audio with background noise.
    Handles PCM audio data mixing and volume control.
    """

    def __init__(self, sample_width: int = 2, frame_rate: int = 8000, channels: int = 1):
        """
        Initialize AudioMixer with audio format parameters.

        Args:
            sample_width: Bytes per sample (1 for 8-bit, 2 for 16-bit)
            frame_rate: Sample rate in Hz (e.g., 8000, 16000)
            channels: Number of audio channels (1 for mono, 2 for stereo)
        """
        self.logger = logging.getLogger(__name__)
        self.sample_width = sample_width
        self.frame_rate = frame_rate
        self.channels = channels
        self._background_noise_cache: bytes | None = None

        if not self.load_background_noise("static/internal/ambiance-bureau.pcm"):
            self.logger.error("/!\\ Failed to load background noise ! ")

    def load_background_noise(self, file_path: str) -> bool:
        """
        Load background noise from a PCM file and cache it.
        """
        try:
            if not os.path.exists(file_path):
                self.logger.warning(f"Background noise file not found: {file_path}")
                return False

            with open(file_path, "rb") as f:
                self._background_noise_cache = f.read()

            if not self._background_noise_cache:
                self.logger.warning(f"Background noise file is empty: {file_path}")
                return False

            self.logger.info(f"Loaded background noise: {len(self._background_noise_cache)} bytes from {file_path}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to load background noise from {file_path}: {e}")
            return False

    def loop_audio_to_length(self, audio_data: bytes, target_length: int) -> bytes:
        """
        Loop audio data to match a target length by repeating it.

        Args:
            audio_data: Source audio data to loop
            target_length: Target length in bytes

        Returns:
            Audio data looped to the target length
        """
        if not audio_data or target_length <= 0:
            return b""

        if len(audio_data) >= target_length:
            return audio_data[:target_length]

        # Calculate how many full loops we need plus remainder
        full_loops = target_length // len(audio_data)
        remainder = target_length % len(audio_data)

        # Build the looped audio
        looped_audio = audio_data * full_loops
        if remainder > 0:
            looped_audio += audio_data[:remainder]

        return looped_audio

    def adjust_volume(self, audio_data: bytes, volume_factor: float) -> bytes:
        """
        Adjust the volume of PCM audio data.

        Args:
            audio_data: PCM audio data
            volume_factor: Volume multiplier (0.0 = silence, 1.0 = original, >1.0 = amplified)

        Returns:
            Volume-adjusted audio data
        """
        if not audio_data or volume_factor == 1.0:
            return audio_data

        try:
            # Determine the format string for struct based on sample width
            if self.sample_width == 1:
                # 8-bit unsigned
                format_char = "B"
                max_val = 255
                bias = 128  # 8-bit is unsigned, centered at 128
            elif self.sample_width == 2:
                # 16-bit signed
                format_char = "h"
                max_val = 32767
                bias = 0
            else:
                self.logger.warning(f"Unsupported sample width: {self.sample_width}")
                return audio_data

            # Calculate number of samples
            num_samples = len(audio_data) // self.sample_width

            # Unpack audio data
            samples = struct.unpack(f"<{num_samples}{format_char}", audio_data)

            # Apply volume adjustment with clipping
            adjusted_samples = []
            for sample in samples:
                # Convert to signed if needed, apply volume, then clip
                signed_sample = sample - bias
                adjusted = int(signed_sample * volume_factor)

                # Clip to valid range
                if self.sample_width == 1:
                    adjusted = max(-128, min(127, adjusted)) + bias
                    adjusted = max(0, min(255, adjusted))
                else:  # 16-bit
                    adjusted = max(-32768, min(32767, adjusted))

                adjusted_samples.append(adjusted)

            # Pack back to bytes
            return struct.pack(f"<{len(adjusted_samples)}{format_char}", *adjusted_samples)

        except Exception as e:
            self.logger.error(f"Failed to adjust volume: {e}")
            return audio_data

    def mix_audio_with_background(self, speech_audio: bytes, background_volume: float = 0.1) -> bytes:
        """
        Mix speech audio with background noise.

        Args:
            speech_audio: Primary speech audio data (PCM)
            background_volume: Volume level for background noise (0.0 to 1.0)

        Returns:
            Mixed audio data, or original speech if mixing fails
        """
        if not speech_audio or not self._background_noise_cache or background_volume <= 0:
            return speech_audio

        try:
            speech_length = len(speech_audio)

            # Loop background noise to match speech length
            background_looped = self.loop_audio_to_length(self._background_noise_cache, speech_length)

            # Adjust background volume
            background_adjusted = self.adjust_volume(background_looped, background_volume)

            # Mix the audio by adding samples
            mixed_audio = self._mix_pcm_audio(speech_audio, background_adjusted)

            self.logger.debug(
                f"Mixed {len(speech_audio)} bytes of speech with background noise (volume: {background_volume})"
            )
            return mixed_audio

        except Exception as e:
            self.logger.error(f"Failed to mix audio with background: {e}")
            return speech_audio

    def _mix_pcm_audio(self, audio1: bytes, audio2: bytes) -> bytes:
        """
        Mix two PCM audio streams by adding their samples.

        Args:
            audio1: First audio stream (primary)
            audio2: Second audio stream (background)

        Returns:
            Mixed audio data
        """
        if len(audio1) != len(audio2):
            # Ensure both audio streams are the same length
            min_length = min(len(audio1), len(audio2))
            audio1 = audio1[:min_length]
            audio2 = audio2[:min_length]

        try:
            # Determine format for struct operations
            if self.sample_width == 1:
                format_char = "B"
                bias = 128
                max_val = 255
                min_val = 0
            elif self.sample_width == 2:
                format_char = "h"
                bias = 0
                max_val = 32767
                min_val = -32768
            else:
                raise ValueError(f"Unsupported sample width: {self.sample_width}")

            # Calculate number of samples
            num_samples = len(audio1) // self.sample_width

            # Unpack both audio streams
            samples1 = struct.unpack(f"<{num_samples}{format_char}", audio1)
            samples2 = struct.unpack(f"<{num_samples}{format_char}", audio2)

            # Mix samples by adding them
            mixed_samples = []
            for s1, s2 in zip(samples1, samples2, strict=False):
                # Convert to signed values for mixing
                signed1 = s1 - bias
                signed2 = s2 - bias

                # Add samples
                mixed = signed1 + signed2

                # Convert back and clip to valid range
                if self.sample_width == 1:
                    mixed = max(min_val - bias, min(max_val - bias, mixed)) + bias
                else:
                    mixed = max(min_val, min(max_val, mixed))

                mixed_samples.append(mixed)

            # Pack back to bytes
            return struct.pack(f"<{len(mixed_samples)}{format_char}", *mixed_samples)

        except Exception as e:
            self.logger.error(f"Failed to mix PCM audio: {e}")
            return audio1  # Return original audio on error

    def has_background_noise_loaded(self) -> bool:
        """
        Check if background noise is loaded and ready for mixing.

        Returns:
            True if background noise is loaded, False otherwise
        """
        return self._background_noise_cache and len(self._background_noise_cache) > 0
