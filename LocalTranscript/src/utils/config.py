"""Configuration management for LocalTranscript."""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class VibeConfig:
    """Vibe-related configuration."""
    executable_path: str = r"C:\Users\e.millerioux\AppData\Local\vibe\vibe.exe"
    watch_folder: str = ""
    output_formats: list = None

    def __post_init__(self):
        if self.output_formats is None:
            self.output_formats = ["txt", "srt", "vtt"]


@dataclass
class OutputConfig:
    """Output-related configuration."""
    auto_clipboard: bool = True
    auto_inject: bool = False
    notification_enabled: bool = True
    notification_sound: bool = True


@dataclass
class WhisperConfig:
    """Whisper model configuration."""
    model_size: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str = "fr"


@dataclass
class HotkeyConfig:
    """Hotkey configuration."""
    enabled: bool = False
    start_transcription: str = "ctrl+shift+t"
    copy_last: str = "ctrl+shift+c"
    inject_last: str = "ctrl+shift+v"


@dataclass
class AppConfig:
    """Complete application configuration."""
    vibe: VibeConfig
    output: OutputConfig
    whisper: WhisperConfig
    hotkeys: HotkeyConfig

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        """Create config from dictionary."""
        return cls(
            vibe=VibeConfig(**data.get('vibe', {})),
            output=OutputConfig(**data.get('output', {})),
            whisper=WhisperConfig(**data.get('whisper', {})),
            hotkeys=HotkeyConfig(**data.get('hotkeys', {}))
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            'vibe': asdict(self.vibe),
            'output': asdict(self.output),
            'whisper': asdict(self.whisper),
            'hotkeys': asdict(self.hotkeys)
        }


class ConfigManager:
    """Manages application configuration."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize config manager.

        Args:
            config_path: Path to config file (default: config/settings.json)
        """
        if config_path is None:
            # Default to config/settings.json in project root
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "settings.json"

        self.config_path = Path(config_path)
        self.config: Optional[AppConfig] = None
        self.load()

    def load(self) -> AppConfig:
        """
        Load configuration from file.

        Returns:
            Loaded configuration

        Raises:
            FileNotFoundError: If config file doesn't exist
        """
        if not self.config_path.exists():
            logger.warning(f"Config file not found: {self.config_path}")
            logger.info("Creating default configuration")
            self.config = self._create_default_config()
            self.save()
            return self.config

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.config = AppConfig.from_dict(data)
            logger.info(f"Configuration loaded from: {self.config_path}")
            return self.config

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise

    def save(self):
        """Save configuration to file."""
        if self.config is None:
            logger.warning("No configuration to save")
            return

        try:
            # Ensure config directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Save to file
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config.to_dict(), f, indent=2, ensure_ascii=False)

            logger.info(f"Configuration saved to: {self.config_path}")

        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            raise

    def _create_default_config(self) -> AppConfig:
        """Create default configuration."""
        return AppConfig(
            vibe=VibeConfig(),
            output=OutputConfig(),
            whisper=WhisperConfig(),
            hotkeys=HotkeyConfig()
        )

    def get(self) -> AppConfig:
        """Get current configuration."""
        if self.config is None:
            self.load()
        return self.config

    def update(self, **kwargs):
        """
        Update configuration values.

        Args:
            **kwargs: Configuration values to update
        """
        if self.config is None:
            self.load()

        # Update fields
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
            else:
                logger.warning(f"Unknown config field: {key}")

        self.save()


# Global config manager instance
_config_manager = None


def get_config() -> AppConfig:
    """Get global configuration."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager.get()


def save_config():
    """Save global configuration."""
    global _config_manager
    if _config_manager is not None:
        _config_manager.save()
