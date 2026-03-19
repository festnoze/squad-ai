import sounddevice as sd
import soundfile as sf
import numpy as np
import tempfile
import os
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class AudioRecorder:
    """
    Audio recorder using sounddevice.
    """

    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        """
        Initialize recorder.

        Args:
            sample_rate: Sample rate in Hz (default 16000 for Whisper)
            channels: Number of channels (default 1 for mono)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.recording = False
        self.frames = []
        self.stream: Optional[sd.InputStream] = None
        self.output_filename: Optional[str] = None
        self._callback: Optional[Callable[[float], None]] = None

    def start_recording(self, callback: Optional[Callable[[float], None]] = None):
        """
        Start recording audio.

        Args:
            callback: Optional callback function to receive audio levels (0.0 to 1.0)
        """
        if self.recording:
            logger.warning("Already recording")
            return

        self.frames = []
        self.recording = True
        self._callback = callback

        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                callback=self._audio_callback,
            )
            self.stream.start()
            logger.info("Recording started")
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.recording = False
            raise

    def stop_recording(self) -> Optional[str]:
        """
        Stop recording and save to temporary file.

        Returns:
            Path to the recorded WAV file, or None if no recording was made.
        """
        if not self.recording:
            return None

        self.recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        logger.info("Recording stopped")

        if not self.frames:
            logger.warning("No audio recorded")
            return None

        # Concatenate all frames
        audio_data = np.concatenate(self.frames, axis=0)

        # Save to temp file
        fd, filename = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        try:
            sf.write(filename, audio_data, self.sample_rate)
            self.output_filename = filename
            logger.info(f"Audio saved to {filename}")
            return filename
        except Exception as e:
            logger.error(f"Failed to save audio file: {e}")
            return None

    def _audio_callback(self, indata, frames, time, status):
        """Callback for sounddevice input stream."""
        if status:
            logger.warning(f"Audio status: {status}")

        if self.recording:
            self.frames.append(indata.copy())

            # Calculate audio level for visualization
            if self._callback:
                level = np.linalg.norm(indata) * 10  # Amplify a bit
                self._callback(min(level, 1.0))

    def get_devices(self):
        """Get list of input devices."""
        return sd.query_devices()
