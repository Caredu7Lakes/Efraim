"""Seed idempotente (rodavel N vezes sem duplicar).

UNICA fonte de admins, papeis e config de dominio. Nada de SQL ad-hoc:
todo administrador vem daqui, aparece em diff, com autoria e justificativa.

    python -m scripts.seed_dev
"""
from __future__ import annotations

import json

from app.domain.classificacao import PONTOS_VENDA
from app.persistence.db import criar_tabelas, sessao
from app.persistence.orm import Categoria, Role, Usuario

ROLES = {
    "usuario": "lista:criar,busca:disparar,resultado:ver",
    "operador": "lista:criar,busca:disparar,resultado:ver,cotacao:enviar",
    "admin": "*",
}

ADMINS = [
    # (email, role, justificativa) — rastreavel
    ("admin@efraim.local", "admin", "bootstrap Efraim v1"),
]

CATEGORIAS_18 = [
    "eletronico", "informatica", "alimento", "hortifruti", "pet", "construcao",
    "ferramenta", "limpeza", "vestuario", "farmacia", "papelaria", "automotivo",
    "movel", "eletrodomestico", "brinquedo", "esporte", "beleza", "geral",
]


def _upsert_role(s, nome: str, perms: str) -> Role:
    r = s.query(Role).filter_by(nome=nome).one_or_none()
    if r is None:
        r = Role(nome=nome, perms=perms)
        s.add(r)
    else:
        r.perms = perms
    s.flush()
    return r


def _upsert_admin(s, email: str, role_nome: str, justificativa: str) -> None:
    role = s.query(Role).filter_by(nome=role_nome).one()
    u = s.query(Usuario).filter_by(email=email).one_or_none()
    if u is None:
        s.add(Usuario(email=email, role_id=role.id, justificativa=justificativa))
    else:
        u.role_id = role.id
        u.justificativa = justificativa


def _upsert_categoria(s, nome: str) -> None:
    pv = json.dumps(PONTOS_VENDA.get(nome, {}), ensure_ascii=False)
    c = s.query(Categoria).filter_by(nome=nome).one_or_none()
    if c is None:
        s.add(Categoria(nome=nome, pontos_venda=pv))
    else:
        c.pontos_venda = pv


def seed() -> None:
    criar_tabelas()
    with sessao() as s:
        for nome, perms in ROLES.items():
            _upsert_role(s, nome, perms)
        for email, role, just in ADMINS:
            _upsert_admin(s, email, role, just)
        for cat in CATEGORIAS_18:
            _upsert_categoria(s, cat)
    print("seed concluido (idempotente).")


if __name__ == "__main__":
    seed()
