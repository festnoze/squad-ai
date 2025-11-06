"""Text cleaning utilities for database operations.

This module provides utilities to clean text content before database insertion,
particularly for PostgreSQL which has strict UTF-8 encoding requirements.
"""

import re
from typing import Any


class TextCleaner:
    """Utility class for cleaning text content before database operations."""

    @staticmethod
    def clean_for_postgres(text: str | None) -> str:
        """Remove null bytes and problematic control characters for PostgreSQL.

        PostgreSQL's UTF-8 encoding does not support null bytes (0x00) and can have
        issues with certain control characters. This function removes them to prevent
        CharacterNotInRepertoireError and similar encoding errors.

        Args:
            text: String content that may contain problematic characters (can be None)

        Returns:
            Cleaned string safe for PostgreSQL insertion, or empty string if input is None

        Examples:
            >>> TextCleaner.clean_for_postgres("Hello\\x00World")
            'HelloWorld'

            >>> TextCleaner.clean_for_postgres("Normal text")
            'Normal text'

            >>> TextCleaner.clean_for_postgres(None)
            ''
        """
        if not text:
            return ""

        # Remove null bytes (0x00) - PRIMARY CAUSE of CharacterNotInRepertoireError
        text = text.replace("\x00", "")

        # Remove other problematic control characters (0x01-0x1F) except common whitespace
        # Keep: \n (0x0A), \r (0x0D), \t (0x09)
        # Remove: All other control characters that can cause encoding issues
        text = re.sub(r"[\x01-\x08\x0B\x0C\x0E-\x1F]", "", text)

        return text

    @staticmethod
    def clean_dict_strings(data: dict[Any, Any]) -> dict[Any, Any]:
        """Recursively clean all string values in a dictionary.

        Useful for cleaning JSON/dict data structures before database insertion.

        Args:
            data: Dictionary that may contain string values with problematic characters

        Returns:
            Dictionary with all string values cleaned

        Examples:
            >>> TextCleaner.clean_dict_strings({"key": "value\\x00"})
            {'key': 'value'}

            >>> TextCleaner.clean_dict_strings({"nested": {"key": "val\\x00ue"}})
            {'nested': {'key': 'value'}}
        """
        if not isinstance(data, dict):
            return data

        cleaned: dict[Any, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                cleaned[key] = TextCleaner.clean_for_postgres(value)
            elif isinstance(value, dict):
                cleaned[key] = TextCleaner.clean_dict_strings(value)
            elif isinstance(value, list):
                cleaned[key] = [TextCleaner.clean_dict_strings(item) if isinstance(item, dict) else TextCleaner.clean_for_postgres(item) if isinstance(item, str) else item for item in value]
            else:
                cleaned[key] = value

        return cleaned
