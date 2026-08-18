from datetime import UTC, datetime

from app.domain.models import Condicao, Disponibilidade, Oferta
from app.sourcing.filtro import filtrar_top7


def _of(preco, cond=Condicao.NOVO, disp=Disponibilidade.EM_ESTOQUE, frete=0):
    return Oferta(produto="x", local="l", link="u", fonte="t",
                  coletado_em=datetime.now(UTC), preco_centavos=preco,
                  condicao=cond, disponibilidade=disp, frete_centavos=frete)


def test_ordena_por_custo_total_e_corta_em_7():
    ofertas = [_of(p) for p in [900, 800, 700, 600, 500, 400, 300, 200, 100]]
    r = filtrar_top7(ofertas)
    assert len(r.top7_online) == 7
    assert r.total_descartados == 2
    assert [o.preco_centavos for o in r.top7_online] == [100, 200, 300, 400, 500, 600, 700]


def test_frete_entra_no_custo_total():
    barato_com_frete = _of(100, frete=1000)   # total 1100
    caro_sem_frete = _of(500, frete=0)         # total 500
    r = filtrar_top7([barato_com_frete, caro_sem_frete])
    assert r.top7_online[0] is caro_sem_frete


def test_usado_e_indisponivel_nao_vencem_por_padrao():
    novo = _of(500)
    usado = _of(100, cond=Condicao.USADO)
    indisp = _of(50, disp=Disponibilidade.INDISPONIVEL)
    r = filtrar_top7([usado, indisp, novo])
    assert r.top7_online[0] is novo


def test_sem_preco_todos_mantidos():
    sem = Oferta(produto="x", local="l", link="u", fonte="t",
                 coletado_em=datetime.now(UTC), preco_centavos=None)
    r = filtrar_top7([sem, sem, _of(100)])
    assert len(r.sem_preco) == 2
    assert len(r.top7_online) == 1
