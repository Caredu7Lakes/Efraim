"""ETAPA 4 — filtrar_top7 (ENFORCEMENT).

Ponto UNICO de decisao do resultado final. Python puro, sem rede, testavel.
O agente/LLM nunca reordena nem readiciona descartado: usa somente esta saida.
"""
from __future__ import annotations

from app.domain.models import Condicao, Disponibilidade, Oferta, ResultadoFiltro

TOP_N = 7


def _penalidade(o: Oferta) -> int:
    """Ofertas indisponiveis ou nao-novas nao vencem por padrao: desempatam por baixo."""
    p = 0
    if o.disponibilidade is Disponibilidade.INDISPONIVEL:
        p += 1
    if o.condicao in (Condicao.USADO, Condicao.RECONDICIONADO):
        p += 1
    return p


def filtrar_top7(ofertas: list[Oferta], top_n: int = TOP_N) -> ResultadoFiltro:
    com_preco = [o for o in ofertas if o.tem_preco]
    sem_preco = [o for o in ofertas if not o.tem_preco]

    # ordena por (penalidade, custo total). Custo total = preco + frete.
    com_preco.sort(key=lambda o: (_penalidade(o), o.custo_total_centavos or 0))

    top = com_preco[:top_n]
    descartados = max(0, len(com_preco) - len(top))

    return ResultadoFiltro(
        top7_online=top,
        sem_preco=sem_preco,
        total_descartados=descartados,
    )
