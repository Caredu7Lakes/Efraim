"""Adapter Apify - PriceSource/LocalBusinessSource via REST, sem CLI/
subprocess (ETAPA 2/3).

Verificado contra a documentacao real da Apify (api.apify.com/v2 e paginas
dos actors, 19/08/2026): `POST /v2/actors/{actorId}/run-sync-get-dataset-
items` roda o actor e devolve os itens do dataset numa unica chamada HTTP -
sem polling manual. So' precisa de `APIFY_API_TOKEN`. Bem menos codigo que o
adapter Bright Data (que depende do CLI `bdata` instalado + login
interativo, nenhum dos dois disponivel neste ambiente) - por isso e' o
adapter primario pra dado real agora; Bright Data continua disponivel atras
da mesma porta.

Actors escolhidos (schema de entrada/saida confirmado por fetch direto da
pagina de cada um, nao por suposicao a partir do nome):
  - `gio21/mercado-livre-scraper` (Bloco A nacional) - busca por keyword.
  - `truefetch/amazon-price-tracker` (Bloco D internacional) - apesar do
    nome "Price Tracker", o input real e' busca por keyword (nao rastreio
    de ASIN conhecido) - confirmado na doc do actor.
  - `dtrungtin/ebay-items-scraper` (Bloco D internacional) - busca por
    keyword tambem, output NAO validado contra execucao real ainda.
  - `compass/google-maps-extractor` (Bloco B local/regional) - devolve
    nome/endereco/telefone/website do estabelecimento, sem preco (Maps nao
    tem preco) - por isso essas ofertas sempre caem em "sem_preco" com
    `contato` preenchido, que e' exatamente o proposito da Etapa Local.

Contrato de orcamento: cada chamada HTTP a um actor conta contra
`OrcamentoMCP` INDIVIDUALMENTE (nao uma vez por `buscar()`) - mesmo padrao
de `brightdata_mcp.py`, porque um `buscar()` pode disparar mais de um actor
(ex.: Mercado Livre + eBay + Amazon quando escopo e' internacional).
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from urllib.parse import quote

import httpx

from app.domain.busca_mercadolivre import extrair_mlb_id
from app.domain.classificacao import (
    REGIOES_BR,
    gerar_queries_fornecedores,
    gerar_queries_produto,
    pontos_venda_amostra,
)
from app.domain.extracao_pagina import (
    extrair_preco,
    extrair_quantidade_numerica,
    extrair_telefone,
    extrair_whatsapp,
    produto_aparece,
)
from app.domain.models import ConsultaLocal, ConsultaProduto, Oferta
from app.domain.normalizador import oferta_ou_none
from app.sourcing.erros import MCPRateLimitError
from app.sourcing.orcamento import OrcamentoExcedidoError, OrcamentoMCP

log = logging.getLogger("efraim.apify")

_BASE_URL = "https://api.apify.com/v2"

# header realista pra visitar site de terceiro (Bloco C, camada 2) - so'
# User-Agent levou 406 Not Acceptable em site real (achado 20/08); alguns
# servidores exigem Accept/Accept-Language tambem pra nao tratar como bot.
_HEADERS_VISITA_PAGINA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


async def _rodar_actor(
    actor_id: str, entrada: dict, *, token: str, timeout_s: float,
    nome_fonte: str, bloco: str, orcamento: OrcamentoMCP,
) -> list[dict]:
    orcamento.registrar_chamada(bloco)  # pode levantar OrcamentoExcedidoError
    # a API da Apify separa dono~nome do actor por til na URL, nao barra
    # (confirmado na doc oficial, 19/08/2026) - os IDs de config ficam no
    # formato "dono/nome" (igual ao Store) por legibilidade; convertido aqui.
    actor_id_url = actor_id.replace("/", "~")
    url = f"{_BASE_URL}/actors/{actor_id_url}/run-sync-get-dataset-items"
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(url, params={"token": token}, json=entrada)
    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After")
        raise MCPRateLimitError(nome_fonte, float(retry_after) if retry_after else None)
    if resp.status_code == 408:
        raise TimeoutError(f"actor '{actor_id}' nao terminou em {timeout_s}s (Apify run-sync)")
    resp.raise_for_status()
    # JSON e' SEMPRE UTF-8 por especificacao (RFC 8259) - `resp.json()`
    # decodifica via `resp.text`, que segue o charset DECLARADO no header
    # Content-Type quando presente, mesmo que esse charset esteja errado.
    # Titulos com aspas tipograficas/acentuacao vinham corrompidos
    # ("â€\x9d" no lugar de """) porque a resposta real da Apify caia nesse
    # caso - decodificar os bytes brutos como UTF-8 explicitamente e'
    # sempre correto pra JSON e elimina a dependencia do charset declarado
    # (achado em execucao real, 19/08).
    return json.loads(resp.content.decode("utf-8"))


