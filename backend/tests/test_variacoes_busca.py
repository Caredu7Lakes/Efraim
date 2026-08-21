"""Mocks abaixo diferenciam a chamada pela URL (shopping/organico/visita
de link) - o `buscar_e_aprender` real faz VARIAS chamadas por busca agora
(shopping + paginas organicas + 1 visita por link achado), nao mais 1 so'.

Correcao do usuario (20/08): a paginacao SEMPRE vai ate' `MAX_PAGINAS`,
mesmo quando uma pagina no meio nao traz link novo ("duplicidade" so' faz
o link ja' visto ser pulado, nunca encerra a busca inteira)."""
from __future__ import annotations

import httpx
import pytest

from app.sourcing.orcamento import OrcamentoMCP
from app.sourcing.variacoes_busca import buscar_e_aprender

_ORGANICO_PAGINA_1 = """
<div class="yuRUbf"><a jsname="x" class="zReHs"
href="https://orielec.com.br/">
<h3 class="LC20lb">ORIELEC - Componentes Eletrônicos</h3></a></div>
<div class="related-question-pair"
data-q="conector jack p10"></div>
<div class="related-question-pair"
data-q="Onde comprar eletrônicos importados?"></div>
"""

_HTML_LOJA = "<html>Conector Jack P10 disponivel. R$ 12,50. wa.me/5511999998888</html>"


class _Repo:
    def __init__(self) -> None:
        self.chamadas: list[tuple[str, list[str]]] = []

    async def salvar_variacoes_busca(self, categoria: str, variacoes: list[str]) -> None:
        self.chamadas.append((categoria, variacoes))


class _RespostaFalsa:
    def __init__(self, status_code: int, texto: str) -> None:
        self.status_code = status_code
        self.text = texto
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro", request=None, response=self)  # type: ignore[arg-type]


def _post_padrao(pagina2_vazia: bool = True):
    chamadas_por_url: list[str] = []

    async def _post(self, url, headers=None, json=None):
        alvo = json["url"]
        chamadas_por_url.append(alvo)
        if "tbm=shop" in alvo:
            return _RespostaFalsa(200, "<html>sem shopping neste teste</html>")
        if "orielec.com.br" in alvo:
            return _RespostaFalsa(200, _HTML_LOJA)
        if "start=" not in alvo:  # pagina 1
            return _RespostaFalsa(200, _ORGANICO_PAGINA_1)
        # paginas seguintes: sem resultado novo -> para por duplicidade
        return _RespostaFalsa(200, "<html>sem resultado organico aqui</html>")

    return _post, chamadas_por_url


def _consulta_padrao():
    return "conector jack p10", "eletronico"


@pytest.mark.asyncio
async def test_sem_credenciais_devolve_vazio_sem_chamar_rede(monkeypatch):
    chamou = False

    async def _post_falso(self, url, headers=None, json=None):
        nonlocal chamou
        chamou = True
        return _RespostaFalsa(200, "")

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    repo = _Repo()
    termo, categoria = _consulta_padrao()
    ofertas = await buscar_e_aprender(
        termo, categoria, zone=None, token=None, repo=repo,
        orcamento=OrcamentoMCP(limite_por_job=400),
    )
    assert ofertas == []
    assert not chamou
    assert repo.chamadas == []


@pytest.mark.asyncio
async def test_visita_cada_link_organico_e_pagina_ate_max_paginas_mesmo_com_pagina_vazia(
    monkeypatch,
):
    post_falso, chamadas = _post_padrao()
    monkeypatch.setattr(httpx.AsyncClient, "post", post_falso)

    repo = _Repo()
    termo, categoria = _consulta_padrao()
    ofertas = await buscar_e_aprender(
        termo, categoria, zone="efraim_1", token="token-fake", repo=repo,
        orcamento=OrcamentoMCP(limite_por_job=400),
    )

    # shopping (1) + 18 paginas organicas (pagina 1 tem resultado, 2-18 nao) +
    # 1 visita ao unico link achado (na pagina 1) = 20
    assert len(chamadas) == 20
    assert any("tbm=shop" in c for c in chamadas)
    assert any("start=10" in c for c in chamadas)  # pagina 2, sem resultado - nao para aqui
    assert any("start=170" in c for c in chamadas)  # foi ate' a ultima pagina (18a, indice 17)
    assert not any("start=180" in c for c in chamadas)  # nao passou de MAX_PAGINAS

    assert len(ofertas) == 1
    oferta = ofertas[0]
    assert oferta.preco_centavos == 1250  # produto apareceu na pagina - preco aceito
    assert oferta.contato.whatsapp == ("5511999998888",)
    assert oferta.fonte == "google-serp-direto"

    assert len(repo.chamadas) == 1
    categoria_salva, variacoes = repo.chamadas[0]
    assert categoria_salva == "eletronico"
    assert variacoes == ["Onde comprar eletrônicos importados?"]


@pytest.mark.asyncio
async def test_shopping_sem_link_marca_preco_como_nao_confirmado(monkeypatch):
    html_shopping = (
        '<div class="mhqZ2c"><div class="gkQHve x">Conector P10</div></div>'
        '<div class="mhqZ2c"><div class="FG68Ac" aria-label="Pre'
        + "ç" + 'o atual: R$' + "\xa0" + '5,00. " role="group">'
        '<span class="lmQWe">R$' + "\xa0" + '5,00</span></div></div>'
        '<div class="mhqZ2c"><span class="WJMUdc rw5ecc">LojaX</span></div>'
    )

    async def _post_falso(self, url, headers=None, json=None):
        alvo = json["url"]
        if "tbm=shop" in alvo:
            return _RespostaFalsa(200, html_shopping)
        return _RespostaFalsa(200, "<html>sem resultado organico</html>")

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    repo = _Repo()
    termo, categoria = _consulta_padrao()
    ofertas = await buscar_e_aprender(
        termo, categoria, zone="efraim_1", token="token-fake", repo=repo,
        orcamento=OrcamentoMCP(limite_por_job=400),
    )

    shopping = [o for o in ofertas if o.fonte == "google-shopping"]
    assert len(shopping) == 1
    assert shopping[0].link == ""
    assert shopping[0].preco_centavos == 500
    assert "nao confirmada" in shopping[0].produto or "não confirmada" in shopping[0].produto
    assert shopping[0].local == "LojaX"


@pytest.mark.asyncio
async def test_orcamento_esgotado_no_meio_devolve_parcial_sem_quebrar(monkeypatch):
    post_falso, _ = _post_padrao()
    monkeypatch.setattr(httpx.AsyncClient, "post", post_falso)

    repo = _Repo()
    termo, categoria = _consulta_padrao()
    # orcamento pequeno: da' pra 1 ou 2 chamadas, nao pra tudo
    ofertas = await buscar_e_aprender(
        termo, categoria, zone="efraim_1", token="token-fake", repo=repo,
        orcamento=OrcamentoMCP(limite_por_job=1),
    )
    assert isinstance(ofertas, list)  # nao quebrou, so' devolveu o que deu


@pytest.mark.asyncio
async def test_falha_de_rede_na_pagina_1_devolve_vazio_sem_quebrar(monkeypatch):
    async def _post_falso(self, url, headers=None, json=None):
        return _RespostaFalsa(500, "")

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_falso)
    repo = _Repo()
    termo, categoria = _consulta_padrao()
    ofertas = await buscar_e_aprender(
        termo, categoria, zone="efraim_1", token="token-fake", repo=repo,
        orcamento=OrcamentoMCP(limite_por_job=400),
    )
    assert ofertas == []
    assert repo.chamadas == []
