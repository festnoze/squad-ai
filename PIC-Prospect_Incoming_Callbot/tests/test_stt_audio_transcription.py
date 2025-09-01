import pytest
import os
from app.speech.speech_to_text import GoogleSTTProvider, OpenAISTTProvider, HybridSTTProvider


class TestSTTAudioTranscription:
    """Test speech-to-text transcription with audio files"""
    
    @pytest.fixture
    def audio_file_path(self):
        """Path to the test audio file"""
        return "tests/audio/asserts/oui-low-noise.wav"
    
    @pytest.fixture
    def expected_text(self):
        """Expected transcription text"""
        return "oui"
    
    @pytest.mark.asyncio
    async def test_google_stt_transcription(self, audio_file_path, expected_text):
        """Test Google STT provider with audio file"""
        # Verify audio file exists
        assert os.path.exists(audio_file_path), f"Audio file not found: {audio_file_path}"
        
        try:
            # Initialize Google STT provider with test directory
            test_dir = "tests/audio/asserts"
            provider = GoogleSTTProvider(language_code="fr-FR", frame_rate=8000, temp_dir=test_dir)
            
            # Extract filename from path
            audio_filename = os.path.basename(audio_file_path)
            
            # Transcribe audio
            result = await provider.transcribe_audio_async(audio_filename)
            
            # Assert the result contains expected text
            assert result.lower().strip() == expected_text.lower(), f"Expected '{expected_text}', got '{result}'"
        except Exception as e:
            if "DefaultCredentialsError" in str(e) or "credentials" in str(e).lower():
                pytest.skip(f"Google Cloud credentials not available: {e}")
            else:
                raise
    
    @pytest.mark.asyncio
    async def test_openai_stt_transcription(self, audio_file_path, expected_text):
        """Test OpenAI STT provider with audio file"""
        # Verify audio file exists
        assert os.path.exists(audio_file_path), f"Audio file not found: {audio_file_path}"
        
        try:
            # Initialize OpenAI STT provider with test directory
            test_dir = "tests/audio/asserts"
            provider = OpenAISTTProvider(language_code="fr-FR", frame_rate=8000, temp_dir=test_dir)
            
            # Extract filename from path
            audio_filename = os.path.basename(audio_file_path)
            
            # Transcribe audio
            result = await provider.transcribe_audio_async(audio_filename)
            
            # Assert the result contains expected text
            assert expected_text in result.lower().strip(), f"Expected '{expected_text}', got '{result}'"
        except Exception as e:
            if "api key" in str(e).lower() or "openai" in str(e).lower():
                pytest.skip(f"OpenAI API key not available: {e}")
            else:
                raise
    
    @pytest.mark.asyncio
    async def test_hybrid_stt_transcription(self, audio_file_path, expected_text):
        """Test Hybrid STT provider with audio file"""
        # Verify audio file exists
        assert os.path.exists(audio_file_path), f"Audio file not found: {audio_file_path}"
        
        try:
            # Initialize Hybrid STT provider with test directory
            test_dir = "tests/audio/asserts"
            provider = HybridSTTProvider(language_code="fr-FR", frame_rate=8000, temp_dir=test_dir)
            
            # Extract filename from path
            audio_filename = os.path.basename(audio_file_path)
            
            # Transcribe audio
            result = await provider.transcribe_audio_async(audio_filename)
            
            # Assert the result contains expected text
            assert result.lower().strip() == expected_text.lower(), f"Expected '{expected_text}', got '{result}'"
        except Exception as e:
            if "DefaultCredentialsError" in str(e) or "credentials" in str(e).lower() or "api key" in str(e).lower():
                pytest.skip(f"Required credentials not available for hybrid STT: {e}")
            else:
                raise