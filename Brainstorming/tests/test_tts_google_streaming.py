"""Integration tests for Google Cloud TTS streaming.

Requires GOOGLE_API_KEY in .env and the Cloud Text-to-Speech API enabled.
These tests call the real Google API — they are skipped if credentials are missing.
"""

import os
import sys

import pytest
from dotenv import load_dotenv

load_dotenv()

# Add TTS directory to path so we can import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "TTS"))

from text_to_speech_google_streaming import (
    _lang_code_from_voice,
    _split_into_sentences,
)

has_api_key = bool(os.environ.get("GOOGLE_API_KEY"))
skip_no_credentials = pytest.mark.skipif(not has_api_key, reason="GOOGLE_API_KEY not set")


# ── unit tests (no API call) ────────────────────────────────────────────────


class TestLangCodeFromVoice:
    def test_french_voice(self):
        assert _lang_code_from_voice("fr-FR-Chirp3-HD-Charon") == "fr-FR"

    def test_english_voice(self):
        assert _lang_code_from_voice("en-US-Chirp3-HD-Puck") == "en-US"

    def test_short_name_fallback(self):
        assert _lang_code_from_voice("invalid") == "fr-FR"


class TestSplitIntoSentences:
    def test_simple_sentences(self):
        result = _split_into_sentences("Bonjour. Comment allez-vous? Bien!")
        assert result == ["Bonjour.", "Comment allez-vous?", "Bien!"]

    def test_newlines(self):
        result = _split_into_sentences("Ligne un\nLigne deux")
        assert result == ["Ligne un", "Ligne deux"]

    def test_empty_string(self):
        assert _split_into_sentences("") == []

    def test_whitespace_only(self):
        assert _split_into_sentences("   \n  ") == []

    def test_single_sentence_no_punctuation(self):
        result = _split_into_sentences("Bonjour Etienne")
        assert result == ["Bonjour Etienne"]


# ── integration tests (real API calls) ──────────────────────────────────────


@skip_no_credentials
class TestUnaryTTS:
    @pytest.fixture()
    def client(self):
        from google.api_core import client_options as client_options_lib
        from google.cloud import texttospeech

        api_key = os.environ["GOOGLE_API_KEY"]
        opts = client_options_lib.ClientOptions(api_key=api_key)
        return texttospeech.TextToSpeechClient(client_options=opts)

    def test_unary_returns_audio_bytes(self, client):
        from google.cloud import texttospeech

        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text="Test"),
            voice=texttospeech.VoiceSelectionParams(
                name="fr-FR-Chirp3-HD-Charon",
                language_code="fr-FR",
            ),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                sample_rate_hertz=24000,
            ),
        )
        assert response.audio_content
        assert len(response.audio_content) > 100


@skip_no_credentials
class TestStreamingTTS:
    @pytest.fixture()
    def client(self):
        from google.api_core import client_options as client_options_lib
        from google.cloud import texttospeech

        api_key = os.environ["GOOGLE_API_KEY"]
        opts = client_options_lib.ClientOptions(api_key=api_key)
        return texttospeech.TextToSpeechClient(client_options=opts)

    def test_streaming_returns_audio_chunks(self, client):
        from google.cloud import texttospeech

        config = texttospeech.StreamingSynthesizeConfig(
            voice=texttospeech.VoiceSelectionParams(
                name="fr-FR-Chirp3-HD-Charon",
                language_code="fr-FR",
            ),
        )

        def request_generator():
            yield texttospeech.StreamingSynthesizeRequest(streaming_config=config)
            yield texttospeech.StreamingSynthesizeRequest(
                input=texttospeech.StreamingSynthesisInput(text="Bonjour, ceci est un test de streaming.")
            )

        audio_chunks = []
        for response in client.streaming_synthesize(request_generator()):
            if response.audio_content:
                audio_chunks.append(response.audio_content)

        assert len(audio_chunks) > 0
        total_bytes = sum(len(c) for c in audio_chunks)
        assert total_bytes > 100
