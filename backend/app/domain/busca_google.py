"""Extracao de resultados organicos e variacoes de busca ("As pessoas
tambem perguntam") de uma pagina real de resultados do Google (ETAPA 1 -
extensao, 20/08/2026).

Confirmado ao vivo (Web Unlocker, zona `efraim_1` - a mesma ja' usada pro
Bloco B, NAO precisou da zona SERP dedicada `efraim_2`, que emperrou num
problema de permissao da API de gerenciamento de conta - achado que tornou
essa segunda zona desnecessaria pra este uso). A pagina de busca do Google
(`google.com/search?q=<termo>`) devolve, no proprio HTML:
  - resultados organicos: `<a href="...">` que envolve um `<h3>` com o
    titulo - o `href` NAO e' sempre o primeiro atributo da tag `<a>`
    (jsname/class costumam vir antes), entao o regex nao pode assumir
    `<a href=`  fixo (achado testando contra a pagina real - a 1a versao
    do regex, ancorada em `<a href=`, batia 0 resultados).
  - "As pessoas tambem perguntam": `data-q="<pergunta>"` por item - sao
    variacoes REAIS de como as pessoas buscam sobre o mesmo assunto,
    exatamente o pedido do usuario (20/08) de "aprender" essas variacoes e
    reusar como query nas proximas buscas.

Verificado contra a busca real "importador de componentes eletronicos" -
devolveu 9 resultados organicos com URL (fornecedores reais: ORIELEC,
FECOMP, JBT, DigiKey Brasil, Atllas, PRIME S&A, Comp Total, JNL,
Embarcados) e 4 perguntas relacionadas.

Este modulo so' PARSEIA o HTML (sem I/O) - mesma separacao de
`categoria_mercadolivre.py`/`extracao_pagina.py`; quem busca a pagina (Web
Unlocker) fica de fora daqui de proposito.
"""
from __future__ import annotations

import html as _html_lib
import re
from urllib.parse import quote_plus

_RESULTADO_RE = re.compile(
    r'<a\b[^>]*?href="(https?://[^"]+)"[^>]*>\s*<h3[^>]*>([^<]+)</h3>',
)
_PERGUNTA_RE = re.compile(r'data-q="([^"]+)"')

# Carrossel "Produtos Patrocinados" (Google Shopping) - estrutura DIFERENTE
# do resultado organico, achada testando contra a pagina real de
# "led 3mm round long diffused red" com `&tbm=shop` (20/08, verificado
# byte a byte - o separador entre "R$" e o valor e' U+00A0, nao espaco
# comum). Classes CSS do Google (minificadas, podem mudar sem aviso - risco
# aceito, mesmo padrao fragil de qualquer scraper de pagina de terceiro).
# `&tbm=shop` sozinho ja' devolveu 39 itens reais (bem mais que os ~6
# visiveis no carrossel resumido de uma busca comum) - "resultado
# significativo" pedido pelo usuario, 20/08.
_SHOPPING_ITEM_RE = re.compile(
    r'<div class="mhqZ2c"><div class="gkQHve[^"]*"[^>]*>([^<]+)</div></div>'
    r'.*?aria-label="Pre[^"]*?R\$\xa0([\d.,]+)\.'
    r'.*?<span class="WJMUdc rw5ecc">([^<]+)</span>',
    re.S,
)


def montar_url_busca_shopping(termo: str) -> str:
    """`&tbm=shop` - modo dedicado de Shopping do Google, devolve muito mais
    itens que o carrossel resumido de uma busca comum (39 reais testado
    contra "led 3mm round long diffused red", 20/08)."""
    return f"https://www.google.com/search?q={quote_plus(termo)}&tbm=shop&gl=br&hl=pt-BR"


def montar_url_busca_google(termo: str, pagina: int = 0) -> str:
    """Mesma URL/parametros usados na chamada real que validou este
    modulo: `gl=br&hl=pt-BR` fixa resultado em portugues do Brasil.
    `pagina` (0-indexado) usa o parametro `start` do Google - 10 resultados
    por pagina, `start=0` e' a 1a pagina (omitido), `start=10` a 2a, etc.
    Correcao do usuario (20/08): 1 pagina so' (~8-10 resultados) nao e'
    "resultado significativo" comparado ao que a busca no Google de
    verdade tem pra oferecer - precisa paginar."""
    url = f"https://www.google.com/search?q={quote_plus(termo)}&gl=br&hl=pt-BR"
    if pagina > 0:
        url += f"&start={pagina * 10}"
    return url


def extrair_resultados_organicos(html: str) -> list[tuple[str, str]]:
    """Devolve lista de (titulo, url) dos resultados organicos - decodifica
    entidades HTML no titulo (`&amp;` -> `&` etc). NAO inclui o card de
    Mapa (estrutura HTML diferente de um resultado organico comum) nem
    anuncios (Google os marca com outra estrutura, sem `<h3>` dentro do
    mesmo padrao de link)."""
    pares = _RESULTADO_RE.findall(html)
    return [(_html_lib.unescape(titulo), url) for url, titulo in pares]


def extrair_resultados_shopping(html: str) -> list[dict]:
    """Devolve lista de {titulo, preco_texto, vendedor} do carrossel de
    Shopping (`montar_url_busca_shopping`). SEM link direto - achado real
    (20/08): o card nao tem `<a href>` nem qualquer URL externa no HTML
    estatico, a Google resolve o destino via JS so' no clique (nao
    disponivel num fetch de HTML puro, nem via Web Unlocker). `preco_texto`
    vem cru ("0,19", sem "R$") - quem chama decide como converter."""
    achados = _SHOPPING_ITEM_RE.findall(html)
    return [
        {"titulo": _html_lib.unescape(titulo), "preco_texto": preco, "vendedor": vendedor}
        for titulo, preco, vendedor in achados
    ]


def extrair_variacoes_de_busca(html: str, termo_original: str) -> list[str]:
    """Devolve as perguntas de "As pessoas tambem perguntam" - exclui o
    proprio termo buscado quando ele aparece repetido no `data-q` (o
    Google as vezes inclui o termo original como 1a entrada, que nao e'
    uma variacao nova)."""
    perguntas = _PERGUNTA_RE.findall(html)
    termo_norm = termo_original.strip().lower()
    return [
        _html_lib.unescape(p) for p in perguntas
        if p.strip().lower() != termo_norm
    ]
