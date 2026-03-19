"""File watcher for Vibe transcription outputs."""

import logging
import time
from pathlib import Path
from typing import Callable, Optional, List
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

from ..output.clipboard_manager import copy_to_clipboard
from ..output.notifier import notify_transcription_complete, notify_watching

logger = logging.getLogger(__name__)


class TranscriptionFileHandler(FileSystemEventHandler):
    """Handles file system events for transcription files."""

    def __init__(
        self,
        callback: Optional[Callable[[str, str], None]] = None,
        auto_clipboard: bool = True,
        file_extensions: Optional[List[str]] = None
    ):
        """
        Initialize file handler.

        Args:
            callback: Function to call with (file_path, content) when file detected
            auto_clipboard: Automatically copy to clipboard
            file_extensions: List of file extensions to watch (e.g., ['.txt', '.srt'])
        """
        super().__init__()
        self.callback = callback
        self.auto_clipboard = auto_clipboard
        self.file_extensions = file_extensions or ['.txt', '.srt', '.vtt']
        self.processed_files = set()
        self.last_process_time = {}

    def _should_process_file(self, file_path: Path) -> bool:
        """Check if file should be processed."""
        # Check extension
        if file_path.suffix.lower() not in self.file_extensions:
            return False

        # Avoid processing same file multiple times quickly
        file_key = str(file_path)
        current_time = time.time()
        last_time = self.last_process_time.get(file_key, 0)

        if current_time - last_time < 2:  # 2 second debounce
            return False

        return True

    def _process_file(self, file_path: Path):
        """Process a transcription file."""
        try:
            # Wait a bit for file to be fully written
            time.sleep(0.5)

            # Read file content
            content = file_path.read_text(encoding='utf-8')

            if not content.strip():
                logger.warning(f"File is empty: {file_path}")
                return

            logger.info(f"Processing transcription file: {file_path.name} ({len(content)} chars)")

            # Update tracking
            self.last_process_time[str(file_path)] = time.time()
            self.processed_files.add(str(file_path))

            # Copy to clipboard if enabled
            if self.auto_clipboard:
                if copy_to_clipboard(content):
                    logger.info("Content copied to clipboard")

            # Calculate processing time (approximate)
            file_age = time.time() - file_path.stat().st_mtime
            duration = max(0.1, file_age)

            # Notify
            notify_transcription_complete(
                filename=file_path.name,
                char_count=len(content),
                duration_seconds=duration
            )

            # Call callback if provided
            if self.callback:
                try:
                    self.callback(str(file_path), content)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")

    def on_created(self, event):
        """Handle file creation event."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        if self._should_process_file(file_path):
            logger.info(f"New file detected: {file_path.name}")
            self._process_file(file_path)

    def on_modified(self, event):
        """Handle file modification event."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Only process if not recently processed
        if str(file_path) not in self.processed_files and self._should_process_file(file_path):
            logger.info(f"Modified file detected: {file_path.name}")
            self._process_file(file_path)


class VibeWatcher:
    """Watches a folder for Vibe transcription outputs."""

    def __init__(
        self,
        watch_folder: str,
        callback: Optional[Callable[[str, str], None]] = None,
        auto_clipboard: bool = True,
        file_extensions: Optional[List[str]] = None
    ):
        """
        Initialize Vibe watcher.

        Args:
            watch_folder: Folder to watch for transcription files
            callback: Function to call when transcription detected
            auto_clipboard: Automatically copy to clipboard
            file_extensions: File extensions to watch
        """
        self.watch_folder = Path(watch_folder)
        self.callback = callback
        self.auto_clipboard = auto_clipboard
        self.file_extensions = file_extensions or ['.txt', '.srt', '.vtt']

        self.observer = None
        self.event_handler = None
        self.is_watching = False

        # Validate folder
        if not self.watch_folder.exists():
            logger.warning(f"Watch folder does not exist: {self.watch_folder}")
            self.watch_folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created watch folder: {self.watch_folder}")

    def start(self):
        """Start watching the folder."""
        if self.is_watching:
            logger.warning("Already watching")
            return

        logger.info(f"Starting to watch: {self.watch_folder}")

        # Create event handler
        self.event_handler = TranscriptionFileHandler(
            callback=self.callback,
            auto_clipboard=self.auto_clipboard,
            file_extensions=self.file_extensions
        )

        # Create and start observer
        self.observer = Observer()
        self.observer.schedule(
            self.event_handler,
            str(self.watch_folder),
            recursive=False
        )
        self.observer.start()
        self.is_watching = True

        # Notify user
        notify_watching(str(self.watch_folder))

        logger.info(f"Now watching: {self.watch_folder}")

    def stop(self):
        """Stop watching the folder."""
        if not self.is_watching:
            return

        logger.info("Stopping watcher")

        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)

        self.is_watching = False
        logger.info("Watcher stopped")

    def watch_forever(self):
        """Watch folder indefinitely (blocking)."""
        self.start()

        try:
            logger.info("Watching forever. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
