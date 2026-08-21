"""Fixtures abaixo reproduzem a estrutura REAL confirmada ao vivo (Web
Unlocker, 20/08) contra `lista.mercadolivre.com.br/conector-jack-p10-
stereo` - trechos trimados, nao inventados (ver docstring de
`app.domain.busca_mercadolivre`)."""
from __future__ import annotations

from pathlib import Path

from app.domain.busca_mercadolivre import (
    extrair_mlb_id,
    extrair_resultados_mercadolivre,
    montar_url_busca_ml,
)

_FIXTURES = Path(__file__).parent / "fixtures"

_CARTAO_COM_DESCONTO = """
<div class="andes-card poly-card poly-card--grid-card">
<div class="poly-card__content"><h3 class="poly-component__title-wrapper">
<a href="https://click1.mercadolivre.com.br/mclics/clicks/external/MLB/count?a=xyz"
target="_self" class="poly-component__title">Kit 6 Conectores P10 Trs Femea Painel</a></h3>
<div class="poly-component__price"><span class="andes-money-amount__fraction"
role="img" aria-label="72 reais">72</span></div>
<s class="andes-money-amount polylabel-price andes-money-amount--previous"
style="font-size:12px" data-andes-money-amount-size="12">
<span class="andes-money-amount__fraction" aria-hidden="true">72</span>
<span class="andes-visually-hidden" aria-hidden="true">,</span>
<span class="andes-money-amount__cents andes-money-amount__cents--superscript-12"
aria-hidden="true">90</span></s>
<span class="andes-money-amount poly-price__part-price" data-andes-money-amount-size="24">
<span class="andes-money-amount__fraction" aria-hidden="true"
data-andes-money-amount-fraction="true">69</span>
<span class="andes-visually-hidden" aria-hidden="true">,</span>
<span class="andes-money-amount__cents andes-money-amount__cents--superscript-24"
aria-hidden="true" data-andes-money-amount-cents="true">25</span></span>
</div></div></div>
"""

_CARTAO_LOJA_OFICIAL_SEM_DESCONTO = """
<div class="andes-card poly-card poly-card--grid-card">
<div class="poly-card__content"><h3 class="poly-component__title-wrapper">
<a href="https://www.mercadolivre.com.br/cabo-xlr-cirilo-cabos/p/MLB44227515"
target="_self" class="poly-component__title">Cabo XLR Cirilo Cabos 5m P2</a></h3>
<span class="poly-component__seller">CiriloCabos <svg aria-label="Loja oficial"
role="img" class="polylabel-icon"><use href="#poly_cockade"></use></svg></span>
<span class="andes-money-amount poly-price__part-price" data-andes-money-amount-size="24">
<span class="andes-money-amount__fraction" aria-hidden="true"
data-andes-money-amount-fraction="true">19</span></span>
</div></div></div>
"""

_PAGINACAO_HTML = (
    '{"value":"2","url":"https:\\u002F\\u002Flista.mercadolivre.com.br'
    '\\u002Fconector-jack-p10-stereo_Desde_49_NoIndex_True"}'
)


def test_montar_url_pagina_zero_sem_sufixo():
    assert montar_url_busca_ml("conector jack p10 stereo") == (
        "https://lista.mercadolivre.com.br/conector-jack-p10-stereo"
    )


def test_montar_url_paginas_seguintes_usa_desde_confirmado_ao_vivo():
    """Offsets 49/97 confirmados no HTML real da paginacao (nao inventados) -
    ver docstring do modulo."""
    assert montar_url_busca_ml("conector jack p10 stereo", pagina=1).endswith(
        "_Desde_49_NoIndex_True"
    )
    assert montar_url_busca_ml("conector jack p10 stereo", pagina=2).endswith(
        "_Desde_97_NoIndex_True"
    )


def test_montar_url_remove_acento_e_usa_hifen():
    url = montar_url_busca_ml("conector jack p10 estéreo")
    assert url == "https://lista.mercadolivre.com.br/conector-jack-p10-estereo"


