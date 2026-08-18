"""Classificacao de produto e geracao de queries (ETAPA 1).

Unica fonte das queries. O catalogo completo de 18 categorias e os 6 grupos
de pontos de venda vivem no seed idempotente (scripts/seed_dev.py) e podem ser
carregados do banco; aqui mantemos um subconjunto canonico como fallback e para
testes deterministicos.
"""
from __future__ import annotations

import re
import unicodedata

from app.domain.models import (
    ConsultaLocal,
    ConsultaProduto,
    Escopo,
    ItemProduto,
    Localizacao,
)

FALLBACK_GERAL = "geral"

# categoria -> palavras-chave que a indicam
CATEGORIAS_KEYWORDS: dict[str, list[str]] = {
    "eletronico": ["conector", "jack", "cabo", "led", "resistor", "arduino", "fonte", "bateria"],
    "informatica": ["notebook", "ssd", "teclado", "mouse", "monitor", "roteador"],
    "alimento": ["arroz", "feijao", "acucar", "cafe", "oleo", "farinha"],
    "hortifruti": ["banana", "tomate", "alface", "batata", "cebola", "maca"],
    "pet": ["racao", "petisco", "coleira", "aquario", "areia"],
    "construcao": ["cimento", "tijolo", "argamassa", "tinta", "cano", "telha"],
    "ferramenta": ["furadeira", "parafusadeira", "chave", "alicate", "serra"],
    "limpeza": ["detergente", "sabao", "desinfetante", "agua sanitaria"],
}

# categoria -> 6 grupos de pontos de venda
PONTOS_VENDA: dict[str, dict[str, list[str]]] = {
    "eletronico": {
        "primarios": ["loja de eletronicos", "loja de celulares", "magazine"],
        "secundarios": ["supermercado", "hipermercado", "loja de informatica"],
        "cruzados": ["marketplace online", "loja de departamentos", "app de delivery"],
        "fabricantes": ["fabricante de eletronicos", "industria eletroeletronica"],
        "distribuidores": ["distribuidora de eletronicos", "atacadista", "representante"],
        "importadoras": ["importadora de eletronicos", "distribuidora importada"],
    },
    FALLBACK_GERAL: {
        "primarios": ["loja de variedades", "magazine"],
        "secundarios": ["supermercado", "hipermercado"],
        "cruzados": ["marketplace online", "loja de departamentos", "shopping center"],
        "fabricantes": ["fabricante"],
        "distribuidores": ["distribuidora", "atacadista"],
        "importadoras": ["importadora"],
    },
}

MARKETPLACES_BR = [
    "mercadolivre.com.br", "amazon.com.br", "magazineluiza.com.br",
    "americanas.com.br", "shopee.com.br", "aliexpress.com",
    "carrefour.com.br", "atacadao.com.br",
]

REGIOES_BR = ["Sul", "Sudeste", "Centro-Oeste", "Norte", "Nordeste"]


def normalizar(texto: str) -> str:
    """lowercase, sem acento, colapsa espacos. Usado tambem no historico."""
    t = unicodedata.normalize("NFKD", texto)
    t = t.encode("ascii", "ignore").decode("ascii").lower()
    t = re.sub(r"\s+", " ", t).strip()
    return t


def classificar(nome: str) -> str:
    n = normalizar(nome)
    melhores = [
        cat for cat, kws in CATEGORIAS_KEYWORDS.items()
        if any(normalizar(k) in n for k in kws)
    ]
    return melhores[0] if melhores else FALLBACK_GERAL


def pontos_venda_de(categoria: str) -> list[str]:
    grupos = PONTOS_VENDA.get(categoria, PONTOS_VENDA[FALLBACK_GERAL])
    return [pv for grupo in grupos.values() for pv in grupo]


def _batches(itens: list[str], n: int) -> list[list[str]]:
    return [itens[i:i + n] for i in range(0, len(itens), n)]


def gerar_queries_nacionais(item: ItemProduto) -> list[str]:
    base = f"{item.nome} {item.marca or ''}".strip()
    queries: list[str] = []
    # batches de 3 marketplaces para nao estourar limite de string do buscador
    for batch in _batches(MARKETPLACES_BR, 3):
        sites = " OR ".join(f"site:{s}" for s in batch)
        queries.append(f"{base} comprar preco {sites}")
    return queries


def gerar_queries_profundas(item: ItemProduto, categoria: str) -> list[str]:
    pvs = pontos_venda_de(categoria)[:3]
    queries: list[str] = []
    for regiao in REGIOES_BR:
        for pv in pvs:
            queries.append(f"{pv} {regiao} Brasil")
    # sites proprios de distribuidores/fabricantes, excluindo marketplaces
    exc = " ".join(f"-site:{s}" for s in MARKETPLACES_BR)
    queries.append(f"{item.nome} distribuidor fabricante {exc}")
    return queries


def gerar_queries_locais(item: ItemProduto, loc: Localizacao, categoria: str) -> list[str]:
    onde = loc.cidade or loc.cep or "Brasil"
    return [f"{pv} {onde} raio {loc.raio_km}km" for pv in pontos_venda_de(categoria)[:4]]


def gerar_queries_internacionais(item: ItemProduto, termo_en: str, termo_zh: str) -> list[str]:
    eua = ["mouser.com", "digikey.com", "newark.com", "ebay.com", "amazon.com"]
    china = ["1688.com", "alibaba.com", "made-in-china.com", "lcsc.com"]
    q = [f"{termo_en} buy price site:{s}" for s in eua]
    q += [f"{termo_zh} site:{s}" for s in china]
    return q


def montar_consulta_produto(item: ItemProduto, escopo: Escopo) -> ConsultaProduto:
    categoria = classificar(item.nome)
    queries = gerar_queries_nacionais(item)
    if escopo is Escopo.INTERNACIONAL:
        # traducao real e feita pelo agente (LLM); aqui apenas placeholder.
        queries += gerar_queries_internacionais(item, item.nome, item.nome)
    return ConsultaProduto(item=item, escopo=escopo, categoria=categoria, queries=queries)


def montar_consulta_local(item: ItemProduto, loc: Localizacao) -> ConsultaLocal:
    categoria = classificar(item.nome)
    return ConsultaLocal(
        item=item,
        categoria=categoria,
        pontos_venda=pontos_venda_de(categoria),
        localizacao=loc,
        queries=gerar_queries_locais(item, loc, categoria),
    )
