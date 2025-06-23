import pytest
from speech.text_processing import ProcessText

@pytest.mark.parametrize("test_input,max_words,max_chars,expected", [
    # Test case 1: Simple case of sentence splitting
    (
        "This is a test. This is another test! This is a new test ? end",
        15, 100,
        ["This is a test.", "This is another test!", "This is a new test ?", "end"]
    ),
    # Test case 2: Long sentence splitting
    (
        "This sentence has more than ten words and should be split into multiple chunks based on the word limit.",
        4, 100,
        ["This sentence has more", "than ten words and", "should be split into", "multiple chunks based on", "the word limit."]
    ),
    # Test case 3: Character limit splitting
    (
        "Short text. But this one is a bit longer and should be split based on character count if needed.",
        20, 20,
        ["Short text.", "But this one is a", "bit longer and", "should be split", "based on character", "count if needed."]
    ),
    # Test case 4: Empty input
    (
        "",
        10, 100,
        []
    ),
    # Test case 5: Single word exceeding character limit
    (
        "Supercalifragilisticexpialidocious",
        100, 10,
        ["Supercalif", "ragilistic", "expialidoc", "ious"]
    ),
    # Test case 6: Sentence exceeding character limit
    (
        "This one is a very long sentence of more than one hundred characters that should be split into multiple chunks based on the specified character limit.",
        100, 100,
        ["This one is a very long sentence of more than one hundred characters that should be split into", "multiple chunks based on the specified character limit."]
    ),
])
def test_chunk_text_by_sized_sentences(test_input, max_words, max_chars, expected):
    """Test the chunk_text_by_sized_sentences method with various inputs."""
    result = ProcessText.chunk_text_by_sentences_size(
        test_input, 
        max_words_by_sentence=max_words, 
        max_chars_by_sentence=max_chars
    )
    assert result == expected, f"Expected {expected}, got {result}"

def test_estimate_speech_duration():
    """Test the estimate_speech_duration method."""
    # Test with empty text
    assert ProcessText.estimate_speech_duration("") == 0.0
    
    # Test with simple text
    text = "Hello world"
    duration = ProcessText.estimate_speech_duration(text)
    assert duration > 0, "Duration should be greater than zero"
    
    # Test with punctuation
    text_with_punctuation = "Hello, world! How are you today?"
    duration_with_punctuation = ProcessText.estimate_speech_duration(text_with_punctuation)
    assert duration_with_punctuation > duration, "Text with punctuation should have longer duration"

def test_calculate_speech_timing():
    """Test the calculate_speech_timing method."""
    text = "Hello world"
    start_time, end_time = ProcessText.calculate_speech_timing(text)
    
    # Start time should be positive
    assert start_time >= 0
    
    # End time should be greater than start time
    assert end_time > start_time
    
    # Test with previous chunk end time
    prev_end_time = 1000.0  # 1 second
    new_start_time, new_end_time = ProcessText.calculate_speech_timing(text, prev_end_time)
    
    # New start time should be greater than previous end time
    assert new_start_time > prev_end_time
    
    # New end time should be greater than new start time
    assert new_end_time > new_start_time

def test_optimize_speech_timing():
    """Test the optimize_speech_timing method."""
    chunks = ["Hello.", "How are you?", "I'm fine, thank you."]
    result = ProcessText.optimize_speech_timing(chunks)
    
    # Should return the correct number of chunks
    assert len(result) == len(chunks)
    
    # Each result should be a tuple of (text, start_time, end_time)
    for chunk_result in result:
        assert len(chunk_result) == 3
        assert isinstance(chunk_result[0], str)
        assert isinstance(chunk_result[1], float)
        assert isinstance(chunk_result[2], float)
        assert chunk_result[2] > chunk_result[1]  # End time > start time
    
    # Chunks should be in sequence (end time of one is before start time of next)
    for i in range(len(result) - 1):
        assert result[i+1][1] >= result[i][2]

def test_is_sentence_ending():
    """Test the is_sentence_ending method."""
    # Positive cases
    assert ProcessText.is_sentence_ending("This is a test.") == True
    assert ProcessText.is_sentence_ending("Hello!") == True
    assert ProcessText.is_sentence_ending("Are you there?") == True
    assert ProcessText.is_sentence_ending("Hello.  ") == True  # With trailing spaces
    
    # Negative cases
    assert ProcessText.is_sentence_ending("Hello,") == False
    assert ProcessText.is_sentence_ending("This is a test") == False
    assert ProcessText.is_sentence_ending("") == False

def test_get_next_chunk_from_text():
    """Test the get_next_chunk_from_text method."""
    # Test with short text
    text = "This is a short text."
    chunk, remaining = ProcessText.get_next_chunk_from_text(text, max_words=10)
    assert chunk == text
    assert remaining == ""
    
    # Test with long text
    long_text = "This is a longer text that should be split into multiple chunks. This is the second sentence."
    chunk, remaining = ProcessText.get_next_chunk_from_text(long_text, max_words=5)
    assert "This is a longer text" in chunk
    assert "second sentence" in remaining
    
    # Test with empty text
    chunk, remaining = ProcessText.get_next_chunk_from_text("", max_words=10)
    assert chunk == ""
    assert remaining == ""

# Pure pytest style - no unittest main needed