"""Fumaca da API /buscas ponta a ponta — POST enfileira via Celery (eager em
teste), GET le o resultado ja pronto na mesma chamada (task sincrona).
`/buscas` exige autenticacao; helper `_token` registra+loga um usuario novo
por teste (email unico) pra nao colidir entre testes."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _token(prefixo: str = "u") -> str:
    email = f"{prefixo}-{uuid.uuid4().hex[:8]}@teste.local"
    client.post("/auth/registrar", json={"email": email, "senha": "senha12345"})
    resp = client.post("/auth/login", json={"email": email, "senha": "senha12345"})
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_criar_e_consultar_busca_fake():
    token = _token()
    resp = client.post("/buscas", json={
        "produtos": [{"nome": "arroz tipo 1 5kg"}],  # categoria "alimento" - so' nacional
        "escopo": "nacional",
    }, headers=_auth(token))
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    status = client.get(f"/buscas/{job_id}", headers=_auth(token))
    assert status.status_code == 200
    corpo = status.json()
    assert corpo["status"] == "concluido"
    resultados = corpo["resultado"]["resultados"]
    assert len(resultados) == 1
    r = resultados[0]
    assert r["escopo_efetivo"] == ["nacional"]
    assert r["top7_online"]
    # campos que existem no dominio (Oferta) mas antes desapareciam na
    # resposta - achado em teste real (19/08).
    oferta = r["top7_online"][0]
    assert "condicao" in oferta
    assert "frete_centavos" in oferta
    assert "coletado_em" in oferta
    assert "contato" in oferta


def test_multiplos_produtos_todos_processados():
    """Antes so' o primeiro produto da lista era processado (limite
    documentado do v1) - corrigido junto com o roteamento por idioma."""
    token = _token()
    resp = client.post("/buscas", json={
        "produtos": [{"nome": "arroz tipo 1"}, {"nome": "feijao carioca"}],
        "escopo": "nacional",
    }, headers=_auth(token))
    job_id = resp.json()["job_id"]

    corpo = client.get(f"/buscas/{job_id}", headers=_auth(token)).json()
    resultados = corpo["resultado"]["resultados"]
    assert {r["produto"] for r in resultados} == {"arroz tipo 1", "feijao carioca"}


def test_produto_eletronico_em_ingles_roda_tambem_internacional():
    """LED com nome tecnico em ingles: categoria 'eletronico' ja' basta pra
    rodar o Bloco D, mesmo com escopo='nacional' pedido. Termo internacional
    e' o nome como veio (ja' em ingles - nao ha nada pra adaptar)."""
    token = _token()
    resp = client.post("/buscas", json={
        "produtos": [{"nome": "LED 3MM round Long lead diffused red"}],
        "escopo": "nacional",
    }, headers=_auth(token))
    job_id = resp.json()["job_id"]

    corpo = client.get(f"/buscas/{job_id}", headers=_auth(token)).json()
    r = corpo["resultado"]["resultados"][0]
    assert r["idioma_detectado"] == "en"
    assert r["categoria"] == "eletronico"
    assert set(r["escopo_efetivo"]) == {"nacional", "internacional"}
    assert r["termo_busca_internacional"] == "LED 3MM round Long lead diffused red"


def test_produto_eletronico_em_portugues_adapta_termo_internacional():
    """Conector jack P10: nome em portugues, mas categoria 'eletronico'
    tambem roda o Bloco D - com o termo ADAPTADO (senao a busca internacional
    voltaria vazia, ninguem anuncia 'conector jack p10 estereo' la' fora)."""
    token = _token()
    resp = client.post("/buscas", json={
        "produtos": [{"nome": "conector jack p10 stereo profissional"}],
        "escopo": "nacional",
    }, headers=_auth(token))
    job_id = resp.json()["job_id"]

    corpo = client.get(f"/buscas/{job_id}", headers=_auth(token)).json()
    r = corpo["resultado"]["resultados"][0]
    assert r["idioma_detectado"] == "pt"
    assert r["categoria"] == "eletronico"
    assert set(r["escopo_efetivo"]) == {"nacional", "internacional"}
    assert r["termo_busca_internacional"] == "3.5mm stereo jack connector"


def test_local_sem_cep_e_422():
    """CEP e' obrigatorio pra escopo=local (achado em teste real, 19/08:
    antes nao havia nenhum criterio - cidade e cep eram opcionais)."""
    token = _token()
    resp = client.post("/buscas", json={
        "produtos": [{"nome": "racao para gato"}],
        "escopo": "local",
        "cidade": "Itatiba",
    }, headers=_auth(token))
    assert resp.status_code == 422


def test_local_com_cep_inclui_contato_da_fonte_local():
    token = _token()
    resp = client.post("/buscas", json={
        "produtos": [{"nome": "racao para gato"}],
        "escopo": "local",
        "cep": "13252-000",
        "cidade": "Itatiba",
    }, headers=_auth(token))
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    corpo = client.get(f"/buscas/{job_id}", headers=_auth(token)).json()
    sem_preco = corpo["resultado"]["resultados"][0]["sem_preco"]
    assert sem_preco
    assert sem_preco[0]["contato"] is not None
    assert sem_preco[0]["contato"]["whatsapp"]


def test_lista_vazia_e_422():
    token = _token()
    resp = client.post("/buscas", json={"produtos": [], "escopo": "nacional"}, headers=_auth(token))
    assert resp.status_code == 422


def test_escopo_invalido_e_422_nao_500():
    """Antes do fix, escopo invalido so' estourava dentro da task Celery
    (500 cru); agora o proprio FastAPI rejeita na validacao do payload."""
    token = _token()
    resp = client.post("/buscas", json={
        "produtos": [{"nome": "x"}],
        "escopo": "nacionl",  # typo proposital
    }, headers=_auth(token))
    assert resp.status_code == 422


def test_sem_token_e_401():
    resp = client.post("/buscas", json={"produtos": [{"nome": "x"}], "escopo": "nacional"})
    assert resp.status_code == 401


def test_usuario_nao_ve_busca_de_outro():
    token_a = _token("a")
    token_b = _token("b")

    resp = client.post("/buscas", json={
        "produtos": [{"nome": "conector jack P10"}],
        "escopo": "nacional",
    }, headers=_auth(token_a))
    job_id = resp.json()["job_id"]

    # dono ve normalmente
    assert client.get(f"/buscas/{job_id}", headers=_auth(token_a)).status_code == 200
    # outro usuario nao ve o job de A - 404, nao 403 (nao revela que existe)
    resp_b = client.get(f"/buscas/{job_id}", headers=_auth(token_b))
    assert resp_b.status_code == 404
