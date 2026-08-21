"""Busca real e paginada na Shopee (ETAPA 1 - extensao, 20/08/2026, pedido
do usuario: "mercado livre nao e' o unico marketplace que deve ser
visitado" - fecha o 2o dos 4 marketplaces de `docs/ARQUITETURA.md` §6, ver
`domain.busca_shopee` pra' o achado real de estrutura/paginacao).

Mesmo criterio ja' estabelecido em `variacoes_busca.py`/`busca_mercadolivre
.py`: uma pagina sem anuncio novo so' e' pulada, nunca encerra a busca
inteira - confirmado ao vivo que paginas 0/1 da Shopee tem overlap parcial
(reordenacao de busca), nao duplicidade total.

Sem "pente fino"/visita por anuncio - a propria pagina de busca ja' devolve
preco/titulo estruturados e confiaveis (mesmo tratamento do Mercado Livre e
do carrossel do Google Shopping)."""
from __future__ import annotations

import logging

import httpx

from app.domain.busca_shopee import extrair_resultados_shopee, montar_url_busca_shopee
from app.domain.models import Oferta
from app.domain.normalizador import oferta_ou_none
from app.sourcing.brightdata_client import chamar_web_unlocker
from app.sourcing.erros import MCPRateLimitError
from app.sourcing.orcamento import OrcamentoExcedidoError, OrcamentoMCP

log = logging.getLogger("efraim.busca_shopee")

NOME_FONTE = "shopee-direto"

# mesma pratica de `variacoes_busca.MAX_PAGINAS` - teto real de paginas,
# sempre percorrido por completo (link ja' visto so' e' pulado).
MAX_PAGINAS = 18


async def buscar_shopee(
    termo: str, *, zone: str | None, token: str | None,
    orcamento: OrcamentoMCP, timeout_s: float = 60.0,
) -> list[Oferta]:
    """Lista vazia sem credenciais - nunca levanta (exceto
    `MCPRateLimitError`, tratado pelo orquestrador em outros pontos).
    `timeout_s` default mais alto que o do Google/ML (30s): achado real
    (20/08) - a pagina da Shopee e' pesada (500KB+) e o Web Unlocker levou
    ReadTimeout em 30s repetidas vezes num teste ao vivo; com 90s uma
    tentativa passou do timeout mas a OUTRA devolveu HTTP 200 com 0
    resultados (paginas de bloqueio/anti-bot sao um risco real e conhecido
    da Shopee, nao um bug de extracao - o regex ja' foi validado contra uma
    pagina real com dado de verdade). Falha isolada por pagina (ja' trata
    ambos os casos: timeout e pagina vazia sem erro)."""
    if not zone or not token:
        return []

    ofertas: list[Oferta] = []
    links_vistos: set[str] = set()

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        for pagina in range(MAX_PAGINAS):
            url = montar_url_busca_shopee(termo, pagina=pagina)
            try:
                html = await chamar_web_unlocker(
                    url, client=client, zone=zone, token=token,
                    orcamento=orcamento, bloco="C", nome_fonte=NOME_FONTE,
                )
            except OrcamentoExcedidoError:
                log.info("orcamento esgotado na Shopee (pagina %d de '%s')", pagina, termo)
                break
            except MCPRateLimitError:
                raise
            except Exception as exc:  # noqa: BLE001 - 1 pagina falhar nao pode
                # impedir de chegar ate' MAX_PAGINAS (mesmo criterio do Google/ML)
                log.warning(
                    "falha ao buscar Shopee '%s' (pagina %d): %r - seguindo pra proxima",
                    termo, pagina, exc,
                )
                continue

            resultados = extrair_resultados_shopee(html)
            novos = [r for r in resultados if r["link"] not in links_vistos]
            if not novos:
                log.info(
                    "pagina %d sem anuncio novo na Shopee pra '%s' - seguindo pra proxima",
                    pagina, termo,
                )
                continue
            links_vistos.update(r["link"] for r in novos)

            for r in novos:
                oferta = oferta_ou_none({
                    "produto": r["titulo"], "preco": r["preco_texto"],
                    "local": "Shopee", "link": r["link"], "disponibilidade": "desconhecida",
                }, fonte=NOME_FONTE)
                if oferta is not None:
                    ofertas.append(oferta)

    return ofertas
