"""Configuration settings for the API."""

from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""
    
    # API Settings
    API_V1_STR: str = "/api"
    PROJECT_NAME: str = "Turtle Trading Bot API"
    
    # CORS Settings
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3001",  # Frontend
        "http://localhost:8000"   # API (self)
    ]
    
    # Database Settings
    DATABASE_URL: str = "sqlite:///./turtle_trading.db"
    
    # Trading Settings
    DEFAULT_PORTFOLIO_BALANCE: float = 100000.0
    DEFAULT_PORTFOLIO_CURRENCY: str = "USD"
    
    # Data Download Settings
    BINANCE_API_BASE_URL: str = "https://api.binance.com"
    ALPHA_VANTAGE_API_KEY: str = ""  # Set via environment variable
    
    # File Storage
    CHART_DATA_DIR: str = "./data/charts"
    STRATEGY_DATA_DIR: str = "./data/strategies"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()