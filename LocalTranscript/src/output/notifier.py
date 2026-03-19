"""Windows notification system for transcription events."""

import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class Notifier:
    """Handles Windows toast notifications."""

    def __init__(self, app_name: str = "LocalTranscript"):
        """
        Initialize notifier.

        Args:
            app_name: Application name for notifications
        """
        self.app_name = app_name
        self.enabled = True
        self._init_backend()

    def _init_backend(self):
        """Initialize notification backend."""
        try:
            from win10toast_ng import ToastNotifier

            self.toaster = ToastNotifier()
            self.backend = "win10toast"
            logger.info("Notification backend initialized: win10toast-ng")
        except ImportError:
            logger.warning("win10toast-ng not available, notifications disabled")
            self.toaster = None
            self.backend = "none"

    def notify(
        self,
        title: str,
        message: str,
        duration: int = 5,
        icon_path: Optional[str] = None,
        threaded: bool = True,
    ) -> bool:
        """
        Show a Windows toast notification.

        Args:
            title: Notification title
            message: Notification message
            duration: Duration in seconds
            icon_path: Path to icon file (optional)
            threaded: Run in separate thread (default True)

        Returns:
            True if notification was shown successfully
        """
        if not self.enabled:
            logger.debug("Notifications disabled")
            return False

        if self.backend == "none":
            logger.warning(f"Cannot show notification (no backend): {title}")
            return False

        try:
            self.toaster.show_toast(
                title=title,
                msg=message,
                duration=duration,
                icon_path=icon_path,
                threaded=threaded,
            )
            logger.info(f"Notification shown: {title}")
            return True
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")
            return False

    def notify_transcription_complete(
        self, filename: str, char_count: int, duration_seconds: float
    ) -> bool:
        """
        Notify that transcription is complete.

        Args:
            filename: Name of transcribed file
            char_count: Number of characters transcribed
            duration_seconds: Processing duration

        Returns:
            True if successful
        """
        title = "Transcription Terminée"
        message = (
            f"Fichier: {filename}\n"
            f"Caractères: {char_count:,}\n"
            f"Durée: {duration_seconds:.1f}s"
        )
        return self.notify(title, message, duration=7)

    def notify_error(self, error_message: str) -> bool:
        """
        Notify about an error.

        Args:
            error_message: Error description

        Returns:
            True if successful
        """
        return self.notify(
            title="Erreur LocalTranscript", message=error_message, duration=10
        )

    def notify_watching(self, folder_path: str) -> bool:
        """
        Notify that file watching has started.

        Args:
            folder_path: Path being watched

        Returns:
            True if successful
        """
        return self.notify(
            title="Surveillance Activée",
            message=f"Surveille: {folder_path}",
            duration=5,
        )

    def notify_clipboard_copied(self, char_count: int) -> bool:
        """
        Notify that text was copied to clipboard.

        Args:
            char_count: Number of characters copied

        Returns:
            True if successful
        """
        return self.notify(
            title="Copié dans le Presse-papier",
            message=f"{char_count:,} caractères copiés",
            duration=3,
        )


# Global notifier instance
_notifier = None


def get_notifier() -> Notifier:
    """Get global notifier instance."""
    global _notifier
    if _notifier is None:
        _notifier = Notifier()
    return _notifier


def notify_transcription_complete(
    filename: str, char_count: int, duration: float
) -> bool:
    """Convenience function for transcription complete notification."""
    return get_notifier().notify_transcription_complete(filename, char_count, duration)


def notify_error(message: str) -> bool:
    """Convenience function for error notification."""
    return get_notifier().notify_error(message)


def notify_watching(folder_path: str) -> bool:
    """Convenience function for watching notification."""
    return get_notifier().notify_watching(folder_path)
