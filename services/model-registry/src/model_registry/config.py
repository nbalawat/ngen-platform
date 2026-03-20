from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "NGEN Model Registry"
    DEBUG: bool = False

    model_config = {"env_prefix": "NGEN_"}


settings = Settings()
