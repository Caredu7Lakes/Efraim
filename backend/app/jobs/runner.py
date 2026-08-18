"""Runner de jobs assincrono (in-process, v1).

Contrato pensado para ser trocado por Celery/RQ sem mexer na API:
enfileira -> devolve job_id -> executa em background -> consulta status.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StatusJob(str, Enum):
    PENDENTE = "pendente"
    EXECUTANDO = "executando"
    CONCLUIDO = "concluido"
    ERRO = "erro"


@dataclass
class Job:
    id: str
    status: StatusJob = StatusJob.PENDENTE
    resultado: Any = None
    erro: str | None = None


@dataclass
class JobStore:
    _jobs: dict[str, Job] = field(default_factory=dict)

    def criar(self) -> Job:
        job = Job(id=uuid.uuid4().hex)
        self._jobs[job.id] = job
        return job

    def obter(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)


store = JobStore()


async def _rodar(job: Job, coro) -> None:
    job.status = StatusJob.EXECUTANDO
    try:
        job.resultado = await coro
        job.status = StatusJob.CONCLUIDO
    except Exception as exc:  # noqa: BLE001
        job.erro = repr(exc)
        job.status = StatusJob.ERRO


def enfileirar(coro) -> Job:
    job = store.criar()
    asyncio.create_task(_rodar(job, coro))
    return job
