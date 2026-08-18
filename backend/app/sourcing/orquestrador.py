"""ETAPA 2 — Orquestrador.

Executa os blocos em paralelo com:
- semaforo (concorrencia limitada por fonte),
- timeout por chamada,
- circuit breaker por fonte (fonte que falha repetido e isolada no run).

Uma fonte degradada NUNCA trava o run: seus erros viram lista vazia e o
restante e entregue.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from app.domain.models import (
    ConsultaLocal,
    ConsultaProduto,
    Oferta,
    ResultadoFiltro,
)
from app.sourcing.filtro import filtrar_top7
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


@dataclass
class Orquestrador:
    price_sources: list[PriceSource] = field(default_factory=list)
    local_sources: list[LocalBusinessSource] = field(default_factory=list)
    concorrencia: int = 5
    timeout_s: float = 20.0
    _breakers: dict[str, _Breaker] = field(default_factory=dict)

    def _breaker(self, nome: str) -> _Breaker:
        return self._breakers.setdefault(nome, _Breaker())

    async def _com_protecao(self, nome: str, coro, sem: asyncio.Semaphore) -> list[Oferta]:
        breaker = self._breaker(nome)
        if breaker.aberto:
            log.warning("circuito aberto para fonte '%s' — pulando", nome)
            return []
        async with sem:
            try:
                res = await asyncio.wait_for(coro, timeout=self.timeout_s)
                breaker.registrar_sucesso()
                return res
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
        tarefas = [
            self._com_protecao(ps.nome, ps.buscar(consulta_produto), sem)
            for ps in self.price_sources
        ]
        if consulta_local is not None:
            tarefas += [
                self._com_protecao(ls.nome, ls.buscar(consulta_local), sem)
                for ls in self.local_sources
            ]

        blocos = await asyncio.gather(*tarefas)
        todas: list[Oferta] = [o for bloco in blocos for o in bloco]
        return filtrar_top7(todas)  # ENFORCEMENT
