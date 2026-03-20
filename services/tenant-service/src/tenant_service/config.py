from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = (
        "postgresql+asyncpg://ngen:ngen_dev_password@localhost:5432/ngen"
    )
    APP_NAME: str = "NGEN Tenant Service"
    DEBUG: bool = False

    model_config = {"env_prefix": "NGEN_"}


settings = Settings()
