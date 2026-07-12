from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DSPYER_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Langfuse credentials are read by the langfuse SDK itself from
    # LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST.
    default_task_model: str = "openai/gpt-4o-mini"
    optimizer_model: str = "openai/gpt-4o"
    judge_model: str = "openai/gpt-4o-mini"
    max_concurrency: int = 8
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
