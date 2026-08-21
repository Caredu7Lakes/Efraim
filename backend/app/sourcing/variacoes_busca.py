"""Aprendizado de variacoes de busca via Google direto - busca ampla e
profunda, nao so' a 1a pagina (ETAPA 1 - extensao, 20/08/2026, reescrito no
mesmo dia apos correcao do usuario: "8 ofertas e' menos opcoes que uma
pagina simples do Google apresenta").

Cobre 3 fontes que uma pagina de busca real do Google mostra, TODAS
diferentes em estrutura HTML (achado testando contra paginas reais,
20/08):
  1. Carrossel "Produtos Patrocinados" (Shopping, `&tbm=shop`) - titulo/
     preco/vendedor, SEM link direto (a Google resolve a URL real via JS
     no clique, nao esta' no HTML estatico nem via Web Unlocker - limitacao
     real, nao falta de esforco no regex).
  2. Resultados organicos, PAGINADOS - o Google devolve so' ~10 por pagina;
     pagina ate' `MAX_PAGINAS` SEMPRE (correcao do usuario, 20/08: parar a
     busca inteira so' porque UMA pagina nao trouxe link novo cortava
     paginas seguintes que podiam ter resultado novo de verdade - ex.:
     Mercado Livre so' apareceu numa pagina mais funda em "conector jack
     p10 stereo"). "Duplicidade" e' so' identificada por pagina (um link ja'
     visto NAO e' revisitado de novo), nunca usada como motivo pra parar de
     paginar - a busca sempre vai ate' `MAX_PAGINAS`.
  3. "As pessoas tambem perguntam" - variacoes reais de busca, persistidas
     POR CATEGORIA pra reuso em buscas futuras do mesmo tipo de item
     (`persistence.repositorio.RepositorioSQL.salvar_variacoes_busca`).

Pedido explicito do usuario (20/08): "voce deve entrar em cada link
existente na pagina, e dentro do link procurar o produto" - por isso todo
resultado organico e' VISITADO (nao so' uma amostra), extraindo nome do
fornecedor, contato, preco confirmado e SE esse preco e' por quantas
unidades (`extracao_pagina.extrair_quantidade_unidades` - preco de
anuncio/carrossel costuma ser de kit/lote, nao de 1 peca).

Custo: em escala cheia (ate' 18 paginas x ~16 resultados/pagina, cada um
visitado) isso pode passar de 250 chamadas por produto - decisao explicita
do usuario foi "nao deve ficar imaginando o custo... o que importa e' a
qualidade do retorno" - por isso o orcamento desta etapa e' bem mais
generoso que o resto do pipeline (ver `jobs/tasks.py::_aprender_variacoes`)
e INDEPENDENTE do orcamento principal (Bloco A/B/C/D), nao compete com ele.

Falha aqui e' isolada (resiliencia, mesmo padrao do resto do projeto) - e'
um passo de ENRIQUECIMENTO/aprendizado, nao a busca principal; nunca pode
derrubar o pipeline por causa disso. Sem credenciais Bright Data
configuradas, simplesmente nao roda (devolve lista vazia).
"""
from __future__ import annotations

import logging

import httpx

from app.domain.busca_google import (
    extrair_resultados_organicos,
    extrair_resultados_shopping,
    extrair_variacoes_de_busca,
    montar_url_busca_google,
    montar_url_busca_shopping,
)
from app.domain.extracao_pagina import (
    extrair_preco,
    extrair_quantidade_numerica,
    extrair_quantidade_unidades,
    extrair_telefone,
    extrair_whatsapp,
    produto_aparece,
)
from app.domain.models import Oferta
from app.domain.normalizador import oferta_ou_none
from app.persistence.repositorio import RepositorioSQL
from app.sourcing.brightdata_client import chamar_web_unlocker
from app.sourcing.erros import MCPRateLimitError
from app.sourcing.orcamento import OrcamentoExcedidoError, OrcamentoMCP

log = logging.getLogger("efraim.variacoes_busca")

