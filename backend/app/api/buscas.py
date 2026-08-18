from __future__ import annotations

from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException

from app.api.schemas import BuscaIn, ResultadoOut
from app.jobs.celery_app import celery_app
from app.jobs.tasks import executar_busca_task

router = APIRouter(prefix="/buscas", tags=["buscas"])

_ESTADO_CELERY_PARA_API = {
    "PENDING": "pendente",
    "STARTED": "executando",
    "RETRY": "executando",
    "SUCCESS": "concluido",
    "FAILURE": "erro",
}


@router.post("", status_code=202)
def criar_busca(payload: BuscaIn) -> dict:
    # sync de proposito: `.delay()` e' chamada sincrona (enfileira e retorna);
    # em modo eager (dev/teste) ela roda a task inline via `asyncio.run()`
    # dentro dela, o que exige rodar fora do event loop do proprio FastAPI —
    # rota sync, o Starlette executa isso numa threadpool.
    if not payload.produtos:
        raise HTTPException(422, "lista de produtos vazia")
    task = executar_busca_task.delay(payload.model_dump())
    return {"job_id": task.id, "status": "pendente"}


@router.get("/{job_id}")
def status_busca(job_id: str) -> dict:
    # Celery nao distingue "job_id nunca existiu" de "ainda pendente" - ambos
    # caem em PENDING (limitacao conhecida do backend de resultado, diferente
    # do 404 limpo que o JobStore in-process v1 dava; ver ARQUITETURA.md).
    resultado = AsyncResult(job_id, app=celery_app)
    status = _ESTADO_CELERY_PARA_API.get(resultado.state, resultado.state.lower())

    if resultado.state == "SUCCESS":
        out = ResultadoOut(**resultado.result)
        return {"status": status, "resultado": out.model_dump()}
    if resultado.state == "FAILURE":
        return {"status": status, "erro": str(resultado.result)}
    return {"status": status}
