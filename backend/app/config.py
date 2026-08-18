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

    # Teto de chamadas MCP por job (custo). Deliberadamente generoso: o produto
    # prioriza completude/qualidade do resultado sobre economia agressiva -
    # isto e' um failsafe contra loop/bug, nao uma alavanca de reduzir gasto no
    # caso normal. Calibrar com dados reais de `session_stats` quando o adapter
    # Bright Data estiver medindo custo de verdade (ver ARQUITETURA.md secao 11).
    max_chamadas_mcp_por_job: int = 120
    max_tentativas_rate_limit: int = 2
    backoff_rate_limit_s: float = 5.0

    # TTL do cache de consulta normalizada. Curto de proposito: preco
    # desatualizado e' um problema de qualidade/confianca pra um produto que
    # recomenda "mais barato", entao o padrao favorece frescor sobre economia
    # de chamada MCP (ver app/persistence/cache.py).
    cache_ttl_s: int = 900

    # Fila de jobs (Celery). Eager=True roda a task no mesmo processo sem
    # precisar de broker real - e' o padrao em dev/teste. Em producao,
    # CELERY_TASK_EAGER=false + broker/backend Redis reais permitem escalar
    # workers horizontalmente sem tocar na API (ver app/jobs/celery_app.py).
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_task_eager: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
