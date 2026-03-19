"""
LocalTranscript - Interface avec Vibe pour transcription automatique.

Ce script permet de :
1. Surveiller un dossier pour les sorties de Vibe et copier automatiquement dans le presse-papier
2. Transcrire directement des fichiers audio/vidéo avec faster-whisper
3. Gérer les notifications Windows
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.utils.logger import setup_logger
from src.utils.config import get_config

logger = setup_logger()


def run_gui():
    """Run the GUI application."""
    from src.ui.gui import run_gui as start_gui
    logger.info("Starting GUI...")
    start_gui()


def run_watcher(folder: str):
    """Run file watcher in console mode."""
    from src.core.vibe_watcher import VibeWatcher

    logger.info(f"Starting file watcher for: {folder}")

    watcher = VibeWatcher(
        watch_folder=folder,
        auto_clipboard=True
    )

    try:
        watcher.watch_forever()
    except KeyboardInterrupt:
        logger.info("Watcher stopped by user")


def run_transcribe(audio_file: str, output_file: str = None, format: str = "txt"):
    """Run direct transcription."""
    from src.core.whisper_direct import WhisperTranscriber
    from src.output.clipboard_manager import copy_to_clipboard
    from src.output.notifier import notify_transcription_complete

    config = get_config()

    logger.info(f"Transcribing: {audio_file}")

    # Initialize transcriber
    transcriber = WhisperTranscriber(
        model_size=config.whisper.model_size,
        device=config.whisper.device,
        compute_type=config.whisper.compute_type,
        language=config.whisper.language if config.whisper.language != "auto" else None
    )

    # Transcribe
    try:
        if output_file:
            # Save to file
            output_path = transcriber.transcribe_to_file(
                audio_file,
                output_file,
                format=format
            )
            logger.info(f"Transcription saved to: {output_path}")

            # Read and copy to clipboard
            content = Path(output_path).read_text(encoding='utf-8')
            copy_to_clipboard(content)
            notify_transcription_complete(
                filename=Path(audio_file).name,
                char_count=len(content),
                duration_seconds=0
            )
        else:
            # Just transcribe and copy
            result = transcriber.transcribe_file(audio_file)
            copy_to_clipboard(result.text)
            logger.info(f"Transcription complete: {len(result.text)} characters")
            notify_transcription_complete(
                filename=Path(audio_file).name,
                char_count=len(result.text),
                duration_seconds=result.duration_seconds
            )
            print(result.text)

    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="LocalTranscript - Interface avec Vibe pour transcription automatique"
    )

    subparsers = parser.add_subparsers(dest='command', help='Commandes disponibles')

    # GUI command
    subparsers.add_parser('gui', help='Lancer l\'interface graphique (par défaut)')

    # Watch command
    watch_parser = subparsers.add_parser('watch', help='Surveiller un dossier')
    watch_parser.add_argument('folder', help='Dossier à surveiller')

    # Transcribe command
    transcribe_parser = subparsers.add_parser('transcribe', help='Transcrire un fichier audio')
    transcribe_parser.add_argument('file', help='Fichier audio/vidéo à transcrire')
    transcribe_parser.add_argument(
        '-o', '--output',
        help='Fichier de sortie (optionnel)',
        default=None
    )
    transcribe_parser.add_argument(
        '-f', '--format',
        help='Format de sortie (txt, srt, vtt)',
        choices=['txt', 'srt', 'vtt'],
        default='txt'
    )

    args = parser.parse_args()

    # Default to GUI if no command
    if not args.command:
        run_gui()
    elif args.command == 'gui':
        run_gui()
    elif args.command == 'watch':
        run_watcher(args.folder)
    elif args.command == 'transcribe':
        run_transcribe(args.file, args.output, args.format)


if __name__ == "__main__":
    main()
