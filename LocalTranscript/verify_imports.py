import sys
import os

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

try:
    from src.ui.gui import LocalTranscriptGUI
    from src.ui.mini_recorder import MiniRecorder
    from src.core.audio_recorder import AudioRecorder
    from src.core.window_manager import WindowManager

    print("Imports successful")
except Exception as e:
    print(f"Import failed: {e}")
    sys.exit(1)
