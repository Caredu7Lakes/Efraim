"""Fumaca da API /buscas ponta a ponta — POST enfileira via Celery (eager em
teste), GET le o resultado ja pronto na mesma chamada (task sincrona)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_criar_e_consultar_busca_fake():
    resp = client.post("/buscas", json={
        "produtos": [{"nome": "conector jack P10"}],
        "escopo": "nacional",
    })
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    status = client.get(f"/buscas/{job_id}")
    assert status.status_code == 200
    corpo = status.json()
    assert corpo["status"] == "concluido"
    assert corpo["resultado"]["top7_online"]


def test_lista_vazia_e_422():
    resp = client.post("/buscas", json={"produtos": [], "escopo": "nacional"})
    assert resp.status_code == 422


def test_escopo_invalido_e_422_nao_500():
    """Antes do fix, escopo invalido so' estourava dentro da task Celery
    (500 cru); agora o proprio FastAPI rejeita na validacao do payload."""
    resp = client.post("/buscas", json={
        "produtos": [{"nome": "x"}],
        "escopo": "nacionl",  # typo proposital
    })
    assert resp.status_code == 422
