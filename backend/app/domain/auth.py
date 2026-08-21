"""Identidade (ETAPA 0): hash de senha e JWT. Sem I/O — nao toca banco nem
rede, so' criptografia/codificacao, mesmo padrao de `normalizador.py` — por
isso mora em domain/ e nao em persistence/ ou api/.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import Settings


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("utf-8"))


def criar_token(usuario_id: int, cfg: Settings) -> str:
    agora = datetime.now(UTC)
    payload = {
        "sub": str(usuario_id),
        "iat": agora,
        "exp": agora + timedelta(minutes=cfg.jwt_expira_minutos),
    }
    return jwt.encode(payload, cfg.jwt_secret_key, algorithm=cfg.jwt_algorithm)


class TokenInvalidoError(Exception):
    pass


def usuario_id_do_token(token: str, cfg: Settings) -> int:
    try:
        payload = jwt.decode(token, cfg.jwt_secret_key, algorithms=[cfg.jwt_algorithm])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise TokenInvalidoError(str(exc)) from exc
