"""Dependencia FastAPI que protege rotas com JWT (ETAPA 0)."""
from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.domain.auth import TokenInvalidoError, usuario_id_do_token
from app.persistence.orm import Usuario
from app.persistence.usuarios import RepositorioUsuarios

_bearer = HTTPBearer(auto_error=False)


async def get_usuario_atual(
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Usuario:
    if credenciais is None:
        raise HTTPException(401, "token ausente")
    cfg = get_settings()
    try:
        usuario_id = usuario_id_do_token(credenciais.credentials, cfg)
    except TokenInvalidoError:
        raise HTTPException(401, "token invalido ou expirado") from None
    usuario = await RepositorioUsuarios().por_id(usuario_id)
    if usuario is None:
        raise HTTPException(401, "usuario nao encontrado")
    return usuario
