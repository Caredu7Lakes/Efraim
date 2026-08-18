
from datetime import UTC, datetime

import pytest

from app.domain.classificacao import montar_consulta_local, montar_consulta_produto
from app.domain.models import Escopo, ItemProduto, Localizacao, Oferta
from app.persistence.cache import CacheTTL
from app.sourcing.adapters.fake_source import FakeLocalSource, FakePriceSource
from app.sourcing.erros import MCPRateLimitError
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
    async def buscar(self, consulta, orcamento):
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


class FonteRateLimitDepoisOk:
    """Simula 429 na primeira tentativa e sucesso na segunda."""
    nome = "rate-limit-depois-ok"

    def __init__(self) -> None:
        self.chamadas = 0

    async def buscar(self, consulta, orcamento):
        self.chamadas += 1
        if self.chamadas == 1:
            raise MCPRateLimitError(self.nome, retry_after_s=0.01)
        return [Oferta(produto="x", local="L", link="http://x", fonte=self.nome,
                        coletado_em=datetime.now(UTC), preco_centavos=100)]


@pytest.mark.asyncio
async def test_rate_limit_tenta_de_novo_sem_abrir_breaker():
    item = ItemProduto(nome="x")
    cp = montar_consulta_produto(item, Escopo.NACIONAL)
    fonte = FonteRateLimitDepoisOk()
    orq = Orquestrador(price_sources=[fonte], backoff_rate_limit_s=0.01)
    r = await orq.executar(cp)
    assert fonte.chamadas == 2
    assert len(r.top7_online) == 1
    assert orq._breaker(fonte.nome).aberto is False


class FonteRateLimitPersistente:
    """429 sempre — deve desistir apos o teto de tentativas e abrir o breaker."""
    nome = "rate-limit-sempre"

    async def buscar(self, consulta, orcamento):
        raise MCPRateLimitError(self.nome, retry_after_s=0.01)


@pytest.mark.asyncio
async def test_rate_limit_persistente_desiste_e_conta_como_falha():
    item = ItemProduto(nome="x")
    cp = montar_consulta_produto(item, Escopo.NACIONAL)
    fonte = FonteRateLimitPersistente()
    orq = Orquestrador(
        price_sources=[fonte], backoff_rate_limit_s=0.01, max_tentativas_rate_limit=2
    )
    for _ in range(3):
        r = await orq.executar(cp)
    assert r.top7_online == []
    # so' abre apos esgotar as tentativas de retry EM CADA run (3 runs = 3 falhas)
    assert orq._breaker(fonte.nome).aberto is True


class FonteOrcamentoCaro:
    """Registra 1 chamada MCP real por busca — usado pra testar o teto de custo."""
    nome = "orcamento-caro"

    async def buscar(self, consulta, orcamento):
        orcamento.registrar_chamada("price")
        return [Oferta(produto="x", local="L", link="http://x", fonte=self.nome,
                        coletado_em=datetime.now(UTC), preco_centavos=100)]


@pytest.mark.asyncio
async def test_orcamento_esgotado_nao_conta_como_falha_de_fonte():
    item = ItemProduto(nome="x")
    cp = montar_consulta_produto(item, Escopo.NACIONAL)
    fonte = FonteOrcamentoCaro()
    orq = Orquestrador(price_sources=[fonte], max_chamadas_mcp_por_job=0)
    r = await orq.executar(cp)
    assert r.top7_online == []
    assert orq._breaker(fonte.nome).aberto is False  # nao e' falha, e' teto de custo


class FonteContaChamadas:
    nome = "conta-chamadas"

    def __init__(self) -> None:
        self.chamadas = 0

    async def buscar(self, consulta, orcamento):
        self.chamadas += 1
        return [Oferta(produto="x", local="L", link="http://x", fonte=self.nome,
                        coletado_em=datetime.now(UTC), preco_centavos=100)]


@pytest.mark.asyncio
async def test_cache_evita_segunda_chamada_pela_mesma_consulta():
    item = ItemProduto(nome="x")
    cp = montar_consulta_produto(item, Escopo.NACIONAL)
    fonte = FonteContaChamadas()
    orq = Orquestrador(price_sources=[fonte], cache=CacheTTL(ttl_segundos=60))
    await orq.executar(cp)
    await orq.executar(cp)
    assert fonte.chamadas == 1
