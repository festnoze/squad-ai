"""
Google Cloud TTS Streaming — standalone CLI script.

Usage:
    python TTS/text_to_speech_google_streaming.py "Texte à lire"
    python TTS/text_to_speech_google_streaming.py --voice fr-FR-Chirp3-HD-Puck "Texte"
    echo "Texte" | python TTS/text_to_speech_google_streaming.py

Requires:
    - google-cloud-texttospeech
    - sounddevice
    - GOOGLE_API_KEY env var (or GOOGLE_APPLICATION_CREDENTIALS, or application default credentials)

Audio: headerless LINEAR16 PCM, 24 kHz mono — played via sounddevice.
Streaming is only compatible with Chirp3-HD voices.
For short texts (< 200 chars), falls back to the simpler unary API.
"""

import argparse
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from envvar import EnvVar
import numpy as np
import sounddevice as sd
from google.api_core import client_options as client_options_lib
from google.cloud import texttospeech

SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = np.int16
DEFAULT_VOICE = "fr-FR-Chirp3-HD-Charon"
SHORT_TEXT_THRESHOLD = 200


# ── helpers ──────────────────────────────────────────────────────────────────


def _lang_code_from_voice(voice_name: str) -> str:
    """Extract language code from voice name like 'fr-FR-Chirp3-HD-Charon'."""
    parts = voice_name.split("-")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return "fr-FR"


def _split_into_sentences(text: str) -> list[str]:
    """Split text on sentence boundaries, keeping delimiters attached."""
    chunks = re.split(r"(?<=[.!?])\s+", text)
    # Further split on newlines
    result = []
    for chunk in chunks:
        for sub in chunk.split("\n"):
            sub = sub.strip()
            if sub:
                result.append(sub)
    return result


# ── unary fallback (short texts) ─────────────────────────────────────────────


def synthesize_unary(client: texttospeech.TextToSpeechClient, text: str, voice_name: str) -> None:
    """Synthesize with the classic unary API and play the result."""
    lang_code = _lang_code_from_voice(voice_name)
    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(name=voice_name, language_code=lang_code),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=SAMPLE_RATE,
        ),
    )
    pcm = response.audio_content
    # Strip WAV header if present
    if pcm[:4] == b"RIFF":
        pcm = pcm[44:]
    if not pcm:
        return
    samples = np.frombuffer(pcm, dtype=DTYPE)
    sd.play(samples, samplerate=SAMPLE_RATE)
    sd.wait()


# ── streaming synthesis ──────────────────────────────────────────────────────


def synthesize_streaming(client: texttospeech.TextToSpeechClient, text: str, voice_name: str) -> None:
    """Synthesize with the bidirectional streaming API and play audio in real time."""
    lang_code = _lang_code_from_voice(voice_name)

    streaming_config = texttospeech.StreamingSynthesizeConfig(
        voice=texttospeech.VoiceSelectionParams(
            name=voice_name,
            language_code=lang_code,
        ),
    )

    config_request = texttospeech.StreamingSynthesizeRequest(
        streaming_config=streaming_config,
    )

    sentences = _split_into_sentences(text)
    if not sentences:
        return

    def request_generator():
        yield config_request
        for sentence in sentences:
            yield texttospeech.StreamingSynthesizeRequest(
                input=texttospeech.StreamingSynthesisInput(text=sentence),
            )

    # Use a blocking OutputStream so we can write PCM chunks as they arrive
    # and they queue up for continuous playback.
    stream = sd.OutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE)
    stream.start()

    try:
        for response in client.streaming_synthesize(request_generator()):
            audio = response.audio_content
            if audio:
                samples = np.frombuffer(audio, dtype=DTYPE)
                # Reshape to (n_frames, channels) for sounddevice
                stream.write(samples.reshape(-1, CHANNELS))
    finally:
        # Drain remaining audio then close
        stream.stop()
        stream.close()


# ── main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Cloud TTS streaming playback")
    parser.add_argument("text", nargs="?", default=None, help="Text to synthesize (reads stdin if omitted)")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help=f"Chirp3-HD voice name (default: {DEFAULT_VOICE})")
    args = parser.parse_args()

    text = args.text
    if text is None:
        if sys.stdin.isatty():
            print("Reading from stdin (Ctrl+Z then Enter to finish on Windows, Ctrl+D on Unix):", file=sys.stderr)
        text = sys.stdin.read().strip()

    if not text:
        print("No text provided.", file=sys.stderr)
        sys.exit(1)

# Set Environment and configuration settings before api_config import
OPENAI_API_KEY = EnvVar.get_openai_api_key()
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# Load Google credentials (for LLM, STT and TTS uses)
project_root = os.path.dirname(Path(__file__).parent)
google_credentials_absolute_path = EnvVar.get_google_credentials_filepath_and_add_to_env(project_root)

if google_credentials_absolute_path:
    print(f"Set GOOGLE_APPLICATION_CREDENTIALS to: {google_credentials_absolute_path}")
else:
    print(f"/!\\ Google calendar credentials file not found at {project_root}")

    api_key = os.environ.get("GOOGLE_API_KEY")
    if api_key:
        opts = client_options_lib.ClientOptions(api_key=api_key)
        client = texttospeech.TextToSpeechClient(client_options=opts)
    else:
        # Falls back to GOOGLE_APPLICATION_CREDENTIALS or application default credentials
        client = texttospeech.TextToSpeechClient()

    if len(text) < SHORT_TEXT_THRESHOLD:
        synthesize_unary(client, text, args.voice)
    else:
        synthesize_streaming(client, text, args.voice)


if __name__ == "__main__":
    main()
