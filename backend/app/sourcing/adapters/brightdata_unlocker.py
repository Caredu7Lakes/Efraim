"""Adapter Bright Data - Bloco B, busca ampla no Brasil com regiao
classificada POS-coleta (ETAPA 1 - extensao, 20/08/2026, 3a versao no
mesmo dia apos 3 correcoes do usuario).

Substitui `ApifyRegionalSource` (`apify_source.py`) como fonte do Bloco B:
o actor `compass/crawler-google-places` bateu 402 Payment Required em teste
real (creditos/plano da conta Apify insuficientes) - decisao explicita do
usuario foi migrar Bloco B pro Bright Data (Bloco A/C/D continuam na Apify,
que funciona).

Historico das 3 correcoes que mudaram o desenho no mesmo dia:

1) "as regioes devem ser apresentadas apos a coleta dos dados... isso e'
   diferente de pesquisa por regiao" — a regiao de cada OFERTA e' derivada
   do endereco real devolvido (`domain.regioes.extrair_uf_e_cidade` +
   `cluster_da_uf`), nunca da cidade-ancora usada na busca.

2) 1a implementacao usava a API REST do Web Unlocker (`api.brightdata.com/
   request`, uma requisicao HTTP por cidade) com concorrencia limitada a 3
   (teto medido contra a conta real). Mesmo assim, rodar as ~31 cidades em
   lotes de 3 levava minutos e o timeout do orquestrador (`timeout_fonte_s`)
   cancelava a chamada inteira ANTES de terminar, descartando tudo (so' 1
   das 31 cidades tinha sido tentada quando o timeout disparou, em execucao
   real).

3) Usuario perguntou por que nao usar "uma unica busca com tempo de
   pesquisa mais prolongado" em vez de 31 requisicoes HTTP nossas em
   paralelo. Resposta encontrada pesquisando a documentacao real da Bright
   Data: existe uma API de Datasets/Discover separada (`POST /datasets/v3/
   trigger?dataset_id=gd_m8ebnr0q2qlklc02fz&discover_by=location`) que
   aceita ATE 5000 ENTRADAS NUM UNICO REQUEST e processa tudo
   assincronamente NO LADO DA BRIGHT DATA (nao no nosso httpx client) -
   troca "31 conexoes simultaneas nossas" por "1 job, polling periodico ate
   ficar pronto". MEDIDO contra a conta real (20/08): 1 entrada levou 146s;
   3 entradas levaram 166s (nao 3x) - forte indicio de paralelismo interno
   do lado da Bright Data, exatamente o que resolve o problema de
   concorrencia sem cortar cobertura. Essa API virou o mecanismo PRINCIPAL
   de descoberta; o Web Unlocker REST (`sourcing.brightdata_client.
   chamar_web_unlocker`, compartilhado com o Bloco C) continua
   existindo so' pra aprofundar (visitar o site de umas poucas lojas atras
   de preco/WhatsApp reais).

Formato das APIs (tudo verificado por chamada real - curl - antes de
escrever qualquer linha; token real usado nos testes, ver `.env`):

  - Discover (Datasets v3), autenticacao so' `Authorization: Bearer
    <token>` (NAO usa `zone`, diferente do Web Unlocker):
      1. Trigger: `POST https://api.brightdata.com/datasets/v3/trigger
         ?dataset_id=gd_m8ebnr0q2qlklc02fz&include_errors=true
         &type=discover_new&discover_by=location&limit_per_input=N`
         corpo `{"input": [{"country": "<cidade>, Brazil", "keyword":
         "<termo>", "lat": ""}, ...], "custom_output_fields": [...]}`
         devolve `{"snapshot_id": "..."}`.
      2. Poll: `GET .../datasets/v3/progress/{snapshot_id}?format=json`
         devolve `{"status": "running"|"ready"|"failed", ...}`.
      3. Download: `GET .../datasets/v3/snapshot/{snapshot_id}?format=json`
         devolve uma LISTA de objetos: `{url, country, name, address,
         phone_number, open_website, rating, reviews_count,
         discovery_input: {...}}`.
    Achado no teste real: `"country": "Brazil"` sozinho (sem cidade) NAO
    da' cobertura nacional - resolve pra 1 unico lugar. Precisa mesmo de
    uma cidade por entrada; o que a API resolve e' rodar as N cidades em
    paralelo DO LADO DELES, nao eliminar a necessidade de enumerar
    cidades.
  - Web Unlocker REST (deepening, so' pras poucas lojas visitadas):
    `POST https://api.brightdata.com/request` com `{"zone": <zone>, "url":
    <site da loja>, "format": "raw"}` devolve o HTML puro - extracao de
    preco/WhatsApp e' regex local. NAO houve mojibake nessa API (diferente
    da Apify) - texto UTF-8 correto direto.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.domain.classificacao import pontos_venda_amostra
from app.domain.extracao_pagina import (
    exporta_para_brasil,
    extrair_preco,
    extrair_telefone,
    extrair_whatsapp,
    produto_aparece,
)
from app.domain.models import ConsultaProduto, Oferta
from app.domain.normalizador import oferta_ou_none
from app.domain.regioes import TODAS_CIDADES, cluster_da_uf, extrair_uf_e_cidade
from app.sourcing.brightdata_client import chamar_web_unlocker
from app.sourcing.erros import MCPRateLimitError
from app.sourcing.orcamento import OrcamentoExcedidoError, OrcamentoMCP

log = logging.getLogger("efraim.brightdata_unlocker")

_DATASET_ID_GOOGLE_MAPS = "gd_m8ebnr0q2qlklc02fz"
_TRIGGER_URL = "https://api.brightdata.com/datasets/v3/trigger"
_PROGRESS_URL = "https://api.brightdata.com/datasets/v3/progress/{snapshot_id}"
_SNAPSHOT_URL = "https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}"

_CAMPOS_SAIDA = [
    "url", "country", "name", "address", "phone_number",
    "open_website", "rating", "reviews_count",
]

# resultados por cidade-ancora pedidos ao discover. Nao multiplica o tempo
# de espera do job (processado em paralelo do lado da Bright Data - ver
# item 3 da docstring do modulo), so' o volume de dados.
LIMITE_POR_CIDADE = 15

POLL_INTERVAL_S = 5.0
# job assincrono do LADO da Bright Data - o tempo aqui e' quanto ESPERAMOS
# via polling, nao um timeout de conexao HTTP nossa. 10min cobre com folga
# o pior caso medido (146s pra 1 entrada; ~31 entradas em paralelo do lado
# deles nao deve escalar linearmente, mas nao foi medido no volume total).
POLL_TIMEOUT_S = 600.0

# quantas lojas (do total descoberto, ja' nao mais "por cidade") tem o
# proprio site visitado atras de preco/WhatsApp real - sequencial, nao
# paralelo (poucas o suficiente pra nao precisar de semaforo de novo).
LOJAS_COM_SITE_VISITADO = 8

_DOMINIOS_NAO_PROPRIOS = ("facebook.com", "instagram.com", "linktr.ee", "wa.me", "goo.gl", "g.page")


def _e_site_proprio(link: str | None) -> bool:
    return bool(link) and not any(d in link for d in _DOMINIOS_NAO_PROPRIOS)


async def _disparar_job(
    inputs: list[dict], *, token: str, client: httpx.AsyncClient,
    orcamento: OrcamentoMCP, nome_fonte: str,
) -> str:
    """Dispara o job de discover (ate' 5000 entradas por request) e devolve
    o snapshot_id. So' registra 1 chamada contra o orcamento - e' o unico
    request que de fato dispara trabalho pago; polling/download so' leem
    status/resultado de um job ja' disparado."""
    orcamento.registrar_chamada("B")  # pode levantar OrcamentoExcedidoError
    resp = await client.post(
        _TRIGGER_URL,
        params={
            "dataset_id": _DATASET_ID_GOOGLE_MAPS, "include_errors": "true",
            "type": "discover_new", "discover_by": "location",
            "limit_per_input": LIMITE_POR_CIDADE,
        },
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"input": inputs, "custom_output_fields": _CAMPOS_SAIDA},
    )
    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After")
        raise MCPRateLimitError(nome_fonte, float(retry_after) if retry_after else None)
    resp.raise_for_status()
    return resp.json()["snapshot_id"]


