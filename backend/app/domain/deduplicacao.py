"""Deduplicacao entre fontes (correcao do usuario, 20/08): links diferentes
(Google, Mercado Livre, Bright Data regional, Apify) podem apontar pro
MESMO fornecedor/anuncio - comparar por URL nunca captura isso, porque cada
fonte gera sua propria URL pro mesmo negocio. "O criterio da exclusao fica
a criterio da melhor pratica" (usuario, 20/08) - a pratica adotada aqui, em
2 niveis de chave (checados nessa ordem, a 1a que existir decide):

  1. `Oferta.id_externo` - id ESTAVEL do anuncio na fonte de origem (ex.:
     "MLB3882572605"). Sinal mais forte que existe: o MESMO anuncio
     literal chegando por 2 caminhos (ex.: actor Apify E busca direta do
     mesmo Mercado Livre - achado 20/08, revisao pedida pelo usuario: "voce
     utilizou scraper do mercado livre ontem" - os dois cobrem o MESMO
     marketplace, sem isso contariam como 2 ofertas diferentes).
  2. Contato do fornecedor (whatsapp/telefone/email, nessa ordem de
     prioridade - o 1o canal presente na oferta decide a chave) - sinal
     mais fraco (mesmo FORNECEDOR, nao necessariamente o mesmo anuncio
     literal), usado quando nao ha' id_externo.

Em qualquer dos 2 niveis, quando 2+ ofertas compartilham a mesma chave,
fica so' a MELHOR: com preco vence sem preco; entre as com preco, o menor
custo unitario (preco + frete, dividido pelas unidades do lote - ver
`Oferta.custo_unitario_centavos`) vence; empate mantem a 1a encontrada.
Ofertas sem id_externo NEM contato nunca sao comparadas entre si - nao ha'
base pra confirmar que sao o mesmo anuncio/fornecedor so' porque
produto/preco parecem iguais.
"""
from __future__ import annotations

import re

from app.domain.models import Oferta

_NAO_DIGITO_RE = re.compile(r"\D+")


def _normalizar_numero(numero: str) -> str:
    """Remove tudo que nao e' digito e o codigo do pais (55) quando presente
    - a mesma linha pode chegar como "5511999998888" (extraida de um link
    wa.me) ou "(11) 99999-8888" (extraida de texto de pagina) dependendo da
    fonte; sem essa normalizacao as duas nunca bateriam como o mesmo
    contato."""
    d = _NAO_DIGITO_RE.sub("", numero)
    if len(d) >= 12 and d.startswith("55"):
        d = d[2:]
    return d


def _chave_contato(oferta: Oferta) -> str | None:
    c = oferta.contato
    if c is None:
        return None
    if c.whatsapp:
        return "wa:" + _normalizar_numero(c.whatsapp[0])
    if c.telefone:
        return "tel:" + _normalizar_numero(c.telefone[0])
    if c.email:
        return "mail:" + c.email[0].strip().lower()
    return None


def _chave(oferta: Oferta) -> str | None:
    """id_externo (mesmo anuncio literal) vence contato (mesmo
    fornecedor, sinal mais fraco) - ver docstring do modulo."""
    if oferta.id_externo:
        return "id:" + oferta.id_externo
    return _chave_contato(oferta)


def _melhor(a: Oferta, b: Oferta) -> Oferta:
    if a.tem_preco != b.tem_preco:
        return a if a.tem_preco else b
    if a.tem_preco and b.tem_preco:
        return a if (a.custo_unitario_centavos or 0) <= (b.custo_unitario_centavos or 0) else b
    return a


def deduplicar_ofertas(ofertas: list[Oferta]) -> list[Oferta]:
    """Devolve a lista de ofertas com duplicatas (mesmo id_externo OU mesmo
    contato normalizado - ver `_chave`) colapsadas na melhor - preserva a
    ordem de 1a aparicao. Ofertas sem id_externo NEM contato passam direto,
    sem participar da deduplicacao."""
    melhor_por_chave: dict[str, Oferta] = {}
    ordem: list[str] = []
    sem_chave: list[Oferta] = []

    for oferta in ofertas:
        chave = _chave(oferta)
        if chave is None:
            sem_chave.append(oferta)
            continue
        if chave not in melhor_por_chave:
            ordem.append(chave)
            melhor_por_chave[chave] = oferta
        else:
            melhor_por_chave[chave] = _melhor(melhor_por_chave[chave], oferta)

    return [melhor_por_chave[chave] for chave in ordem] + sem_chave
