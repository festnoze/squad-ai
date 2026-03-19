"""
Exemples d'utilisation de LocalTranscript par programmation.

Ce fichier montre comment utiliser les différents modules de LocalTranscript
dans vos propres scripts Python.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def exemple_clipboard():
    """Exemple : Utiliser le gestionnaire de presse-papier."""
    print("=== Exemple : Gestionnaire de Presse-papier ===\n")

    from src.output.clipboard_manager import copy_to_clipboard, get_from_clipboard

    # Copier du texte
    texte = "Bonjour depuis LocalTranscript! 🎙️"
    if copy_to_clipboard(texte):
        print(f"✅ Texte copié : {texte}")

    # Lire le presse-papier
    contenu = get_from_clipboard()
    print(f"📋 Contenu actuel : {contenu}")


def exemple_notification():
    """Exemple : Afficher des notifications."""
    print("\n=== Exemple : Notifications ===\n")

    from src.output.notifier import get_notifier

    notifier = get_notifier()

    # Notification simple
    notifier.notify("Test LocalTranscript", "Ceci est une notification de test")

    # Notification de transcription
    notifier.notify_transcription_complete(
        filename="audio_test.mp3",
        char_count=1250,
        duration_seconds=15.5
    )


def exemple_watcher():
    """Exemple : Surveiller un dossier (non bloquant)."""
    print("\n=== Exemple : Surveillance de Dossier ===\n")

    from src.core.vibe_watcher import VibeWatcher

    # Callback personnalisé
    def ma_fonction_callback(file_path: str, content: str):
        print(f"\n🔔 Nouveau fichier détecté : {Path(file_path).name}")
        print(f"   Longueur : {len(content)} caractères")
        print(f"   Aperçu : {content[:100]}...")

    # Créer le watcher
    watcher = VibeWatcher(
        watch_folder="watched_folder",
        callback=ma_fonction_callback,
        auto_clipboard=True
    )

    print(f"📁 Surveillance du dossier : watched_folder")
    print("   Déposez un fichier .txt dans ce dossier pour tester")
    print("   Appuyez sur Ctrl+C pour arrêter\n")

    # Démarrer la surveillance (bloquant)
    try:
        watcher.watch_forever()
    except KeyboardInterrupt:
        print("\n⏹️  Surveillance arrêtée")


def exemple_transcription_directe():
    """Exemple : Transcrire un fichier audio directement."""
    print("\n=== Exemple : Transcription Directe ===\n")

    # Demander un fichier
    audio_file = input("Entrez le chemin d'un fichier audio/vidéo (ou ENTER pour passer) : ").strip()

    if not audio_file:
        print("⏭️  Exemple passé (pas de fichier fourni)")
        return

    if not Path(audio_file).exists():
        print(f"❌ Fichier introuvable : {audio_file}")
        return

    from src.core.whisper_direct import WhisperTranscriber
    from src.output.clipboard_manager import copy_to_clipboard

    print("\n🔄 Chargement du modèle Whisper...")

    # Créer le transcripteur
    transcriber = WhisperTranscriber(
        model_size="base",  # tiny, base, small, medium, large
        language="fr"       # ou None pour auto-détection
    )

    print(f"🎙️  Transcription de : {Path(audio_file).name}")
    print("   Ceci peut prendre quelques secondes...\n")

    # Transcrire
    result = transcriber.transcribe_file(audio_file)

    # Afficher résultat
    print("=" * 60)
    print(result.text)
    print("=" * 60)
    print(f"\n✅ Transcription terminée!")
    print(f"   Langue détectée : {result.language}")
    print(f"   Segments : {len(result.segments)}")
    print(f"   Caractères : {len(result.text)}")
    print(f"   Durée : {result.duration_seconds:.2f}s")

    # Copier dans le presse-papier
    copy_to_clipboard(result.text)
    print(f"\n📋 Texte copié dans le presse-papier")


def exemple_config():
    """Exemple : Lire et modifier la configuration."""
    print("\n=== Exemple : Configuration ===\n")

    from src.utils.config import get_config

    config = get_config()

    print(f"📝 Configuration actuelle :")
    print(f"   Modèle Whisper : {config.whisper.model_size}")
    print(f"   Langue : {config.whisper.language}")
    print(f"   Device : {config.whisper.device}")
    print(f"   Auto-clipboard : {config.output.auto_clipboard}")
    print(f"   Notifications : {config.output.notification_enabled}")
    print(f"   Chemin Vibe : {config.vibe.executable_path}")


def exemple_transcription_batch():
    """Exemple : Transcrire plusieurs fichiers en batch."""
    print("\n=== Exemple : Transcription Batch ===\n")

    from src.core.whisper_direct import WhisperTranscriber
    from pathlib import Path

    # Demander un dossier
    folder = input("Entrez le chemin d'un dossier contenant des fichiers audio (ou ENTER pour passer) : ").strip()

    if not folder:
        print("⏭️  Exemple passé")
        return

    folder_path = Path(folder)
    if not folder_path.exists():
        print(f"❌ Dossier introuvable : {folder}")
        return

    # Extensions audio supportées
    audio_extensions = ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.mp4', '.avi', '.mkv']

    # Trouver tous les fichiers audio
    audio_files = []
    for ext in audio_extensions:
        audio_files.extend(folder_path.glob(f"*{ext}"))

    if not audio_files:
        print(f"❌ Aucun fichier audio trouvé dans : {folder}")
        return

    print(f"📁 {len(audio_files)} fichier(s) audio trouvé(s)")

    # Créer transcripteur
    transcriber = WhisperTranscriber(model_size="base", language="fr")

    # Transcrire chaque fichier
    for i, audio_file in enumerate(audio_files, 1):
        print(f"\n[{i}/{len(audio_files)}] 🎙️  {audio_file.name}")

        try:
            # Transcrire et sauvegarder
            output_file = audio_file.with_suffix('.txt')
            transcriber.transcribe_to_file(
                str(audio_file),
                str(output_file),
                format='txt'
            )
            print(f"   ✅ Sauvegardé : {output_file.name}")

        except Exception as e:
            print(f"   ❌ Erreur : {e}")

    print(f"\n🎉 Transcription batch terminée!")


def menu_principal():
    """Menu interactif pour choisir les exemples."""
    print("\n" + "=" * 60)
    print("   LocalTranscript - Exemples d'Utilisation")
    print("=" * 60)

    exemples = {
        "1": ("Gestionnaire de Presse-papier", exemple_clipboard),
        "2": ("Notifications Windows", exemple_notification),
        "3": ("Surveillance de Dossier", exemple_watcher),
        "4": ("Transcription Directe", exemple_transcription_directe),
        "5": ("Configuration", exemple_config),
        "6": ("Transcription Batch", exemple_transcription_batch),
    }

    print("\nChoisissez un exemple :")
    for key, (nom, _) in exemples.items():
        print(f"  {key}. {nom}")
    print("  0. Quitter")

    choix = input("\nVotre choix : ").strip()

    if choix == "0":
        print("\n👋 Au revoir!")
        return

    if choix in exemples:
        _, fonction = exemples[choix]
        try:
            fonction()
        except Exception as e:
            print(f"\n❌ Erreur : {e}")
            import traceback
            traceback.print_exc()
    else:
        print("\n❌ Choix invalide")

    # Recommencer
    input("\nAppuyez sur ENTER pour continuer...")
    menu_principal()


if __name__ == "__main__":
    # Setup logging
    from src.utils.logger import setup_logger
    setup_logger(level=20)  # INFO level

    # Lancer menu
    menu_principal()
