from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.persistence.orm import Base

_settings = get_settings()
engine = create_engine(_settings.database_url, future=True)


@event.listens_for(engine, "connect")
def _habilitar_fk_sqlite(dbapi_connection, _connection_record) -> None:
    """SQLite ignora FOREIGN KEY por padrao, por conexao - sem isto, o FK NOT
    NULL de `ResultadoBusca.lista_id` (ARQUITETURA.md secao 13, "banco
    recusa registro orfao") nao e' de fato aplicado em dev/teste. So' roda
    no dialeto sqlite - Postgres (producao) ja aplica FK nativamente.
    """
    if engine.dialect.name == "sqlite":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def criar_tabelas() -> None:
    """Conveniencia p/ dev (sqlite). Em producao use Alembic."""
    Base.metadata.create_all(engine)


@contextmanager
def sessao() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
