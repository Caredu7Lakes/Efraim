"""Selecao de fontes por configuracao, com degradacao para fake."""
from __future__ import annotations

from app.config import Settings
from app.persistence.cache import CacheTTL
from app.sourcing.adapters.brightdata_mcp import (
    BrightDataLocalSource,
    BrightDataPriceSource,
)
from app.sourcing.adapters.fake_source import FakeLocalSource, FakePriceSource
from app.sourcing.orquestrador import Orquestrador


def montar_orquestrador(cfg: Settings) -> Orquestrador:
    usar_bright = cfg.efraim_fonte == "brightdata" and BrightDataPriceSource.disponivel()
    if usar_bright:
        price = [BrightDataPriceSource(cfg.brightdata_api_key)]
        local = [BrightDataLocalSource(cfg.brightdata_api_key)]
    else:
        price = [FakePriceSource()]
        local = [FakeLocalSource()]
    return Orquestrador(
        price_sources=price,
        local_sources=local,
        concorrencia=cfg.concorrencia,
        timeout_s=cfg.timeout_fonte_s,
        max_chamadas_mcp_por_job=cfg.max_chamadas_mcp_por_job,
        max_tentativas_rate_limit=cfg.max_tentativas_rate_limit,
        backoff_rate_limit_s=cfg.backoff_rate_limit_s,
        cache=CacheTTL(ttl_segundos=cfg.cache_ttl_s),
    )
