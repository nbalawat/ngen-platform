"""Model gateway configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "NGEN_GATEWAY_"}

    DEBUG: bool = False
    DEFAULT_MODEL: str = "mock-model"
    DEFAULT_UPSTREAM_URL: str = "http://localhost:9100"
    RATE_LIMIT_RPM: int = 60
    RATE_LIMIT_TPM: int = 100_000

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_API_URL: str = "https://api.anthropic.com"

    # Ollama
    OLLAMA_URL: str = "http://localhost:11434"


settings = Settings()
