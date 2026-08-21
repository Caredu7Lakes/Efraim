"""Testa o adapter Apify sem rede real: `httpx.AsyncClient.post` e' trocado
por um fake via monkeypatch (sem dependencia nova - httpx ja e' usado).
`_RespostaFalsa` simula bytes reais (`.content`), nao um dict ja' pronto -
e' o que permite pegar bug de encoding (a resposta real e' decodificada via
`.content.decode("utf-8")`, nao via `.json()` do httpx)."""
from __future__ import annotations

import json as jsonlib

import httpx
import pytest

from app.domain.models import (
    ConsultaLocal,
    ConsultaProduto,
    Escopo,
    ItemProduto,
    Localizacao,
)
from app.sourcing.adapters.apify_source import (
    ApifyBroadSource,
    ApifyLocalSource,
    ApifyPriceSource,
    ApifyRegionalSource,
)
from app.sourcing.erros import MCPRateLimitError
from app.sourcing.orcamento import OrcamentoMCP


class _RespostaFalsa:
    def __init__(self, status_code: int, dados, headers: dict | None = None) -> None:
        self.status_code = status_code
        if dados is not None:
            self.content = jsonlib.dumps(dados, ensure_ascii=False).encode("utf-8")
        else:
            self.content = b""
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro apify", request=None, response=self)  # type: ignore[arg-type]


def _fonte_preco() -> ApifyPriceSource:
    return ApifyPriceSource("token-fake", "actor-ml", "actor-ebay", "actor-amazon")


def _consulta(nome: str, escopo: Escopo) -> ConsultaProduto:
    return ConsultaProduto(item=ItemProduto(nome=nome), escopo=escopo, categoria="eletronico")


def test_disponivel_exige_token():
    assert ApifyPriceSource.disponivel(None) is False
    assert ApifyPriceSource.disponivel("") is False
    assert ApifyPriceSource.disponivel("algum-token") is True


@pytest.mark.asyncio
async def test_url_usa_til_nao_barra_para_dono_do_actor(monkeypatch):
    """API da Apify separa dono~nome do actor por til, nao barra - IDs de
    config ficam no formato "dono/nome" (igual ao Store) por legibilidade,
    convertidos na hora de montar a URL (achado em teste real, 19/08)."""
    urls = []

    async def _post_falso(self, url, params=None, json=None):
        urls.append(url)
        return _RespostaFalsa(200, [])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    fonte = ApifyPriceSource(
        "token-fake", "gio21/mercado-livre-scraper", "actor-ebay", "actor-amazon",
    )
    await fonte.buscar(_consulta("x", Escopo.NACIONAL), OrcamentoMCP(limite_por_job=10))

    assert "gio21~mercado-livre-scraper" in urls[0]
    assert "gio21/mercado-livre-scraper" not in urls[0]


@pytest.mark.asyncio
async def test_buscar_mercadolivre_mapeia_para_oferta(monkeypatch):
    async def _post_falso(self, url, params=None, json=None):
        assert "run-sync-get-dataset-items" in url
        assert params["token"] == "token-fake"
        return _RespostaFalsa(200, [
            {"title": "Conector Jack P10", "price": "8.00", "seller": "Cirilo Cabos",
             "url": "https://cirilocabos.com.br/x"},
        ])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    orcamento = OrcamentoMCP(limite_por_job=10)
    consulta = _consulta("conector jack p10", Escopo.NACIONAL)
    ofertas = await _fonte_preco().buscar(consulta, orcamento)

    assert len(ofertas) == 1
    assert ofertas[0].produto == "Conector Jack P10"
    assert ofertas[0].preco_centavos == 800
    assert ofertas[0].local == "Cirilo Cabos"
    assert ofertas[0].fonte == "apify-price"
    assert ofertas[0].moeda == "BRL"
    assert orcamento.total_usado() == 1


@pytest.mark.asyncio
async def test_decodifica_utf8_mesmo_sem_charset_no_content_type(monkeypatch):
    """Achado em execucao real (19/08): titulos com aspas tipograficas/
    acentuacao vinham corrompidos ("a ums ão" virava mojibake) porque
    `resp.json()` seguia o charset (errado) que o httpx detectava, em vez
    de decodificar como UTF-8 - que e' o unico charset valido pra JSON."""
    titulo = "Notebook 15,6” com acentuação e çedilha"  # aspa tipografica U+201D

    async def _post_falso(self, url, params=None, json=None):
        return _RespostaFalsa(200, [{"title": titulo, "price": "10.00", "seller": "Loja"}])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("notebook", Escopo.NACIONAL)
    ofertas = await _fonte_preco().buscar(consulta, OrcamentoMCP(limite_por_job=10))
    assert ofertas[0].produto == titulo


