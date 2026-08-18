"""Adapter Bright Data — implementa PriceSource e LocalBusinessSource.

Backbone de web data do Efraim (skill `bright-data-mcp`). Mapa Bloco->ferramenta:

  Bloco A (marketplaces BR)     -> search_engine_batch + scrape_as_markdown / extract
  Bloco A (agregador)           -> web_data_google_shopping
  Bloco A (retailers c/ pipeline) -> web_data_amazon_product / walmart / ebay / bestbuy
  Bloco B (Google Maps regional)-> grupo `business` + search_engine + extract (contatos)
  Bloco C (sites proprios)      -> scrape_as_markdown + extract
  Bloco D (internacional)       -> web_data_* (--country us) + scrape_as_markdown

Dois caminhos de execucao (auto-detectados em `disponivel()`):
  1) CLI `bdata` (skill price-comparison) — subprocess.
  2) MCP remoto (mcp.brightdata.com) via cliente MCP.

Enquanto as credenciais/CLI nao estiverem presentes, `disponivel()` retorna
False e o app degrada para o fake (ver factory em app.sourcing.factory).
Os pontos de integracao estao marcados com TODO(bright-data).
"""
from __future__ import annotations

import shutil

from app.domain.models import ConsultaLocal, ConsultaProduto, Oferta


class BrightDataPriceSource:
    nome = "brightdata-price"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    @staticmethod
    def disponivel() -> bool:
        # CLI instalado (curl -fsSL https://cli.brightdata.com/install.sh | bash)
        return shutil.which("bdata") is not None

    async def buscar(self, consulta: ConsultaProduto) -> list[Oferta]:
        # TODO(bright-data): resolver-antes-de-coletar.
        # 1) search_engine_batch(consulta.queries) -> URLs candidatas
        # 2) preferir web_data_* estruturado; senao scrape_as_markdown + extract
        # 3) normalizar cada resultado para Oferta (preco_centavos, disponibilidade...)
        raise NotImplementedError(
            "Integracao Bright Data pendente. Instale/login do CLI `bdata` ou "
            "configure o MCP remoto e implemente o mapeamento para Oferta."
        )


class BrightDataLocalSource:
    nome = "brightdata-local"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    @staticmethod
    def disponivel() -> bool:
        return shutil.which("bdata") is not None

    async def buscar(self, consulta: ConsultaLocal) -> list[Oferta]:
        # TODO(bright-data): grupo `business` (Google Maps) + search_engine por
        # "ponto de venda + cidade"; para comercio sem preco no site, usar
        # `extract` (ou app.sourcing.contatos.extrair_contatos como fallback).
        raise NotImplementedError("Integracao Bright Data (business) pendente.")
