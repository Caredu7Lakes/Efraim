"""Normalizacao para o schema unico `Oferta` e do nome de produto (historico)."""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import UTC, datetime

from app.domain.extracao_pagina import extrair_quantidade_numerica
from app.domain.models import (
    Condicao,
    Contato,
    Disponibilidade,
    Oferta,
)

log = logging.getLogger("efraim.normalizador")

_UNIDADES = {
    "kg",
    "g",
    "mg",
    "l",
    "ml",
    "un",
    "und",
    "cx",
    "m",
    "cm",
    "mm",
    "kit",
    "pc",
    "pct",
    "pacote",
    "caixa",
}


def normalizar_nome(nome: str) -> str:
    """Base de casamento do HistoricoPreco: sem acento, minusculo, sem unidade."""
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    tokens = [t for t in s.split() if t not in _UNIDADES]
    return " ".join(tokens)


def _preco_para_centavos(valor: float | int | str | None) -> int | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, str):
        valor = re.sub(r"[^0-9.,]", "", valor)
        if not valor:
            return None
        tem_ponto, tem_virgula = "." in valor, "," in valor
        if tem_ponto and tem_virgula:
            # separador decimal e o que aparece por ultimo (BR: "1.999,90" / US: "1,999.90")
            if valor.rfind(",") > valor.rfind("."):
                valor = valor.replace(".", "").replace(",", ".")
            else:
                valor = valor.replace(",", "")
        elif tem_virgula:
            valor = valor.replace(",", ".")
        elif tem_ponto:
            # ponto unico: decimal se tiver ate 2 casas (US "19.99"), senao e milhar BR ("1.999")
            inteiro, _, fracao = valor.rpartition(".")
            if not (inteiro and len(fracao) <= 2):
                valor = valor.replace(".", "")
        if not valor:
            return None
    return int(round(float(valor) * 100))


def normalizar(raw: dict, *, fonte: str) -> Oferta:
    """Converte um dict cru (de qualquer adapter/MCP) em `Oferta`."""
    contato_raw = raw.get("contato")
    contato = Contato(**contato_raw) if isinstance(contato_raw, dict) else contato_raw

    # quantidade real do lote/kit - quem chama pode passar explicitamente
    # (ex.: `_visitar_organico`, que ja' tem o HTML completo da pagina em
    # mãos, sinal mais confiavel) ou deixar em branco pra' inferir do
    # proprio nome/titulo do produto (cobre Mercado Livre/Shopee/actors,
    # cujos titulos reais costumam dizer "Kit 6 Conectores..." - correcao
    # do usuario, 20/08: "so' pode descartar apos fazer a conversao").
    unidades_no_lote = raw.get("unidades_no_lote") or extrair_quantidade_numerica(
        raw.get("produto", ""),
    )

    return Oferta(
        produto=raw["produto"],
        marca=raw.get("marca"),
        preco_centavos=_preco_para_centavos(raw.get("preco")),
        moeda=raw.get("moeda", "BRL"),
        local=raw.get("local", ""),
        link=raw.get("link", ""),
        fonte=fonte,
        coletado_em=raw.get("coletado_em") or datetime.now(UTC),
        pagamento=raw.get("pagamento"),
        unidades_no_lote=unidades_no_lote,
        id_externo=raw.get("id_externo"),
        # `Oferta.frete_centavos` e' `int` (default 0), nao `int | None` -
        # sem isso, custo_total_centavos (preco + frete) quebraria com
        # TypeError sempre que o raw nao trouxer "frete" (achado ao ligar o
        # primeiro chamador real de `normalizar`, o adapter Apify, 19/08).
        frete_centavos=_preco_para_centavos(raw.get("frete")) or 0,
        contato=contato,
        disponibilidade=Disponibilidade(raw.get("disponibilidade", "desconhecida")),
        condicao=Condicao(raw.get("condicao", "desconhecida")),
        regiao=raw.get("regiao"),
        cidade=raw.get("cidade"),
        uf=raw.get("uf"),
    )


def oferta_ou_none(bruto: dict, *, fonte: str) -> Oferta | None:
    """Wrapper de `normalizar` que descarta (com log) item malformado em vez
    de derrubar o adapter inteiro - um item ruim de uma fonte com centenas
    de resultados nao pode custar os outros. Ponto UNICO desse try/except:
    antes cada adapter (Apify, Bright Data MCP, Bright Data Unlocker)
    reimplementava a mesma logica separadamente (achado em 20/08, revisao
    pedida pelo usuario - "a logica nao pode ser duplicada")."""
    try:
        return normalizar(bruto, fonte=fonte)
    except (KeyError, ValueError, TypeError) as exc:
        log.warning("item ignorado — nao normalizou para Oferta (fonte=%s): %r", fonte, exc)
        return None
