"""Roteamento de escopo efetivo por item (ETAPA 1 - extensao).

Decide, PRODUTO A PRODUTO, se a consulta roda so' nacional ou tambem
internacional - independente do escopo pedido pra busca inteira - e qual
termo usar na consulta internacional quando aplicavel.

Regra: categorias tipicamente sourced internacionalmente (hoje: eletronico,
o vertical que o Bloco D do organograma - Mouser/DigiKey/eBay/Amazon.com/
Alibaba/1688 - endereca) sempre rodam tambem o bloco internacional, mesmo
quando a busca pediu so' "nacional". Isso cobre dois casos reais:

  1) nome ja' em ingles (ex. "LED 3mm round long lead diffused red") - usado
     como veio, tanto nas queries internacionais quanto nas nacionais.
     Importador brasileiro tende a anunciar com o MESMO termo tecnico, nao
     traduzido - traduzir pra portugues faria a busca NACIONAL voltar vazia.

  2) nome em portugues descrevendo um produto vendido internacionalmente
     (ex. "conector jack p10 estereo") - o termo pra busca internacional
     PRECISA ser adaptado (`nomenclatura_internacional`), senao a busca
     la' fora tambem volta vazia (ninguem anuncia em portugues). O nome
     original em portugues continua sendo usado nas queries NACIONAIS.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.classificacao import classificar
from app.domain.idioma import detectar_idioma
from app.domain.models import Escopo, ItemProduto
from app.domain.nomenclatura_chinesa import nomenclatura_chinesa
from app.domain.nomenclatura_internacional import nomenclatura_internacional

CATEGORIAS_INTERNACIONAIS = {"eletronico"}


@dataclass(frozen=True)
class EscopoEfetivo:
    escopo: Escopo
    # so' importam quando escopo e' INTERNACIONAL; nas queries nacionais o
    # nome original do item sempre e' usado, nunca traduzido.
    termo_internacional: str  # termo em ingles - Bloco D EUA
    termo_zh: str  # termo em chines - Bloco D China
    idioma_detectado: str
    categoria: str


def montar_escopo_efetivo(item: ItemProduto, escopo_pedido: Escopo) -> EscopoEfetivo:
    categoria = classificar(item.nome)
    idioma = detectar_idioma(item.nome)

    if escopo_pedido is Escopo.LOCAL:
        return EscopoEfetivo(Escopo.LOCAL, item.nome, item.nome, idioma, categoria)

    pede_internacional = (
        escopo_pedido is Escopo.INTERNACIONAL or categoria in CATEGORIAS_INTERNACIONAIS
    )
    if not pede_internacional:
        return EscopoEfetivo(Escopo.NACIONAL, item.nome, item.nome, idioma, categoria)

    termo_en = item.nome if idioma == "en" else nomenclatura_internacional(item.nome)
    # termo_zh SEMPRE deriva de termo_en (ponto unico de verdade) - nao do
    # item.nome original, que pode estar em portugues (ver docstring de
    # `nomenclatura_chinesa`).
    termo_zh = nomenclatura_chinesa(termo_en)
    return EscopoEfetivo(Escopo.INTERNACIONAL, termo_en, termo_zh, idioma, categoria)
