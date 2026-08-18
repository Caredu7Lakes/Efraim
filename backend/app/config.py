"""Configuracao via pydantic-settings (.env)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # dev usa sqlite; producao aponta para Postgres (docker-compose)
    database_url: str = "sqlite:///./efraim_dev.db"

    # "fake" (default, sem rede) ou "brightdata"
    efraim_fonte: str = "fake"
    brightdata_api_key: str | None = None

    whatsapp_access_token: str | None = None
    whatsapp_phone_number_id: str | None = None

    concorrencia: int = 5
    timeout_fonte_s: float = 20.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
