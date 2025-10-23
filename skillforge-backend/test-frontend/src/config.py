"""Configuration module for SkillForge Frontend.

Loads and validates environment variables from .env file.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    # Backend API Configuration
    SKILLFORGE_API_URL: str = os.getenv("SKILLFORGE_API_URL", "http://localhost:8372")
    SKILLFORGE_JWT_TOKEN: str = os.getenv("SKILLFORGE_JWT_TOKEN", "")

    # Frontend Configuration
    OUTPUTS_DIR: Path = Path(os.getenv("OUTPUTS_DIR", "outputs/"))
    STREAMLIT_SERVER_PORT: int = int(os.getenv("STREAMLIT_SERVER_PORT", "8577"))
    STREAMLIT_SERVER_ADDRESS: str = os.getenv("STREAMLIT_SERVER_ADDRESS", "localhost")

    # Optional Configuration
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    @classmethod
    def validate(cls) -> None:
        """Validate that required configuration is present."""
        if not cls.SKILLFORGE_JWT_TOKEN:
            msg = "SKILLFORGE_JWT_TOKEN environment variable is required"
            raise ValueError(msg)

        if not cls.SKILLFORGE_API_URL:
            msg = "SKILLFORGE_API_URL environment variable is required"
            raise ValueError(msg)

        if cls.DEBUG:
            print(f"[DEBUG] API URL: {cls.SKILLFORGE_API_URL}")
            print(f"[DEBUG] Outputs directory: {cls.OUTPUTS_DIR}")


# Validate configuration on import (but skip if JWT token not set for initial setup)
if Config.SKILLFORGE_JWT_TOKEN:
    Config.validate()