def _corrigir_mojibake(texto: str) -> str:
    """Reverte UTF-8 lido como cp1252 (padrao classico de mojibake).
    Achado em execucao real (19/08): o actor de busca ampla (Bloco C) trouxe
    titulos corrompidos ("STÃ‰REO" no lugar de "STÉREO") - a causa aqui NAO
    e' decodificacao errada nossa (isso ja' foi corrigido em `_rodar_actor`,
    que forca UTF-8 na resposta HTTP da Apify) - o texto ja' chega
    corrompido de dentro do JSON, herdado de como o actor leu a pagina de
    origem de terceiro. So' substitui quando o roundtrip fecha sem erro
    (decode estrito) - mantem o original em qualquer duvida, pra nao
    arriscar corromper texto que ja' estava certo."""
    try:
        return texto.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto


def _sanear(bruto: dict) -> dict:
    return {k: (_corrigir_mojibake(v) if isinstance(v, str) else v) for k, v in bruto.items()}


def _para_oferta(bruto: dict, fonte: str) -> Oferta | None:
    return oferta_ou_none(_sanear(bruto), fonte=fonte)


class ApifyPriceSource:
    nome = "apify-price"

    def __init__(self, api_token: str, actor_mercadolivre: str, actor_ebay: str,
                 actor_amazon: str, timeout_s: float = 120.0) -> None:
        self.api_token = api_token
        self.actor_mercadolivre = actor_mercadolivre
        self.actor_ebay = actor_ebay
        self.actor_amazon = actor_amazon
        self.timeout_s = timeout_s

    @staticmethod
    def disponivel(api_token: str | None) -> bool:
        return bool(api_token)

    async def _rodar(
        self, actor_id: str, entrada: dict, bloco: str, orcamento: OrcamentoMCP,
    ) -> list[dict]:
        return await _rodar_actor(
            actor_id, entrada, token=self.api_token, timeout_s=self.timeout_s,
            nome_fonte=self.nome, bloco=bloco, orcamento=orcamento,
        )

    async def _tentar(
        self, corrotina: Awaitable[list[dict]], mapear: Callable[[dict], Oferta | None],
    ) -> tuple[list[Oferta], bool]:
        """Roda UM actor isoladamente. Uma falha aqui (rede, 403, actor
        indisponivel...) nao pode derrubar ofertas ja' obtidas de outro
        actor no mesmo `buscar()` - por isso cada chamada tem seu proprio
        try/except, nao um so' cobrindo A+D inteiro (achado em teste real,
        19/08: um 403 no actor de eBay estava descartando ofertas do
        Mercado Livre que ja' tinham sido buscadas com sucesso).
        Devolve (ofertas, orcamento_esgotado) - orcamento esgotado interrompe
        as PROXIMAS chamadas deste `buscar()`, as outras excecoes nao.

        `MCPRateLimitError` sobe pro orquestrador de proposito (backoff+
        retry do `buscar()` inteiro, ver `orquestrador.py::_com_protecao`) -
        um 429 e' sinal de "desacelera tudo", nao so' desta chamada.
        `TimeoutError` (incl. `httpx.ReadTimeout`, que E' um `TimeoutError`
        nesta versao) NAO sobe mais - fica isolado aqui como qualquer outro
        erro generico. Achado em execucao real (19/08, Bloco B): deixar
        TimeoutError propagar matava as 5 chamadas de regiao de uma vez so'
        quando UMA regiao ficava lenta - o mesmo problema vale aqui pra
        A/D."""
        try:
            itens = await corrotina
        except OrcamentoExcedidoError:
            return [], True
        except MCPRateLimitError:
            raise
        except Exception:  # noqa: BLE001 - isolamento proposital entre actors
            log.exception("falha num actor Apify individual — seguindo com os demais")
            return [], False
        return [o for i in itens if (o := mapear(i)) is not None], False

    async def buscar(self, consulta: ConsultaProduto, orcamento: OrcamentoMCP) -> list[Oferta]:
        termo = f"{consulta.item.nome} {consulta.item.marca or ''}".strip()
        ofertas: list[Oferta] = []

        novas, esgotado = await self._tentar(
            self._rodar(
                self.actor_mercadolivre,
                {"keyword": termo, "maxItems": 20, "maxPages": 1, "sort": "relevance"},
                "A", orcamento,
            ),
            self._mercadolivre_para_oferta,
        )
        ofertas += novas
        if esgotado or consulta.escopo.value != "internacional":
            return ofertas

        # este actor nao aceita keyword solto - precisa da URL de busca
        # pronta do eBay (achado em execucao real, 19/08, ao trocar de
        # actor por causa do aluguel expirado do anterior).
        url_busca_ebay = f"https://www.ebay.com/sch/i.html?_nkw={quote(termo)}"
        novas, esgotado = await self._tentar(
            self._rodar(
                self.actor_ebay,
                {"startUrls": [{"url": url_busca_ebay}], "maxItems": 20}, "D", orcamento,
            ),
            self._ebay_para_oferta,
        )
        ofertas += novas
        if esgotado:
            return ofertas

        novas, _ = await self._tentar(
            self._rodar(
                self.actor_amazon,
                # "United States" (nome completo, nao ISO "us") - achado real
                # (20/08): o actor rejeitava com 400 "Field input.country
                # must be equal to one of the allowed values: ...United
                # States..." - inspecionado o corpo da resposta real, nao
                # suposicao.
                {"keyword": termo, "country": "United States", "max_results": 20}, "D",
                orcamento,
            ),
            self._amazon_para_oferta,
        )
        ofertas += novas
        return ofertas

    def _mercadolivre_para_oferta(self, item: dict) -> Oferta | None:
        # actor devolve um item placeholder {"warning": "No products
        # found"...} quando a busca nao acha nada - nao e' produto, precisa
        # ser descartado aqui (achado em execucao real, 19/08).
        titulo = item.get("title")
        if not titulo:
            return None
        url = item.get("url", "")
        return _para_oferta({
            "produto": titulo,
            "preco": item.get("price"),
            "local": item.get("seller") or "Mercado Livre",
            "link": url,
            "moeda": "BRL",
            "disponibilidade": "em_estoque",
            # mesmo id do anuncio que `sourcing.busca_mercadolivre` extrai -
            # este actor E a busca direta cobrem o MESMO Mercado Livre por
            # 2 caminhos, podem trazer o mesmo anuncio 2x sem isso (achado
            # 20/08, revisao pedida pelo usuario).
            "id_externo": extrair_mlb_id(url),
        }, self.nome)

    def _ebay_para_oferta(self, item: dict) -> Oferta | None:
        # Campos de saida confirmados na doc real do actor (19/08/2026):
        # itemId, url, title, price, priceText, currency, condition,
        # buyingFormat, shipping, soldCount, watchers, soldDate, imageUrl.
        # "seller" so' vem com scrapeDetails=True (nao ligado - custo extra
        # por chamada), por isso o fallback "eBay" fica mais frequente aqui
        # do que nos outros blocos.
        titulo = item.get("title")
        if not titulo:
            return None
        return _para_oferta({
            "produto": titulo,
            "preco": item.get("price") or item.get("priceText"),
            "local": "eBay",
            "link": item.get("url", ""),
            "moeda": item.get("currency") or "USD",
            "disponibilidade": "em_estoque",
        }, self.nome)

    def _amazon_para_oferta(self, item: dict) -> Oferta | None:
        titulo = item.get("title")
        if not titulo:
            return None
        disponibilidade = "em_estoque" if item.get("stock_status") == "in_stock" else "desconhecida"
        return _para_oferta({
            "produto": titulo,
            "preco": item.get("price"),
            "marca": item.get("brand"),
            "local": item.get("seller") or "Amazon",
            "link": item.get("product_url", ""),
            "moeda": item.get("currency") or "USD",
            "disponibilidade": disponibilidade,
        }, self.nome)


