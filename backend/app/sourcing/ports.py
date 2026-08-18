"""Portas (contratos) do nucleo. O nucleo depende SO destes Protocols,
nunca de um provedor concreto. Adapters implementam-nos.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.models import (
    ConsultaLocal,
    ConsultaProduto,
    Fornecedor,
    Oferta,
)
from app.sourcing.orcamento import OrcamentoMCP


@runtime_checkable
class PriceSource(Protocol):
    nome: str
    async def buscar(self, consulta: ConsultaProduto, orcamento: OrcamentoMCP) -> list[Oferta]: ...


@runtime_checkable
class LocalBusinessSource(Protocol):
    nome: str
    async def buscar(self, consulta: ConsultaLocal, orcamento: OrcamentoMCP) -> list[Oferta]: ...


@runtime_checkable
class NotificationPort(Protocol):
    nome: str
    async def cotar(self, fornecedor: Fornecedor, produto: str) -> dict: ...


@runtime_checkable
class RepositorioBusca(Protocol):
    async def salvar(self, lista_id: int, ofertas: list[Oferta]) -> None: ...
    async def variacao(self, produto_normalizado: str, local: str,
                       preco_atual_centavos: int) -> dict | None: ...
