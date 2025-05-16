import io
import wave
import logging
import webrtcvad
import audioop
from typing import Tuple
from pydub import AudioSegment
from pydub.effects import normalize

logger = logging.getLogger(__name__)

class IncomingAudioProcessing:
    """Audio processing utilities for improving speech recognition quality"""
    
    def __init__(self, sample_width=2, frame_rate=8000, channels=1, vad_aggressiveness=3):
        """
        Initialize the audio processor
        
        Args:
            sample_width: Sample width in bytes (2 = 16-bit PCM)
            frame_rate: Sample rate in Hz
            channels: Number of audio channels
            vad_aggressiveness: WebRTC VAD aggressiveness (0-3, 3 is most aggressive)
        """
        self.sample_width = sample_width
        self.frame_rate = frame_rate
        self.channels = channels
        self.vad = webrtcvad.Vad(vad_aggressiveness)
        logger.info(f"Initialized AudioProcessor with VAD aggressiveness {vad_aggressiveness}")
    
    def is_speech(self, audio_chunk: bytes, frame_duration_ms=30) -> bool:
        """
        Determine if audio chunk contains speech using WebRTC VAD
        
        Args:
            audio_chunk: Raw PCM audio bytes
            frame_duration_ms: Frame duration in milliseconds
        
        Returns:
            True if speech is detected, False otherwise
        """
        # WebRTC VAD only accepts 10, 20, or 30 ms frames
        if frame_duration_ms not in (10, 20, 30):
            frame_duration_ms = 30
            
        # Calculate frame size and ensure audio chunk is the right length
        frame_size = int(self.frame_rate * frame_duration_ms / 1000) * self.sample_width * self.channels
        
        # If chunk is too small, return False
        if len(audio_chunk) < frame_size:
            return False
            
        # If chunk is too large, only use the beginning
        if len(audio_chunk) > frame_size:
            audio_chunk = audio_chunk[:frame_size]
            
        try:
            return self.vad.is_speech(audio_chunk, self.frame_rate)
        except Exception as e:
            logger.error(f"VAD error: {e}")
            # Fallback to RMS-based detection
            rms = audioop.rms(audio_chunk, self.sample_width)
            return rms > 250  # Default threshold
    
    def preprocess_audio(self, audio_data: bytes) -> bytes:
        """
        Preprocess audio data to improve speech recognition quality
        
        Args:
            audio_data: Raw PCM audio bytes
            
        Returns:
            Processed audio bytes
        """
        try:
            # Convert bytes to AudioSegment via WAV
            buffer = io.BytesIO()
            with wave.open(buffer, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.sample_width)
                wf.setframerate(self.frame_rate)
                wf.writeframes(audio_data)
            
            buffer.seek(0)
            audio = AudioSegment.from_wav(buffer)
            
            # Step 1: Normalize audio (adjust volume to optimal level)
            audio = normalize(audio)
            
            # Step 2: Apply high-pass filter to remove low-frequency noise
            audio = audio.high_pass_filter(80)
            
            # Convert back to bytes
            output = io.BytesIO()
            audio.export(output, format="wav")
            output.seek(0)
            
            # Extract raw PCM data from WAV
            with wave.open(output, 'rb') as wf:
                processed_audio = wf.readframes(wf.getnframes())
                
            return processed_audio
        except Exception as e:
            logger.error(f"Audio preprocessing error: {e}")
            # Return original data if processing fails
            return audio_data
    
    def detect_silence_speech(self, audio_data: bytes, threshold=250) -> Tuple[bool, int]:
        """
        Detect silence vs speech using both VAD and RMS
        
        Args:
            audio_data: Raw PCM audio bytes
            threshold: RMS threshold for silence detection
            
        Returns:
            Tuple of (is_silence, speech_to_noise_ratio)
        """
        # Get RMS value (volume)
        speech_to_noise_ratio = audioop.rms(audio_data, self.sample_width)
        
        # Check using VAD (more accurate but may not work on all chunks)
        try:
            frame_size = len(audio_data)
            if frame_size >= 480:  # At least 30ms at 8kHz, 16-bit mono
                vad_result = self.is_speech(audio_data)
                if vad_result:
                    return False, speech_to_noise_ratio  # VAD detected speech
        except Exception:
            pass  # Fall back to RMS method
            
        # RMS-based detection (fallback)
        is_silence = speech_to_noise_ratio < threshold
        return is_silence, speech_to_noise_ratio
