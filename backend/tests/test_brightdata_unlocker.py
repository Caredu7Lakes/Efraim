"""Testa o adapter Bright Data (Bloco B) sem rede real - `httpx.AsyncClient.
post`/`.get` trocados por fake via monkeypatch. Shapes de request/response
(trigger -> poll -> download, campos `name`/`address`/`phone_number`/
`open_website`) sao os mesmos capturados em chamadas reais (curl) contra a
API antes de escrever o adapter, ver docstring de `brightdata_unlocker.py`.
A regiao de cada oferta vem do `address` da loja (nao da cidade-ancora que
entrou no job) - ver correcao do usuario documentada la'."""
from __future__ import annotations

import httpx
import pytest

from app.domain.models import ConsultaProduto, Escopo, ItemProduto
from app.domain.regioes import TODAS_CIDADES
from app.sourcing.adapters.brightdata_unlocker import BrightDataRegionalSource
from app.sourcing.erros import MCPRateLimitError
from app.sourcing.orcamento import OrcamentoMCP

_TOTAL_CIDADES = len(TODAS_CIDADES)
_ENDERECO_CURITIBA = "Av. Sete de Setembro, 3561 - Centro, Curitiba - PR, 80250-250"
_ENDERECO_SALVADOR = "Rua Chile, 20 - Centro, Salvador - BA, 40020-000"


class _RespostaFalsa:
    def __init__(self, status_code: int, dados, headers: dict | None = None) -> None:
        self.status_code = status_code
        self._dados = dados
        self.headers = headers or {}
        self.content = b""
        self.text = ""

    def json(self):
        return self._dados

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro brightdata", request=None, response=self)  # type: ignore[arg-type]


def _loja(nome: str, site: str, endereco: str, telefone: str | None = "04132251333") -> dict:
    return {
        "url": f"https://maps.google.com/{nome}", "country": "Brazil", "name": nome,
        "address": endereco, "phone_number": telefone, "open_website": site,
        "rating": 4.5, "reviews_count": 10,
    }


def _fonte() -> BrightDataRegionalSource:
    return BrightDataRegionalSource("zona-fake", "token-fake")


def _consulta() -> ConsultaProduto:
    return ConsultaProduto(
        item=ItemProduto(nome="conector jack p10"), escopo=Escopo.NACIONAL, categoria="eletronico",
    )


