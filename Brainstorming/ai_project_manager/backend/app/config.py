"""Application settings loaded from environment / .env file.

Uses pydantic-settings to read the .env file at the backend root and expose
a cached `get_settings()` accessor used across the app.
"""

import json
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default LLM configuration used if the env var is missing or malformed.
_DEFAULT_LLM_INFO: dict[str, Any] = {
    "type": "OpenAI",
    "model": "gpt-5.4-mini",
    "temperature": 0.0,
    "timeout": 120,
}


class Settings(BaseSettings):
    """Typed application settings.

    Attributes:
        database_url: SQLAlchemy async URL (default: local SQLite file).
        openai_api_key: API key for the LLM provider (OpenAI by default).
            Picked up automatically by common-tools' LlmFactory.
        llm_info: JSON describing the LLM to instantiate via the common-tools
            LlmFactory (keys: type, model, temperature, timeout).
        commontools_local_path: Absolute path to the local `ai-commun-tools`
            checkout installed in editable mode via `pyproject.toml`.
        cors_origins: List of allowed origins for CORS middleware.
        app_name: Human-readable app name.
    """

    database_url: str = "sqlite+aiosqlite:///./ai_pm.db"
    openai_api_key: str | None = None
    llm_info: dict[str, Any] = Field(default_factory=lambda: dict(_DEFAULT_LLM_INFO))
    commontools_local_path: str | None = None
    cors_origins: list[str] = ["http://localhost:5173"]
    app_name: str = "AI Project Manager"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("llm_info", mode="before")
    @classmethod
    def _parse_llm_info(cls, raw: Any) -> Any:
        """Accept both a dict (already parsed) and a JSON string from .env."""
        if raw is None or raw == "":
            return dict(_DEFAULT_LLM_INFO)
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return dict(_DEFAULT_LLM_INFO)
        return dict(_DEFAULT_LLM_INFO)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton)."""
    return Settings()
