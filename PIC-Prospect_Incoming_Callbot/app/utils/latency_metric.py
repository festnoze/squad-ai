from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class OperationType(Enum):
    """Types d'opérations monitored for latency"""
    STT = "speech_to_text"
    TTS = "text_to_speech"
    SALESFORCE = "salesforce_api"
    RAG = "rag_inference"


class OperationStatus(Enum):
    """Statut de l'opération"""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class LatencyMetric:
    """Modèle de données pour une mesure de latence"""
    operation_type: OperationType
    operation_name: str  # e.g., "transcribe_audio_async", "schedule_new_appointment_async"
    latency_ms: float
    status: OperationStatus
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    call_sid: str | None = None
    stream_sid: str | None = None
    provider: str | None = None  # e.g., "google", "openai", "salesforce"
    error_message: str | None = None
    metadata: dict[str, any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "operation_type": self.operation_type.value,
            "operation_name": self.operation_name,
            "latency_ms": self.latency_ms,
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "call_sid": self.call_sid,
            "stream_sid": self.stream_sid,
            "provider": self.provider,
            "error_message": self.error_message,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, any]) -> "LatencyMetric":
        """Create from dictionary"""
        return cls(
            operation_type=OperationType(data["operation_type"]),
            operation_name=data["operation_name"],
            latency_ms=data["latency_ms"],
            status=OperationStatus(data["status"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            call_sid=data.get("call_sid"),
            stream_sid=data.get("stream_sid"),
            provider=data.get("provider"),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {})
        )
    
    def is_above_threshold(self, threshold_ms: float) -> bool:
        """Check if latency exceeds threshold"""
        return self.latency_ms > threshold_ms
    
    def __str__(self) -> str:
        return f"{self.operation_type.value}/{self.operation_name}: {self.latency_ms:.2f}ms ({self.status.value})"