def _mocks_padrao(
    monkeypatch, lojas: list[dict], *, status_trigger: int = 200, status_poll: str = "ready",
):
    """Monta o fluxo completo trigger->poll->download com as `lojas` dadas.
    Retorna listas pra inspecao (chamadas de trigger/poll/download)."""
    chamadas_post = []
    chamadas_get = []

    async def _post_falso(self, url, headers=None, params=None, json=None):
        chamadas_post.append((url, params, json))
        if "/trigger" in url:
            if status_trigger != 200:
                return _RespostaFalsa(status_trigger, {}, headers={"Retry-After": "3"})
            return _RespostaFalsa(200, {"snapshot_id": "snap-fake-1"})
        # visita de site (Web Unlocker) - resposta generica sem preco
        return _RespostaFalsa(200, {})

    async def _get_falso(self, url, headers=None, params=None):
        chamadas_get.append((url, params))
        if "/progress/" in url:
            return _RespostaFalsa(200, {"status": status_poll})
        if "/snapshot/" in url:
            return _RespostaFalsa(200, lojas)
        raise AssertionError(f"GET inesperado: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    monkeypatch.setattr(httpx.AsyncClient, "get", _get_falso)
    return chamadas_post, chamadas_get


def test_disponivel_exige_zone_e_token():
    assert BrightDataRegionalSource.disponivel(None, "token") is False
    assert BrightDataRegionalSource.disponivel("zona", None) is False
    assert BrightDataRegionalSource.disponivel("", "") is False
    assert BrightDataRegionalSource.disponivel("zona", "token") is True


@pytest.mark.asyncio
async def test_trigger_envia_uma_entrada_por_cidade_num_unico_job(monkeypatch):
    """1 UNICO job cobre todas as cidades - nao mais 1 requisicao por
    cidade (correcao do usuario, 20/08: 'uma unica busca com tempo de
    pesquisa mais prolongado')."""
    lojas = [_loja("Loja Sem Site", "https://facebook.com/x", _ENDERECO_CURITIBA)]
    chamadas_post, _ = _mocks_padrao(monkeypatch, lojas)

    orcamento = OrcamentoMCP(limite_por_job=1000)
    await _fonte().buscar(_consulta(), orcamento)

    triggers = [c for c in chamadas_post if "/trigger" in c[0]]
    assert len(triggers) == 1  # UM UNICO POST de trigger, nao 31
    _, params, corpo = triggers[0]
    assert params["dataset_id"] == "gd_m8ebnr0q2qlklc02fz"
    assert params["discover_by"] == "location"
    assert len(corpo["input"]) == _TOTAL_CIDADES
    cidades_no_input = {item["country"] for item in corpo["input"]}
    assert len(cidades_no_input) == _TOTAL_CIDADES  # cada cidade aparece uma vez


@pytest.mark.asyncio
async def test_regiao_vem_do_endereco_da_loja(monkeypatch):
    """Correcao do usuario (20/08): regiao e' classificada apos a coleta, a
    partir do endereco real - nao depende de qual entrada do job gerou o
    resultado."""
    lojas = [
        _loja("Loja SP", "https://facebook.com/a", _ENDERECO_CURITIBA),
        _loja("Loja BA", "https://facebook.com/b", _ENDERECO_SALVADOR),
    ]
    _mocks_padrao(monkeypatch, lojas)

    ofertas = await _fonte().buscar(_consulta(), OrcamentoMCP(limite_por_job=1000))

    assert len(ofertas) == 2
    por_nome = {o.produto: o for o in ofertas}
    assert por_nome["Loja SP"].regiao == "Sul"
    assert por_nome["Loja SP"].uf == "PR"
    assert por_nome["Loja SP"].cidade == "Curitiba"
    assert por_nome["Loja BA"].regiao == "Norte e Nordeste"
    assert por_nome["Loja BA"].uf == "BA"


@pytest.mark.asyncio
async def test_visita_site_proprio_e_extrai_preco_e_whatsapp(monkeypatch):
    html_loja = (
        "<html><body>Conector Jack P10 custa R$ 45,90 hoje. "
        "Fale conosco: https://wa.me/5541998892777</body></html>"
    )
    lojas = [_loja("Loja Com Site", "https://sotudo.com.br/", _ENDERECO_CURITIBA)]

    async def _post_falso(self, url, headers=None, params=None, json=None):
        if "/trigger" in url:
            return _RespostaFalsa(200, {"snapshot_id": "snap-fake-1"})
        assert json is None or "zone" in json  # visita de site: Web Unlocker
        resp = _RespostaFalsa(200, {})
        resp.text = html_loja
        return resp

    async def _get_falso(self, url, headers=None, params=None):
        if "/progress/" in url:
            return _RespostaFalsa(200, {"status": "ready"})
        return _RespostaFalsa(200, lojas)

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    monkeypatch.setattr(httpx.AsyncClient, "get", _get_falso)

    ofertas = await _fonte().buscar(_consulta(), OrcamentoMCP(limite_por_job=1000))

    assert len(ofertas) == 1
    oferta = ofertas[0]
    assert oferta.preco_centavos == 4590
    assert oferta.contato.whatsapp == ("5541998892777",)
    assert oferta.regiao == "Sul"


@pytest.mark.asyncio
async def test_pente_fino_ignora_preco_quando_produto_nao_aparece_na_pagina(monkeypatch):
    """Camada 2 (correcao do usuario, 20/08): a descoberta e' por
    categoria, so' a visita ao site confirma se o item da busca principal
    esta' la'. Um "R$" solto (frete, outro produto, rodape) sem o produto
    aparecer na pagina nao pode virar oferta com preco - falso positivo."""
    html_sem_produto = (
        "<html><body>Frete gratis acima de R$ 45,90. "
        "Fale conosco: https://wa.me/5541998892777</body></html>"
    )
    lojas = [_loja("Loja Sem O Produto", "https://sotudo.com.br/", _ENDERECO_CURITIBA)]

    async def _post_falso(self, url, headers=None, params=None, json=None):
        if "/trigger" in url:
            return _RespostaFalsa(200, {"snapshot_id": "snap-fake-1"})
        resp = _RespostaFalsa(200, {})
        resp.text = html_sem_produto
        return resp

    async def _get_falso(self, url, headers=None, params=None):
        if "/progress/" in url:
            return _RespostaFalsa(200, {"status": "ready"})
        return _RespostaFalsa(200, lojas)

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    monkeypatch.setattr(httpx.AsyncClient, "get", _get_falso)

    ofertas = await _fonte().buscar(_consulta(), OrcamentoMCP(limite_por_job=1000))

    assert len(ofertas) == 1
    oferta = ofertas[0]
    assert oferta.preco_centavos is None  # "R$" existe na pagina, mas o produto nao - descartado
    assert oferta.contato.whatsapp == ("5541998892777",)  # contato ainda e' valido
    assert oferta.contato.whatsapp == ("5541998892777",)
    assert oferta.regiao == "Sul"


@pytest.mark.asyncio
async def test_rede_social_nao_e_visitada_mas_ainda_vira_oferta_sem_preco(monkeypatch):
    visitas = []
    lojas = [_loja("So' Instagram", "https://instagram.com/lojafake", _ENDERECO_CURITIBA)]

    async def _post_falso(self, url, headers=None, params=None, json=None):
        if "/trigger" in url:
            return _RespostaFalsa(200, {"snapshot_id": "snap-fake-1"})
        visitas.append(url)
        return _RespostaFalsa(200, {})

    async def _get_falso(self, url, headers=None, params=None):
        if "/progress/" in url:
            return _RespostaFalsa(200, {"status": "ready"})
        return _RespostaFalsa(200, lojas)

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    monkeypatch.setattr(httpx.AsyncClient, "get", _get_falso)

    ofertas = await _fonte().buscar(_consulta(), OrcamentoMCP(limite_por_job=1000))

    assert visitas == []  # nunca visitou o link de instagram
    assert len(ofertas) == 1
    assert ofertas[0].preco_centavos is None
    assert ofertas[0].contato.telefone == ("04132251333",)


@pytest.mark.asyncio
async def test_poll_aguarda_ate_status_ready(monkeypatch):
    """Job comeca 'running', so' fica 'ready' na 3a consulta de status -
    confirma que o adapter espera de verdade, nao assume pronto na 1a."""
    lojas = [_loja("Loja", "https://facebook.com/x", _ENDERECO_CURITIBA)]
    status_sequencia = iter(["running", "running", "ready"])
    consultas_de_status = []

    async def _post_falso(self, url, headers=None, params=None, json=None):
        return _RespostaFalsa(200, {"snapshot_id": "snap-fake-1"})

    async def _get_falso(self, url, headers=None, params=None):
        if "/progress/" in url:
            status = next(status_sequencia)
            consultas_de_status.append(status)
            return _RespostaFalsa(200, {"status": status})
        return _RespostaFalsa(200, lojas)

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    monkeypatch.setattr(httpx.AsyncClient, "get", _get_falso)

    fonte = _fonte()
    import app.sourcing.adapters.brightdata_unlocker as modulo
    monkeypatch.setattr(modulo, "POLL_INTERVAL_S", 0.01)  # nao esperar de verdade no teste

    ofertas = await fonte.buscar(_consulta(), OrcamentoMCP(limite_por_job=1000))

    assert consultas_de_status == ["running", "running", "ready"]
    assert len(ofertas) == 1


@pytest.mark.asyncio
async def test_job_com_falha_devolve_lista_vazia_sem_quebrar(monkeypatch):
    async def _post_falso(self, url, headers=None, params=None, json=None):
        return _RespostaFalsa(200, {"snapshot_id": "snap-fake-1"})

    async def _get_falso(self, url, headers=None, params=None):
        if "/progress/" in url:
            return _RespostaFalsa(200, {"status": "failed"})
        return _RespostaFalsa(200, [])

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    monkeypatch.setattr(httpx.AsyncClient, "get", _get_falso)

    ofertas = await _fonte().buscar(_consulta(), OrcamentoMCP(limite_por_job=1000))
    assert ofertas == []


@pytest.mark.asyncio
async def test_rate_limit_no_trigger_propaga_pro_orquestrador(monkeypatch):
    async def _post_falso(self, url, headers=None, params=None, json=None):
        return _RespostaFalsa(429, {}, headers={"Retry-After": "3"})

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)

    with pytest.raises(MCPRateLimitError):
        await _fonte().buscar(_consulta(), OrcamentoMCP(limite_por_job=1000))


