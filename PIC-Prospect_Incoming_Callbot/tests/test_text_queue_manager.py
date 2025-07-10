import pytest
from app.speech.text_queue_manager import TextQueueManager

# Define the fixture at the module level
@pytest.fixture
def text_queue_manager() -> TextQueueManager:
    """Fixture to create a TextQueueManager for each test"""
    return TextQueueManager()


@pytest.mark.parametrize("texts_to_add", [
    ["This is a test message.", "Another part.", "And a third part."],
    ["Hello world!", "This is another test.", "With three parts."],
    ["A short text.", "With some punctuation,", "commas, and a period."],
    ["A longer sentence that exceeds the word limit", "is to be sent in multiple chunks.", "It's the third chunk."]
])
async def test_enqueue_text(text_queue_manager : TextQueueManager, texts_to_add : list[str]):
    """Test enqueueing multiple text chunks to the queue"""
    # Reset the queue for each test case
    await text_queue_manager.clear_queue()
    text_queue_manager.total_enqueued_chars = 0
    
    # Track expected values
    total_expected_length = 0
    expected_combined_text = ""
    
    # Process each text chunk in the list
    for text in texts_to_add:
        # Measure the length of this chunk
        chunk_length = len(text)
        total_expected_length += chunk_length
        expected_combined_text += ' ' + text
        
        # Enqueue the text chunk
        result = await text_queue_manager.enqueue_text(text)
        
        # Verify the chunk was correctly enqueued
        assert result, f"Enqueue should return True for valid text: '{text}'"
        
    # Verify the final state after all chunks are added
    assert text_queue_manager.text_queue == expected_combined_text.strip(), \
        f"Queue content mismatch for dataset with texts: {texts_to_add}"
    assert text_queue_manager.total_enqueued_chars == total_expected_length + len(texts_to_add) - 1, \
        f"Character count mismatch for dataset with texts: {texts_to_add}"
    

async def test_enqueue_empty_text(text_queue_manager : TextQueueManager):
    """Test that enqueueing empty text returns False"""
    result = await text_queue_manager.enqueue_text("")
    assert result is False, "Enqueue should return False for empty text"


async def test_get_text_chunk_sentence_end(text_queue_manager : TextQueueManager):
    """Test getting a text chunk that ends with a sentence"""
    # Enqueue text with a sentence end
    await text_queue_manager.enqueue_text("This is a short sentence. This is another sentence.")
    
    # Get a chunk - should return the first sentence
    chunk = await text_queue_manager.get_next_text_chunk(max_words_by_sentence=8, max_chars_by_sentence=100)
    assert chunk == "This is a short sentence."
    
    # Queue should now only contain the second sentence
    assert text_queue_manager.text_queue == "This is another sentence."
    
    chunk = await text_queue_manager.get_next_text_chunk(max_words_by_sentence=8, max_chars_by_sentence=100)
    assert chunk == "This is another sentence."


async def test_get_text_chunk_word_limit(text_queue_manager : TextQueueManager):
    """Test getting a text chunk based on word limit"""
    # Enqueue text with more than 10 words but no sentence end
    await text_queue_manager.enqueue_text("One two three four five six seven eight nine ten eleven twelve thirteen")
    
    # Get a chunk - should return the first 10 words
    chunk = await text_queue_manager.get_next_text_chunk(max_words_by_sentence=10, max_chars_by_sentence=100)
    assert chunk == "One two three four five six seven eight nine ten"
    
    # Queue should now only contain the remaining words
    assert text_queue_manager.text_queue == "eleven twelve thirteen"


async def test_get_text_chunk_empty_queue(text_queue_manager : TextQueueManager):
    """Test getting a chunk from an empty queue"""
    chunk = await text_queue_manager.get_next_text_chunk()
    assert chunk == None


async def test_is_empty(text_queue_manager : TextQueueManager):
    """Test is_empty method"""
    assert text_queue_manager.is_empty() is True, "Queue should be empty initially"
    
    await text_queue_manager.enqueue_text("Some text")
    assert text_queue_manager.is_empty() is False, "Queue should not be empty after enqueuing"
    
    await text_queue_manager.get_next_text_chunk()
    assert text_queue_manager.is_empty() is True, "Queue should be empty after getting all text"


async def test_clear_queue(text_queue_manager : TextQueueManager):
    """Test clearing the queue"""
    await text_queue_manager.enqueue_text("Text to be cleared")
    await text_queue_manager.clear_queue()
    assert text_queue_manager.text_queue == ""
    assert text_queue_manager.is_empty() is True
