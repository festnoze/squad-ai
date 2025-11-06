"""Prompt Helper

This module provides a helper class for loading and caching prompt files.
"""

from common_tools.helpers.file_helper import file  # type: ignore[import-untyped]


class PromptHelper:
    """Helper class for loading and caching prompt files.

    This class provides a centralized way to load prompt files from the filesystem
    with automatic caching to avoid repeated file I/O operations.

    All prompt files are expected to be in the 'prompts/' directory.
    """

    # Class-level cache to store loaded prompts (shared across all instances)
    _prompt_cache: dict[str, str] = {}

    # Base directory for all prompt files
    PROMPTS_DIR = "prompts"

    @classmethod
    def aget_prompt(cls, prompt_filename: str, remove_comments: bool = True) -> str:
        """Load a prompt from file with caching.

        Args:
            prompt_filename: Filename of the prompt (e.g., "query_course_content_prompt.txt")
                            The 'prompts/' prefix is automatically added.
            remove_comments: Whether to remove comments from the prompt file (default: True)

        Returns:
            The prompt content as a string

        Note:
            This is a synchronous method despite the 'a' prefix. The prefix is kept
            for consistency with the project's async naming convention, but prompt
            loading is intentionally synchronous as it's a fast I/O operation.

        Example:
            >>> prompt = PromptHelper.aget_prompt("summarize_content_full_prompt.txt")
            # Loads from "prompts/summarize_content_full_prompt.txt"
        """
        # Construct full path with prompts directory prefix
        full_path = f"{cls.PROMPTS_DIR}/{prompt_filename}"

        # Create cache key based on file path and remove_comments flag
        cache_key = f"{full_path}:{remove_comments}"

        # Check if prompt is already cached
        if cache_key in cls._prompt_cache:
            return cls._prompt_cache[cache_key]

        # Load the prompt from file
        prompt_content: str = file.get_as_str(full_path, remove_comments=remove_comments) or ""

        # Cache the loaded prompt
        cls._prompt_cache[cache_key] = prompt_content

        return prompt_content

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the prompt cache.

        This method is useful for testing or when prompts need to be reloaded
        (e.g., after updating prompt files during development).
        """
        cls._prompt_cache.clear()

    @classmethod
    def get_cache_stats(cls) -> dict[str, int]:
        """Get statistics about the prompt cache.

        Returns:
            Dictionary with cache statistics:
                - cached_prompts: Number of prompts currently cached
        """
        return {"cached_prompts": len(cls._prompt_cache)}