@pytest.mark.asyncio
async def test_orcamento_esgotado_antes_do_trigger_devolve_vazio_sem_quebrar(monkeypatch):
    async def _post_falso(self, url, headers=None, params=None, json=None):
        raise AssertionError("nao deveria chamar - orcamento ja' esgotado")

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    orcamento = OrcamentoMCP(limite_por_job=0)  # ja' no teto
    ofertas = await _fonte().buscar(_consulta(), orcamento)
    assert ofertas == []


@pytest.mark.asyncio
async def test_internacional_com_sinal_de_exportacao_tem_preco_aceito(monkeypatch):
    """Correcao do usuario (20/08): resultado sem endereco BR reconhecido
    (a busca por localizacao as vezes devolve loja de fora, achado em
    execucao real) nao e' "lixo" quando o site sinaliza que exporta/atende
    o Brasil - "se o preco do Peru for menor... e' o tipo de resultado que
    esperamos, isso e' minerar"."""
    # extracao de preco hoje so' reconhece formato R$ (BRL) - limitacao
    # conhecida, nao resolvida nesta correcao (o foco aqui e' o GATE de
    # exportacao, nao suporte a moeda estrangeira). Preco em R$ num site
    # peruano e' artificial pro teste, mas isola exatamente o que esta'
    # sendo verificado: o sinal de exportacao libera o preco encontrado.
    html_com_exportacao = (
        "<html>Conector Jack P10 - R$ 12,50. We ship worldwide, including Brazil. "
        "Contact: wa.me/51987654321</html>"
    )
    lojas = [_loja(
        "IR ELECTRONICS PERU", "http://irelectronics.pe/",
        "Av. Larco 123, Lima, Peru", telefone="+51 947 154 095",
    )]

    async def _post_falso(self, url, headers=None, params=None, json=None):
        if "/trigger" in url:
            return _RespostaFalsa(200, {"snapshot_id": "snap-fake-1"})
        resp = _RespostaFalsa(200, {})
        resp.text = html_com_exportacao
        return resp

    async def _get_falso(self, url, headers=None, params=None):
        if "/progress/" in url:
            return _RespostaFalsa(200, {"status": "ready"})
        return _RespostaFalsa(200, lojas)

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    monkeypatch.setattr(httpx.AsyncClient, "get", _get_falso)

    ofertas = await _fonte().buscar(_consulta(), OrcamentoMCP(limite_por_job=1000))

    assert len(ofertas) == 1
    assert ofertas[0].uf is None  # endereco nao reconhecido como BR
    assert ofertas[0].preco_centavos == 1250  # aceito mesmo assim - sinal de exportacao presente


