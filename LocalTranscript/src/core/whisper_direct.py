"""Direct Whisper transcription using faster-whisper."""

import logging
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Result of a transcription."""
    text: str
    segments: List[Dict[str, Any]]
    language: str
    duration_seconds: float
    file_path: str


class WhisperTranscriber:
    """Direct transcription using faster-whisper."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        language: Optional[str] = None
    ):
        """
        Initialize Whisper transcriber.

        Args:
            model_size: Model size (tiny, base, small, medium, large)
            device: Device to use (cpu, cuda)
            compute_type: Computation type (int8, float16, float32)
            language: Language code (e.g., 'fr', 'en') or None for auto-detect
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.model = None
        self._init_model()

    def _init_model(self):
        """Initialize the Whisper model."""
        try:
            from faster_whisper import WhisperModel

            logger.info(f"Loading Whisper model: {self.model_size} on {self.device}")
            start_time = time.time()

            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type
            )

            load_time = time.time() - start_time
            logger.info(f"Model loaded in {load_time:.2f}s")

        except ImportError:
            logger.error("faster-whisper not installed. Install with: pip install faster-whisper")
            raise
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise

    def transcribe_file(
        self,
        audio_path: str,
        language: Optional[str] = None,
        task: str = "transcribe"
    ) -> TranscriptionResult:
        """
        Transcribe an audio file.

        Args:
            audio_path: Path to audio file
            language: Language override (None to use instance default)
            task: Task type ('transcribe' or 'translate')

        Returns:
            TranscriptionResult object

        Raises:
            FileNotFoundError: If audio file doesn't exist
            RuntimeError: If transcription fails
        """
        audio_path_obj = Path(audio_path)

        if not audio_path_obj.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if self.model is None:
            raise RuntimeError("Model not initialized")

        logger.info(f"Transcribing: {audio_path_obj.name}")
        start_time = time.time()

        try:
            # Use provided language or instance default
            lang = language or self.language

            # Transcribe
            segments_generator, info = self.model.transcribe(
                str(audio_path_obj),
                language=lang,
                task=task
            )

            # Collect segments
            segments = []
            full_text_parts = []

            for segment in segments_generator:
                segment_dict = {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip()
                }
                segments.append(segment_dict)
                full_text_parts.append(segment.text.strip())

            # Combine text
            full_text = " ".join(full_text_parts)

            duration = time.time() - start_time

            logger.info(
                f"Transcription complete: {len(full_text)} chars, "
                f"{len(segments)} segments, {duration:.2f}s"
            )

            return TranscriptionResult(
                text=full_text,
                segments=segments,
                language=info.language,
                duration_seconds=duration,
                file_path=str(audio_path_obj)
            )

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise RuntimeError(f"Transcription failed: {e}")

    def transcribe_to_file(
        self,
        audio_path: str,
        output_path: Optional[str] = None,
        format: str = "txt",
        **kwargs
    ) -> str:
        """
        Transcribe audio and save to file.

        Args:
            audio_path: Path to audio file
            output_path: Output file path (auto-generated if None)
            format: Output format ('txt', 'srt', 'vtt')
            **kwargs: Additional args for transcribe_file

        Returns:
            Path to output file

        Raises:
            ValueError: If format is invalid
        """
        if format not in ['txt', 'srt', 'vtt']:
            raise ValueError(f"Invalid format: {format}. Use 'txt', 'srt', or 'vtt'")

        # Transcribe
        result = self.transcribe_file(audio_path, **kwargs)

        # Generate output path if not provided
        if output_path is None:
            audio_path_obj = Path(audio_path)
            output_path = audio_path_obj.with_suffix(f".{format}")

        output_path_obj = Path(output_path)

        # Write file based on format
        if format == "txt":
            content = result.text
        elif format == "srt":
            content = self._format_srt(result.segments)
        elif format == "vtt":
            content = self._format_vtt(result.segments)

        output_path_obj.write_text(content, encoding='utf-8')
        logger.info(f"Saved transcription to: {output_path_obj}")

        return str(output_path_obj)

    def _format_srt(self, segments: List[Dict[str, Any]]) -> str:
        """Format segments as SRT subtitle format."""
        lines = []
        for i, segment in enumerate(segments, 1):
            start = self._format_timestamp_srt(segment['start'])
            end = self._format_timestamp_srt(segment['end'])
            text = segment['text']

            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")  # Empty line between entries

        return "\n".join(lines)

    def _format_vtt(self, segments: List[Dict[str, Any]]) -> str:
        """Format segments as WebVTT format."""
        lines = ["WEBVTT", ""]

        for segment in segments:
            start = self._format_timestamp_vtt(segment['start'])
            end = self._format_timestamp_vtt(segment['end'])
            text = segment['text']

            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _format_timestamp_srt(seconds: float) -> str:
        """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def _format_timestamp_vtt(seconds: float) -> str:
        """Format seconds as WebVTT timestamp (HH:MM:SS.mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
