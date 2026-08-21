from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _email() -> str:
    return f"auth-{uuid.uuid4().hex[:8]}@teste.local"


def test_registrar_e_logar():
    email = _email()
    r = client.post("/auth/registrar", json={"email": email, "senha": "senha12345"})
    assert r.status_code == 201
    assert r.json()["email"] == email

    r = client.post("/auth/login", json={"email": email, "senha": "senha12345"})
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    assert r.json()["access_token"]


def test_registrar_email_duplicado_e_409():
    email = _email()
    client.post("/auth/registrar", json={"email": email, "senha": "senha12345"})
    r = client.post("/auth/registrar", json={"email": email, "senha": "outrasenha123"})
    assert r.status_code == 409


def test_senha_curta_e_422():
    r = client.post("/auth/registrar", json={"email": _email(), "senha": "curta"})
    assert r.status_code == 422


def test_login_senha_errada_e_401():
    email = _email()
    client.post("/auth/registrar", json={"email": email, "senha": "senha12345"})
    r = client.post("/auth/login", json={"email": email, "senha": "senhaerrada"})
    assert r.status_code == 401


def test_login_email_inexistente_e_401():
    r = client.post("/auth/login", json={"email": _email(), "senha": "qualquercoisa123"})
    assert r.status_code == 401


def test_me_com_token_valido():
    email = _email()
    client.post("/auth/registrar", json={"email": email, "senha": "senha12345"})
    login = client.post("/auth/login", json={"email": email, "senha": "senha12345"})
    token = login.json()["access_token"]

    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == email


def test_me_sem_token_e_401():
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_com_token_invalido_e_401():
    r = client.get("/auth/me", headers={"Authorization": "Bearer token-fajuto"})
    assert r.status_code == 401
