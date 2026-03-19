import customtkinter as ctk
from tkinter import messagebox
import threading
import logging
import os
from typing import Optional, Callable

from ..core.audio_recorder import AudioRecorder
from ..core.whisper_direct import WhisperTranscriber
from ..output.clipboard_manager import copy_to_clipboard
from ..core.window_manager import WindowManager

logger = logging.getLogger(__name__)


class MiniRecorder(ctk.CTkToplevel):
    """
    Minimalist floating recorder window.
    """

    def __init__(
        self,
        parent,
        transcriber: Optional[WhisperTranscriber] = None,
        on_close: Optional[Callable] = None,
    ):
        """
        Initialize MiniRecorder.

        Args:
            parent: Parent window
            transcriber: Existing transcriber instance
            on_close: Callback when window is closed
        """
        super().__init__(parent)

        self.transcriber = transcriber
        self.on_close_callback = on_close
        self.recorder = AudioRecorder()
        self.is_recording = False
        self.is_processing = False

        # Window setup
        self.title("VoiceInk Mini")
        self.geometry("300x60")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.overrideredirect(True)  # Frameless

        # Center on screen or position where appropriate
        # For now, let's put it near the bottom center
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - 300) // 2
        y = screen_height - 150
        self.geometry(f"300x60+{x}+{y}")

        # Configure grid
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # UI Elements
        self._setup_ui()

        # Dragging mechanism
        self.bind("<Button-1>", self._start_move)
        self.bind("<B1-Motion>", self._on_move)

        # Close handler
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_ui(self):
        """Setup UI components."""

        # Main container with rounded corners look (achieved via frame)
        self.main_frame = ctk.CTkFrame(self, corner_radius=30, fg_color="#1a1a1a")
        self.main_frame.pack(fill="both", expand=True, padx=2, pady=2)

        # Record Button (Left)
        self.record_btn = ctk.CTkButton(
            self.main_frame,
            text="",
            width=40,
            height=40,
            corner_radius=20,
            fg_color="#ff4444",
            hover_color="#cc0000",
            command=self._toggle_recording,
        )
        self.record_btn.pack(side="left", padx=10)

        # Status/Visualizer (Center)
        self.status_label = ctk.CTkLabel(
            self.main_frame, text="Prêt", text_color="white", font=("Arial", 12)
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        # Progress bar (hidden by default, used for audio level or processing)
        self.progress_bar = ctk.CTkProgressBar(self.main_frame, width=100, height=5)
        self.progress_bar.set(0)
        # self.progress_bar.pack(side="left", padx=5) # Optional

        # Settings/Close Button (Right)
        self.close_btn = ctk.CTkButton(
            self.main_frame,
            text="✕",
            width=30,
            height=30,
            corner_radius=15,
            fg_color="#333333",
            hover_color="#555555",
            command=self._on_close,
        )
        self.close_btn.pack(side="right", padx=10)

    def _start_move(self, event):
        self.x = event.x
        self.y = event.y

    def _on_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.winfo_x() + deltax
        y = self.winfo_y() + deltay
        self.geometry(f"+{x}+{y}")

    def _toggle_recording(self):
        """Toggle recording state."""
        if self.is_processing:
            return

        if not self.is_recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        """Start recording."""
        try:
            self.recorder.start_recording(callback=self._update_audio_level)
            self.is_recording = True
            self.record_btn.configure(fg_color="#cc0000")  # Darker red
            self.status_label.configure(text="Enregistrement...")
            logger.info("MiniRecorder: Started recording")
        except Exception as e:
            messagebox.showerror(
                "Erreur", f"Impossible de démarrer l'enregistrement: {e}"
            )

    def _stop_recording(self):
        """Stop recording and transcribe."""
        self.is_recording = False
        self.record_btn.configure(fg_color="#ff4444")
        self.status_label.configure(text="Traitement...")
        self.is_processing = True

        # Stop in thread to avoid blocking
        threading.Thread(target=self._process_recording).start()

    def _process_recording(self):
        """Process the recording (save and transcribe)."""
        try:
            audio_file = self.recorder.stop_recording()

            if not audio_file:
                self._update_status("Annulé (Audio vide)")
                self.is_processing = False
                return

            self._update_status("Transcription...")

            # Initialize transcriber if needed
            if self.transcriber is None:
                # This might take a while, so we should probably have it ready
                self.transcriber = WhisperTranscriber(model_size="base")  # Default

            # Transcribe
            result = self.transcriber.transcribe_file(audio_file)
            text = result.text.strip()

            if text:
                # Copy to clipboard
                copy_to_clipboard(text)

                # Try to paste
                # We need to be careful about focus.
                # Since this window is "topmost", it might have focus.
                # We might need to hide it or yield focus before pasting.

                # self.withdraw() # Hide window momentarily?
                # time.sleep(0.1)
                WindowManager.paste_to_active_window(text)
                # self.deiconify()

                self._update_status("Terminé!")
            else:
                self._update_status("Aucun texte détecté")

            # Cleanup temp file
            try:
                os.remove(audio_file)
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Processing failed: {e}")
            self._update_status("Erreur")
        finally:
            self.is_processing = False
            # Reset status after a delay
            self.after(2000, lambda: self._update_status("Prêt"))

    def _update_status(self, text: str):
        """Update status label safely."""
        self.status_label.configure(text=text)

    def _update_audio_level(self, level: float):
        """Update visualizer (callback from recorder)."""
        # This runs in audio thread, so we should use after
        # But for simple color change or progress bar update it might be ok?
        # Better to be safe
        # self.after(0, lambda: self.progress_bar.set(level))
        pass

    def _on_close(self):
        """Handle close."""
        if self.is_recording:
            self.recorder.stop_recording()

        self.destroy()
        if self.on_close_callback:
            self.on_close_callback()
