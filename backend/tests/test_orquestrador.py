
import pytest

from app.domain.classificacao import montar_consulta_local, montar_consulta_produto
from app.domain.models import Escopo, ItemProduto, Localizacao
from app.sourcing.adapters.fake_source import FakeLocalSource, FakePriceSource
from app.sourcing.orquestrador import Orquestrador


@pytest.mark.asyncio
async def test_pipeline_fake_end_to_end():
    item = ItemProduto(nome="conector jack P10")
    cp = montar_consulta_produto(item, Escopo.LOCAL)
    cl = montar_consulta_local(item, Localizacao(cidade="Itatiba"))
    orq = Orquestrador(price_sources=[FakePriceSource()], local_sources=[FakeLocalSource()])
    r = await orq.executar(cp, cl)
    # 2 novos com preco (o usado desempata por baixo), 1 sem preco do local
    assert len(r.top7_online) >= 1
    assert r.top7_online[0].preco_centavos == 1550
    assert len(r.sem_preco) == 1


class FonteQueFalha:
    nome = "quebrada"
    async def buscar(self, consulta):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_fonte_quebrada_nao_derruba_o_run():
    item = ItemProduto(nome="cimento")
    cp = montar_consulta_produto(item, Escopo.NACIONAL)
    orq = Orquestrador(price_sources=[FakePriceSource(), FonteQueFalha()])
    r = await orq.executar(cp)
    assert len(r.top7_online) >= 1  # entregou apesar da fonte quebrada


@pytest.mark.asyncio
async def test_circuit_breaker_abre_apos_falhas():
    orq = Orquestrador(price_sources=[FonteQueFalha()])
    item = ItemProduto(nome="x")
    cp = montar_consulta_produto(item, Escopo.NACIONAL)
    for _ in range(3):
        await orq.executar(cp)
    assert orq._breaker("quebrada").aberto is True
