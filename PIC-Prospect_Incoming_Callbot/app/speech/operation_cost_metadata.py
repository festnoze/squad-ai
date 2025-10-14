"""Cost metadata models for STT and TTS operations.

These models store cost information that will be logged to the database
after messages are persisted (when conversation_id and message_id are available).
"""
from dataclasses import dataclass


@dataclass
class STTCostMetadata:
    """Cost metadata for Speech-to-Text operations."""
    provider: str
    model: str
    audio_duration_seconds: float
    price_per_unit: float  # Price per second
    cost_usd: float


@dataclass
class TTSCostMetadata:
    """Cost metadata for Text-to-Speech operations."""
    provider: str
    model: str
    character_count: int
    price_per_unit: float  # Price per character
    cost_usd: float
