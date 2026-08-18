"""ETAPA 2 — Orquestrador.

Executa os blocos em paralelo com:
- semaforo (concorrencia limitada por fonte),
- timeout por chamada,
- circuit breaker por fonte (fonte que falha repetido e isolada no run),
- orcamento de chamadas MCP por job (corta ANTES de estourar custo),
- backoff dedicado para rate limit (429), separado de falha generica,
- cache TTL por consulta normalizada (evita pagar de novo pela mesma busca).

Uma fonte degradada NUNCA trava o run: seus erros viram lista vazia e o
restante e entregue. Rate limit e orcamento esgotado NAO contam como falha
de fonte pro circuit breaker - sao decisoes nossas (esperar / parar de
gastar), nao evidencia de que o provedor esta quebrado.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.domain.models import (
    ConsultaLocal,
    ConsultaProduto,
    Oferta,
    ResultadoFiltro,
)
from app.persistence.cache import CacheTTL
from app.sourcing.erros import MCPRateLimitError
from app.sourcing.filtro import filtrar_top7
from app.sourcing.orcamento import OrcamentoExcedidoError, OrcamentoMCP
from app.sourcing.ports import LocalBusinessSource, PriceSource

log = logging.getLogger("efraim.orquestrador")


@dataclass
class _Breaker:
    """Circuit breaker simples por fonte."""
    limite_falhas: int = 3
    falhas: int = 0
    aberto: bool = False

    def registrar_falha(self) -> None:
        self.falhas += 1
        if self.falhas >= self.limite_falhas:
            self.aberto = True

    def registrar_sucesso(self) -> None:
        self.falhas = 0
        self.aberto = False


def _chave_cache(prefixo: str, consulta: ConsultaProduto | ConsultaLocal) -> str:
    """Chave deriva do conteudo normalizado da consulta, nao do objeto (frozen mas com
    campo `queries: list[str]`, que e' inerentemente nao-hasheavel)."""
    item = consulta.item
    marca = (item.marca or "").strip().lower()
    partes = [prefixo, item.nome.strip().lower(), marca, consulta.categoria]
    if isinstance(consulta, ConsultaLocal):
        loc = consulta.localizacao
        partes.append(loc.cidade or loc.cep or "")
    return "|".join(partes)


@dataclass
class Orquestrador:
    price_sources: list[PriceSource] = field(default_factory=list)
    local_sources: list[LocalBusinessSource] = field(default_factory=list)
    concorrencia: int = 5
    timeout_s: float = 20.0
    max_chamadas_mcp_por_job: int = 120
    max_tentativas_rate_limit: int = 2
    backoff_rate_limit_s: float = 5.0
    cache: CacheTTL | None = None
    _breakers: dict[str, _Breaker] = field(default_factory=dict)

    def _breaker(self, nome: str) -> _Breaker:
        return self._breakers.setdefault(nome, _Breaker())

    async def _com_protecao(
        self,
        nome: str,
        bloco: str,
        coro_factory: Callable[[], Awaitable[list[Oferta]]],
        sem: asyncio.Semaphore,
        orcamento: OrcamentoMCP,
        chave_cache: str | None,
    ) -> list[Oferta]:
        if chave_cache and self.cache is not None:
            cacheado = self.cache.get(chave_cache)
            if cacheado is not None:
                log.info("cache hit para '%s' (bloco=%s) — 0 chamadas MCP", nome, bloco)
                return cacheado

        breaker = self._breaker(nome)
        if breaker.aberto:
            log.warning("circuito aberto para fonte '%s' — pulando", nome)
            return []

        tentativas_rate_limit = 0
        while True:
            async with sem:
                try:
                    # a contagem contra o orcamento acontece DENTRO do adapter
                    # (cada chamada MCP real, nao esta invocacao externa) — ver
                    # `sourcing/adapters/brightdata_mcp.py`.
                    res = await asyncio.wait_for(coro_factory(), timeout=self.timeout_s)
                    breaker.registrar_sucesso()
                    if chave_cache and self.cache is not None:
                        self.cache.set(chave_cache, res)
                    return res
                except OrcamentoExcedidoError:
                    log.info(
                        "orcamento MCP esgotado no bloco '%s' — parando fonte '%s' nesta "
                        "busca (nao e' falha, e' teto de custo)",
                        bloco,
                        nome,
                    )
                    return []
                except MCPRateLimitError as exc:
                    tentativas_rate_limit += 1
                    if tentativas_rate_limit > self.max_tentativas_rate_limit:
                        log.warning(
                            "rate limit persistente em '%s' apos %d tentativas — desistindo",
                            nome,
                            tentativas_rate_limit,
                        )
                        breaker.registrar_falha()
                        return []
                    espera = exc.retry_after_s or self.backoff_rate_limit_s * tentativas_rate_limit
                    log.info(
                        "rate limit em '%s' — aguardando %.1fs (tentativa %d/%d)",
                        nome,
                        espera,
                        tentativas_rate_limit,
                        self.max_tentativas_rate_limit,
                    )
                    await asyncio.sleep(espera)
                    continue
                except TimeoutError:
                    log.warning("timeout na fonte '%s'", nome)
                    breaker.registrar_falha()
                    return []
                except Exception:  # noqa: BLE001 - resiliencia proposital
                    log.exception("falha na fonte '%s'", nome)
                    breaker.registrar_falha()
                    return []

    async def executar(
        self,
        consulta_produto: ConsultaProduto,
        consulta_local: ConsultaLocal | None = None,
    ) -> ResultadoFiltro:
        sem = asyncio.Semaphore(self.concorrencia)
        orcamento = OrcamentoMCP(limite_por_job=self.max_chamadas_mcp_por_job)

        tarefas = [
            self._com_protecao(
                ps.nome, "price",
                lambda ps=ps: ps.buscar(consulta_produto, orcamento),
                sem, orcamento,
                _chave_cache(f"price:{ps.nome}", consulta_produto),
            )
            for ps in self.price_sources
        ]
        if consulta_local is not None:
            tarefas += [
                self._com_protecao(
                    ls.nome, "local",
                    lambda ls=ls: ls.buscar(consulta_local, orcamento),
                    sem, orcamento,
                    _chave_cache(f"local:{ls.nome}", consulta_local),
                )
                for ls in self.local_sources
            ]

        blocos = await asyncio.gather(*tarefas)
        todas: list[Oferta] = [o for bloco in blocos for o in bloco]
        return filtrar_top7(todas)  # ENFORCEMENT