@pytest.mark.asyncio
async def test_internacional_sem_sinal_de_exportacao_descarta_preco_mas_mantem_contato(monkeypatch):
    """Sem endereco BR E sem sinal de exportacao, o preco fica de fora da
    comparacao (nao confirmado que atende o Brasil) - mas o contato
    continua disponivel, nao e' descartado por completo."""
    html_sem_exportacao = (
        "<html>Conector Jack P10 - R$ 12,50 disponible en tienda. "
        "Contact: wa.me/51987654321</html>"
    )
    lojas = [_loja(
        "Nanoparuro", "http://nanoparuro.com/",
        "Av. Larco 456, Lima, Peru", telefone="+51 954 989 953",
    )]

    async def _post_falso(self, url, headers=None, params=None, json=None):
        if "/trigger" in url:
            return _RespostaFalsa(200, {"snapshot_id": "snap-fake-1"})
        resp = _RespostaFalsa(200, {})
        resp.text = html_sem_exportacao
        return resp

    async def _get_falso(self, url, headers=None, params=None):
        if "/progress/" in url:
            return _RespostaFalsa(200, {"status": "ready"})
        return _RespostaFalsa(200, lojas)

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    monkeypatch.setattr(httpx.AsyncClient, "get", _get_falso)

    ofertas = await _fonte().buscar(_consulta(), OrcamentoMCP(limite_por_job=1000))

    assert len(ofertas) == 1
    assert ofertas[0].preco_centavos is None  # sem sinal de exportacao - nao confirmado
    assert ofertas[0].contato.whatsapp == ("51987654321",)  # contato continua disponivel