def test_extrai_preco_atual_nao_o_riscado_de_desconto():
    """O cartao tem preco riscado (72,90, size=12, dentro de <s>) e o preco
    atual (69,25, size=24) - so' o atual deve ser extraido (achado real,
    20/08: usar o 1o "fraction" encontrado pegava o riscado por engano)."""
    resultados = extrair_resultados_mercadolivre(_CARTAO_COM_DESCONTO)
    assert len(resultados) == 1
    assert resultados[0]["preco_texto"] == "69,25"
    assert resultados[0]["titulo"] == "Kit 6 Conectores P10 Trs Femea Painel"
    assert "click1.mercadolivre.com.br" in resultados[0]["link"]


def test_extrai_preco_redondo_sem_centavos():
    """Card sem desconto: preco redondo real ("R$19", sem span de centavos) -
    achado real, nem todo cartao tem os dois spans."""
    resultados = extrair_resultados_mercadolivre(_CARTAO_LOJA_OFICIAL_SEM_DESCONTO)
    assert resultados[0]["preco_texto"] == "19,00"
    assert resultados[0]["vendedor"] == "CiriloCabos"


def test_dois_cartoes_na_mesma_pagina_sao_separados_corretamente():
    html = _CARTAO_COM_DESCONTO + _CARTAO_LOJA_OFICIAL_SEM_DESCONTO
    resultados = extrair_resultados_mercadolivre(html)
    assert len(resultados) == 2
    assert resultados[0]["vendedor"] is None
    assert resultados[1]["vendedor"] == "CiriloCabos"


def test_pagina_sem_cartao_devolve_lista_vazia():
    assert extrair_resultados_mercadolivre("<html>sem resultado aqui</html>") == []


def test_mlb_id_extraido_do_link_direto():
    resultados = extrair_resultados_mercadolivre(_CARTAO_LOJA_OFICIAL_SEM_DESCONTO)
    assert resultados[0]["mlb_id"] == "MLB44227515"


def test_mlb_id_extraido_do_link_de_tracking_patrocinado():
    """Link de anuncio patrocinado (`click1.mercadolivre.com.br/...`) nao
    e' o link direto do produto, mas ainda embute o mesmo id MLB real -
    confirmado ao vivo (ver docstring do modulo)."""
    resultados = extrair_resultados_mercadolivre(_CARTAO_COM_DESCONTO)
    assert resultados[0]["mlb_id"] is None  # este fixture nao tem wid=/item_id no link
    assert extrair_mlb_id(
        "https://click1.mercadolivre.com.br/mclics/x?a=y&pdp_filters=item_id"
        "%3AMLB3882572605#polycard_client=search&wid=MLB3882572605&sid=search",
    ) == "MLB3882572605"


def test_preco_com_separador_de_milhar_e_convertido_certo():
    """Preco de 4+ digitos (ex.: R$1.299,90) - o separador de milhar do ML
    e' ponto, igual ao formato BR que `_preco_para_centavos` (normalizador)
    ja' trata; aqui so' confirma que o texto extraido preserva o ponto pra'
    aquela conversao funcionar (mesma estrutura real de card, so' o valor
    do preco trocado pra' um de 4 digitos)."""
    cartao_caro = _CARTAO_LOJA_OFICIAL_SEM_DESCONTO.replace(
        'data-andes-money-amount-fraction="true">19</span>',
        'data-andes-money-amount-fraction="true">1.299</span>',
    )
    resultados = extrair_resultados_mercadolivre(cartao_caro)
    assert resultados[0]["preco_texto"] == "1.299,00"


def test_contrato_pagina_real_capturada_ao_vivo():
    """Teste de contrato (pedido do usuario, 20/08): roda contra uma pagina
    REAL do Mercado Livre capturada ao vivo (`tests/fixtures/
    mercadolivre_busca_real.html`, 4 cartoes, Web Unlocker zona `efraim_1`,
    20/08) - se o parser parar de achar esses 4 anuncios conhecidos, e'
    sinal de que o ML mudou o layout, e quem avisa e' a suite, nao uma
    validacao ao vivo cara."""
    html = (_FIXTURES / "mercadolivre_busca_real.html").read_text(encoding="utf-8")
    resultados = extrair_resultados_mercadolivre(html)
    assert len(resultados) == 4
    assert resultados[0]["preco_texto"] == "69,25"
    assert resultados[0]["mlb_id"] == "MLB3882572605"
    assert resultados[3]["vendedor"] == "CiriloCabos"
    assert resultados[3]["preco_texto"] == "168,00"
    assert all(r["titulo"] and r["link"] for r in resultados)
