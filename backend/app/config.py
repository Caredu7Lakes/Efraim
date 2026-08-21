"""Configuracao via pydantic-settings (.env)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # dev usa sqlite; producao aponta para Postgres (docker-compose)
    database_url: str = "sqlite:///./efraim_dev.db"

    # "fake" (default, sem rede), "apify" ou "brightdata"
    efraim_fonte: str = "fake"
    brightdata_api_key: str | None = None
    # Web Unlocker REST (`POST https://api.brightdata.com/request`) - usado
    # pelo Bloco B (regional) desde 20/08: o actor Apify de Google Maps
    # (`compass/crawler-google-places`) bateu 402 Payment Required em teste
    # real, decisao explicita do usuario foi migrar Bloco B pro Bright Data
    # em vez de resolver credito na Apify. Zona e token verificados contra
    # a API real (curl) antes de escrever qualquer adapter - resposta de
    # Maps exige `&brd_json=1` na URL (a API avisa isso no proprio erro
    # quando falta), formato confirmado em `docs/ARQUITETURA.md`.
    brightdata_web_unlocker_zone: str | None = None
    brightdata_web_unlocker_token: str | None = None

    # Apify (adapter primario pra dado real - ver app/sourcing/adapters/
    # apify_source.py). So' precisa do token, sem CLI/instalacao - por isso
    # e' mais simples de operar que o Bright Data hoje. Actor de Mercado
    # Livre verificado contra a doc real da Apify (19/08/2026).
    apify_api_token: str | None = None
    apify_actor_mercadolivre: str = "gio21/mercado-livre-scraper"
    # `dtrungtin/ebay-items-scraper` (escolha original) exige ALUGUEL pago
    # (trial expirado - confirmado em execucao real, 19/08: 403
    # "actor-is-not-rented"). Trocado por este, que e' pay-per-result DENTRO
    # do credito gratuito da conta, sem assinatura - so' que o input e'
    # `startUrls` (URL de busca do eBay), nao um campo `keyword` solto.
    apify_actor_ebay: str = "piotrv1001/ebay-listings-scraper"
    # "Amazon Price Tracker" no nome, mas o input real e' busca por keyword
    # (nao rastreio de ASIN conhecido) - verificado contra a doc do actor,
    # 19/08/2026. Cobre 22 paises, serve o Bloco D (Amazon.com).
    apify_actor_amazon: str = "truefetch/amazon-price-tracker"
    # Bloco B (local/regional) - substitui o placeholder que reaproveitava o
    # actor de Mercado Livre pra busca local (nao fazia sentido: Mercado
    # Livre nao tem endereco fisico/telefone de loja). ID confirmado pelo
    # usuario via SDK oficial (apify_client), nao so' pela doc.
    apify_actor_google_maps: str = "compass/crawler-google-places"
    # Bloco C (busca ampla) - qualquer fornecedor fora do marketplace
    # (loja/fabricante/distribuidor/atacadista/importador/representante),
    # nao restrito a uma lista fixa de sites. Confirmado que aceita
    # multiplas queries por chamada (uma por linha), 19/08/2026.
    apify_actor_google_search: str = "apify/google-search-scraper"
    apify_timeout_s: float = 120.0

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

    # Identidade (ETAPA 0). O default so' serve pra dev/teste - producao
    # PRECISA sobrescrever via env (segredo real, nao versionado). Token
    # dura 24h; nao ha' refresh token nesta v1 (login de novo apos expirar).
    jwt_secret_key: str = "efraim-dev-somente-troque-em-producao"
    jwt_algorithm: str = "HS256"
    jwt_expira_minutos: int = 60 * 24


@lru_cache
def get_settings() -> Settings:
    return Settings()
