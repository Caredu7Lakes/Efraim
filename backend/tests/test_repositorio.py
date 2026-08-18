from datetime import UTC, datetime

import pytest

from app.domain.models import Disponibilidade, Oferta
from app.persistence.repositorio import RepositorioSQL


def _oferta(preco: int, local: str = "Loja X") -> Oferta:
    return Oferta(
        produto="produto teste repositorio", local=local, link="http://x",
        fonte="teste", coletado_em=datetime.now(UTC), preco_centavos=preco,
        disponibilidade=Disponibilidade.EM_ESTOQUE,
    )


@pytest.mark.asyncio
async def test_criar_lista_devolve_id_usavel_em_salvar():
    repo = RepositorioSQL()
    lista_id = await repo.criar_lista(escopo="nacional", localizacao=None)
    assert lista_id is not None
    await repo.salvar(lista_id, [_oferta(1000)])  # nao deve levantar (FK valida)


@pytest.mark.asyncio
async def test_salvar_sem_lista_id_valido_levanta_erro_fk():
    repo = RepositorioSQL()
    with pytest.raises(Exception):  # noqa: B017 - FK NOT NULL/violacao, tipo varia por driver
        await repo.salvar(999_999_999, [_oferta(1000)])


@pytest.mark.asyncio
async def test_variacao_detecta_diferenca_de_preco():
    repo = RepositorioSQL()
    lista_id = await repo.criar_lista(escopo="nacional", localizacao=None)
    await repo.salvar(lista_id, [_oferta(1000, local="Loja Variacao")])

    var = await repo.variacao("produto teste repositorio", "Loja Variacao", 1200)
    assert var is not None
    assert var["variacao_pct"] == pytest.approx(20.0)
