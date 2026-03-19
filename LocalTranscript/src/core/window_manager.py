import logging
import pyautogui

try:
    import win32gui
    import win32con
except ImportError:
    win32gui = None
    win32con = None

logger = logging.getLogger(__name__)


class WindowManager:
    """Manages window interactions."""

    @staticmethod
    def paste_to_active_window(text: str):
        """
        Paste text to the currently active window.

        Args:
            text: Text to paste
        """
        if not text:
            return

        logger.info("Attempting to paste to active window")

        # Ensure we are not holding any keys (sometimes modifiers get stuck)
        pyautogui.keyUp("shift")
        pyautogui.keyUp("ctrl")
        pyautogui.keyUp("alt")

        # Small delay to ensure focus is back on the target window
        # (if the user clicked on our UI, we might need to give focus back?
        # Actually, if our UI is "always on top" and doesn't steal focus or we minimize it,
        # the previous window might still be active.
        # But usually clicking a button steals focus.
        # So we might need to restore focus to the previous window if we tracked it.)

        # For now, we assume the user has the target window active OR
        # we rely on the fact that our floating window might be "no focus" (hard in tkinter).

        # If we use a global hotkey, the focus remains on the target window.
        # If we click a button on our app, our app gets focus.
        # So we need a way to "paste to PREVIOUS window".

        # Let's try to find the previous window.
        # This is tricky.
        # A simple approach: The user positions the cursor, then clicks "Record" on our floating window.
        # Focus moves to us.
        # When we stop, we want to paste to where they were.
        # So we should remember the active window when "Record" started?
        # Or just use Alt+Tab to go back? No, that's risky.

        # Better approach:
        # 1. Get handle of active window BEFORE we take focus (e.g. when we start recording, if we use a hotkey).
        # 2. If we use a button, we steal focus.
        # We can try `pyautogui.hotkey('alt', 'tab')` to switch back, but that's unreliable.

        # Let's stick to simulating Ctrl+V.
        # If the user uses a global hotkey, focus doesn't change (much).
        # If the user clicks our UI, they need to click back to their doc?
        # VoiceInk on macOS likely uses accessibility APIs to insert text or just pastes.

        # If we want to be "minimalist", maybe we don't steal focus?
        # Tkinter windows steal focus by default.
        # We can set `overrideredirect(True)` and `attributes("-topmost", True)`.

        # Let's just implement the paste command for now.
        try:
            pyautogui.hotkey("ctrl", "v")
            logger.info("Sent Ctrl+V")
        except Exception as e:
            logger.error(f"Failed to paste: {e}")

    @staticmethod
    def get_active_window_title() -> str:
        """Get title of active window."""
        if win32gui:
            try:
                hwnd = win32gui.GetForegroundWindow()
                return win32gui.GetWindowText(hwnd)
            except Exception:
                pass
        return "Unknown"
