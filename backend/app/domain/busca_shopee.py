"""Extracao de resultados reais de busca da Shopee (ETAPA 1 - extensao,
20/08/2026, pedido do usuario: "mercado livre nao e' o unico marketplace
que deve ser visitado - passei uma relacao ontem" - a relacao real esta' em
`docs/ARQUITETURA.md` §6: "A — Marketplaces BR (ML, Magalu, Shopee,
Americanas) | Sem pipeline dedicado" - este modulo fecha a Shopee).

Confirmado ao vivo (Web Unlocker, zona `efraim_1`) contra
`https://shopee.com.br/search?keyword=conector+jack+p10+stereo`:
  - cada anuncio fica dentro de um
    `<li class="col-xs-2-4 shopee-search-item-result__item" data-sqe="item">`
    - usado como marcador de fronteira entre cartoes via `re.split`.
  - titulo: vem PRONTO no atributo `aria-label="Product card: TITULO"` de um
    `<div role="group">` dentro do cartao - nao precisa caçar tag de texto
    separada.
  - link: o cartao expoe `itemid`/`shopid` num href de "produtos
    similares" (`/find_similar_products?...itemid=N&shopid=M`) - o link
    CANONICO do produto (`https://shopee.com.br/product/{shopid}/{itemid}`)
    foi confirmado ao vivo resolvendo pra' pagina real do mesmo anuncio.
  - preco: `R$</span><span class="truncate text-base/5 font-medium">VALOR
    </span>` - formato "13,79" direto (BRL, ja' com virgula).
  - paginacao: `&page=N` (0-indexado, testado ao vivo: pagina 0 e 1 tem 26
    de 40 titulos em comum - overlap real de reordenacao de busca, nao um
    bug; segue o mesmo criterio ja' adotado pro Google/ML: link ja' visto
    so' e' pulado, nunca para a paginacao).

ACHADO REAL, documentado por transparencia (nao bloqueou a implementacao):
`shopee.com.br/robots.txt` devolveu literalmente o corpo "Forbidden" via
Web Unlocker (nao um robots.txt de verdade) - a Shopee bloqueia ate' a
leitura do proprio robots.txt pra' esse tipo de acesso. Sem regra explicita
pra' confirmar/negar, e o Bright Data (que ja' bloqueou paginas do Mercado
Livre por causa de Disallow real) NAO bloqueou esta busca - seguindo o
mesmo padrao de "melhor pratica" ja' usado no resto do projeto.

Sem "pente fino"/visita por anuncio - mesmo tratamento do carrossel do
Google Shopping e do Mercado Livre (`domain.busca_mercadolivre`): a propria
pagina de busca ja' devolve preco/titulo estruturados e confiaveis.
"""
from __future__ import annotations

import html as _html_lib
import re
from urllib.parse import quote

_CARTAO_BOUNDARY_RE = re.compile(
    r'(?=<li class="col-xs-2-4 shopee-search-item-result__item")',
)
_TITULO_RE = re.compile(r'aria-label="Product card: ([^"]+)"')
_ID_RE = re.compile(r'itemid=(\d+)[^"]*shopid=(\d+)')
_PRECO_RE = re.compile(r'R\$</span>\s*<span class="truncate[^"]*"[^>]*>([\d.,]+)</span>')

RESULTADOS_POR_PAGINA = 40


def montar_url_busca_shopee(termo: str, pagina: int = 0) -> str:
    """`&page=N`, 0-indexado - confirmado ao vivo (ver docstring do
    modulo)."""
    url = f"https://shopee.com.br/search?keyword={quote(termo)}"
    if pagina > 0:
        url += f"&page={pagina}"
    return url


def extrair_resultados_shopee(html: str) -> list[dict]:
    """Devolve lista de {titulo, link, preco_texto} - link e' o formato
    canonico `https://shopee.com.br/product/{shopid}/{itemid}` (confirmado
    ao vivo resolvendo pra' pagina real do mesmo anuncio, mais estavel que
    o link de "produtos similares" cru que aparece no cartao)."""
    cartoes = re.split(_CARTAO_BOUNDARY_RE, html)
    resultados = []
    for cartao in cartoes:
        if 'data-sqe="item"' not in cartao:
            continue
        titulo_match = _TITULO_RE.search(cartao)
        id_match = _ID_RE.search(cartao)
        if not titulo_match or not id_match:
            continue
        titulo = _html_lib.unescape(titulo_match.group(1))
        item_id, shop_id = id_match.groups()
        link = f"https://shopee.com.br/product/{shop_id}/{item_id}"

        preco_match = _PRECO_RE.search(cartao)
        preco_texto = preco_match.group(1) if preco_match else None

        resultados.append({"titulo": titulo, "link": link, "preco_texto": preco_texto})
    return resultados
