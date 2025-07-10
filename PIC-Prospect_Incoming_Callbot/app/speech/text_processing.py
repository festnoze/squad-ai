import re

"""
Text processing utilities for speech synthesis.

This module provides helper functions for processing text before speech synthesis,
including text chunking, duration estimation, and timing calculations.
"""
class ProcessText:
    @staticmethod
    def chunk_text_by_sentences_size(text: str, max_words_by_sentence: int = 10, max_chars_by_sentence: int = 100) -> list[str]:
        """
        Split text into chunks at natural sentence boundaries.
        
        Args:
            text: The text to split
            max_words_by_sentence: Maximum number of words per chunk
            max_chars_by_sentence: Maximum number of characters per chunk
            
        Returns:
            A list of text chunks
        """
        if not text:
            return []
        
        # Phase 1: Extract individual sentences
        sentences = []
        
        # Find all sentences ending with punctuation
        # This pattern keeps the sentence-ending punctuation with the sentence
        pattern = r'[^.!?]+[.!?]'
        matches = re.findall(pattern, text)
        
        # Process matches to get clean sentences
        for match in matches:
            # Remove leading/trailing whitespace
            clean_match = match.strip()
            if clean_match:  # Only add non-empty matches
                sentences.append(clean_match)
        
        # Check if there's any text left after the last punctuation
        if matches:
            last_match = matches[-1]
            last_match_end = text.rfind(last_match) + len(last_match)
            remaining_text = text[last_match_end:].strip()
            if remaining_text:
                sentences.append(remaining_text)
        # If no matches were found but there's text, treat the whole text as one sentence
        elif text.strip():
            sentences.append(text.strip())
        
        # Phase 2: Process sentences into appropriately sized chunks
        chunks = []

        for sentence in sentences:
            # If the sentence itself is too long, split it
            if len(sentence.split()) > max_words_by_sentence or len(sentence) > max_chars_by_sentence:
                words = sentence.split()
                current_word_chunk = ""
                for word in words:
                    # If a single word exceeds max_chars, split the word itself
                    if len(word) > max_chars_by_sentence:
                        if current_word_chunk: # Add any preceding part of the word chunk
                            chunks.append(current_word_chunk.strip())
                            current_word_chunk = ""
                        # Split the long word into character chunks
                        for i in range(0, len(word), max_chars_by_sentence):
                            char_chunk = word[i:i+max_chars_by_sentence]
                            chunks.append(char_chunk)
                    # Check if adding this word would exceed limits for the current_word_chunk
                    elif current_word_chunk and \
                         (len(current_word_chunk.split()) + 1 > max_words_by_sentence or \
                          len(current_word_chunk) + len(word) + 1 > max_chars_by_sentence):
                        chunks.append(current_word_chunk.strip())
                        current_word_chunk = word
                    else:
                        current_word_chunk += " " + word if current_word_chunk else word
            
                # Add any remaining part of the sentence after word splitting
                if current_word_chunk:
                    # Preserve original sentence punctuation if it was split
                    if re.search(r'[.!?]$', sentence) and not re.search(r'[.!?]$', current_word_chunk):
                        punctuation = re.search(r'[.!?]$', sentence).group(0)
                        current_word_chunk = current_word_chunk.rstrip() + punctuation
                    chunks.append(current_word_chunk.strip())
            else:
                # Sentence fits within limits, add it as its own chunk
                chunks.append(sentence.strip())
        
        return chunks

    @staticmethod
    def estimate_speech_duration(text: str, chars_per_second: float = 15.0) -> float:
        """
        Estimate the duration of speech in milliseconds based on text length.
        
        Args:
            text: The text to estimate
            chars_per_second: Average characters spoken per second
            
        Returns:
            Estimated duration in milliseconds
        """
        if not text:
            return 0.0
            
        # Basic estimation based on character count
        # This is a simple heuristic that can be improved with more sophisticated models
        char_count = len(text)
        
        # Adjust for punctuation (pauses)
        pause_chars = len(re.findall(r'[.!?,;:]', text))
        effective_chars = char_count + (pause_chars * 5)  # Each punctuation adds ~5 char worth of time
        
        # Calculate duration in milliseconds
        duration_ms = (effective_chars / chars_per_second) * 1000
        
        # Enforce minimum duration
        return max(duration_ms, 50.0)  # At least 50ms

    @staticmethod
    def calculate_speech_timing(
        text_chunk: str, 
        previous_chunk_end_time: float = 0.0,
        min_gap: float = 0.05
    ) -> tuple[float, float]:
        """
        Calculate the start and end times for a speech chunk.
        
        Args:
            text_chunk: The text chunk to calculate timing for
            previous_chunk_end_time: When the previous chunk ends (milliseconds)
            min_gap: Minimum gap between chunks (seconds)
            
        Returns:
            tuple of (start_time_ms, end_time_ms)
        """
        # Start time is the previous end time plus the minimum gap
        start_time_ms = previous_chunk_end_time + (min_gap * 1000)
        
        # Calculate the duration
        duration_ms = ProcessText.estimate_speech_duration(text_chunk)
        
        # End time is the start time plus the duration
        end_time_ms = start_time_ms + duration_ms
        
        return start_time_ms, end_time_ms

    @staticmethod
    def optimize_speech_timing(chunks: list[str]) -> list[tuple[str, float, float]]:
        """
        Optimize timing for a series of speech chunks for natural-sounding speech.
        
        Args:
            chunks: list of text chunks to optimize timing for
            
        Returns:
            list of tuples (chunk_text, start_time_ms, end_time_ms)
        """
        result = []
        last_end_time = 0.0
        
        for i, chunk in enumerate(chunks):
            # Calculate minimum gap based on punctuation
            min_gap = 0.05  # Default minimum gap
            
            # If previous chunk ended with sentence-ending punctuation, add extra pause
            if i > 0 and ProcessText.is_sentence_ending(chunks[i-1]):
                min_gap = 0.3  # Longer pause after sentence endings
            # If previous chunk ended with comma, add medium pause
            elif i > 0 and chunks[i-1].strip().endswith(','):
                min_gap = 0.15  # Medium pause after commas
                
            # Calculate timing
            start_time, end_time = ProcessText.calculate_speech_timing(chunk, last_end_time, min_gap)
            result.append((chunk, start_time, end_time))
            last_end_time = end_time
        
        return result

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
