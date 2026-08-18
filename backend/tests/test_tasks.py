"""Task Celery em modo eager (sem broker real) — mesmo pipeline que rodava no
runner in-process de v1, agora atras do contrato serializavel."""
from __future__ import annotations

from app.jobs.tasks import executar_busca_task
from app.persistence.db import sessao
from app.persistence.orm import ResultadoBusca


def test_executar_busca_task_end_to_end_fake():
    payload = {
        "produtos": [{"nome": "conector jack P10", "marca": None, "quantidade": 1,
                       "unidade": "un", "qualidade": None}],
        "escopo": "nacional",
        "cidade": None,
        "cep": None,
        "lista_id": None,
    }
    resultado = executar_busca_task.apply(args=[payload]).get()
    assert resultado["top7_online"]
    assert resultado["top7_online"][0]["preco_centavos"] == 1550


def test_executar_busca_persiste_resultado_busca():
    """A ETAPA 6 (persistencia) precisa de fato gravar, nao so' nao quebrar o
    pipeline — `_persistir` engole excecao de proposito (resiliencia), entao
    sem este teste um bug de persistencia passaria em silencio."""
    payload = {
        "produtos": [{"nome": "teste persistencia unico xyz", "marca": None,
                       "quantidade": 1, "unidade": "un", "qualidade": None}],
        "escopo": "nacional",
        "cidade": None,
        "cep": None,
        "lista_id": None,
    }
    executar_busca_task.apply(args=[payload]).get()
    with sessao() as s:
        gravados = s.query(ResultadoBusca).filter_by(produto="teste persistencia unico xyz").all()
    assert len(gravados) >= 1
    assert gravados[0].lista_id is not None
