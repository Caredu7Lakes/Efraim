"""Rotas de identidade (ETAPA 0): registro e login por email/senha."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_usuario_atual
from app.api.schemas import LoginIn, RegistroIn, TokenOut, UsuarioOut
from app.config import get_settings
from app.domain.auth import criar_token, verificar_senha
from app.persistence.orm import Usuario
from app.persistence.usuarios import EmailJaCadastradoError, RepositorioUsuarios

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/registrar", status_code=201)
async def registrar(payload: RegistroIn) -> UsuarioOut:
    try:
        usuario = await RepositorioUsuarios().criar(email=payload.email, senha=payload.senha)
    except EmailJaCadastradoError:
        raise HTTPException(409, "email ja cadastrado") from None
    return UsuarioOut(id=usuario.id, email=usuario.email)


@router.post("/login")
async def login(payload: LoginIn) -> TokenOut:
    usuario = await RepositorioUsuarios().por_email(payload.email)
    # mesma mensagem pra email inexistente e senha errada - nao da' pra
    # descobrir se um email esta cadastrado so' tentando logar.
    senha_ok = usuario is not None and usuario.senha_hash is not None and \
        verificar_senha(payload.senha, usuario.senha_hash)
    if not senha_ok:
        raise HTTPException(401, "credenciais invalidas")
    token = criar_token(usuario.id, get_settings())
    return TokenOut(access_token=token)


@router.get("/me")
async def me(usuario: Usuario = Depends(get_usuario_atual)) -> UsuarioOut:
    return UsuarioOut(id=usuario.id, email=usuario.email)
