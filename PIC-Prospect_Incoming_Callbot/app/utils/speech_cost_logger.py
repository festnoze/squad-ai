"""
Cost logger for Speech-to-Text and Text-to-Speech operations.
Logs operations to CSV file for cost tracking and analysis.
Uses French CSV format: semicolon separator and comma for decimal separator.
Costs are stored in millidollars (1/1000 of a dollar).
"""
import csv
import logging
import os
from datetime import datetime
from pathlib import Path
from threading import Lock


class SpeechCostLogger:
    """Logger for tracking STT and TTS operation costs."""

    def __init__(self, log_file_path: str = "outputs/logs/speech_costs.csv"):
        self.log_file_path = log_file_path
        self.logger = logging.getLogger(__name__)
        self._lock = Lock()
        self._ensure_log_file_exists()

    def _ensure_log_file_exists(self):
        """Create the log file with headers if it doesn't exist."""
        Path(self.log_file_path).parent.mkdir(parents=True, exist_ok=True)

        if not os.path.exists(self.log_file_path):
            with open(self.log_file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow([
                    "timestamp",
                    "stream_id",
                    "call_sid",
                    "phone_number",
                    "operation_type",
                    "provider",
                    "model",
                    "cost_millidollars",
                    "duration_seconds",
                    "character_count",
                ])

    def log_operation(
        self,
        operation_type: str,
        provider: str,
        model: str,
        cost_usd: float,
        stream_id: str | None = None,
        call_sid: str | None = None,
        phone_number: str | None = None,
        duration_seconds: float | None = None,
        character_count: int | None = None,
    ):
        """
        Log a STT or TTS operation to CSV.

        Args:
            operation_type: "STT" or "TTS"
            provider: "google" or "openai"
            model: Model name used
            cost_usd: Cost in USD
            stream_id: Optional stream ID
            call_sid: Optional call SID
            phone_number: Optional phone number
            duration_seconds: Optional audio duration (for STT)
            character_count: Optional character count (for TTS)
        """
        try:
            # Convert to millidollars and format with French decimal separator (comma)
            cost_millidollars = cost_usd * 1000
            cost_millidollars_str = f"{cost_millidollars:.3f}".replace(".", ",")

            timestamp = datetime.now().isoformat()

            # Format duration with French decimal separator
            duration_str = ""
            if duration_seconds is not None:
                duration_str = f"{duration_seconds:.2f}".replace(".", ",")

            with self._lock:
                with open(self.log_file_path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f, delimiter=";")
                    writer.writerow([
                        timestamp,
                        stream_id or "",
                        call_sid or "",
                        phone_number or "",
                        operation_type,
                        provider,
                        model,
                        cost_millidollars_str,
                        duration_str,
                        character_count or "",
                    ])

            self.logger.debug(
                f"Logged {operation_type} operation: {provider}/{model}, "
                f"cost={cost_millidollars_str} millidollars, stream_id={stream_id}"
            )

        except Exception as e:
            self.logger.error(f"Error logging speech cost: {e}", exc_info=True)


# Global singleton instance
_cost_logger = None


def get_speech_cost_logger() -> SpeechCostLogger:
    """Get the global speech cost logger instance."""
    global _cost_logger
    if _cost_logger is None:
        _cost_logger = SpeechCostLogger()
    return _cost_logger
