"""Cliente compartilhado do Bright Data Web Unlocker REST (ETAPA 1 -
extensao, 20/08/2026).

Ponto UNICO desta chamada - antes vivia dentro de
`adapters/brightdata_unlocker.py` (Bloco B); agora tambem e' usada por
`variacoes_busca.py` (Bloco C, aprendizado de variacoes via Google SERP
direto) - mesmo motivo de `domain/extracao_pagina.py` existir separado:
"a logica nao pode ser duplicada" (correcao do usuario, 20/08).

`POST https://api.brightdata.com/request` com `{"zone": <zone>, "url":
<alvo>, "format": "raw"}` - verificado por chamada real (curl) antes de
integrar. Usa `resp.text` (nao `.content.decode("utf-8")`) porque o corpo
e' HTML de site de TERCEIROS, que pode declarar qualquer charset (achado
em execucao real, 20/08: `UnicodeDecodeError` numa loja que servia
iso-8859-1) - `resp.text` do httpx detecta o charset certo a partir do
header/conteudo.
"""
from __future__ import annotations

import httpx

from app.sourcing.erros import MCPRateLimitError
from app.sourcing.orcamento import OrcamentoMCP

UNLOCKER_URL = "https://api.brightdata.com/request"


async def chamar_web_unlocker(
    url_alvo: str, *, client: httpx.AsyncClient, zone: str, token: str, orcamento: OrcamentoMCP,
    bloco: str, nome_fonte: str,
) -> str:
    orcamento.registrar_chamada(bloco)  # pode levantar OrcamentoExcedidoError
    resp = await client.post(
        UNLOCKER_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"zone": zone, "url": url_alvo, "format": "raw"},
    )
    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After")
        raise MCPRateLimitError(nome_fonte, float(retry_after) if retry_after else None)
    resp.raise_for_status()
    return resp.text
