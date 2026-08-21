import os

# Precisa vir ANTES de qualquer `import app...`: `app.persistence.db` le
# `DATABASE_URL` uma unica vez, no import (engine e' modulo-level). Testes
# usam seu proprio arquivo sqlite, nunca o `efraim_dev.db` de dev - pytest
# garante que este conftest.py roda antes de qualquer teste do diretorio ser
# coletado, entao isto vence a leitura de `.env` feita por `get_settings()`.
os.environ.setdefault("DATABASE_URL", "sqlite:///./efraim_test.db")
# mesma logica: a suite NUNCA pode depender do que esta' configurado no
# .env de dev de quem esta' rodando (ex.: EFRAIM_FONTE=apify com token real
# ligado pra testar manualmente) - senao testes que nao mockam rede batem
# na API paga de verdade e travam a suite por minutos (achado ao vivo,
# 19/08, rodando com token real da Apify no .env).
os.environ.setdefault("EFRAIM_FONTE", "fake")
# mesmo motivo: `_aprender_variacoes` (jobs/tasks.py, Bloco C - aprendizado
# de variacoes via Google direto) le BRIGHTDATA_WEB_UNLOCKER_ZONE/TOKEN
# direto de `Settings`, SEM passar pelo gate de EFRAIM_FONTE - sem isto,
# `test_executar_busca_task_end_to_end_fake` bateria na API real da Bright
# Data com o token de verdade do .env, toda vez que a suite roda (achado
# em revisao, 20/08, antes de rodar a suite de novo).
os.environ.setdefault("BRIGHTDATA_WEB_UNLOCKER_ZONE", "")
os.environ.setdefault("BRIGHTDATA_WEB_UNLOCKER_TOKEN", "")

import pytest  # noqa: E402

from scripts.seed_dev import seed  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _tabelas_de_teste():
    # seed() cria as tabelas E semeia os papeis (inclui "usuario", exigido
    # por RepositorioUsuarios.criar) - idempotente, mesmo caminho de dev.
    seed()


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
