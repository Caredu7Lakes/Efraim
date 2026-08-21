"""Adapter Bright Data — implementa PriceSource e LocalBusinessSource.

Backbone de web data do Efraim (skill `bright-data-mcp`). Mapa Bloco->ferramenta:

  Bloco A (marketplaces BR)     -> search_engine_batch + scrape_as_markdown / extract
  Bloco A (agregador)           -> web_data_google_shopping
  Bloco A (retailers c/ pipeline) -> web_data_amazon_product / walmart / ebay / bestbuy
  Bloco B (Google Maps regional)-> grupo `business` + search_engine + extract (contatos)
  Bloco C (sites proprios)      -> scrape_as_markdown + extract
  Bloco D (internacional)       -> web_data_* (--country us) + scrape_as_markdown

Dois caminhos de execucao (auto-detectados em `disponivel()`):
  1) CLI `bdata` (skill price-comparison) — subprocess. E' o unico implementado
     aqui; o caminho MCP remoto (mcp.brightdata.com) fica para quando houver
     necessidade de rodar fora de um host com o CLI instalado.
  2) MCP remoto (mcp.brightdata.com) via cliente MCP — nao implementado.

Enquanto as credenciais/CLI nao estiverem presentes, `disponivel()` retorna
False e o app degrada para o fake (ver factory em app.sourcing.factory).

ATENCAO — LIMITE DESTA IMPLEMENTACAO: o formato exato de entrada/saida do CLI
`bdata` (nomes de flag, shape do JSON de resposta de cada ferramenta) nao foi
verificado contra uma instalacao real neste ambiente — nao ha' binario nem
credenciais Bright Data disponiveis aqui. O que segue abaixo e' estrutural e
testavel (contagem de orcamento, diferenciacao de 429, subprocess real), mas o
mapeamento de campos em `_para_oferta`/`_para_fornecedor` e' uma suposicao
com base no DTO `Oferta` e PRECISA ser validado contra a saida real do CLI
antes de ir para producao.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil

from app.domain.models import ConsultaLocal, ConsultaProduto, Oferta
from app.domain.normalizador import oferta_ou_none
from app.sourcing.erros import MCPRateLimitError
from app.sourcing.orcamento import OrcamentoExcedidoError, OrcamentoMCP

log = logging.getLogger("efraim.brightdata")

_RETRY_AFTER_RE = re.compile(r"retry[-_]after[\"':\s]*(\d+(?:\.\d+)?)", re.I)


def _extrair_retry_after(texto: str) -> float | None:
    m = _RETRY_AFTER_RE.search(texto)
    return float(m.group(1)) if m else None


def _e_rate_limit(codigo_saida: int, stderr: str) -> bool:
    baixo = stderr.lower()
    if codigo_saida == 429 or "429" in baixo:
        return True
    return "rate limit" in baixo or "too many requests" in baixo


async def _chamar_bdata(
    nome_fonte: str, bloco: str, ferramenta: str, argumentos: dict, orcamento: OrcamentoMCP
) -> list[dict]:
    """Invoca uma ferramenta do CLI `bdata`, contando contra o orcamento do job.

    Levanta `OrcamentoExcedidoError` (nao mais chamadas neste job) ou
    `MCPRateLimitError` (429 — o orquestrador decide o backoff), deixando
    qualquer outra falha subir como excecao generica pro circuit breaker.
    """
    orcamento.registrar_chamada(bloco)  # pode levantar OrcamentoExcedidoError
    proc = await asyncio.create_subprocess_exec(
        "bdata", ferramenta, "--json", json.dumps(argumentos),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    stderr_txt = stderr.decode(errors="replace")
    if _e_rate_limit(proc.returncode or 0, stderr_txt):
        raise MCPRateLimitError(nome_fonte, _extrair_retry_after(stderr_txt))
    if proc.returncode != 0:
        raise RuntimeError(f"bdata {ferramenta} falhou (rc={proc.returncode}): {stderr_txt[:300]}")
    dado = json.loads(stdout or b"{}")
    # aceita tanto `{"resultados": [...]}` quanto uma lista solta na raiz —
    # forma exata NAO verificada, ver aviso no topo do arquivo.
    if isinstance(dado, list):
        return dado
    return dado.get("resultados", dado.get("items", []))


def _para_oferta(bruto: dict, fonte: str) -> Oferta | None:
    return oferta_ou_none(bruto, fonte=fonte)


class BrightDataPriceSource:
    nome = "brightdata-price"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    @staticmethod
    def disponivel() -> bool:
        # CLI instalado (curl -fsSL https://cli.brightdata.com/install.sh | bash)
        return shutil.which("bdata") is not None

    async def buscar(self, consulta: ConsultaProduto, orcamento: OrcamentoMCP) -> list[Oferta]:
        ofertas: list[Oferta] = []
        try:
            # resolve nome->URL antes de extrair (ETAPA "resolver-antes-de-coletar",
            # ver docs/ARQUITETURA.md secao 11) — search_engine_batch aceita ate 10
            # queries por chamada.
            resolvidos = await _chamar_bdata(
                self.nome, "A", "search_engine_batch",
                {"queries": consulta.queries[:10]}, orcamento,
            )
        except OrcamentoExcedidoError:
            log.info("orcamento esgotado antes de resolver bloco A — 0 ofertas de %s", self.nome)
            return ofertas

        for item in resolvidos:
            url = item.get("url") if isinstance(item, dict) else None
            if not url:
                continue
            try:
                extraido = await _chamar_bdata(
                    self.nome, "A", "extract",
                    {"url": url, "schema": "oferta_preco"}, orcamento,
                )
            except OrcamentoExcedidoError:
                log.info(
                    "orcamento esgotado no meio do bloco A — devolvendo %d ofertas parciais",
                    len(ofertas),
                )
                break
            for bruto in extraido:
                oferta = _para_oferta(bruto, self.nome)
                if oferta is not None:
                    ofertas.append(oferta)
        return ofertas


class BrightDataLocalSource:
    nome = "brightdata-local"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    @staticmethod
    def disponivel() -> bool:
        return shutil.which("bdata") is not None

    async def buscar(self, consulta: ConsultaLocal, orcamento: OrcamentoMCP) -> list[Oferta]:
        ofertas: list[Oferta] = []
        try:
            argumentos = {"queries": consulta.queries[:10], "cidade": consulta.localizacao.cidade}
            achados = await _chamar_bdata(self.nome, "local", "business", argumentos, orcamento)
        except OrcamentoExcedidoError:
            log.info("orcamento esgotado antes do bloco B/local — 0 ofertas de %s", self.nome)
            return ofertas

        for bruto in achados:
            oferta = _para_oferta(bruto, self.nome)
            if oferta is not None:
                ofertas.append(oferta)
        return ofertas
