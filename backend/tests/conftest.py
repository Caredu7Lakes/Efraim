import os

# Precisa vir ANTES de qualquer `import app...`: `app.persistence.db` le
# `DATABASE_URL` uma unica vez, no import (engine e' modulo-level). Testes
# usam seu proprio arquivo sqlite, nunca o `efraim_dev.db` de dev - pytest
# garante que este conftest.py roda antes de qualquer teste do diretorio ser
# coletado, entao isto vence a leitura de `.env` feita por `get_settings()`.
os.environ.setdefault("DATABASE_URL", "sqlite:///./efraim_test.db")

import pytest  # noqa: E402

from app.persistence.db import criar_tabelas  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _tabelas_de_teste():
    criar_tabelas()


@pytest.fixture
def html_com_contatos() -> str:
    return """
    <html><body>
      <a href="https://wa.me/5511988887777">WhatsApp</a>
      <a href="https://api.whatsapp.com/send?phone=551133224455">fale</a>
      contato: vendas@loja.com.br / suporte@loja.com.br
      Tel: (11) 3322-4455
      <form action="/enviar-cotacao" method="post"></form>
    </body></html>
    """
