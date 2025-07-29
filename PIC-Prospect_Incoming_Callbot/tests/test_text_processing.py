import pytest
from app.speech.text_processing import ProcessText

@pytest.mark.parametrize("test_input,max_words,max_chars,expected", [
    # Test case 1: Simple case of sentence splitting within limits
    (
        "This is a test. This is another test! This is a new test ? end",
        15, 120,
        ["This is a test.", "This is another test!", "This is a new test ?", "end"]
    ),
    # Test case 2: Sentence that exceeds word limit gets further split
    (
        "This is a very long sentence with many words that exceeds the word limit.",
        5, 120,
        ["This is a very long", "sentence with many words that", "exceeds the word limit."]
    ),
    # Test case 3: Sentence that exceeds character limit gets further split
    (
        "This sentence is short. But this one is much longer and exceeds character set limits.",
        20, 30,
        ["This sentence is short.", "But this one is much longer", "and exceeds character set", "limits."]
    ),
    # Test case 4: Empty input
    (
        "",
        10, 100,
        []
    ),
    # Test case 5: Mixed separators within limits
    (
        "Hello world. How are you? I am fine! Thanks: you; welcome",
        15, 120,
        ["Hello world.", "How are you?", "I am fine!", "Thanks:", "you;", "welcome"]
    ),
    # Test case 6: Single sentence with no separators within limits
    (
        "This is a single sentence with no separators",
        15, 120,
        ["This is a single sentence with no separators"]
    ),
    # Test case 7: Single sentence with no separators exceeding word limit
    (
        "This is a single sentence with no separators that has many words exceeding the limit",
        8, 120,
        ["This is a single sentence with no separators", "that has many words exceeding the limit"]
    ),
])
def test_chunk_text_by_sized_sentences(test_input, max_words, max_chars, expected):
    """Test the chunk_text_by_sentences_size method with simplified splitting behavior."""
    result = ProcessText.chunk_text_by_sentences_size(
        test_input, 
        max_words_by_sentence=max_words, 
        max_chars_by_sentence=max_chars
    )
    assert result == expected, f"Expected {expected}, got {result}"

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