@pytest.mark.asyncio
async def test_corrige_mojibake_herdado_do_actor(monkeypatch):
    """Achado em execucao real (19/08, Bloco C): o actor de busca ampla
    trouxe titulos com UTF-8 lido como cp1252 DENTRO do proprio dataset
    (nao e' erro nosso de decodificacao HTTP - isso ja' foi corrigido
    separadamente) - "STÉREO" chegava como "STÃ‰REO"."""
    titulo_corrompido = "CONECTOR PLUG P10 - ST" + chr(0xC3) + chr(0x2030) + "REO"

    async def _post_falso(self, url, params=None, json=None):
        return _RespostaFalsa(200, [
            {"title": titulo_corrompido, "price": "10.00", "seller": "Loja"},
        ])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("conector p10", Escopo.NACIONAL)
    ofertas = await _fonte_preco().buscar(consulta, OrcamentoMCP(limite_por_job=10))
    assert ofertas[0].produto == "CONECTOR PLUG P10 - STÉREO"


@pytest.mark.asyncio
async def test_correcao_de_mojibake_nao_mexe_em_texto_ja_correto(monkeypatch):
    """A correcao so' deve agir quando o roundtrip fecha sem erro - texto
    ja' corretamente acentuado nao pode ser corrompido por engano."""
    titulo_correto = "Distribuidora Eletrônicos São Paulo Ltda"

    async def _post_falso(self, url, params=None, json=None):
        return _RespostaFalsa(200, [
            {"title": titulo_correto, "price": "10.00", "seller": "Loja"},
        ])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("x", Escopo.NACIONAL)
    ofertas = await _fonte_preco().buscar(consulta, OrcamentoMCP(limite_por_job=10))
    assert ofertas[0].produto == titulo_correto


@pytest.mark.asyncio
async def test_item_sem_produto_do_actor_e_descartado(monkeypatch):
    """O actor de Mercado Livre devolve um item placeholder
    {"warning": "No products found"...} quando a busca nao acha nada - nao
    e' produto, tem que ser descartado (achado em execucao real, 19/08)."""
    async def _post_falso(self, url, params=None, json=None):
        return _RespostaFalsa(200, [
            {"warning": "No products found. Try a different keyword or try again later.",
             "keyword": "x"},
        ])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("x", Escopo.NACIONAL)
    ofertas = await _fonte_preco().buscar(consulta, OrcamentoMCP(limite_por_job=10))
    assert ofertas == []


@pytest.mark.asyncio
async def test_escopo_internacional_chama_ebay_e_amazon_tambem(monkeypatch):
    urls_chamadas = []

    async def _post_falso(self, url, params=None, json=None):
        urls_chamadas.append(url)
        return _RespostaFalsa(200, [])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("3.5mm stereo jack connector", Escopo.INTERNACIONAL)
    await _fonte_preco().buscar(consulta, OrcamentoMCP(limite_por_job=10))

    assert len(urls_chamadas) == 3  # mercado livre + ebay + amazon
    assert any("actor-ebay" in u for u in urls_chamadas)
    assert any("actor-amazon" in u for u in urls_chamadas)


@pytest.mark.asyncio
async def test_escopo_nacional_nao_chama_ebay_nem_amazon(monkeypatch):
    chamadas = []

    async def _post_falso(self, url, params=None, json=None):
        chamadas.append(url)
        return _RespostaFalsa(200, [])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("arroz tipo 1", Escopo.NACIONAL)
    await _fonte_preco().buscar(consulta, OrcamentoMCP(limite_por_job=10))

    assert len(chamadas) == 1
    assert "actor-ml" in chamadas[0]


@pytest.mark.asyncio
async def test_orcamento_esgotado_devolve_lista_vazia_sem_chamar_http(monkeypatch):
    chamadas = []

    async def _post_falso(self, url, params=None, json=None):
        chamadas.append(url)
        return _RespostaFalsa(200, [{"title": "x", "price": "1.00"}])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("x", Escopo.NACIONAL)
    ofertas = await _fonte_preco().buscar(consulta, OrcamentoMCP(limite_por_job=0))
    assert ofertas == []
    assert chamadas == []  # orcamento corta ANTES da chamada HTTP acontecer


