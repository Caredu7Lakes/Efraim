"""Task Celery que executa o pipeline de busca (ETAPA 1-5), substituindo o
runner in-process de v1.

Recebe e devolve SOMENTE dados serializaveis (dict) - nunca um objeto de
dominio (`Oferta`, `ConsultaProduto`...) nem uma coroutine. E' essa fronteira
que torna a fila trocavel de broker e escalavel: um worker Celery rodando em
outro processo/maquina so' consegue receber o `payload` se ele for JSON.
"""
from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.domain.classificacao import montar_consulta_local, montar_consulta_produto
from app.domain.models import Escopo, ItemProduto, Localizacao, Oferta, ResultadoFiltro
from app.jobs.celery_app import celery_app
from app.persistence.repositorio import RepositorioSQL
from app.sourcing.factory import montar_orquestrador

log = logging.getLogger("efraim.tasks")


def oferta_para_dict(o: Oferta) -> dict:
    return {
        "produto": o.produto, "marca": o.marca, "preco_centavos": o.preco_centavos,
        "moeda": o.moeda, "local": o.local, "link": o.link, "pagamento": o.pagamento,
        "disponibilidade": o.disponibilidade.value, "fonte": o.fonte,
    }


def resultado_para_dict(r: ResultadoFiltro) -> dict:
    return {
        "top7_online": [oferta_para_dict(o) for o in r.top7_online],
        "sem_preco": [oferta_para_dict(o) for o in r.sem_preco],
        "total_descartados": r.total_descartados,
    }


async def _executar_pipeline(payload: dict) -> dict:
    cfg = get_settings()
    orq = montar_orquestrador(cfg)
    escopo = Escopo(payload["escopo"])
    # v1: processa o primeiro produto da lista (loop multiproduto entra no proximo ciclo)
    p = payload["produtos"][0]
    item = ItemProduto(
        nome=p["nome"], marca=p.get("marca"), quantidade=p.get("quantidade", 1),
        unidade=p.get("unidade", "un"), qualidade=p.get("qualidade"),
    )
    cp = montar_consulta_produto(item, escopo)
    cl = None
    if escopo is Escopo.LOCAL:
        loc = Localizacao(cep=payload.get("cep"), cidade=payload.get("cidade"))
        cl = montar_consulta_local(item, loc)
    resultado = await orq.executar(cp, cl)
    await _persistir(resultado, escopo=escopo, payload=payload)
    return resultado_para_dict(resultado)


async def _persistir(resultado: ResultadoFiltro, *, escopo: Escopo, payload: dict) -> None:
    """Grava ResultadoBusca/HistoricoPreco (ETAPA 6). Falha aqui NUNCA derruba
    a resposta ao usuario - o resultado ja' foi calculado e e' o que importa
    pra quem pediu a busca; persistencia e' registro historico, nao o produto
    principal (mesma filosofia de resiliencia do orquestrador: uma parte
    degradada nao trava o todo)."""
    try:
        repo = RepositorioSQL()
        lista_id = payload.get("lista_id")
        if lista_id is None:
            localizacao = payload.get("cidade") or payload.get("cep")
            lista_id = await repo.criar_lista(escopo=escopo.value, localizacao=localizacao)
        await repo.salvar(lista_id, resultado.top7_online + resultado.sem_preco)
    except Exception:  # noqa: BLE001 - resiliencia proposital, ver docstring
        log.exception("falha ao persistir resultado da busca (resposta ao usuario segue normal)")


@celery_app.task(name="efraim.executar_busca")
def executar_busca_task(payload: dict) -> dict:
    return asyncio.run(_executar_pipeline(payload))
