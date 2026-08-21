"""Busca real no Mercado Livre (ETAPA 1 - extensao, 20/08/2026, pedido do
usuario: "Mercado Livre deve receber uma busca semelhante ao Google" - ate'
agora so' havia 1 chamada rasa de actor Apify (`gio21/mercado-livre-
scraper`, maxPages=1) que num teste real ("conector jack p10 stereo")
devolveu 0 ofertas aproveitaveis. Esta busca complementa isso visitando a
propria pagina de busca do ML direto via Web Unlocker.

ACHADO REAL (20/08, verificado ao vivo, nao suposicao): ao contrario do
Google, a paginacao do Mercado Livre NAO pode ser replicada da mesma forma.
O robots.txt real do dominio (`lista.mercadolivre.com.br/robots.txt`, sob
`User-agent: *`) tem `Disallow: /*_Desde_` e `Disallow: /*_NoIndex_True` -
exatamente o padrao de URL que a paginacao real do ML usa (confirmado no
proprio HTML da pagina 1: pagina 2 = `..._Desde_49_NoIndex_True`). O Bright
Data Web Unlocker RESPEITA esse robots.txt no modo residencial sem KYC da
conta atual - toda tentativa de pagina >0 devolve erro de compliance
("Residential Failed (bad_endpoint): ... not available for immediate
residential (no KYC) access mode in accordance with robots.txt"), nunca
dado real. Paginar mesmo assim so' gastaria orcamento repetindo uma falha
JA' conhecida - por isso `MAX_PAGINAS = 1` (so' a pagina inicial, que NAO
bate em `_Desde_`/`_NoIndex_True` e retorna dado real - 35 anuncios reais
confirmados no teste ao vivo). Destravar paginacao de verdade exige
verificacao KYC na conta Bright Data (formulario em brightdata.com/cp/kyc)
- decisao de conta, fora do escopo deste codigo.

Sem "pente fino"/visita por anuncio - ver `domain.busca_mercadolivre` (a
propria pagina de busca ja' devolve preco/titulo confiaveis, mesmo
tratamento do carrossel do Google Shopping)."""
from __future__ import annotations

import logging

import httpx

from app.domain.busca_mercadolivre import extrair_resultados_mercadolivre, montar_url_busca_ml
from app.domain.models import Oferta
from app.domain.normalizador import oferta_ou_none
from app.sourcing.brightdata_client import chamar_web_unlocker
from app.sourcing.erros import MCPRateLimitError
from app.sourcing.orcamento import OrcamentoExcedidoError, OrcamentoMCP

log = logging.getLogger("efraim.busca_mercadolivre")

NOME_FONTE = "mercadolivre-direto"

# teto REAL hoje - ver docstring do modulo: robots.txt do ML bloqueia
# qualquer pagina >0 (`_Desde_`/`_NoIndex_True`), e o Web Unlocker respeita
# isso no modo residencial sem KYC da conta atual. Nao e' um numero
# arbitrario/conservador - e' o que a propria plataforma permite agora.
MAX_PAGINAS = 1


async def buscar_mercadolivre(
    termo: str, *, zone: str | None, token: str | None,
    orcamento: OrcamentoMCP, timeout_s: float = 30.0,
) -> list[Oferta]:
    """Lista vazia sem credenciais - nunca levanta (exceto
    `MCPRateLimitError`, tratado pelo orquestrador em outros pontos)."""
    if not zone or not token:
        return []

    ofertas: list[Oferta] = []
    links_vistos: set[str] = set()

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        for pagina in range(MAX_PAGINAS):
            url = montar_url_busca_ml(termo, pagina=pagina)
            try:
                html = await chamar_web_unlocker(
                    url, client=client, zone=zone, token=token,
                    orcamento=orcamento, bloco="C", nome_fonte=NOME_FONTE,
                )
            except OrcamentoExcedidoError:
                log.info(
                    "orcamento esgotado no Mercado Livre (pagina %d de '%s')", pagina, termo,
                )
                break
            except MCPRateLimitError:
                raise
            except Exception as exc:  # noqa: BLE001 - 1 pagina falhar nao pode
                # impedir de chegar ate' MAX_PAGINAS (mesmo criterio do Google)
                log.warning(
                    "falha ao buscar Mercado Livre '%s' (pagina %d): %r - seguindo pra proxima",
                    termo, pagina, exc,
                )
                continue

            resultados = extrair_resultados_mercadolivre(html)
            novos = [r for r in resultados if r["link"] not in links_vistos]
            if not novos:
                log.info(
                    "pagina %d sem anuncio novo no Mercado Livre pra '%s' - seguindo pra proxima",
                    pagina, termo,
                )
                continue
            links_vistos.update(r["link"] for r in novos)

            for r in novos:
                oferta = oferta_ou_none({
                    "produto": r["titulo"], "preco": r["preco_texto"],
                    "local": r["vendedor"] or "Mercado Livre", "link": r["link"],
                    "disponibilidade": "desconhecida", "id_externo": r["mlb_id"],
                }, fonte=NOME_FONTE)
                if oferta is not None:
                    ofertas.append(oferta)

    return ofertas