@pytest.mark.asyncio
async def test_falha_no_ebay_nao_descarta_ofertas_do_mercado_livre(monkeypatch):
    """Achado em teste real (19/08): um 403 no actor de eBay estava
    derrubando ofertas do Mercado Livre ja' buscadas com sucesso, porque as
    3 chamadas dividiam um so' try/except."""
    async def _post_falso(self, url, params=None, json=None):
        if "actor-ml" in url:
            return _RespostaFalsa(200, [
                {"title": "Conector Jack P10", "price": "8.00", "seller": "Cirilo Cabos"},
            ])
        if "actor-ebay" in url:
            return _RespostaFalsa(403, None)
        return _RespostaFalsa(200, [])  # amazon

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("3.5mm stereo jack connector", Escopo.INTERNACIONAL)
    ofertas = await _fonte_preco().buscar(consulta, OrcamentoMCP(limite_por_job=10))

    assert any(o.local == "Cirilo Cabos" for o in ofertas)


@pytest.mark.asyncio
async def test_amazon_mapeia_estoque_e_moeda(monkeypatch):
    async def _post_falso(self, url, params=None, json=None):
        if "actor-ebay" in url:
            return _RespostaFalsa(200, [])
        if "actor-amazon" in url:
            return _RespostaFalsa(200, [{
                "title": "3.5mm Stereo Jack Connector", "price": 4.5, "currency": "USD",
                "brand": "Amphenol", "seller": "Amazon.com", "product_url": "https://amazon.com/x",
                "stock_status": "in_stock",
            }])
        return _RespostaFalsa(200, [])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("3.5mm stereo jack connector", Escopo.INTERNACIONAL)
    ofertas = await _fonte_preco().buscar(consulta, OrcamentoMCP(limite_por_job=10))
    amazon = next(o for o in ofertas if o.local == "Amazon.com")
    assert amazon.preco_centavos == 450
    assert amazon.moeda == "USD"
    assert amazon.disponibilidade.value == "em_estoque"
    assert amazon.marca == "Amphenol"


@pytest.mark.asyncio
async def test_429_levanta_rate_limit_error(monkeypatch):
    async def _post_falso(self, url, params=None, json=None):
        return _RespostaFalsa(429, None, headers={"Retry-After": "3"})

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("x", Escopo.NACIONAL)
    with pytest.raises(MCPRateLimitError) as exc:
        await _fonte_preco().buscar(consulta, OrcamentoMCP(limite_por_job=10))
    assert exc.value.retry_after_s == 3.0


@pytest.mark.asyncio
async def test_408_e_isolado_nao_propaga(monkeypatch):
    """Achado em execucao real (19/08, Bloco B): deixar TimeoutError
    propagar matava um `buscar()` inteiro (5 chamadas de regiao) so' porque
    UMA ficou lenta. Agora e' isolado como qualquer outro erro generico -
    devolve lista vazia pra ESSE actor, nao derruba o resto."""
    async def _post_falso(self, url, params=None, json=None):
        return _RespostaFalsa(408, None)

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("x", Escopo.NACIONAL)
    ofertas = await _fonte_preco().buscar(consulta, OrcamentoMCP(limite_por_job=10))
    assert ofertas == []


@pytest.mark.asyncio
async def test_local_google_maps_mapeia_para_sem_preco_com_contato(monkeypatch):
    async def _post_falso(self, url, params=None, json=None):
        assert "actor-maps" in url
        assert json["locationQuery"] == "Itatiba"
        return _RespostaFalsa(200, [{
            "title": "Distribuidora Eletronica Itatiba", "phoneUnformatted": "+551199998888",
            "website": "https://distribuidora.example.com", "categoryName": "Loja de eletronicos",
        }])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    fonte = ApifyLocalSource("token-fake", "actor-maps")
    consulta = ConsultaLocal(
        item=ItemProduto(nome="conector jack p10"), categoria="eletronico",
        pontos_venda=["loja de eletronicos"], localizacao=Localizacao(cidade="Itatiba"),
    )
    ofertas = await fonte.buscar(consulta, OrcamentoMCP(limite_por_job=10))

    assert len(ofertas) == 1
    o = ofertas[0]
    assert o.preco_centavos is None  # Google Maps nao tem preco - vai pra sem_preco
    assert o.local == "Distribuidora Eletronica Itatiba"
    assert o.contato is not None
    assert o.contato.telefone == ("+551199998888",)
    assert o.contato.form_url == "https://distribuidora.example.com"


def _fonte_ampla() -> ApifyBroadSource:
    return ApifyBroadSource("token-fake", "actor-busca")