NOME_FONTE = "google-serp-direto"
NOME_FONTE_SHOPPING = "google-shopping"

# quantidade REAL de paginas a varrer, sempre - correcao do usuario (20/08):
# nao parar antes disso so' porque uma pagina no meio do caminho nao trouxe
# link novo (isso e' "duplicidade" - um link ja' visto so' e' pulado, nunca
# motivo pra encerrar a busca inteira).
MAX_PAGINAS = 18


async def _visitar_organico(
    titulo: str, url: str, produto_alvo: str, *,
    client: httpx.AsyncClient, zone: str, token: str, orcamento: OrcamentoMCP,
) -> Oferta | None:
    """Visita UM resultado organico (pedido do usuario: "entrar em cada
    link existente na pagina") - extrai contato sempre; preco (e a
    quantidade que ele cobre) so' quando o produto da busca principal de
    fato aparece na pagina ("pente fino", mesmo criterio de
    `apify_source.ApifyBroadSource`/`brightdata_unlocker.BrightDataRegionalSource`)."""
    try:
        html = await chamar_web_unlocker(
            url, client=client, zone=zone, token=token,
            orcamento=orcamento, bloco="C", nome_fonte=NOME_FONTE,
        )
    except (OrcamentoExcedidoError, MCPRateLimitError):
        raise
    except Exception as exc:  # noqa: BLE001 - site de terceiro, isola por link
        log.warning(
            "falha ao visitar '%s' (aprendizado): %r - mantendo so' o titulo", url, exc,
        )
        return oferta_ou_none({
            "produto": produto_alvo, "preco": None, "local": titulo, "link": url,
            "disponibilidade": "desconhecida",
        }, fonte=NOME_FONTE)

    whatsapp = extrair_whatsapp(html) or extrair_telefone(html)
    contato = None
    if whatsapp:
        contato = {"telefone": (), "whatsapp": (whatsapp,), "email": ()}

    preco = None
    local = titulo
    unidades_no_lote = 1
    if produto_aparece(html, produto_alvo):
        preco = extrair_preco(html)
        qtd = extrair_quantidade_unidades(html)
        if preco and qtd:
            local = f"{titulo} ({qtd})"
        # numero real (nao so' o texto de anotacao acima) - extraido do
        # HTML completo da PAGINA VISITADA, mais confiavel que o titulo do
        # resultado de busca (`produto_alvo` aqui e' o TERMO buscado, nao o
        # titulo da pagina - `normalizar()` nao teria como inferir certo a
        # partir dele, por isso passamos explicito - ver `domain.
        # normalizador.normalizar`).
        unidades_no_lote = extrair_quantidade_numerica(html)

    return oferta_ou_none({
        "produto": produto_alvo, "preco": preco, "local": local, "link": url,
        "disponibilidade": "desconhecida", "contato": contato,
        "unidades_no_lote": unidades_no_lote,
    }, fonte=NOME_FONTE)


async def _buscar_shopping(
    termo: str, *, client: httpx.AsyncClient, zone: str, token: str, orcamento: OrcamentoMCP,
) -> list[Oferta]:
    """Carrossel de Shopping - SEM link direto (limitacao real, ver
    docstring do modulo). O preco mostrado costuma ser de anuncio/kit, nao
    confirmado por unidade - fica marcado no proprio nome do produto pra
    nao passar a falsa impressao de preco unitario certo."""
    try:
        html = await chamar_web_unlocker(
            montar_url_busca_shopping(termo), client=client, zone=zone, token=token,
            orcamento=orcamento, bloco="C", nome_fonte=NOME_FONTE_SHOPPING,
        )
    except OrcamentoExcedidoError:
        log.info("orcamento esgotado antes do shopping pra '%s' - pulando", termo)
        return []
    except Exception as exc:  # noqa: BLE001
        log.warning("falha ao buscar shopping pra '%s': %r", termo, exc)
        return []

    ofertas: list[Oferta] = []
    for item in extrair_resultados_shopping(html):
        oferta = oferta_ou_none({
            "produto": f"{item['titulo']} (preco de anuncio - unidade nao confirmada)",
            "preco": item["preco_texto"], "local": item["vendedor"], "link": "",
            "disponibilidade": "desconhecida",
        }, fonte=NOME_FONTE_SHOPPING)
        if oferta is not None:
            ofertas.append(oferta)
    return ofertas


