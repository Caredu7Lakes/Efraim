from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.persistence.orm import Base

_settings = get_settings()
engine = create_engine(_settings.database_url, future=True)
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
