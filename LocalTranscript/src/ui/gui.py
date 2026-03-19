"""Graphical user interface for LocalTranscript."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import logging
from pathlib import Path
from typing import Optional

from ..core.vibe_watcher import VibeWatcher
from ..core.whisper_direct import WhisperTranscriber
from ..output.clipboard_manager import copy_to_clipboard
from ..output.notifier import get_notifier
from ..utils.config import get_config

logger = logging.getLogger(__name__)


class LocalTranscriptGUI:
    """Main GUI application."""

    def __init__(self, root: tk.Tk):
        """
        Initialize GUI.

        Args:
            root: Tkinter root window
        """
        self.root = root
        self.root.title("LocalTranscript - Vibe Intégration")
        self.root.geometry("800x600")

        self.config = get_config()
        self.notifier = get_notifier()

        self.watcher: Optional[VibeWatcher] = None
        self.transcriber: Optional[WhisperTranscriber] = None
        self.last_transcription = ""

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """Setup UI components."""
        # Create notebook (tabs)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Tab 1: File Watcher
        self.watcher_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.watcher_tab, text="Surveillance Vibe")
        self._setup_watcher_tab()

        # Tab 2: Direct Transcription
        self.transcribe_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.transcribe_tab, text="Transcription Directe")
        self._setup_transcribe_tab()

        # Tab 3: Settings
        self.settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_tab, text="Paramètres")
        self._setup_settings_tab()

        # Status bar
        self.status_bar = tk.Label(
            self.root, text="Prêt", bd=1, relief=tk.SUNKEN, anchor=tk.W
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Mini Mode Button (Top Right)
        mini_btn = ttk.Button(
            self.root,
            text="Mode Mini (Enregistrement)",
            command=self._switch_to_mini_mode,
        )
        mini_btn.place(relx=1.0, x=-10, y=5, anchor="ne")

    def _switch_to_mini_mode(self):
        """Switch to mini recorder mode."""
        try:
            from .mini_recorder import MiniRecorder

            # Hide main window
            self.root.withdraw()

            # Initialize transcriber if needed so it's ready for mini mode
            if self.transcriber is None:
                lang = self.language_var.get()
                if lang == "auto":
                    lang = None

                # Show loading
                loading = tk.Toplevel(self.root)
                loading.title("Chargement")
                ttk.Label(loading, text="Chargement du modèle Whisper...").pack(
                    padx=20, pady=20
                )
                loading.update()

                try:
                    self.transcriber = WhisperTranscriber(
                        model_size=self.model_size_var.get(), language=lang
                    )
                finally:
                    loading.destroy()

            # Create mini recorder
            MiniRecorder(
                self.root, transcriber=self.transcriber, on_close=self._on_mini_close
            )

        except Exception as e:
            logger.error(f"Failed to switch to mini mode: {e}")
            messagebox.showerror("Erreur", f"Impossible de lancer le mode mini:\n{e}")
            self.root.deiconify()

    def _on_mini_close(self):
        """Handle mini recorder close."""
        self.root.deiconify()

    def _setup_watcher_tab(self):
        """Setup file watcher tab."""
        frame = ttk.Frame(self.watcher_tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title = ttk.Label(
            frame,
            text="Surveillance du dossier de sortie Vibe",
            font=("Arial", 12, "bold"),
        )
        title.pack(pady=(0, 10))

        # Folder selection
        folder_frame = ttk.Frame(frame)
        folder_frame.pack(fill=tk.X, pady=10)

        ttk.Label(folder_frame, text="Dossier à surveiller:").pack(
            side=tk.LEFT, padx=(0, 10)
        )
        self.watch_folder_var = tk.StringVar()
        self.watch_folder_entry = ttk.Entry(
            folder_frame, textvariable=self.watch_folder_var, width=50
        )
        self.watch_folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        browse_btn = ttk.Button(
            folder_frame, text="Parcourir...", command=self._browse_watch_folder
        )
        browse_btn.pack(side=tk.LEFT, padx=(10, 0))

        # Options
        options_frame = ttk.LabelFrame(frame, text="Options", padding=10)
        options_frame.pack(fill=tk.X, pady=10)

        self.auto_clipboard_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame,
            text="Copier automatiquement dans le presse-papier",
            variable=self.auto_clipboard_var,
        ).pack(anchor=tk.W)

        self.notification_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame,
            text="Afficher les notifications",
            variable=self.notification_var,
        ).pack(anchor=tk.W)

        # Control buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=20)

        self.start_watch_btn = ttk.Button(
            btn_frame,
            text="Démarrer la Surveillance",
            command=self._start_watching,
            style="Accent.TButton",
        )
        self.start_watch_btn.pack(side=tk.LEFT, padx=5)

        self.stop_watch_btn = ttk.Button(
            btn_frame, text="Arrêter", command=self._stop_watching, state=tk.DISABLED
        )
        self.stop_watch_btn.pack(side=tk.LEFT, padx=5)

        # Status
        self.watch_status_label = ttk.Label(
            frame, text="Status: Arrêté", font=("Arial", 10)
        )
        self.watch_status_label.pack(pady=10)

        # Log
        log_frame = ttk.LabelFrame(frame, text="Journal", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.watch_log = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD)
        self.watch_log.pack(fill=tk.BOTH, expand=True)

    def _setup_transcribe_tab(self):
        """Setup direct transcription tab."""
        frame = ttk.Frame(self.transcribe_tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title = ttk.Label(
            frame,
            text="Transcription Directe (faster-whisper)",
            font=("Arial", 12, "bold"),
        )
        title.pack(pady=(0, 10))

        # File selection
        file_frame = ttk.Frame(frame)
        file_frame.pack(fill=tk.X, pady=10)

        ttk.Label(file_frame, text="Fichier audio/vidéo:").pack(
            side=tk.LEFT, padx=(0, 10)
        )
        self.audio_file_var = tk.StringVar()
        self.audio_file_entry = ttk.Entry(
            file_frame, textvariable=self.audio_file_var, width=50
        )
        self.audio_file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        browse_audio_btn = ttk.Button(
            file_frame, text="Parcourir...", command=self._browse_audio_file
        )
        browse_audio_btn.pack(side=tk.LEFT, padx=(10, 0))

        # Model settings
        model_frame = ttk.LabelFrame(frame, text="Paramètres Whisper", padding=10)
        model_frame.pack(fill=tk.X, pady=10)

        # Model size
        size_frame = ttk.Frame(model_frame)
        size_frame.pack(fill=tk.X, pady=5)
        ttk.Label(size_frame, text="Taille du modèle:").pack(side=tk.LEFT, padx=(0, 10))
        self.model_size_var = tk.StringVar(value="base")
        model_sizes = ["tiny", "base", "small", "medium", "large"]
        ttk.Combobox(
            size_frame,
            textvariable=self.model_size_var,
            values=model_sizes,
            state="readonly",
            width=15,
        ).pack(side=tk.LEFT)

        # Language
        lang_frame = ttk.Frame(model_frame)
        lang_frame.pack(fill=tk.X, pady=5)
        ttk.Label(lang_frame, text="Langue:").pack(side=tk.LEFT, padx=(0, 10))
        self.language_var = tk.StringVar(value="fr")
        languages = ["auto", "fr", "en", "es", "de", "it"]
        ttk.Combobox(
            lang_frame,
            textvariable=self.language_var,
            values=languages,
            state="readonly",
            width=15,
        ).pack(side=tk.LEFT)

        # Transcribe button
        transcribe_btn = ttk.Button(
            frame,
            text="Transcrire",
            command=self._start_transcription,
            style="Accent.TButton",
        )
        transcribe_btn.pack(pady=20)

        # Progress
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            frame, mode="indeterminate", variable=self.progress_var
        )
        self.progress_bar.pack(fill=tk.X, pady=10)

        # Result
        result_frame = ttk.LabelFrame(frame, text="Résultat", padding=10)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.result_text = scrolledtext.ScrolledText(
            result_frame, height=15, wrap=tk.WORD
        )
        self.result_text.pack(fill=tk.BOTH, expand=True)

        # Copy button
        copy_btn = ttk.Button(
            result_frame, text="Copier dans le Presse-papier", command=self._copy_result
        )
        copy_btn.pack(pady=(10, 0))

    def _setup_settings_tab(self):
        """Setup settings tab."""
        frame = ttk.Frame(self.settings_tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(frame, text="Paramètres", font=("Arial", 12, "bold"))
        title.pack(pady=(0, 20))

        # Vibe path
        vibe_frame = ttk.LabelFrame(frame, text="Vibe", padding=10)
        vibe_frame.pack(fill=tk.X, pady=10)

        path_frame = ttk.Frame(vibe_frame)
        path_frame.pack(fill=tk.X, pady=5)
        ttk.Label(path_frame, text="Chemin vibe.exe:").pack(side=tk.LEFT, padx=(0, 10))
        self.vibe_path_var = tk.StringVar()
        ttk.Entry(path_frame, textvariable=self.vibe_path_var, width=50).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        # Save button
        save_btn = ttk.Button(
            frame, text="Sauvegarder les Paramètres", command=self._save_settings
        )
        save_btn.pack(pady=20)

    def _load_settings(self):
        """Load settings from config."""
        self.watch_folder_var.set(self.config.vibe.watch_folder)
        self.auto_clipboard_var.set(self.config.output.auto_clipboard)
        self.notification_var.set(self.config.output.notification_enabled)
        self.vibe_path_var.set(self.config.vibe.executable_path)
        self.model_size_var.set(self.config.whisper.model_size)
        self.language_var.set(self.config.whisper.language)

    def _save_settings(self):
        """Save settings to config."""
        self.config.vibe.watch_folder = self.watch_folder_var.get()
        self.config.vibe.executable_path = self.vibe_path_var.get()
        self.config.output.auto_clipboard = self.auto_clipboard_var.get()
        self.config.output.notification_enabled = self.notification_var.get()
        self.config.whisper.model_size = self.model_size_var.get()
        self.config.whisper.language = self.language_var.get()

        from ..utils.config import save_config

        save_config()

        messagebox.showinfo("Succès", "Paramètres sauvegardés!")

    def _browse_watch_folder(self):
        """Browse for watch folder."""
        folder = filedialog.askdirectory(title="Sélectionner le dossier à surveiller")
        if folder:
            self.watch_folder_var.set(folder)

    def _browse_audio_file(self):
        """Browse for audio file."""
        file = filedialog.askopenfilename(
            title="Sélectionner un fichier audio/vidéo",
            filetypes=[
                ("Fichiers audio", "*.mp3 *.wav *.m4a *.flac *.ogg"),
                ("Fichiers vidéo", "*.mp4 *.avi *.mkv *.mov"),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if file:
            self.audio_file_var.set(file)

    def _start_watching(self):
        """Start file watcher."""
        folder = self.watch_folder_var.get()

        if not folder:
            messagebox.showerror(
                "Erreur", "Veuillez sélectionner un dossier à surveiller"
            )
            return

        def transcription_callback(file_path: str, content: str):
            """Callback when transcription detected."""
            self._log_watch(f"Transcription détectée: {Path(file_path).name}")
            self.last_transcription = content

        try:
            self.watcher = VibeWatcher(
                watch_folder=folder,
                callback=transcription_callback,
                auto_clipboard=self.auto_clipboard_var.get(),
            )
            self.watcher.start()

            self.start_watch_btn.config(state=tk.DISABLED)
            self.stop_watch_btn.config(state=tk.NORMAL)
            self.watch_status_label.config(text=f"Status: En surveillance - {folder}")
            self.status_bar.config(text="Surveillance active")

            self._log_watch(f"Surveillance démarrée: {folder}")

        except Exception as e:
            logger.error(f"Failed to start watcher: {e}")
            messagebox.showerror(
                "Erreur", f"Impossible de démarrer la surveillance:\n{e}"
            )

    def _stop_watching(self):
        """Stop file watcher."""
        if self.watcher:
            self.watcher.stop()
            self.watcher = None

        self.start_watch_btn.config(state=tk.NORMAL)
        self.stop_watch_btn.config(state=tk.DISABLED)
        self.watch_status_label.config(text="Status: Arrêté")
        self.status_bar.config(text="Prêt")

        self._log_watch("Surveillance arrêtée")

    def _log_watch(self, message: str):
        """Add message to watch log."""
        self.watch_log.insert(tk.END, f"{message}\n")
        self.watch_log.see(tk.END)

    def _start_transcription(self):
        """Start direct transcription."""
        audio_file = self.audio_file_var.get()

        if not audio_file:
            messagebox.showerror("Erreur", "Veuillez sélectionner un fichier audio")
            return

        if not Path(audio_file).exists():
            messagebox.showerror("Erreur", "Le fichier n'existe pas")
            return

        # Run transcription in thread to avoid blocking UI
        thread = threading.Thread(target=self._transcribe_thread, args=(audio_file,))
        thread.daemon = True
        thread.start()

        # Start progress bar
        self.progress_bar.start()
        self.status_bar.config(text="Transcription en cours...")

    def _transcribe_thread(self, audio_file: str):
        """Transcription thread."""
        try:
            # Initialize transcriber if needed
            if self.transcriber is None:
                lang = self.language_var.get()
                if lang == "auto":
                    lang = None

                self.transcriber = WhisperTranscriber(
                    model_size=self.model_size_var.get(), language=lang
                )

            # Transcribe
            result = self.transcriber.transcribe_file(audio_file)

            # Update UI (must be done in main thread)
            self.root.after(0, self._transcription_complete, result.text)

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            self.root.after(0, self._transcription_error, str(e))

    def _transcription_complete(self, text: str):
        """Handle transcription completion."""
        self.progress_bar.stop()
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert("1.0", text)
        self.last_transcription = text
        self.status_bar.config(text="Transcription terminée")

        # Auto-copy if enabled
        if self.auto_clipboard_var.get():
            copy_to_clipboard(text)
            messagebox.showinfo(
                "Succès", "Transcription terminée et copiée dans le presse-papier!"
            )
        else:
            messagebox.showinfo("Succès", "Transcription terminée!")

    def _transcription_error(self, error: str):
        """Handle transcription error."""
        self.progress_bar.stop()
        self.status_bar.config(text="Erreur")
        messagebox.showerror(
            "Erreur de Transcription", f"La transcription a échoué:\n{error}"
        )

    def _copy_result(self):
        """Copy result to clipboard."""
        text = self.result_text.get("1.0", tk.END).strip()
        if text:
            if copy_to_clipboard(text):
                messagebox.showinfo("Succès", "Texte copié dans le presse-papier!")
            else:
                messagebox.showerror(
                    "Erreur", "Impossible de copier dans le presse-papier"
                )

    def run(self):
        """Run the GUI application."""
        self.root.mainloop()


def run_gui():
    """Run the GUI application."""
    root = tk.Tk()
    app = LocalTranscriptGUI(root)
    app.run()


if __name__ == "__main__":
    from ..utils.logger import setup_logger

    setup_logger()
    run_gui()