async def buscar_e_aprender(
    termo: str, categoria: str, *, zone: str | None, token: str | None,
    repo: RepositorioSQL, orcamento: OrcamentoMCP, timeout_s: float = 30.0,
) -> list[Oferta]:
    """Busca ampla e profunda no Google (shopping + organico paginado,
    visitando cada link), persiste as variacoes de busca achadas. Lista
    vazia sem credenciais - nunca levanta (exceto `MCPRateLimitError`, que
    o orquestrador ja' trata em outros pontos do pipeline)."""
    if not zone or not token:
        return []

    ofertas: list[Oferta] = []
    variacoes_todas: list[str] = []
    urls_vistas: set[str] = set()

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        ofertas.extend(await _buscar_shopping(
            termo, client=client, zone=zone, token=token, orcamento=orcamento,
        ))

        for pagina in range(MAX_PAGINAS):
            url = montar_url_busca_google(termo, pagina=pagina)
            try:
                html = await chamar_web_unlocker(
                    url, client=client, zone=zone, token=token,
                    orcamento=orcamento, bloco="C", nome_fonte=NOME_FONTE,
                )
            except OrcamentoExcedidoError:
                log.info("orcamento esgotado no aprendizado (pagina %d de '%s')", pagina, termo)
                break
            except Exception as exc:  # noqa: BLE001 - 1 pagina falhar nao pode
                # impedir de chegar ate' MAX_PAGINAS (pedido do usuario, 20/08)
                log.warning(
                    "falha ao buscar Google direto '%s' (pagina %d): %r - seguindo pra proxima",
                    termo, pagina, exc,
                )
                continue

            resultados_pagina = extrair_resultados_organicos(html)
            novos = [(t, u) for t, u in resultados_pagina if u not in urls_vistas]
            if not novos:
                # link ja' visto e' so' pulado (nao revisitado) - "duplicidade"
                # nunca e' motivo pra parar de paginar, a busca sempre segue
                # ate' MAX_PAGINAS (correcao do usuario, 20/08).
                log.info("pagina %d sem link novo pra '%s' - seguindo pra proxima", pagina, termo)
                continue
            urls_vistas.update(u for _, u in novos)
            variacoes_todas.extend(extrair_variacoes_de_busca(html, termo))

            orcamento_esgotado = False
            for titulo, url_resultado in novos:
                if orcamento_esgotado:
                    ofertas.append(oferta_ou_none({
                        "produto": termo, "preco": None, "local": titulo,
                        "link": url_resultado, "disponibilidade": "desconhecida",
                    }, fonte=NOME_FONTE))
                    continue
                try:
                    oferta = await _visitar_organico(
                        titulo, url_resultado, termo,
                        client=client, zone=zone, token=token, orcamento=orcamento,
                    )
                except OrcamentoExcedidoError:
                    orcamento_esgotado = True
                    log.info(
                        "orcamento esgotado visitando links (pagina %d de '%s')", pagina, termo,
                    )
                    oferta = oferta_ou_none({
                        "produto": termo, "preco": None, "local": titulo,
                        "link": url_resultado, "disponibilidade": "desconhecida",
                    }, fonte=NOME_FONTE)
                if oferta is not None:
                    ofertas.append(oferta)

    variacoes_unicas = list(dict.fromkeys(variacoes_todas))
    if variacoes_unicas:
        try:
            await repo.salvar_variacoes_busca(categoria, variacoes_unicas)
        except Exception:  # noqa: BLE001 - persistencia de aprendizado, nao a busca principal
            log.exception("falha ao salvar variacoes de busca (categoria=%s)", categoria)

    return ofertas
