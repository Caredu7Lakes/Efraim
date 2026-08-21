"""`buscar_mercadolivre` - so' busca a pagina 0 hoje (`MAX_PAGINAS = 1`).
Achado real (20/08, ver docstring de `app.sourcing.busca_mercadolivre`): o
robots.txt do Mercado Livre bloqueia `_Desde_`/`_NoIndex_True` (o padrao de
URL da paginacao real do site) e o Bright Data Web Unlocker respeita isso
no modo residencial sem KYC da conta - tentar pagina >0 so' repetiria uma
falha ja' confirmada, sem gastar orcamento a toa."""
from __future__ import annotations

import httpx
import pytest

from app.sourcing.busca_mercadolivre import MAX_PAGINAS, buscar_mercadolivre
from app.sourcing.orcamento import OrcamentoMCP

_CARTAO = """
<div class="andes-card poly-card poly-card--grid-card">
<div class="poly-card__content"><h3 class="poly-component__title-wrapper">
<a href="https://www.mercadolivre.com.br/produto/p/MLB123"
target="_self" class="poly-component__title">Conector Jack P10 Stereo</a></h3>
<span class="andes-money-amount poly-price__part-price" data-andes-money-amount-size="24">
<span class="andes-money-amount__fraction" aria-hidden="true"
data-andes-money-amount-fraction="true">45</span></span>
</div></div></div>
"""


class _RespostaFalsa:
    def __init__(self, status_code: int, texto: str) -> None:
        self.status_code = status_code
        self.text = texto
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro", request=None, response=self)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_sem_credenciais_devolve_vazio_sem_chamar_rede(monkeypatch):
    chamou = False

    async def _post_falso(self, url, headers=None, json=None):
        nonlocal chamou
        chamou = True
        return _RespostaFalsa(200, "")

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    ofertas = await buscar_mercadolivre(
        "conector jack p10", zone=None, token=None,
        orcamento=OrcamentoMCP(limite_por_job=400),
    )
    assert ofertas == []
    assert not chamou


def test_max_paginas_e_1_por_causa_do_robots_txt_real():
    """Nao e' um numero arbitrario - e' o que o proprio robots.txt do
    Mercado Livre permite hoje (ver docstring do modulo)."""
    assert MAX_PAGINAS == 1


@pytest.mark.asyncio
async def test_busca_so_a_pagina_0_nunca_tenta_desde(monkeypatch):
    """Pagina >0 usaria `_Desde_`, que o robots.txt bloqueia - o codigo nao
    deve nem tentar (gastaria orcamento numa falha ja' conhecida)."""
    chamadas: list[str] = []

    async def _post_falso(self, url, headers=None, json=None):
        chamadas.append(json["url"])
        return _RespostaFalsa(200, _CARTAO)

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    ofertas = await buscar_mercadolivre(
        "conector jack p10 stereo", zone="efraim_1", token="token-fake",
        orcamento=OrcamentoMCP(limite_por_job=400),
    )

    assert len(chamadas) == 1
    assert "_Desde_" not in chamadas[0]
    assert len(ofertas) == 1
    assert ofertas[0].preco_centavos == 4500
    assert ofertas[0].fonte == "mercadolivre-direto"
    assert ofertas[0].produto == "Conector Jack P10 Stereo"


@pytest.mark.asyncio
async def test_falha_na_pagina_0_devolve_vazio_sem_quebrar(monkeypatch):
    async def _post_falso(self, url, headers=None, json=None):
        return _RespostaFalsa(500, "")

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    ofertas = await buscar_mercadolivre(
        "conector jack p10 stereo", zone="efraim_1", token="token-fake",
        orcamento=OrcamentoMCP(limite_por_job=400),
    )
    assert ofertas == []
