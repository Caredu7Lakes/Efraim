"""Selecao de fontes por configuracao, com degradacao para fake."""
from __future__ import annotations

from app.config import Settings
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
    )
