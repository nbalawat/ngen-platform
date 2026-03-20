"""Configuration for the Workflow Engine service."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Workflow Engine settings loaded from environment variables."""

    HOST: str = "0.0.0.0"
    PORT: int = 8003
    LOG_LEVEL: str = "INFO"
    MAX_CONCURRENT_RUNS: int = 50
    DEFAULT_AGENT_TIMEOUT: int = 300
    HUMAN_APPROVAL_TIMEOUT: int = 3600
    MODEL_GATEWAY_URL: str = "http://model-gateway:8001"

    model_config = SettingsConfigDict(env_prefix="WF_")
