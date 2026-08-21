from __future__ import annotations

import asyncio
import uuid

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_usuario_atual
from app.api.schemas import BuscaIn, ResultadoOut
from app.jobs.celery_app import celery_app
from app.jobs.tasks import executar_busca_task
from app.persistence.orm import Usuario
from app.persistence.usuarios import RepositorioUsuarios

router = APIRouter(prefix="/buscas", tags=["buscas"])

_ESTADO_CELERY_PARA_API = {
    "PENDING": "pendente",
    "STARTED": "executando",
    "RETRY": "executando",
    "SUCCESS": "concluido",
    "FAILURE": "erro",
}


@router.post("", status_code=202)
def criar_busca(payload: BuscaIn, usuario: Usuario = Depends(get_usuario_atual)) -> dict:
    # sync de proposito: `.delay()`/`apply_async()` sao chamadas sincronas;
    # em modo eager (dev/teste) elas rodam a task inline via `asyncio.run()`
    # dentro dela, o que exige rodar fora do event loop do proprio FastAPI —
    # rota sync, o Starlette executa isso numa threadpool.
    if not payload.produtos:
        raise HTTPException(422, "lista de produtos vazia")

    # job_id gerado ANTES de disparar a task: registra o dono primeiro, pra
    # nunca existir um job concluido sem dono rastreavel (isolamento entre
    # usuarios depende disso - ver `status_busca` abaixo).
    job_id = str(uuid.uuid4())
    asyncio.run(RepositorioUsuarios().registrar_job(job_id, usuario.id))

    dados = payload.model_dump()
    dados["usuario_id"] = usuario.id
    executar_busca_task.apply_async(args=[dados], task_id=job_id)
    return {"job_id": job_id, "status": "pendente"}


@router.get("/{job_id}")
def status_busca(job_id: str, usuario: Usuario = Depends(get_usuario_atual)) -> dict:
    # dono nao bate (ou job nunca existiu) -> 404, nunca 403: nao da' pra
    # confirmar pra um usuario que um job_id de OUTRO usuario existe.
    dono = asyncio.run(RepositorioUsuarios().dono_do_job(job_id))
    if dono is None or dono != usuario.id:
        raise HTTPException(404, "job nao encontrado")

    resultado = AsyncResult(job_id, app=celery_app)
    status = _ESTADO_CELERY_PARA_API.get(resultado.state, resultado.state.lower())

    if resultado.state == "SUCCESS":
        out = ResultadoOut(**resultado.result)
        return {"status": status, "resultado": out.model_dump()}
    if resultado.state == "FAILURE":
        return {"status": status, "erro": str(resultado.result)}
    return {"status": status}