class ApifyLocalSource:
    nome = "apify-local"

    def __init__(self, api_token: str, actor_google_maps: str, timeout_s: float = 120.0) -> None:
        self.api_token = api_token
        self.actor_google_maps = actor_google_maps
        self.timeout_s = timeout_s

    @staticmethod
    def disponivel(api_token: str | None) -> bool:
        return bool(api_token)

    async def buscar(self, consulta: ConsultaLocal, orcamento: OrcamentoMCP) -> list[Oferta]:
        onde = consulta.localizacao.cidade or consulta.localizacao.cep or "Brasil"
        termos = [f"{pv} {onde}" for pv in consulta.pontos_venda[:3]]
        termos = termos or [f"{consulta.item.nome} {onde}"]
        try:
            entrada = {
                "searchStringsArray": termos, "locationQuery": onde,
                "maxCrawledPlacesPerSearch": 5,
            }
            lugares = await _rodar_actor(
                self.actor_google_maps, entrada,
                token=self.api_token, timeout_s=self.timeout_s, nome_fonte=self.nome,
                bloco="B", orcamento=orcamento,
            )
        except OrcamentoExcedidoError:
            log.info("orcamento esgotado antes do bloco B/local — 0 ofertas de %s", self.nome)
            return []

        ofertas = [self._google_maps_para_oferta(consulta.item.nome, lugar) for lugar in lugares]
        return [o for o in ofertas if o is not None]

    def _google_maps_para_oferta(self, item_nome: str, lugar: dict) -> Oferta | None:
        telefone = lugar.get("phoneUnformatted") or lugar.get("phone")
        website = lugar.get("website")
        contato_raw = None
        if telefone or website:
            contato_raw = {"telefone": (telefone,) if telefone else (), "form_url": website}
        # Google Maps nao tem preco - a oferta sempre cai em "sem_preco",
        # com o contato do estabelecimento pra cotacao (proposito da Etapa
        # Local: achar QUEM contatar, nao QUANTO custa).
        return _para_oferta({
            "produto": item_nome,
            "preco": None,
            "local": lugar.get("title", ""),
            "link": website or "",
            "contato": contato_raw,
            "disponibilidade": "desconhecida",
            "cidade": lugar.get("city"),
            "uf": lugar.get("state"),
        }, self.nome)


