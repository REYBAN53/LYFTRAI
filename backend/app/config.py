"""Application configuration, loaded exclusively from environment variables."""

from __future__ import annotations

from functools import cached_property
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful, accurate and concise assistant. "
    "Use Markdown formatting when it improves readability."
)


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore")

    # --- Required by the assignment -------------------------------------------------
    llm_api_keys: str = Field(default="", description="Comma-separated key pool; ids are key_1, key_2, ...")
    database_url: str = "sqlite:///./data/app.db"
    allowed_origins: str = "http://localhost:3000"
    enable_failure_simulation: bool = False

    # --- LLM -----------------------------------------------------------------------
    llm_model: str = "gemini/gemini-flash-lite-latest"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_tokens: int = Field(default=1024, gt=0)
    default_system_prompt: str = DEFAULT_SYSTEM_PROMPT

    # --- LiteLLM response cache -----------------------------------------------------
    llm_cache_ttl_seconds: int = Field(default=86_400, gt=0)

    # --- Misc -----------------------------------------------------------------------
    log_level: str = "INFO"

    @cached_property
    def api_keys(self) -> list[str]:
        return _split_csv(self.llm_api_keys)

    @cached_property
    def cors_origins(self) -> list[str]:
        return _split_csv(self.allowed_origins)
