"""Fixture abaixo reproduz a estrutura REAL confirmada ao vivo (Web
Unlocker, 20/08) contra `shopee.com.br/search?keyword=conector+jack+p10
+stereo` - trecho trimado, nao inventado (ver docstring de
`app.domain.busca_shopee`)."""
from __future__ import annotations

from app.domain.busca_shopee import extrair_resultados_shopee, montar_url_busca_shopee

_CARTAO = """
<li class="col-xs-2-4 shopee-search-item-result__item" data-sqe="item">
<div role="group"
aria-label="Product card: Jack Conector P10 Stereo Femea Para Instrumentos">
<a href="/find_similar_products?catid=100639&amp;itemid=23792476279
&amp;shopid=454971236">Similares</a>
<div class="price"><span class="text-shopee-primary">R$</span>
<span class="truncate text-base/5 font-medium">13,79</span></div>
</div></li>
"""

_CARTAO_SEM_PRECO = """
<li class="col-xs-2-4 shopee-search-item-result__item" data-sqe="item">
<div role="group" aria-label="Product card: Outro Conector Sem Preco Visivel">
<a href="/find_similar_products?catid=1&amp;itemid=999&amp;shopid=111">Similares</a>
</div></li>
"""


def test_montar_url_pagina_zero_sem_page_param():
    url = montar_url_busca_shopee("conector jack p10 stereo")
    assert url == "https://shopee.com.br/search?keyword=conector%20jack%20p10%20stereo"


def test_montar_url_paginas_seguintes_usa_page():
    url = montar_url_busca_shopee("conector jack p10 stereo", pagina=1)
    assert url.endswith("&page=1")


def test_extrai_titulo_link_canonico_e_preco():
    resultados = extrair_resultados_shopee(_CARTAO)
    assert len(resultados) == 1
    r = resultados[0]
    assert r["titulo"] == "Jack Conector P10 Stereo Femea Para Instrumentos"
    assert r["link"] == "https://shopee.com.br/product/454971236/23792476279"
    assert r["preco_texto"] == "13,79"


def test_cartao_sem_preco_visivel_devolve_preco_none():
    resultados = extrair_resultados_shopee(_CARTAO_SEM_PRECO)
    assert resultados[0]["preco_texto"] is None


def test_pagina_sem_cartao_devolve_lista_vazia():
    assert extrair_resultados_shopee("<html>sem resultado aqui</html>") == []
