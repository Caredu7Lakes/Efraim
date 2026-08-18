"""App Celery — fila real de jobs, substitui o runner in-process de v1.

Contrato: a task recebe SOMENTE `payload` serializavel (dict/JSON), nunca uma
coroutine nem um objeto de dominio vivo. E' isso, e nao o runner por baixo,
que permite trocar de broker e escalar workers horizontalmente sem tocar na
API (ver `app/jobs/tasks.py` e `app/api/buscas.py`).

`celery_task_eager=True` (padrao em dev/teste) roda a task no mesmo processo,
de forma sincrona, sem precisar de um broker Redis real — e' o modo suportado
nativamente pelo Celery para testes. Em producao, `CELERY_TASK_EAGER=false`
mais um broker/backend Redis reais habilitam workers separados.
"""
from __future__ import annotations

from celery import Celery

from app.config import get_settings

_cfg = get_settings()

# Em modo eager nao ha' worker separado nem broker real envolvido - usar o
# backend Redis mesmo assim exigiria um Redis rodando so' pra dev/teste. O
# backend de memoria do proprio processo resolve isso sem mudar o contrato:
# `AsyncResult(job_id)` continua funcionando (mesma consulta que a API faz em
# producao), so' que guardado em processo em vez de Redis.
_backend = _cfg.celery_result_backend if not _cfg.celery_task_eager else "cache+memory://"

celery_app = Celery(
    "efraim",
    broker=_cfg.celery_broker_url,
    backend=_backend,
)
celery_app.conf.update(
    task_always_eager=_cfg.celery_task_eager,
    task_eager_propagates=True,
    task_store_eager_result=True,
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Sao_Paulo",
)
