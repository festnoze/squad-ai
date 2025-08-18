import re

"""
Text processing utilities for speech synthesis.

This module provides helper functions for processing text before speech synthesis,
including text chunking, duration estimation, and timing calculations.
"""
class ProcessText:
    split_separators = [".", "!", "?", ";", ":"]
    
    @staticmethod
    def chunk_text_by_sentences_size(text: str, max_words_by_sentence: int = 15, max_chars_by_sentence: int = 120) -> list[str]:
        """
        Split text into chunks at every separator found, then further split if chunks exceed limits.
        
        Args:
            text: The text to split
            max_words_by_sentence: Maximum number of words per chunk
            max_chars_by_sentence: Maximum number of characters per chunk
            
        Returns:
            A list of text chunks split at separators and respecting size limits
        """
        if not text:
            return []
        
        # Phase 1: Split at every separator found
        initial_chunks = []
        
        # Create pattern to split at any separator while keeping the separator with the chunk
        separator_pattern = r'([^' + ''.join(ProcessText.split_separators) + r']*[' + ''.join(ProcessText.split_separators) + r'])'
        
        # Find all chunks ending with separators
        matches = re.findall(separator_pattern, text)
        
        # Add all matches as chunks
        for match in matches:
            clean_match = match.strip()
            if clean_match:
                initial_chunks.append(clean_match)
        
        # Handle any remaining text after the last separator
        if matches:
            # Find where the last match ends in the original text
            last_match = matches[-1]
            last_match_end = text.rfind(last_match) + len(last_match)
            remaining_text = text[last_match_end:].strip()
            if remaining_text:
                initial_chunks.append(remaining_text)
        # If no separators found, TODO: rather wait for a separator to be added, unless there to much words or chars.
        elif text.strip():
            initial_chunks.append(text.strip())
        
        # Phase 2: Further split chunks that exceed word or character limits
        final_chunks = []
        
        for chunk in initial_chunks:
            # Check if chunk exceeds limits
            word_count = len(chunk.split())
            char_count = len(chunk)
            
            if word_count <= max_words_by_sentence and char_count <= max_chars_by_sentence:
                # Chunk fits within limits, add as-is
                final_chunks.append(chunk)
            else:
                # Chunk exceeds limits, split it by words
                words = chunk.split()
                current_chunk = ""
                
                for word in words:
                    # Check if adding this word would exceed limits
                    test_chunk = current_chunk + (" " + word if current_chunk else word)
                    test_word_count = len(test_chunk.split())
                    test_char_count = len(test_chunk)
                    
                    if test_word_count <= max_words_by_sentence and test_char_count <= max_chars_by_sentence:
                        # Word fits, add it to current chunk
                        current_chunk = test_chunk
                    else:
                        # Word doesn't fit, save current chunk and start new one
                        if current_chunk:
                            final_chunks.append(current_chunk)
                        current_chunk = word
                
                # Add any remaining chunk
                if current_chunk:
                    final_chunks.append(current_chunk)
        
        return final_chunks

    @staticmethod
    def is_sentence_ending(text: str) -> bool:
        """
        Check if the given text ends with a sentence-ending punctuation.
        
        Args:
            text: The text to check
            
        Returns:
            True if the text ends with a sentence-ending punctuation
        """
        return bool(re.search(r'[.!?](\s*)$', text))

    @staticmethod
    def get_next_chunk_from_text(text: str, max_words: int = 10) -> tuple[str, str]:
        """
        Extract the next chunk from text, prioritizing sentence boundaries.
        
        Args:
            text: The text to extract from
            max_words: Maximum number of words in the chunk
            
        Returns:
            tuple of (chunk, remaining_text)
        """
        if not text:
            return "", ""
            
        # Try to find a sentence ending within a reasonable number of words
        words = text.split()
        
        # If the text is shorter than max_words, return it all
        if len(words) <= max_words:
            return text, ""
            
        # Create a text segment of the first max_words + 5 words to search for sentence endings
        # We add extra words to catch nearby sentence endings
        search_text = " ".join(words[:max_words + 5])
        
        # Find all sentence endings in the search text
        sentence_ends = list(re.finditer(r'[.!?](\s|$)', search_text))
        
        if sentence_ends:
            # Use the last sentence ending that's within or close to max_words
            for end in reversed(sentence_ends):
                end_pos = end.end()
                end_text = search_text[:end_pos]
                end_word_count = len(end_text.split())
                
                # If this ending is within our word limit or close to it
                if end_word_count <= max_words + 2:  # Allow slight overflow
                    chunk = search_text[:end_pos].strip()
                    remaining = text[len(chunk):].strip()
                    return chunk, remaining
        
        # If no suitable sentence ending, just take max_words
        chunk = " ".join(words[:max_words])
        remaining = text[len(chunk):].strip()
        
        return chunk, remaining
