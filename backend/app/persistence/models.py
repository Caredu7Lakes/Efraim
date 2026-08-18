"""Modelo relacional (SQLAlchemy 2.0). Correcoes de concepcao aplicadas:
- ResultadoBusca.lista_id = FK NOT NULL (+ indice)
- HistoricoPreco indexado por (produto_normalizado, local, coletado_em)
Ver docs/efraim_arquitetura.md, secao 9.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(Base):
    __tablename__ = "role"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(50), unique=True)


class Usuario(Base):
    __tablename__ = "usuario"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"))


class ListaCompra(Base):
    __tablename__ = "lista_compra"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    escopo: Mapped[str] = mapped_column(String(20))
    localizacao: Mapped[str | None] = mapped_column(String(255))
    criado_em: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    resultados: Mapped[list[ResultadoBusca]] = relationship(back_populates="lista")


class ResultadoBusca(Base):
    __tablename__ = "resultado_busca"
    id: Mapped[int] = mapped_column(primary_key=True)
    lista_id: Mapped[int] = mapped_column(ForeignKey("lista_compra.id"), nullable=False, index=True)
    produto: Mapped[str] = mapped_column(String(255))
    preco_centavos: Mapped[int | None] = mapped_column(nullable=True)
    local: Mapped[str] = mapped_column(String(255))
    link: Mapped[str] = mapped_column(String(1024))
    fonte: Mapped[str] = mapped_column(String(64))
    disponibilidade: Mapped[str] = mapped_column(String(20), default="desconhecida")
    coletado_em: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    lista: Mapped[ListaCompra] = relationship(back_populates="resultados")


class HistoricoPreco(Base):
    __tablename__ = "historico_preco"
    id: Mapped[int] = mapped_column(primary_key=True)
    produto_normalizado: Mapped[str] = mapped_column(String(255))
    local: Mapped[str] = mapped_column(String(255))
    preco_centavos: Mapped[int] = mapped_column()
    variacao_pct: Mapped[float | None] = mapped_column(nullable=True)
    dias_desde_ultima: Mapped[int | None] = mapped_column(nullable=True)
    coletado_em: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    __table_args__ = (
        Index("idx_hist_produto_local", "produto_normalizado", "local", "coletado_em"),
    )


class Categoria(Base):
    __tablename__ = "categoria"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(50), unique=True)
