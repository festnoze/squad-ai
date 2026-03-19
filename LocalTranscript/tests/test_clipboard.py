"""Tests for clipboard manager."""

import pytest
from src.output.clipboard_manager import ClipboardManager


def test_clipboard_manager_init():
    """Test clipboard manager initialization."""
    cm = ClipboardManager()
    assert cm.backend in ["win32", "pyperclip", "none"]


def test_copy_empty_text():
    """Test copying empty text."""
    cm = ClipboardManager()
    result = cm.copy("")
    assert result is False


def test_copy_and_paste():
    """Test copy and paste operations."""
    cm = ClipboardManager()

    if cm.backend == "none":
        pytest.skip("No clipboard backend available")

    test_text = "Test clipboard content"

    # Copy
    result = cm.copy(test_text)
    assert result is True

    # Paste
    pasted = cm.paste()
    assert pasted == test_text


def test_copy_unicode():
    """Test copying unicode text."""
    cm = ClipboardManager()

    if cm.backend == "none":
        pytest.skip("No clipboard backend available")

    test_text = "Français: àéèêëïôù 中文 العربية"

    result = cm.copy(test_text)
    assert result is True

    pasted = cm.paste()
    assert pasted == test_text
