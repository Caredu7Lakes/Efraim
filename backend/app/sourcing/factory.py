"""Selecao de fontes por configuracao, com degradacao para fake."""
from __future__ import annotations

import logging
from functools import lru_cache

from app.config import Settings
from app.persistence.cache import CacheTTL
from app.sourcing.adapters.apify_source import (
    ApifyBroadSource,
    ApifyLocalSource,
    ApifyPriceSource,
)
from app.sourcing.adapters.brightdata_mcp import (
    BrightDataLocalSource,
    BrightDataPriceSource,
)
from app.sourcing.adapters.brightdata_unlocker import BrightDataRegionalSource
from app.sourcing.adapters.fake_source import FakeLocalSource, FakePriceSource
from app.sourcing.orquestrador import Orquestrador

log = logging.getLogger("efraim.factory")


@lru_cache
def _cache_compartilhado(ttl_segundos: int) -> CacheTTL:
    """Uma unica instancia por processo (memoizada por TTL, que e' constante
    em runtime). `montar_orquestrador` e' chamado DE NOVO a cada job (ver
    `jobs/tasks.py::_executar_pipeline`) - sem isto, cada busca criava e
    descartava seu proprio `CacheTTL` vazio, e o cache nunca sobrevivia
    entre duas requisicoes HTTP (achado em teste real, 19/08). Redis entra
    depois pelo mesmo contrato quando precisar sobreviver a mais de um
    processo worker (ver `persistence/cache.py`)."""
    return CacheTTL(ttl_segundos=ttl_segundos)


def montar_orquestrador(cfg: Settings) -> Orquestrador:
    usar_apify = cfg.efraim_fonte == "apify" and ApifyPriceSource.disponivel(cfg.apify_api_token)
    usar_bright = cfg.efraim_fonte == "brightdata" and BrightDataPriceSource.disponivel()
    usar_bright_regional = BrightDataRegionalSource.disponivel(
        cfg.brightdata_web_unlocker_zone, cfg.brightdata_web_unlocker_token,
    )
    if usar_apify:
        price = [
            ApifyPriceSource(
                cfg.apify_api_token, cfg.apify_actor_mercadolivre, cfg.apify_actor_ebay,
                cfg.apify_actor_amazon, timeout_s=cfg.apify_timeout_s,
            ),
            # Bloco C — busca ampla, roda em paralelo ao Bloco A/D via o
            # mesmo asyncio.gather do orquestrador (list de price_sources).
            ApifyBroadSource(
                cfg.apify_api_token, cfg.apify_actor_google_search, timeout_s=cfg.apify_timeout_s,
            ),
        ]
        # Bloco B — migrado pro Bright Data Web Unlocker em 20/08 (o actor
        # Apify de Google Maps bateu 402 Payment Required em teste real;
        # decisao explicita do usuario foi trocar de fonte, nao resolver
        # credito na Apify). Degrada silenciosamente pra ausencia de Bloco B
        # (nao pro Apify de volta) se as credenciais Bright Data faltarem -
        # evita reintroduzir o 402 sem avisar.
        if usar_bright_regional:
            price.append(BrightDataRegionalSource(
                cfg.brightdata_web_unlocker_zone, cfg.brightdata_web_unlocker_token,
            ))
        else:
            log.warning(
                "Bloco B desligado — BRIGHTDATA_WEB_UNLOCKER_ZONE/TOKEN ausentes "
                "(nao volta pro Apify de Google Maps, que bate 402 nesta conta)"
            )
        local = [ApifyLocalSource(
            cfg.apify_api_token, cfg.apify_actor_google_maps, timeout_s=cfg.apify_timeout_s,
        )]
    elif usar_bright:
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
        cache=_cache_compartilhado(cfg.cache_ttl_s),
    )