async def _aguardar_pronto(snapshot_id: str, *, token: str, client: httpx.AsyncClient) -> None:
    decorrido = 0.0
    headers = {"Authorization": f"Bearer {token}"}
    while decorrido < POLL_TIMEOUT_S:
        resp = await client.get(_PROGRESS_URL.format(snapshot_id=snapshot_id), headers=headers)
        resp.raise_for_status()
        status = resp.json().get("status")
        if status == "ready":
            return
        if status in ("failed", "error"):
            raise RuntimeError(f"job Bright Data '{snapshot_id}' terminou com status '{status}'")
        await asyncio.sleep(POLL_INTERVAL_S)
        decorrido += POLL_INTERVAL_S
    raise TimeoutError(f"job Bright Data '{snapshot_id}' nao ficou pronto em {POLL_TIMEOUT_S}s")


async def _baixar(snapshot_id: str, *, token: str, client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(
        _SNAPSHOT_URL.format(snapshot_id=snapshot_id),
        params={"format": "json"}, headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    dado = resp.json()
    return dado if isinstance(dado, list) else []


class BrightDataRegionalSource:
    """Bloco B - busca ampla e profunda no Brasil (nao "por regiao"; ver
    docstring do modulo). Descoberta via Datasets/discover_by=location da
    Bright Data (1 job cobre `domain.regioes.TODAS_CIDADES` de uma vez,
    processado em paralelo do lado deles); cada OFERTA e' classificada em
    regiao a partir do proprio endereco devolvido, nao da cidade-ancora."""

    nome = "brightdata-regional"

    def __init__(self, zone: str, token: str, timeout_s: float = 30.0) -> None:
        self.zone = zone
        self.token = token
        self.timeout_s = timeout_s

    @staticmethod
    def disponivel(zone: str | None, token: str | None) -> bool:
        return bool(zone and token)

    def _loja_para_oferta(
        self, loja: dict, *, preco: str | None = None, whatsapp: str | None = None,
    ) -> Oferta | None:
        nome = loja.get("name")
        if not nome:
            return None
        uf, cidade = extrair_uf_e_cidade(loja.get("address"))
        regiao = cluster_da_uf(uf)

        telefone = loja.get("phone_number")
        contato = None
        if telefone or whatsapp:
            contato = {
                "telefone": (telefone,) if telefone else (),
                "whatsapp": (whatsapp,) if whatsapp else (),
                "email": (),
            }
        bruto = {
            "produto": nome,
            "preco": preco,
            "local": nome,
            "link": loja.get("open_website") or loja.get("url") or "",
            "regiao": regiao,
            "cidade": cidade,
            "uf": uf,
            "contato": contato,
        }
        return oferta_ou_none(bruto, fonte=self.nome)

    async def _visitar_site(
        self, loja: dict, produto: str, client: httpx.AsyncClient, orcamento: OrcamentoMCP,
    ) -> Oferta | None:
        link = loja.get("open_website")
        try:
            html = await chamar_web_unlocker(
                link, client=client, zone=self.zone, token=self.token,
                orcamento=orcamento, bloco="B", nome_fonte=self.nome,
            )
        except (OrcamentoExcedidoError, MCPRateLimitError):
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "falha ao visitar site de '%s' (%s): %r - usando so' o telefone do Maps",
                loja.get("name"), link, exc,
            )
            return self._loja_para_oferta(loja)

        # "pente fino": so' aceita preco/whatsapp extraidos se o PRODUTO da
        # busca principal de fato aparece na pagina - sem isso, qualquer
        # "R$" no site (frete, outro produto, rodape) virava falso positivo
        # (achado em revisao, 20/08 - correcao do usuario sobre a busca em
        # 2 camadas: camada 2 descobre o NEGOCIO por categoria, so' depois
        # verifica se ELE tem o item da busca principal).
        #
        # Resultado internacional (endereco nao reconhecido como BR - achado
        # em execucao real, 20/08: o discover por localizacao devolveu lojas
        # do Peru/EAU mesmo ancorado no Brasil) NAO e' descartado so' por
        # isso - correcao do usuario: "se o preco do Peru for menor e o site
        # conter informacao que exporta pro Brasil entao nao e' lixo, e' o
        # tipo de resultado que esperamos". So' exige o sinal de exportacao
        # ALEM do produto aparecer - sem endereco BR e sem sinal de
        # exportacao, o preco fica de fora (nao confirmado que atende o
        # Brasil, nao "lixo").
        uf, _ = extrair_uf_e_cidade(loja.get("address"))
        preco_valido = (
            produto_aparece(html, produto) and (uf is not None or exporta_para_brasil(html))
        )

        whatsapp = extrair_whatsapp(html) or extrair_telefone(html)
        preco = extrair_preco(html) if preco_valido else None
        return self._loja_para_oferta(loja, preco=preco, whatsapp=whatsapp)

    async def buscar(self, consulta: ConsultaProduto, orcamento: OrcamentoMCP) -> list[Oferta]:
        # Camada 2 da busca (correcao do usuario, 20/08): a query de
        # DESCOBERTA no Maps e' so' a categoria de fornecedor (loja/
        # distribuidor/importador/fabricante), NUNCA o nome do produto -
        # Maps indexa negocio por categoria, nao por catalogo de produto
        # (misturar os dois derrubou o retorno de ~15 lojas/cidade pra ~0.1
        # em teste real). O produto entra so' depois, na visita ao site
        # (`_visitar_site`/`domain.extracao_pagina.produto_aparece`) - "entrar em cada pagina e
        # procurar o item da busca principal".
        pvs = pontos_venda_amostra(consulta.categoria, por_grupo=1)
        termo_categoria = pvs[0] if pvs else consulta.categoria
        inputs = [
            {"country": f"{cidade}, Brazil", "keyword": termo_categoria, "lat": ""}
            for cidade in TODAS_CIDADES
        ]

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            try:
                snapshot_id = await _disparar_job(
                    inputs, token=self.token, client=client,
                    orcamento=orcamento, nome_fonte=self.nome,
                )
            except OrcamentoExcedidoError:
                log.info("orcamento esgotado antes de disparar o bloco B - 0 ofertas")
                return []

            try:
                await _aguardar_pronto(snapshot_id, token=self.token, client=client)
                lojas = await _baixar(snapshot_id, token=self.token, client=client)
            except Exception as exc:  # noqa: BLE001
                log.warning("job do bloco B ('%s') falhou/expirou: %r", snapshot_id, exc)
                return []

            ofertas: list[Oferta] = []
            visitaveis = 0
            orcamento_esgotado = False
            for loja in lojas:
                pode_visitar = (
                    not orcamento_esgotado
                    and visitaveis < LOJAS_COM_SITE_VISITADO
                    and _e_site_proprio(loja.get("open_website"))
                )
                if pode_visitar:
                    visitaveis += 1
                    try:
                        produto = consulta.item.nome
                        oferta = await self._visitar_site(loja, produto, client, orcamento)
                    except OrcamentoExcedidoError:
                        orcamento_esgotado = True
                        oferta = self._loja_para_oferta(loja)
                else:
                    oferta = self._loja_para_oferta(loja)
                if oferta is not None:
                    ofertas.append(oferta)
        return ofertas