@pytest.mark.asyncio
async def test_broad_source_manda_todas_queries_numa_chamada_so(monkeypatch):
    """Bloco C nao restringe regiao nem tipo de fornecedor - uma chamada
    so' com todas as queries (camada 1: produto puro; camada 2: ponto-de-
    venda x regiao, sem produto), separadas por linha (formato aceito pelo
    actor de busca, confirmado 19/08). Correcao do usuario (20/08): as 2
    camadas nao misturam produto+categoria na mesma query - ver
    test_classificacao.py."""
    entradas = []

    async def _post_falso(self, url, params=None, json=None):
        entradas.append(json)
        return _RespostaFalsa(200, [])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("conector jack p10", Escopo.NACIONAL)
    await _fonte_ampla().buscar(consulta, OrcamentoMCP(limite_por_job=10))

    assert len(entradas) == 1
    queries = entradas[0]["queries"].split("\n")
    # 1 camada 1 (produto) + 15 camada 2 (3 grupos fabricante/distribuidor/
    # importador x 5 regioes - "eletronico" usa o override curado, ver
    # GRUPOS_CAMADA2_POR_CATEGORIA em test_classificacao.py)
    assert len(queries) == 16
    # so' os marketplaces com busca DEDICADA real (ML, Amazon, eBay) ficam
    # excluidos do Bloco C - os demais (Magazine Luiza, Americanas, Shopee,
    # AliExpress, Carrefour, Atacadao) nao tinham cobertura em lugar nenhum
    # (correcao do usuario, 20/08 - ver MARKETPLACES_COM_COBERTURA_DEDICADA)
    assert queries[0] == "conector jack p10 comprar " + " ".join(
        f"-site:{s}" for s in ["mercadolivre.com.br", "amazon.com.br", "ebay.com"]
    )
    assert all("conector jack p10" not in q for q in queries[1:])  # camada 2 nao tem o produto
    assert all("supermercado" not in q for q in queries[1:])  # grupo excluido pra eletronico
    assert any("Sul" in q for q in queries[1:])
    assert any("Norte" in q for q in queries[1:])


@pytest.mark.asyncio
async def test_broad_source_camada1_mapeia_direto_sem_visitar_pagina(monkeypatch):
    """Camada 1 (produto puro) aceita o resultado direto - nao visita a
    pagina (a busca ja' foi pelo produto, sem qualificador de categoria)."""
    visitas = []

    async def _post_falso(self, url, params=None, json=None):
        return _RespostaFalsa(200, [
            {
                "searchQuery": {"term": "conector jack p10 comprar"},
                "organicResults": [
                    {"title": "Loja Camada 1", "url": "https://abc.example.com",
                     "description": "Vende o produto"},
                ],
            },
        ] + [{"searchQuery": {"term": "x"}, "organicResults": []}] * 30)  # camada 2 vazia

    async def _get_falso(self, url, headers=None):
        visitas.append(url)
        raise AssertionError("camada 1 nao deveria visitar pagina")

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    monkeypatch.setattr(httpx.AsyncClient, "get", _get_falso)

    consulta = _consulta("conector jack p10", Escopo.NACIONAL)
    ofertas = await _fonte_ampla().buscar(consulta, OrcamentoMCP(limite_por_job=40))

    assert visitas == []
    assert len(ofertas) == 1
    assert ofertas[0].local == "Loja Camada 1"
    assert ofertas[0].preco_centavos is None


