import pyautogui
import pyperclip
from plyer import notification
import time


def inject_text(text):
    """
    Injects the given text into the active window.
    1. Copies text to clipboard.
    2. Simulates Ctrl+V.
    3. Sends a notification.
    """
    if not text:
        return

    try:
        # Copy to clipboard
        pyperclip.copy(text)

        # Small delay to ensure clipboard is ready
        time.sleep(0.1)

        # Simulate Paste
        pyautogui.hotkey("ctrl", "v")

        # Notification
        notification.notify(
            title="Vibe Injector",
            message="Transcription injected successfully!",
            app_name="Vibe Injector",
            timeout=3,
        )
        print("Text injected successfully.")

    except Exception as e:
        print(f"Error injecting text: {e}")
        notification.notify(
            title="Vibe Injector Error",
            message=f"Failed to inject text: {e}",
            app_name="Vibe Injector",
            timeout=5,
        )
