"""Clipboard manager for Windows using multiple methods."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ClipboardManager:
    """Manages clipboard operations with fallback methods."""

    def __init__(self):
        """Initialize clipboard manager with available backends."""
        self.backend = self._detect_backend()
        logger.info(f"Clipboard backend initialized: {self.backend}")

    def _detect_backend(self) -> str:
        """Detect available clipboard backend."""
        # Try win32clipboard first (best for Windows)
        try:
            import win32clipboard
            return "win32"
        except ImportError:
            logger.warning("win32clipboard not available, falling back to pyperclip")

        # Fallback to pyperclip
        try:
            import pyperclip
            return "pyperclip"
        except ImportError:
            logger.error("No clipboard backend available")
            return "none"

    def copy(self, text: str) -> bool:
        """
        Copy text to clipboard.

        Args:
            text: Text to copy to clipboard

        Returns:
            True if successful, False otherwise
        """
        if not text:
            logger.warning("Attempted to copy empty text")
            return False

        try:
            if self.backend == "win32":
                return self._copy_win32(text)
            elif self.backend == "pyperclip":
                return self._copy_pyperclip(text)
            else:
                logger.error("No clipboard backend available")
                return False
        except Exception as e:
            logger.error(f"Failed to copy to clipboard: {e}")
            return False

    def _copy_win32(self, text: str) -> bool:
        """Copy using win32clipboard."""
        import win32clipboard
        import win32con

        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            logger.info(f"Copied {len(text)} characters to clipboard (win32)")
            return True
        except Exception as e:
            logger.error(f"win32clipboard error: {e}")
            try:
                win32clipboard.CloseClipboard()
            except:
                pass
            return False

    def _copy_pyperclip(self, text: str) -> bool:
        """Copy using pyperclip."""
        import pyperclip

        try:
            pyperclip.copy(text)
            logger.info(f"Copied {len(text)} characters to clipboard (pyperclip)")
            return True
        except Exception as e:
            logger.error(f"pyperclip error: {e}")
            return False

    def paste(self) -> Optional[str]:
        """
        Get text from clipboard.

        Returns:
            Clipboard text or None if failed
        """
        try:
            if self.backend == "win32":
                return self._paste_win32()
            elif self.backend == "pyperclip":
                return self._paste_pyperclip()
            else:
                return None
        except Exception as e:
            logger.error(f"Failed to paste from clipboard: {e}")
            return None

    def _paste_win32(self) -> Optional[str]:
        """Paste using win32clipboard."""
        import win32clipboard

        try:
            win32clipboard.OpenClipboard()
            text = win32clipboard.GetClipboardData()
            win32clipboard.CloseClipboard()
            return text
        except Exception as e:
            logger.error(f"win32clipboard paste error: {e}")
            try:
                win32clipboard.CloseClipboard()
            except:
                pass
            return None

    def _paste_pyperclip(self) -> Optional[str]:
        """Paste using pyperclip."""
        import pyperclip

        try:
            return pyperclip.paste()
        except Exception as e:
            logger.error(f"pyperclip paste error: {e}")
            return None


# Global clipboard manager instance
_clipboard = None


def get_clipboard() -> ClipboardManager:
    """Get global clipboard manager instance."""
    global _clipboard
    if _clipboard is None:
        _clipboard = ClipboardManager()
    return _clipboard


def copy_to_clipboard(text: str) -> bool:
    """
    Convenience function to copy text to clipboard.

    Args:
        text: Text to copy

    Returns:
        True if successful
    """
    return get_clipboard().copy(text)


def get_from_clipboard() -> Optional[str]:
    """
    Convenience function to get text from clipboard.

    Returns:
        Clipboard text or None
    """
    return get_clipboard().paste()
