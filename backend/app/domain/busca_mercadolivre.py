"""Extracao de resultados reais de busca do Mercado Livre (ETAPA 1 -
extensao, 20/08/2026, pedido do usuario: "Mercado Livre deve receber uma
busca semelhante ao Google" - profunda e paginada, nao so' 1 chamada rasa
de actor Apify).

Confirmado ao vivo (Web Unlocker, zona `efraim_1`) contra
`https://lista.mercadolivre.com.br/conector-jack-p10-stereo`:
  - cada anuncio fica dentro de um `<div class="andes-card poly-card ...">`
    - usado como marcador de fronteira entre cartoes via `re.split`.
  - titulo+link: `<a href="URL" ... class="poly-component__title">TITULO
    </a>` - `URL` pode ser um redirect de tracking do proprio Mercado Livre
    (`click1.mercadolivre.com.br/mclics/...`, resultado patrocinado) ou o
    link direto (`mercadolivre.com.br/.../MLB...`, resultado organico) -
    os dois sao URLs reais e clicaveis do dominio ML, aceitos igualmente.
  - preco ATUAL (nao o preco riscado de desconto, que usa a tag `<s>` em
    vez de `<span>` e tamanho 12): sempre marcado com
    `data-andes-money-amount-size="24"`, seguido por
    `andes-money-amount__fraction` e, so' quando o preco tem centavos,
    `andes-money-amount__cents` (preco redondo tipo "R$ 19" nao tem span de
    centavos - achado real, nem todo cartao tem os dois).
  - vendedor: `poly-component__seller` so' aparece pra loja oficial (~8 de
    35 cartoes na pagina real testada) - a maioria dos anuncios individuais
    nao expoe nome de vendedor na propria pagina de busca (limitacao real
    da plataforma, nao do regex).
  - paginacao: pagina 0 e' a URL base; da pagina 1 em diante, sufixo
    `_Desde_{N}_NoIndex_True`, `N = 1 + pagina*48` (confirmado no proprio
    HTML da pagina 1, que lista os links da paginacao real: pagina 2 =
    `_Desde_49`, pagina 3 = `_Desde_97`).
  - id MLB (`mlb_id`): tanto o link direto (`.../up/MLBU1437856589`,
    `.../p/MLB67968642`) quanto o link de tracking patrocinado
    (`...&pdp_filters=item_id%3AMLB3882572605#...&wid=MLB3882572605...`)
    embutem o mesmo id real do anuncio - usado como chave de deduplicacao
    entre esta busca direta e o actor Apify (`ApifyPriceSource`, mesmo
    Mercado Livre por outro caminho) que podem trazer o MESMO anuncio duas
    vezes (achado 20/08, revisao pedida pelo usuario).

Sem "pente fino" (visitar cada anuncio) aqui: a pagina de busca do ML ja'
devolve preco/titulo/link estruturados e confiaveis diretamente da propria
plataforma - mesmo tratamento dado ao carrossel do Google Shopping em
`busca_google.py` (fonte estruturada de 1a mao nao precisa de confirmacao
por visita, ao contrario de uma pagina generica de terceiro achada via
busca ampla).

Este modulo so' PARSEIA o HTML (sem I/O) - mesma separacao de
`busca_google.py`/`categoria_mercadolivre.py`; quem busca a pagina (Web
Unlocker) fica em `sourcing/busca_mercadolivre.py`.
"""
from __future__ import annotations

import html as _html_lib
import re
from urllib.parse import quote

from app.domain.classificacao import normalizar

_CARTAO_BOUNDARY_RE = re.compile(r'(?=<div class="andes-card poly-card)')
_TITULO_LINK_RE = re.compile(r'<a href="([^"]+)"[^>]*class="poly-component__title">([^<]+)</a>')
_PRECO_RE = re.compile(
    r'data-andes-money-amount-size="24">.*?'
    r'<span class="andes-money-amount__fraction"[^>]*>([\d.]+)</span>\s*'
    r'(?:<span class="andes-visually-hidden"[^>]*>,</span>\s*'
    r'<span class="andes-money-amount__cents[^"]*"[^>]*>(\d+)</span>)?',
    re.S,
)
_SELLER_RE = re.compile(r'poly-component__seller">([^<]+?)(?:\s*<svg|</span>)')
_MLB_ID_RE = re.compile(r"(?:wid=|item_id%3A|/)(MLBU?\d+)")

RESULTADOS_POR_PAGINA = 48


def montar_url_busca_ml(termo: str, pagina: int = 0) -> str:
    """Mesmo slug amigavel que o proprio campo de busca do ML gera: termo
    sem acento, minusculo, espacos viram hifen (`domain.classificacao.
    normalizar` ja' remove acento/maiuscula, so' falta o hifen). `pagina`
    0-indexado; da 2a pagina em diante usa `_Desde_N` (ver docstring do
    modulo)."""
    slug = quote(normalizar(termo).replace(" ", "-"))
    url = f"https://lista.mercadolivre.com.br/{slug}"
    if pagina > 0:
        offset = 1 + pagina * RESULTADOS_POR_PAGINA
        url += f"_Desde_{offset}_NoIndex_True"
    return url


def extrair_mlb_id(url: str) -> str | None:
    """Extrai o id MLB de uma URL de anuncio do Mercado Livre, cru ou de
    tracking - funcao publica (nao so' usada aqui) porque o MESMO anuncio
    pode chegar tambem pelo actor Apify (`ApifyPriceSource`, campo `url` do
    item), e os dois precisam bater na mesma chave de dedup (ver docstring
    do modulo)."""
    m = _MLB_ID_RE.search(url)
    return m.group(1) if m else None


def extrair_resultados_mercadolivre(html: str) -> list[dict]:
    """Devolve lista de {titulo, link, preco_texto, vendedor, mlb_id} -
    `preco_texto` vem no formato "123,45" (ou "123" quando o anuncio nao
    mostra centavos, preco redondo real - ver docstring do modulo);
    `vendedor` e' None quando o cartao nao expoe (maioria dos casos);
    `mlb_id` e' None no raríssimo caso do link nao seguir nenhum dos 2
    formatos conhecidos (ver docstring do modulo)."""
    cartoes = re.split(_CARTAO_BOUNDARY_RE, html)
    resultados = []
    for cartao in cartoes:
        if "poly-component__title" not in cartao:
            continue
        titulo_link = _TITULO_LINK_RE.search(cartao)
        if not titulo_link:
            continue
        link, titulo = titulo_link.group(1), _html_lib.unescape(titulo_link.group(2))

        preco_texto = None
        preco_match = _PRECO_RE.search(cartao)
        if preco_match:
            inteiro, centavos = preco_match.groups()
            preco_texto = f"{inteiro},{centavos or '00'}"

        vendedor_match = _SELLER_RE.search(cartao)
        vendedor = vendedor_match.group(1).strip() if vendedor_match else None

        mlb_id = extrair_mlb_id(link)

        resultados.append({
            "titulo": titulo, "link": link, "preco_texto": preco_texto,
            "vendedor": vendedor, "mlb_id": mlb_id,
        })
    return resultados