class ApifyBroadSource:
    """Bloco C — busca ampla e irrestrita em 2 camadas (correcao do
    usuario, 20/08): CAMADA 1 busca so' pelo produto (sem qualificar tipo
    de loja) - todo resultado que voltar e' aceito direto, sem visita.
    CAMADA 2 busca por tipo de FORNECEDOR (loja fisica, fabricante,
    distribuidor, atacadista, importador, representante — os 6 grupos de
    `PONTOS_VENDA`, ver `pontos_venda_amostra`), sem o produto - descobre o
    NEGOCIO por categoria; so' depois visita algumas paginas encontradas
    ("pente fino") pra confirmar se o item da busca principal esta' la' e
    extrair preco/contato reais. Cruzado com as 5 regioes do Brasil na
    camada 2 - a busca NAO se restringe a uma regiao por padrao.

    E' o unico bloco que nao depende de uma lista fixa de sites: usa um
    actor de busca generica (Google SERP), nao um scraper de marketplace
    especifico.
    """
    nome = "apify-broad"

    # quantos resultados da CAMADA 2 tem a pagina visitada atras de preco/
    # contato reais ("pente fino") - conservador pelo mesmo motivo do Bloco
    # B: visitar toda pagina encontrada estouraria o orcamento compartilhado
    # do job. As nao visitadas ainda entram em "sem_preco" (achar QUEM
    # fornece, mesmo sem confirmar preco).
    LOJAS_COM_SITE_VISITADO = 8

    def __init__(self, api_token: str, actor_busca: str, timeout_s: float = 120.0) -> None:
        self.api_token = api_token
        self.actor_busca = actor_busca
        self.timeout_s = timeout_s

    @staticmethod
    def disponivel(api_token: str | None) -> bool:
        return bool(api_token)

    async def buscar(self, consulta: ConsultaProduto, orcamento: OrcamentoMCP) -> list[Oferta]:
        queries_produto = gerar_queries_produto(consulta.item)
        queries_fornecedores = gerar_queries_fornecedores(consulta.categoria)
        try:
            buscas = await _rodar_actor(
                self.actor_busca,
                {"queries": "\n".join(queries_produto + queries_fornecedores),
                 "countryCode": "br", "maxPagesPerQuery": 1, "resultsPerPage": 5},
                token=self.api_token, timeout_s=self.timeout_s,
                nome_fonte=self.nome, bloco="C", orcamento=orcamento,
            )
        except OrcamentoExcedidoError:
            log.info("orcamento esgotado antes do bloco C — 0 ofertas de %s", self.nome)
            return []
        except (MCPRateLimitError, TimeoutError):
            raise
        except Exception:  # noqa: BLE001 - resiliencia proposital
            log.exception("falha no bloco C (busca ampla)")
            return []

        # o actor devolve 1 item de dataset POR QUERY, na mesma ordem que
        # foram enviadas - a fatia separa camada 1 (produto puro) de camada
        # 2 (fornecedor, precisa de "pente fino" antes de aceitar preco).
        buscas_camada1 = buscas[:len(queries_produto)]
        buscas_camada2 = buscas[len(queries_produto):]

        ofertas: list[Oferta] = []
        for busca in buscas_camada1:
            for resultado in busca.get("organicResults", []):
                oferta = self._resultado_para_oferta(consulta.item.nome, resultado)
                if oferta is not None:
                    ofertas.append(oferta)

        candidatas = [
            resultado
            for busca in buscas_camada2
            for resultado in busca.get("organicResults", [])
            if resultado.get("title") and resultado.get("url")
        ]
        visitaveis, restantes = (
            candidatas[:self.LOJAS_COM_SITE_VISITADO], candidatas[self.LOJAS_COM_SITE_VISITADO:],
        )

        async with httpx.AsyncClient(timeout=self.timeout_s, follow_redirects=True) as client:
            orcamento_esgotado = False
            for resultado in visitaveis:
                if orcamento_esgotado:
                    oferta = self._resultado_para_oferta(consulta.item.nome, resultado)
                else:
                    try:
                        oferta = await self._visitar_e_confirmar(
                            consulta.item.nome, resultado, client, orcamento,
                        )
                    except OrcamentoExcedidoError:
                        orcamento_esgotado = True
                        oferta = self._resultado_para_oferta(consulta.item.nome, resultado)
                if oferta is not None:
                    ofertas.append(oferta)

        for resultado in restantes:
            oferta = self._resultado_para_oferta(consulta.item.nome, resultado)
            if oferta is not None:
                ofertas.append(oferta)

        return ofertas

    async def _visitar_e_confirmar(
        self, produto_nome: str, resultado: dict,
        client: httpx.AsyncClient, orcamento: OrcamentoMCP,
    ) -> Oferta | None:
        """Camada 2, "pente fino": visita a pagina do fornecedor descoberto
        por categoria e so' aceita preco se o produto da busca principal de
        fato aparecer nela - sem isso, qualquer "R$" solto (frete, outro
        produto, rodape) viraria falso positivo."""
        url = resultado["url"]
        orcamento.registrar_chamada("C")  # pode levantar OrcamentoExcedidoError
        try:
            # header so' com User-Agent levou 406 Not Acceptable em site real
            # (achado em execucao real, 20/08) - alguns servidores exigem
            # Accept/Accept-Language tambem pra nao tratar como bot.
            resp = await client.get(url, headers=_HEADERS_VISITA_PAGINA)
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:  # noqa: BLE001 - site de terceiro, isola por pagina
            log.warning(
                "falha ao visitar '%s' (bloco C, camada 2): %r - mantendo sem preco confirmado",
                url, exc,
            )
            return self._resultado_para_oferta(produto_nome, resultado)

        whatsapp = extrair_whatsapp(html) or extrair_telefone(html)
        confirmado = produto_aparece(html, produto_nome)
        preco = extrair_preco(html) if confirmado else None
        # numero real de unidades do lote, extraido da PAGINA VISITADA (nao
        # de `produto_nome`, que e' o termo buscado - `normalizar()` nao
        # teria como inferir certo a partir dele) - correcao do usuario
        # (20/08): "so' pode descartar apos fazer a conversao" pro preco por
        # unidade, ver `domain.models.Oferta.custo_unitario_centavos`.
        unidades_no_lote = extrair_quantidade_numerica(html) if confirmado else 1
        contato = None
        if whatsapp:
            contato = {"telefone": (), "whatsapp": (whatsapp,), "email": ()}
        return _para_oferta({
            "produto": produto_nome,
            "preco": preco,
            "local": resultado.get("title"),
            "link": url,
            "disponibilidade": "desconhecida",
            "contato": contato,
            "unidades_no_lote": unidades_no_lote,
        }, self.nome)

    def _resultado_para_oferta(self, produto_nome: str, resultado: dict) -> Oferta | None:
        titulo = resultado.get("title")
        url = resultado.get("url")
        if not titulo or not url:
            return None
        return _para_oferta({
            "produto": produto_nome,
            "preco": None,
            "local": titulo,
            "link": url,
            "disponibilidade": "desconhecida",
        }, self.nome)