@pytest.mark.asyncio
async def test_broad_source_camada2_visita_pagina_e_aceita_preco_so_se_produto_aparece(monkeypatch):
    """Camada 2 (fornecedor por categoria) visita a pagina descoberta e so'
    aceita preco se o produto da busca principal de fato aparecer nela -
    "pente fino" (correcao do usuario, 20/08)."""
    html_por_url = {
        "https://abc.example.com": (
            "<html>Conector Jack P10 por R$ 12,50. Whatsapp wa.me/5511999998888</html>"
        ),
        "https://xyz.example.com": (
            "<html>Frete gratis acima de R$ 200,00 em qualquer compra</html>"
        ),
    }

    async def _post_falso(self, url, params=None, json=None):
        buscas = [{"searchQuery": {"term": "conector jack p10 comprar"}, "organicResults": []}]
        buscas.append({
            "searchQuery": {"term": "distribuidora Sul Brasil"},
            "organicResults": [
                {"title": "Distribuidora ABC Eletrônicos", "url": "https://abc.example.com"},
            ],
        })
        buscas.append({
            "searchQuery": {"term": "importadora Norte Brasil"},
            "organicResults": [
                {"title": "Importadora XYZ", "url": "https://xyz.example.com"},
            ],
        })
        buscas += [{"searchQuery": {"term": "x"}, "organicResults": []}] * 28
        return _RespostaFalsa(200, buscas)

    async def _get_falso(self, url, headers=None):
        class _Resp:
            text = html_por_url[url]
            def raise_for_status(self) -> None:
                return None
        return _Resp()

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    monkeypatch.setattr(httpx.AsyncClient, "get", _get_falso)

    consulta = _consulta("conector jack p10", Escopo.NACIONAL)
    ofertas = await _fonte_ampla().buscar(consulta, OrcamentoMCP(limite_por_job=40))

    por_local = {o.local: o for o in ofertas}
    assert por_local["Distribuidora ABC Eletrônicos"].preco_centavos == 1250
    assert por_local["Distribuidora ABC Eletrônicos"].contato.whatsapp == ("5511999998888",)
    assert por_local["Importadora XYZ"].preco_centavos is None  # produto nao aparece na pagina


@pytest.mark.asyncio
async def test_broad_source_falha_generica_nao_propaga(monkeypatch):
    async def _post_falso(self, url, params=None, json=None):
        return _RespostaFalsa(500, None)

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("x", Escopo.NACIONAL)
    ofertas = await _fonte_ampla().buscar(consulta, OrcamentoMCP(limite_por_job=10))
    assert ofertas == []


def _fonte_regional() -> ApifyRegionalSource:
    return ApifyRegionalSource("token-fake", "actor-maps")


@pytest.mark.asyncio
async def test_regional_cobre_todas_5_regioes_sem_restringir(monkeypatch):
    """Bloco B nao restringe a uma regiao - cobre as 5 por padrao.
    Restringir a uma so' e' pendencia (ainda nao codada)."""
    locations = []

    async def _post_falso(self, url, params=None, json=None):
        locations.append(json["locationQuery"])
        return _RespostaFalsa(200, [])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("conector jack p10", Escopo.NACIONAL)
    await _fonte_regional().buscar(consulta, OrcamentoMCP(limite_por_job=10))

    assert len(locations) == 5
    for regiao in ["Sul", "Sudeste", "Centro-Oeste", "Norte", "Nordeste"]:
        assert any(regiao in loc for loc in locations)


@pytest.mark.asyncio
async def test_regional_marca_cada_oferta_com_a_regiao_de_origem(monkeypatch):
    async def _post_falso(self, url, params=None, json=None):
        regiao = json["locationQuery"].split(",")[0]
        return _RespostaFalsa(200, [{"title": f"Loja {regiao}", "phone": "11999999999"}])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("conector jack p10", Escopo.NACIONAL)
    ofertas = await _fonte_regional().buscar(consulta, OrcamentoMCP(limite_por_job=10))

    assert len(ofertas) == 5
    assert {o.regiao for o in ofertas} == {"Sul", "Sudeste", "Centro-Oeste", "Norte", "Nordeste"}
    assert all(o.preco_centavos is None for o in ofertas)


@pytest.mark.asyncio
async def test_regional_falha_numa_regiao_nao_derruba_as_outras(monkeypatch):
    async def _post_falso(self, url, params=None, json=None):
        if "Norte" in json["locationQuery"]:
            return _RespostaFalsa(500, None)
        return _RespostaFalsa(200, [{"title": "Loja", "phone": "11999999999"}])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("x", Escopo.NACIONAL)
    ofertas = await _fonte_regional().buscar(consulta, OrcamentoMCP(limite_por_job=10))

    assert len(ofertas) == 4  # 5 regioes - 1 que falhou


@pytest.mark.asyncio
async def test_regional_rate_limit_numa_regiao_propaga_pro_orquestrador(monkeypatch):
    """429 e' diferente de falha generica - sobe pro orquestrador (backoff+
    retry do buscar() inteiro), nao fica isolado como as outras excecoes."""
    async def _post_falso(self, url, params=None, json=None):
        if "Norte" in json["locationQuery"]:
            return _RespostaFalsa(429, None, headers={"Retry-After": "2"})
        return _RespostaFalsa(200, [{"title": "Loja", "phone": "11999999999"}])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    consulta = _consulta("x", Escopo.NACIONAL)
    with pytest.raises(MCPRateLimitError):
        await _fonte_regional().buscar(consulta, OrcamentoMCP(limite_por_job=10))
