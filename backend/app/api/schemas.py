from __future__ import annotations

from pydantic import BaseModel

from app.domain.models import Escopo


class ItemIn(BaseModel):
    nome: str
    marca: str | None = None
    quantidade: float = 1
    unidade: str = "un"
    qualidade: str | None = None


class BuscaIn(BaseModel):
    produtos: list[ItemIn]
    # Escopo e' o enum de dominio (nao uma string solta): um valor invalido
    # vira 422 direto do FastAPI, em vez de estourar 500 dentro da task
    # (Escopo(payload["escopo"]) so' seria validado ali, tarde demais).
    escopo: Escopo = Escopo.NACIONAL
    cidade: str | None = None
    cep: str | None = None
    lista_id: int | None = None


class OfertaOut(BaseModel):
    produto: str
    marca: str | None
    preco_centavos: int | None
    moeda: str
    local: str
    link: str
    pagamento: str | None
    disponibilidade: str
    fonte: str


class ResultadoOut(BaseModel):
    top7_online: list[OfertaOut]
    sem_preco: list[OfertaOut]
    total_descartados: int
