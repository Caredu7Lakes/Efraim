"""Modelos SQLAlchemy. lista_id e FK NOT NULL; historico indexado por nome normalizado."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _agora() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Role(Base):
    __tablename__ = "role"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(50), unique=True)
    perms: Mapped[str] = mapped_column(Text, default="")  # csv de permissoes


class Usuario(Base):
    __tablename__ = "usuario"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"))
    # None para contas de bootstrap criadas por seed_dev.py (RBAC, sem login
    # via /auth ainda); auto-registro sempre preenche.
    senha_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    justificativa: Mapped[str | None] = mapped_column(Text, default=None)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class Categoria(Base):
    __tablename__ = "categoria"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(50), unique=True)
    pontos_venda: Mapped[str] = mapped_column(Text, default="")  # json


class ListaCompra(Base):
    __tablename__ = "lista_compra"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), default=None)
    escopo: Mapped[str] = mapped_column(String(20))
    localizacao: Mapped[str | None] = mapped_column(String(120), default=None)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    resultados: Mapped[list[ResultadoBusca]] = relationship(back_populates="lista")


class ResultadoBusca(Base):
    __tablename__ = "resultado_busca"
    id: Mapped[int] = mapped_column(primary_key=True)
    # FK NOT NULL: o banco recusa registro orfao (corrige o bug de lista_id nulo)
    lista_id: Mapped[int] = mapped_column(ForeignKey("lista_compra.id"), nullable=False)
    produto: Mapped[str] = mapped_column(String(255))
    marca: Mapped[str | None] = mapped_column(String(120), default=None)
    preco_centavos: Mapped[int | None] = mapped_column(Integer, default=None)  # nullable
    moeda: Mapped[str] = mapped_column(String(8), default="BRL")
    local: Mapped[str] = mapped_column(String(255))
    link: Mapped[str] = mapped_column(Text)
    fonte: Mapped[str] = mapped_column(String(60))
    disponibilidade: Mapped[str] = mapped_column(String(20), default="desconhecida")
    observacoes: Mapped[str | None] = mapped_column(Text, default=None)  # contatos
    coletado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    lista: Mapped[ListaCompra] = relationship(back_populates="resultados")


class HistoricoPreco(Base):
    __tablename__ = "historico_preco"
    id: Mapped[int] = mapped_column(primary_key=True)
    produto_normalizado: Mapped[str] = mapped_column(String(255))
    local: Mapped[str] = mapped_column(String(255))
    preco_centavos: Mapped[int] = mapped_column(Integer)
    variacao_pct: Mapped[float | None] = mapped_column(Float, default=None)
    dias_desde_ultima: Mapped[int | None] = mapped_column(Integer, default=None)
    coletado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class JobBusca(Base):
    """Dono de cada job assincrono (ETAPA 0/2): amarra o `job_id` do Celery ao
    usuario que disparou a busca, pra `GET /buscas/{job_id}` recusar acesso
    cruzado entre usuarios (isolamento logico - ver `api/deps.py`)."""
    __tablename__ = "job_busca"
    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class VariacaoBusca(Base):
    """Variacoes de query aprendidas de "As pessoas tambem perguntam" do
    Google (Bloco C, camada 1) - persistidas POR CATEGORIA, nao por produto
    especifico, pra reusar entre buscas diferentes do mesmo tipo de item
    (pedido do usuario, 20/08: "essas variacoes encontradas devem ficar
    armazenadas para serem computadas e utilizadas como as que mais vezes
    aparecem"). `vezes_encontrada` incrementa quando a MESMA variacao
    reaparece numa busca futura - e' o que da' o "as que mais aparecem"."""
    __tablename__ = "variacao_busca"
    __table_args__ = (UniqueConstraint("categoria", "variacao", name="uq_categoria_variacao"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    categoria: Mapped[str] = mapped_column(String(50), index=True)
    variacao: Mapped[str] = mapped_column(String(500))
    vezes_encontrada: Mapped[int] = mapped_column(Integer, default=1)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


Index("idx_resultado_lista", ResultadoBusca.lista_id)
Index(
    "idx_hist_produto_local",
    HistoricoPreco.produto_normalizado,
    HistoricoPreco.local,
    HistoricoPreco.coletado_em.desc(),
)
