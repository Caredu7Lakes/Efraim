from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import BuscaIn, OfertaOut, ResultadoOut
from app.config import get_settings
from app.domain.classificacao import montar_consulta_local, montar_consulta_produto
from app.domain.models import Escopo, ItemProduto, Localizacao, Oferta, ResultadoFiltro
from app.jobs.runner import StatusJob, enfileirar, store
from app.sourcing.factory import montar_orquestrador

router = APIRouter(prefix="/buscas", tags=["buscas"])


def _to_out(o: Oferta) -> OfertaOut:
    return OfertaOut(
        produto=o.produto, marca=o.marca, preco_centavos=o.preco_centavos,
        moeda=o.moeda, local=o.local, link=o.link, pagamento=o.pagamento,
        disponibilidade=o.disponibilidade.value, fonte=o.fonte,
    )


async def _pipeline(payload: BuscaIn) -> ResultadoFiltro:
    cfg = get_settings()
    orq = montar_orquestrador(cfg)
    escopo = Escopo(payload.escopo)
    # v1: processa o primeiro produto da lista (loop multiproduto entra no proximo ciclo)
    p = payload.produtos[0]
    item = ItemProduto(nome=p.nome, marca=p.marca, quantidade=p.quantidade,
                       unidade=p.unidade, qualidade=p.qualidade)
    cp = montar_consulta_produto(item, escopo)
    cl = None
    if escopo is Escopo.LOCAL:
        cl = montar_consulta_local(item, Localizacao(cep=payload.cep, cidade=payload.cidade))
    return await orq.executar(cp, cl)


@router.post("", status_code=202)
async def criar_busca(payload: BuscaIn) -> dict:
    if not payload.produtos:
        raise HTTPException(422, "lista de produtos vazia")
    job = enfileirar(_pipeline(payload))
    return {"job_id": job.id, "status": job.status.value}


@router.get("/{job_id}")
async def status_busca(job_id: str) -> dict:
    job = store.obter(job_id)
    if not job:
        raise HTTPException(404, "job nao encontrado")
    if job.status is StatusJob.CONCLUIDO and isinstance(job.resultado, ResultadoFiltro):
        r = job.resultado
        out = ResultadoOut(
            top7_online=[_to_out(o) for o in r.top7_online],
            sem_preco=[_to_out(o) for o in r.sem_preco],
            total_descartados=r.total_descartados,
        )
        return {"status": job.status.value, "resultado": out.model_dump()}
    return {"status": job.status.value, "erro": job.erro}
