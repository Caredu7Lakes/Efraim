"""Fixtures abaixo reproduzem a estrutura REAL da pagina de busca do
Google pra "importador de componentes eletronicos" (capturada via Web
Unlocker, 20/08/2026) - atributos incidentais (jsname/data-ved/ping)
cortados e titulos abreviados pra caber no limite de linha, mas o padrao
de tag e as URLs sao os reais devolvidos."""
from app.domain.busca_google import (
    extrair_resultados_organicos,
    extrair_resultados_shopping,
    extrair_variacoes_de_busca,
    montar_url_busca_google,
    montar_url_busca_shopping,
)

# `href` NAO e' o primeiro atributo da tag `<a>` na pagina real (jsname/
# class vem antes) - reproduzido aqui de proposito, e' o que quebrou a 1a
# versao do regex (ancorada em `<a href=` fixo).
_HTML_RESULTADOS_REAIS = """
<div class="yuRUbf"><a jsname="UWckNb" class="zReHs"
href="https://orielec.com.br/">
<h3 class="LC20lb">ORIELEC - Componentes Eletrônicos</h3></a></div>
<div class="yuRUbf"><a jsname="UWckNb" class="zReHs"
href="https://www.jbtcomponentes.com.br/">
<h3 class="LC20lb">JBT - Distribuidor de Componentes Eletrônicos</h3></a></div>
<div class="yuRUbf"><a jsname="UWckNb" class="zReHs"
href="https://primesaltda.com.br/blog.php?id=45">
<h3 class="LC20lb">PRIME S &amp; A - Importação de Componentes</h3></a></div>
"""

_HTML_PERGUNTAS_REAIS = """
<div class="related-question-pair"
data-q="importador de componentes eletronicos"></div>
<div class="related-question-pair"
data-q="Qual é o melhor site para comprar componentes eletrônicos?"></div>
<div class="related-question-pair"
data-q="Onde comprar eletrônicos importados?"></div>
<div class="related-question-pair"
data-q="Quais são os melhores fornecedores de eletrônicos?"></div>
<div class="related-question-pair"
data-q="Como comprar eletrônicos direto da fábrica?"></div>
"""


def test_extrai_resultados_organicos_com_titulo_e_url():
    resultados = extrair_resultados_organicos(_HTML_RESULTADOS_REAIS)
    assert len(resultados) == 3
    titulo, url = resultados[0]
    assert titulo == "ORIELEC - Componentes Eletrônicos"
    assert url == "https://orielec.com.br/"


def test_decodifica_entidade_html_no_titulo():
    resultados = extrair_resultados_organicos(_HTML_RESULTADOS_REAIS)
    titulo_prime = next(t for t, _ in resultados if "PRIME" in t)
    assert titulo_prime == "PRIME S & A - Importação de Componentes"


def test_pagina_sem_resultados_devolve_lista_vazia():
    assert extrair_resultados_organicos("<html><body>sem resultados</body></html>") == []


def test_extrai_variacoes_de_busca_excluindo_o_termo_original():
    variacoes = extrair_variacoes_de_busca(
        _HTML_PERGUNTAS_REAIS, "importador de componentes eletronicos",
    )
    assert variacoes == [
        "Qual é o melhor site para comprar componentes eletrônicos?",
        "Onde comprar eletrônicos importados?",
        "Quais são os melhores fornecedores de eletrônicos?",
        "Como comprar eletrônicos direto da fábrica?",
    ]


def test_montar_url_busca_codifica_espacos_e_fixa_brasil():
    url = montar_url_busca_google("importador de componentes eletronicos")
    assert url == (
        "https://www.google.com/search?q=importador+de+componentes+eletronicos"
        "&gl=br&hl=pt-BR"
    )


def test_montar_url_busca_com_pagina_usa_parametro_start():
    assert "start=" not in montar_url_busca_google("x", pagina=0)
    assert "start=10" in montar_url_busca_google("x", pagina=1)
    assert "start=20" in montar_url_busca_google("x", pagina=2)


def test_montar_url_shopping_usa_tbm_shop():
    assert "tbm=shop" in montar_url_busca_shopping("led 3mm")


# estrutura real do carrossel de Shopping (verificada byte a byte, 20/08):
# o separador entre "R$" e o valor e' U+00A0 (\xa0), nao espaco comum -
# escrito explicito abaixo pra nao depender de caractere invisivel no
# arquivo fonte.
_NBSP = "\xa0"
_HTML_SHOPPING_REAL = (
    '<div class="mhqZ2c"><div class="gkQHve x">Led Difuso 3mm</div></div>'
    '<div class="mhqZ2c"><div class="FG68Ac" aria-label="Pre' + "ç" + 'o atual: '
    "R$" + _NBSP + '0,19. " role="group"><span class="lmQWe">R$' + _NBSP + "0,19</span>"
    '</div></div><div class="mhqZ2c"><span class="WJMUdc rw5ecc">'
    "Eletrogate</span></div>"
    '<div class="mhqZ2c"><div class="gkQHve x">Diodo Led Difuso 3mm</div></div>'
    '<div class="mhqZ2c"><div class="FG68Ac" aria-label="Pre' + "ç" + 'o atual: '
    "R$" + _NBSP + '0,09. " role="group"><span class="lmQWe">R$' + _NBSP + "0,09</span>"
    '</div></div><div class="mhqZ2c"><span class="WJMUdc rw5ecc">'
    "Proesi Componentes</span></div>"
)


def test_extrai_resultados_shopping_titulo_preco_vendedor():
    itens = extrair_resultados_shopping(_HTML_SHOPPING_REAL)
    assert len(itens) == 2
    assert itens[0] == {
        "titulo": "Led Difuso 3mm", "preco_texto": "0,19", "vendedor": "Eletrogate",
    }
    assert itens[1]["vendedor"] == "Proesi Componentes"


def test_shopping_sem_carrossel_devolve_lista_vazia():
    assert extrair_resultados_shopping("<html><body>sem shopping</body></html>") == []
