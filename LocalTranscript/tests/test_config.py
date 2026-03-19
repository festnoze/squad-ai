"""Tests for configuration management."""

import json
import tempfile
from pathlib import Path
from src.utils.config import ConfigManager, AppConfig


def test_config_creation():
    """Test configuration creation."""
    config = AppConfig.from_dict({})

    assert config.vibe is not None
    assert config.output is not None
    assert config.whisper is not None
    assert config.hotkeys is not None


def test_config_to_dict():
    """Test configuration serialization."""
    config = AppConfig.from_dict({})
    config_dict = config.to_dict()

    assert "vibe" in config_dict
    assert "output" in config_dict
    assert "whisper" in config_dict
    assert "hotkeys" in config_dict


def test_config_manager_save_load():
    """Test saving and loading configuration."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name

    try:
        # Create and save
        manager = ConfigManager(temp_path)
        manager.config.whisper.model_size = "medium"
        manager.save()

        # Load in new manager
        manager2 = ConfigManager(temp_path)
        assert manager2.config.whisper.model_size == "medium"

    finally:
        Path(temp_path).unlink(missing_ok=True)
