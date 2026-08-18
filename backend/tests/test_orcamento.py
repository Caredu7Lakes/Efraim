import pytest

from app.sourcing.orcamento import OrcamentoExcedidoError, OrcamentoMCP


def test_registra_ate_o_limite():
    o = OrcamentoMCP(limite_por_job=3)
    o.registrar_chamada("a")
    o.registrar_chamada("a")
    o.registrar_chamada("b")
    assert o.total_usado() == 3
    assert o.usadas_no_bloco("a") == 2
    assert o.usadas_no_bloco("b") == 1


def test_estoura_levanta_erro_e_nao_incrementa():
    o = OrcamentoMCP(limite_por_job=1)
    o.registrar_chamada("a")
    with pytest.raises(OrcamentoExcedidoError):
        o.registrar_chamada("a")
    assert o.total_usado() == 1


def test_limite_zero_bloqueia_a_primeira_chamada():
    o = OrcamentoMCP(limite_por_job=0)
    with pytest.raises(OrcamentoExcedidoError):
        o.registrar_chamada("a")
