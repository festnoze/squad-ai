import time
import os
import shutil
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from . import injector
from . import config


class TranscriptHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return

        filename = event.src_path
        if not filename.endswith(".txt"):
            return

        print(f"New transcript detected: {filename}")

        # Wait a brief moment to ensure file write is complete
        time.sleep(0.5)

        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()

            if content:
                injector.inject_text(content)

                # Archive the file
                filename_base = os.path.basename(filename)
                archive_path = os.path.join(config.ARCHIVE_DIR, filename_base)

                # Handle duplicate names in archive
                if os.path.exists(archive_path):
                    base, ext = os.path.splitext(filename_base)
                    timestamp = int(time.time())
                    archive_path = os.path.join(
                        config.ARCHIVE_DIR, f"{base}_{timestamp}{ext}"
                    )

                shutil.move(filename, archive_path)
                print(f"Archived to: {archive_path}")

        except Exception as e:
            print(f"Error processing file {filename}: {e}")


def start_watching():
    event_handler = TranscriptHandler()
    observer = Observer()
    observer.schedule(event_handler, config.WATCH_DIR, recursive=False)
    observer.start()
    print(f"Watching for transcripts in: {config.WATCH_DIR}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