class ApifyRegionalSource:
    """Bloco B — Google Maps por regiao. Cobre TODAS as 5 regioes do Brasil
    por padrao (Sul, Sudeste, Centro-Oeste, Norte, Nordeste) - a busca nao
    se restringe a uma regiao. Restringir a uma so' regiao por pedido
    explicito do usuario e' pendencia (campo ainda nao existe no payload da
    API). Cada oferta sai marcada com `regiao`, pra a resposta dividir a
    apresentacao por regiao (ver `jobs/tasks.py::_sem_preco_por_regiao`).

    As 5 chamadas de actor (uma por regiao - o Google Maps Extractor usa UM
    `locationQuery` por execucao, nao da' pra' combinar as 5 numa chamada so'
    com precisao) rodam em PARALELO via `asyncio.gather`, nao em sequencia.
    Achado em execucao real (19/08): sequencial fazia a SOMA das 5 chamadas
    estourar o timeout do orquestrador (`timeout_fonte_s`, que embrulha o
    `buscar()` inteiro) antes de terminar - isolar so' a falha individual
    (tentativa anterior) nao bastava, porque o timeout batia no NIVEL DE
    FORA, cancelando tudo sem devolver o parcial. Em paralelo, o tempo total
    e' o da regiao mais lenta, nao a soma das 5.
    """
    nome = "apify-regional"

    def __init__(self, api_token: str, actor_google_maps: str, timeout_s: float = 120.0) -> None:
        self.api_token = api_token
        self.actor_google_maps = actor_google_maps
        self.timeout_s = timeout_s

    @staticmethod
    def disponivel(api_token: str | None) -> bool:
        return bool(api_token)

    async def _uma_regiao(
        self, termos: list[str], regiao: str, orcamento: OrcamentoMCP,
    ) -> list[dict] | Exception:
        try:
            return await _rodar_actor(
                self.actor_google_maps,
                {"searchStringsArray": termos, "locationQuery": f"{regiao}, Brasil",
                 "maxCrawledPlacesPerSearch": 3},
                token=self.api_token, timeout_s=self.timeout_s,
                nome_fonte=self.nome, bloco="B", orcamento=orcamento,
            )
        except Exception as exc:  # noqa: BLE001 - devolvido pra' triagem no chamador
            return exc

    async def buscar(self, consulta: ConsultaProduto, orcamento: OrcamentoMCP) -> list[Oferta]:
        pvs = pontos_venda_amostra(consulta.categoria, por_grupo=1)[:3]
        termos = [f"{consulta.item.nome} {pv}" for pv in pvs] or [consulta.item.nome]

        resultados = await asyncio.gather(
            *(self._uma_regiao(termos, regiao, orcamento) for regiao in REGIOES_BR),
        )

        ofertas: list[Oferta] = []
        for regiao, resultado in zip(REGIOES_BR, resultados, strict=True):
            if isinstance(resultado, MCPRateLimitError):
                raise resultado  # sobe pro orquestrador (backoff+retry do buscar() inteiro)
            if isinstance(resultado, Exception):
                # OrcamentoExcedidoError, TimeoutError (incl. httpx.ReadTimeout)
                # e qualquer outra falha ficam isoladas por regiao - uma
                # regiao ruim nao pode derrubar as outras 4.
                log.warning(
                    "falha no bloco B pra regiao '%s': %r — seguindo com as demais",
                    regiao, resultado,
                )
                continue
            for lugar in resultado:
                oferta = self._para_oferta(consulta.item.nome, lugar, regiao)
                if oferta is not None:
                    ofertas.append(oferta)
        return ofertas

    def _para_oferta(self, produto_nome: str, lugar: dict, regiao: str) -> Oferta | None:
        telefone = lugar.get("phoneUnformatted") or lugar.get("phone")
        website = lugar.get("website")
        contato_raw = None
        if telefone or website:
            contato_raw = {"telefone": (telefone,) if telefone else (), "form_url": website}
        return _para_oferta({
            "produto": produto_nome,
            "preco": None,
            "local": lugar.get("title", ""),
            "link": website or "",
            "contato": contato_raw,
            "disponibilidade": "desconhecida",
            "regiao": regiao,
            "cidade": lugar.get("city"),
            "uf": lugar.get("state"),
        }, self.nome)
