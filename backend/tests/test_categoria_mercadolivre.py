"""Fixture abaixo reproduz a estrutura REAL do breadcrumb da pagina de
busca do Mercado Livre pra "led 3mm round long lead diffused red"
(capturada via Web Unlocker, 20/08/2026 - atributos incidentais cortados,
mas o padrao de tag schema.org e os textos de categoria sao os reais
devolvidos), confirmando a classificacao deles pra esse item: Eletrônicos,
Áudio e Vídeo > Componentes Eletrônicos > Semicondutores > Chips Leds."""
from app.domain.categoria_mercadolivre import extrair_categoria_ml, montar_url_busca_ml

# estrutura real (schema.org/BreadcrumbList, itemprop="name" por nivel) -
# atributos incidentais (href/class/svg) cortados pra caber no limite de
# linha, mas o padrao de tag e os textos de categoria sao os reais
# capturados via Web Unlocker.
_HTML_BREADCRUMB_REAL = """
<div class="ui-search-breadcrumb"><ol itemtype="https://schema.org/BreadcrumbList">
<li itemprop="itemListElement" itemtype="https://schema.org/ListItem">
<a itemprop="item"><span itemprop="name">Eletrônicos, Áudio e Vídeo</span></a>
<meta itemprop="position" content="1"></li>
<li itemprop="itemListElement" itemtype="https://schema.org/ListItem">
<a itemprop="item"><span itemprop="name">Componentes Eletrônicos</span></a>
<meta itemprop="position" content="2"></li>
<li itemprop="itemListElement" itemtype="https://schema.org/ListItem">
<a itemprop="item"><span itemprop="name">Semicondutores</span></a>
<meta itemprop="position" content="3"></li>
<li itemprop="itemListElement" itemtype="https://schema.org/ListItem">
<a itemprop="item"><span itemprop="name">Chips Leds</span></a>
<meta itemprop="position" content="4"></li>
</ol></div>
"""


def test_extrai_breadcrumb_completo_do_led():
    categorias = extrair_categoria_ml(_HTML_BREADCRUMB_REAL)
    assert categorias == [
        "Eletrônicos, Áudio e Vídeo", "Componentes Eletrônicos", "Semicondutores", "Chips Leds",
    ]


def test_pagina_sem_breadcrumb_devolve_lista_vazia():
    assert extrair_categoria_ml("<html><body>pagina de erro</body></html>") == []


def test_montar_url_busca_troca_espaco_por_traco():
    assert montar_url_busca_ml("led 3mm round long lead diffused red") == (
        "https://lista.mercadolivre.com.br/led-3mm-round-long-lead-diffused-red"
    )
