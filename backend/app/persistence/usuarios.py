"""Persistencia de Usuario e do dono de cada job (ETAPA 0). Schema proprio,
ponto unico de escrita para `usuario`/`job_busca` (nao espalhar em outros
modulos)."""
from __future__ import annotations

from app.domain.auth import hash_senha
from app.persistence.db import sessao
from app.persistence.orm import JobBusca, Role, Usuario


class EmailJaCadastradoError(Exception):
    pass


class RepositorioUsuarios:
    async def criar(self, *, email: str, senha: str) -> Usuario:
        with sessao() as s:
            if s.query(Usuario).filter_by(email=email).one_or_none() is not None:
                raise EmailJaCadastradoError(email)
            # role "usuario" vem do seed idempotente (scripts/seed_dev.py) -
            # nao criamos role aqui, so' referenciamos a ja existente.
            role = s.query(Role).filter_by(nome="usuario").one()
            usuario = Usuario(
                email=email, role_id=role.id, senha_hash=hash_senha(senha),
                justificativa="auto-registro",
            )
            s.add(usuario)
            s.flush()
            return usuario

    async def por_email(self, email: str) -> Usuario | None:
        with sessao() as s:
            return s.query(Usuario).filter_by(email=email).one_or_none()

    async def por_id(self, usuario_id: int) -> Usuario | None:
        with sessao() as s:
            return s.get(Usuario, usuario_id)

    async def registrar_job(self, job_id: str, usuario_id: int) -> None:
        with sessao() as s:
            s.add(JobBusca(job_id=job_id, usuario_id=usuario_id))

    async def dono_do_job(self, job_id: str) -> int | None:
        with sessao() as s:
            jb = s.get(JobBusca, job_id)
            return jb.usuario_id if jb else None
