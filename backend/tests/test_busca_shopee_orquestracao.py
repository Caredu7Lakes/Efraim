"""`buscar_shopee` paginado - mesmo criterio ja' estabelecido em
`variacoes_busca.py`/`busca_mercadolivre.py` (correcao do usuario, 20/08):
pagina sem anuncio novo so' e' pulada, nunca encerra a busca inteira antes
de MAX_PAGINAS."""
from __future__ import annotations

import httpx
import pytest

from app.sourcing.busca_shopee import MAX_PAGINAS, buscar_shopee
from app.sourcing.orcamento import OrcamentoMCP

_CARTAO = """
<li class="col-xs-2-4 shopee-search-item-result__item" data-sqe="item">
<div role="group" aria-label="Product card: Conector Jack P10 Stereo">
<a href="/find_similar_products?catid=1&amp;itemid=555&amp;shopid=222">Similares</a>
<span class="text-shopee-primary">R$</span>
<span class="truncate text-base/5 font-medium">45,00</span>
</div></li>
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
    ofertas = await buscar_shopee(
        "conector jack p10", zone=None, token=None,
        orcamento=OrcamentoMCP(limite_por_job=400),
    )
    assert ofertas == []
    assert not chamou


@pytest.mark.asyncio
async def test_pagina_ate_max_paginas_mesmo_com_pagina_vazia(monkeypatch):
    chamadas: list[str] = []

    async def _post_falso(self, url, headers=None, json=None):
        alvo = json["url"]
        chamadas.append(alvo)
        if "&page=" not in alvo:
            return _RespostaFalsa(200, _CARTAO)
        return _RespostaFalsa(200, "<html>sem anuncio novo aqui</html>")

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    ofertas = await buscar_shopee(
        "conector jack p10 stereo", zone="efraim_1", token="token-fake",
        orcamento=OrcamentoMCP(limite_por_job=400),
    )

    assert len(chamadas) == MAX_PAGINAS
    assert len(ofertas) == 1
    assert ofertas[0].preco_centavos == 4500
    assert ofertas[0].fonte == "shopee-direto"


@pytest.mark.asyncio
async def test_falha_de_rede_numa_pagina_nao_interrompe_as_demais(monkeypatch):
    chamadas: list[str] = []

    async def _post_falso(self, url, headers=None, json=None):
        alvo = json["url"]
        chamadas.append(alvo)
        if len(chamadas) == 2:
            return _RespostaFalsa(500, "")
        if "&page=" not in alvo:
            return _RespostaFalsa(200, _CARTAO)
        return _RespostaFalsa(200, "<html>sem anuncio novo aqui</html>")

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    ofertas = await buscar_shopee(
        "conector jack p10 stereo", zone="efraim_1", token="token-fake",
        orcamento=OrcamentoMCP(limite_por_job=400),
    )

    assert len(chamadas) == MAX_PAGINAS
    assert len(ofertas) == 1
