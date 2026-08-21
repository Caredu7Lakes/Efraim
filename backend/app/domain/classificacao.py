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

# categoria -> palavras-chave que a indicam. Nucleo de 8 categorias (uso
# tecnico/eletronico, foco original do Efraim) + 12 portadas do catalogo do
# protototipo Base44 (`.agents/skills/agente-compras/scripts/run.py` em
# WelcomeScreen/efraim - achado em 19/08 revisando material anexado pelo
# usuario) para cobrir o catalogo domestico completo. "agua mineral"/"agua
# com gas" ficam FORA de "bebida" de proposito - o Base44 original as
# incluia, mas isso quebraria o fallback deliberado pra 'agua' generica (ver
# test_agua_pura_cai_no_fallback_geral).
CATEGORIAS_KEYWORDS: dict[str, list[str]] = {
    "eletronico": ["conector", "jack", "cabo", "led", "resistor", "arduino", "fonte", "bateria"],
    "informatica": ["notebook", "ssd", "teclado", "mouse", "monitor", "roteador"],
    "alimento": ["arroz", "feijao", "acucar", "cafe", "oleo", "farinha"],
    "hortifruti": ["banana", "tomate", "alface", "batata", "cebola", "maca"],
    "pet": ["racao", "petisco", "coleira", "aquario", "areia"],
    "construcao": ["cimento", "tijolo", "argamassa", "tinta", "cano", "telha"],
    "ferramenta": ["furadeira", "parafusadeira", "chave", "alicate", "serra"],
    "limpeza": [
        "detergente", "sabao", "desinfetante", "agua sanitaria",
        "amaciante", "alvejante", "multiuso",
    ],
    "floricultura_jardinagem": [
        "orquidea", "muda", "vaso", "adubo", "fertilizante", "semente",
        "jardinagem", "suculenta", "cacto", "floricultura", "viveiro",
    ],
    "carne": [
        "frango", "linguica", "costela", "alcatra", "picanha", "bacon",
        "presunto", "salsicha", "hamburguer",
    ],
    "bebida": [
        "refrigerante", "suco", "cerveja", "vinho", "whisky", "vodka",
        "cachaca", "energetico", "guarana", "isotonico", "champanhe",
    ],
    "higiene": [
        "shampoo", "condicionador", "creme dental", "fralda", "absorvente",
        "desodorante", "escova de dente", "fio dental", "maquiagem", "perfume",
    ],
    "padaria": [
        "pao", "baguete", "croissant", "rosca", "bolacha", "bolo", "torta", "pao de queijo",
    ],
    "vestuario": [
        "camisa", "calca", "vestido", "blusa", "jaqueta", "terno",
        "gravata", "sutia", "tenis", "sandalia",
    ],
    "papelaria": [
        "caderno", "caneta", "lapis", "borracha", "cartolina",
        "grampeador", "tesoura", "mochila",
    ],
    "farmacia": [
        "remedio", "analgesico", "antitermico", "antialergico", "xarope",
        "vitamina", "suplemento", "atadura",
    ],
    "brinquedo": ["brinquedo", "boneca", "boneco", "lego", "quebra cabeca", "tabuleiro"],
    "livro": ["livro", "revista", "quadrinhos", "manga"],
    "eletrodomesticos": [
        "geladeira", "fogao", "microondas", "lava loucas", "maquina de lavar",
        "air fryer", "liquidificador", "batedeira", "torradeira", "cafeteira",
    ],
    "moveis": ["sofa", "guarda roupa", "estante", "rack", "cristaleira", "colchao"],
}

# categoria -> 6 grupos de pontos de venda. primarios/secundarios/cruzados
# portados do protototipo Base44 (`associar_pontos_venda` em
# WelcomeScreen/efraim/.agents/skills/agente-compras/scripts/run.py, achado
# em 19/08); fabricantes/distribuidores/importadoras sao extensao propria
# do Efraim (o protototipo Base44 so' tinha 3 grupos - ver `pontos_venda_amostra`
# acima sobre por que os 6 grupos importam pra Bloco C nao ficar restrito a
# varejo).
PONTOS_VENDA: dict[str, dict[str, list[str]]] = {
    "eletronico": {
        "primarios": ["loja de eletronicos", "loja de celulares", "magazine"],
        "secundarios": ["supermercado", "hipermercado", "loja de informatica"],
        "cruzados": ["marketplace online", "loja de departamentos", "app de delivery"],
        "fabricantes": ["fabricante de eletronicos", "industria eletroeletronica"],
        "distribuidores": ["distribuidora de eletronicos", "atacadista", "representante"],
        "importadoras": ["importadora de eletronicos", "distribuidora importada"],
    },
    "informatica": {
        "primarios": ["loja de informatica", "loja de eletronicos", "assistencia tecnica"],
        "secundarios": ["magazine", "hipermercado", "papelaria"],
        "cruzados": ["marketplace online", "loja de departamentos"],
        "fabricantes": ["fabricante de informatica", "industria de hardware"],
        "distribuidores": ["distribuidora de informatica", "atacadista", "representante"],
        "importadoras": ["importadora de informatica", "distribuidora importada"],
    },
    "alimento": {
        "primarios": [
            "supermercado", "atacarejo", "atacado", "mercearia",
            "mercado", "mini-mercado", "mercadinho",
        ],
        "secundarios": [
            "distribuidora de alimentos", "emporio",
            "loja de produtos naturais", "quitanda",
        ],
        "cruzados": [
            "padaria", "conveniencia", "posto de gasolina",
            "app de delivery", "feira livre",
        ],
        "fabricantes": ["fabricante de alimentos", "industria alimenticia"],
        "distribuidores": ["distribuidora de alimentos", "atacadista", "representante comercial"],
        "importadoras": ["importadora de alimentos", "trading de alimentos"],
    },
    "hortifruti": {
        "primarios": ["quitanda", "feira", "sacolao", "loja de hortifruti", "verdurao"],
        "secundarios": [
            "supermercado", "ceasa", "mercado municipal",
            "produtor rural", "feira livre",
        ],
        "cruzados": ["atacarejo", "app de delivery", "emporio", "loja de produtos naturais"],
        "fabricantes": ["produtor rural", "cooperativa agricola"],
        "distribuidores": ["distribuidora de hortifruti", "ceasa", "atacadista"],
        "importadoras": ["importadora de frutas", "trading agricola"],
    },
    "pet": {
        "primarios": ["pet shop", "loja de animais", "clinica veterinaria"],
        "secundarios": ["supermercado", "atacarejo", "loja de racao"],
        "cruzados": ["app de delivery", "agropecuaria", "hipermercado"],
        "fabricantes": ["fabricante de racao", "industria pet"],
        "distribuidores": ["distribuidora pet", "atacadista", "representante"],
        "importadoras": ["importadora pet", "distribuidora importada"],
    },
    "construcao": {
        "primarios": ["loja de material de construcao", "ferragista", "home center"],
        "secundarios": ["deposito de material", "distribuidora de material"],
        "cruzados": ["supermercado", "atacarejo", "loja de departamentos", "marketplace online"],
        "fabricantes": ["fabricante de material de construcao", "industria de construcao civil"],
        "distribuidores": [
            "distribuidora de material de construcao", "atacadista", "representante",
        ],
        "importadoras": ["importadora de material de construcao", "distribuidora importada"],
    },
    "ferramenta": {
        "primarios": ["loja de ferramentas", "loja de material de construcao", "ferragista"],
        "secundarios": ["home center", "deposito de material"],
        "cruzados": ["marketplace online", "supermercado", "atacarejo"],
        "fabricantes": ["fabricante de ferramentas", "industria metalurgica"],
        "distribuidores": ["distribuidora de ferramentas", "atacadista", "representante"],
        "importadoras": ["importadora de ferramentas", "distribuidora importada"],
    },
    "limpeza": {
        "primarios": ["supermercado", "atacarejo", "loja de produtos de limpeza"],
        "secundarios": ["atacado", "distribuidora de produtos de limpeza", "mercadinho"],
        "cruzados": ["farmacia", "conveniencia", "posto de gasolina", "app de delivery"],
        "fabricantes": ["fabricante de produtos de limpeza", "industria quimica"],
        "distribuidores": ["distribuidora de produtos de limpeza", "atacadista", "representante"],
        "importadoras": ["importadora de produtos de limpeza", "distribuidora importada"],
    },
    "floricultura_jardinagem": {
        "primarios": [
            "floricultura", "viveiro de plantas", "jardim botanico", "loja de jardinagem",
        ],
        "secundarios": [
            "ceasa", "feira livre", "feira de flores",
            "mercado municipal", "produtor rural",
        ],
        "cruzados": [
            "leroy merlin", "home center", "supermercado", "loja de material de construcao",
        ],
        "fabricantes": ["produtor rural", "viveiro de mudas"],
        "distribuidores": ["distribuidora de plantas", "atacadista de flores"],
        "importadoras": ["importadora de bulbos e sementes"],
    },
    "carne": {
        "primarios": ["acougue", "casa de carnes", "peixaria"],
        "secundarios": ["supermercado", "distribuidora de carnes", "frigorifico"],
        "cruzados": ["atacarejo", "app de delivery", "mercearia", "feira livre"],
        "fabricantes": ["frigorifico", "industria frigorifica"],
        "distribuidores": ["distribuidora de carnes", "atacadista", "representante"],
        "importadoras": ["importadora de carnes", "trading de proteina animal"],
    },
    "bebida": {
        "primarios": [
            "supermercado", "atacarejo", "distribuidora de bebidas",
            "adega", "loja de bebidas",
        ],
        "secundarios": ["mercado", "mercadinho", "emporio"],
        "cruzados": ["padaria", "conveniencia", "posto de gasolina", "bar", "app de delivery"],
        "fabricantes": ["fabricante de bebidas", "cervejaria", "vinicola"],
        "distribuidores": ["distribuidora de bebidas", "atacadista", "representante"],
        "importadoras": ["importadora de bebidas", "distribuidora importada"],
    },
    "higiene": {
        "primarios": ["farmacia", "drogaria", "supermercado"],
        "secundarios": ["perfumaria", "loja de cosmeticos", "atacarejo"],
        "cruzados": ["mercadinho", "conveniencia", "app de delivery", "posto de gasolina"],
        "fabricantes": ["fabricante de cosmeticos", "industria de higiene pessoal"],
        "distribuidores": ["distribuidora de cosmeticos", "atacadista", "representante"],
        "importadoras": ["importadora de cosmeticos", "distribuidora importada"],
    },
    "padaria": {
        "primarios": ["padaria", "confeitaria", "panificadora"],
        "secundarios": ["supermercado", "mercado", "mercadinho"],
        "cruzados": ["conveniencia", "app de delivery", "posto de gasolina"],
        "fabricantes": ["panificadora industrial", "industria de panificacao"],
        "distribuidores": ["distribuidora de panificacao", "atacadista"],
        "importadoras": ["importadora de insumos de panificacao"],
    },
    "vestuario": {
        "primarios": ["loja de roupas", "butique", "loja de moda"],
        "secundarios": ["departamento store", "outlet", "brecho"],
        "cruzados": ["supermercado", "marketplace online", "loja de departamentos", "shopping"],
        "fabricantes": ["fabricante de roupas", "confeccao", "industria textil"],
        "distribuidores": ["distribuidora de vestuario", "atacadista", "representante"],
        "importadoras": ["importadora de vestuario", "distribuidora importada"],
    },
    "papelaria": {
        "primarios": ["papelaria", "loja de artigos escolares"],
        "secundarios": ["supermercado", "conveniencia"],
        "cruzados": ["hipermercado", "loja de departamentos", "marketplace online", "livraria"],
        "fabricantes": ["fabricante de artigos de papelaria", "industria grafica"],
        "distribuidores": ["distribuidora de papelaria", "atacadista", "representante"],
        "importadoras": ["importadora de artigos de papelaria"],
    },
    "farmacia": {
        "primarios": ["farmacia", "drogaria", "farmacia de manipulacao"],
        "secundarios": ["supermercado", "loja de produtos naturais"],
        "cruzados": ["conveniencia", "app de delivery", "mercadinho"],
        "fabricantes": ["fabricante farmaceutico", "industria farmaceutica"],
        "distribuidores": ["distribuidora farmaceutica", "atacadista", "representante"],
        "importadoras": ["importadora farmaceutica", "distribuidora importada"],
    },
    "brinquedo": {
        "primarios": ["loja de brinquedos", "loja infantil"],
        "secundarios": ["supermercado", "hipermercado", "loja de departamentos"],
        "cruzados": ["marketplace online", "loja de artigos escolares", "shopping"],
        "fabricantes": ["fabricante de brinquedos", "industria de brinquedos"],
        "distribuidores": ["distribuidora de brinquedos", "atacadista", "representante"],
        "importadoras": ["importadora de brinquedos", "distribuidora importada"],
    },
    "livro": {
        "primarios": ["livraria", "loja de livros"],
        "secundarios": ["supermercado", "papelaria", "conveniencia"],
        "cruzados": ["marketplace online", "loja de departamentos", "sebo"],
        "fabricantes": ["editora", "grafica"],
        "distribuidores": ["distribuidora de livros", "atacadista"],
        "importadoras": ["importadora de livros"],
    },
    "eletrodomesticos": {
        "primarios": ["loja de eletrodomesticos", "magazine", "loja de utilidades"],
        "secundarios": ["supermercado", "hipermercado", "loja de departamentos"],
        "cruzados": ["loja de material de construcao", "home center", "marketplace online"],
        "fabricantes": ["fabricante de eletrodomesticos", "industria de linha branca"],
        "distribuidores": ["distribuidora de eletrodomesticos", "atacadista", "representante"],
        "importadoras": ["importadora de eletrodomesticos", "distribuidora importada"],
    },
    "moveis": {
        "primarios": ["loja de moveis", "mobiliaria", "marcenaria"],
        "secundarios": ["loja de decoracao", "loja de utilidades domesticas"],
        "cruzados": [
            "loja de material de construcao", "home center",
            "marketplace online", "supermercado",
        ],
        "fabricantes": ["fabricante de moveis", "marcenaria industrial", "industria moveleira"],
        "distribuidores": ["distribuidora de moveis", "atacadista", "representante"],
        "importadoras": ["importadora de moveis", "distribuidora importada"],
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

# Sub-lista de `MARKETPLACES_BR` com busca DEDICADA de verdade no modo ativo
# (`EFRAIM_FONTE=apify`) - Mercado Livre (actor Apify + `sourcing.
# busca_mercadolivre`, paginado), Amazon e eBay (actors, so' quando escopo
# e' internacional). Achado (20/08, correcao do usuario "existem outros
# marketplaces que foram ignorados por que"): os outros 5 de
# `MARKETPLACES_BR` (Magazine Luiza, Americanas, Shopee, AliExpress,
# Carrefour, Atacadao) ERAM excluidos do Bloco C com a premissa de que "o
# Bloco A ja' cobre" - falso pro modo ativo: `gerar_queries_nacionais` (que
# buscaria os 8 via site:) so' e' consumido pelo adapter Bright Data MCP
# legado (`sourcing/adapters/brightdata_mcp.py`), que fica DESLIGADO quando
# `EFRAIM_FONTE=apify` (ver `sourcing/factory.py`) - ou seja, esses 5 nao
# eram buscados em lugar nenhum. So' os que TEM cobertura real entram na
# exclusao do Bloco C agora; os demais passam a ser alcancados pela busca
# ampla (camada 1 e 2), que e' melhor que exclusao sem cobertura nenhuma.
MARKETPLACES_COM_COBERTURA_DEDICADA = [
    "mercadolivre.com.br", "amazon.com.br", "ebay.com",
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


# Bloco C, CAMADA 2 (correcao do usuario, 20/08): nem todo grupo de
# `PONTOS_VENDA` serve pra descoberta de FORNECEDOR - "supermercado"
# (secundarios de eletronico) e' onde um CONSUMIDOR cruza pra comprar
# eletronico basico, nao onde um distribuidor/importador de COMPONENTE
# eletronico (conector, resistor, LED) esta'. Confirmado em teste real
# (20/08): a query "supermercado Sul Brasil" trouxe redes de supermercado
# ("Sul Brasil Supermercado", "Zona Sul") em vez de fornecedor de
# componente. Regra do usuario: "pra cada item existe uma pre
# classificacao que indicara' a query" - NAO e' um conjunto fixo universal
# (arroz 5kg deve continuar usando supermercado/atacarejo/minimercado,
# que sao legitimos pra alimento) - so' as categorias onde isso foi
# CONFIRMADO como problema entram aqui; as demais usam os 6 grupos
# (default), sem curadoria preventiva sem evidencia.
GRUPOS_CAMADA2_POR_CATEGORIA: dict[str, list[str]] = {
    "eletronico": ["fabricantes", "distribuidores", "importadoras"],
}


def pontos_venda_amostra(categoria: str, por_grupo: int = 1) -> list[str]:
    """Amostra ATE `por_grupo` de CADA um dos 6 grupos (primarios,
    secundarios, cruzados, fabricantes, distribuidores, importadoras) - nao
    os N primeiros da lista achatada. `pontos_venda_de(...)[:N]` sempre
    pegava so' o grupo "primarios" (loja/magazine), porque ele vem primeiro
    no dict e ja' tem >= N itens sozinho - a busca nunca alcancava
    distribuidor/importador/atacadista/representante (achado em revisao,
    19/08). Isso e' o que faz a Etapa 1c (sites proprios / Bloco C) cobrir
    TODOS os tipos de fornecedor, nao so' varejo."""
    grupos = PONTOS_VENDA.get(categoria, PONTOS_VENDA[FALLBACK_GERAL])
    return [pv for lista in grupos.values() for pv in lista[:por_grupo]]


def pontos_venda_amostra_fornecedor(categoria: str, por_grupo: int = 1) -> list[str]:
    """Como `pontos_venda_amostra`, mas so' dos grupos validos pra
    DESCOBERTA DE FORNECEDOR (Bloco C, camada 2) dessa categoria - ver
    `GRUPOS_CAMADA2_POR_CATEGORIA`. Sem entrada especifica, usa os 6 grupos
    (mesmo comportamento de `pontos_venda_amostra`) - a curadoria so' entra
    quando um problema real foi confirmado, categoria por categoria."""
    grupos_todos = PONTOS_VENDA.get(categoria, PONTOS_VENDA[FALLBACK_GERAL])
    chaves_validas = GRUPOS_CAMADA2_POR_CATEGORIA.get(categoria, list(grupos_todos.keys()))
    return [pv for chave in chaves_validas for pv in grupos_todos.get(chave, [])[:por_grupo]]


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


def gerar_queries_produto(item: ItemProduto) -> list[str]:
    """Bloco C, CAMADA 1 (correcao do usuario, 20/08): busca so' pelo
    produto, sem qualificar tipo de loja/fornecedor - "a busca se inicia
    apenas pelo produto... todas as paginas que retornarem sao true"; a
    filtragem (preco, tipo de estabelecimento, contato, local) acontece
    DEPOIS, sobre o que voltou, nao restringindo a query em si. So' os
    marketplaces com busca DEDICADA real ficam excluidos aqui (ver
    `MARKETPLACES_COM_COBERTURA_DEDICADA`) - os demais nao tem cobertura em
    lugar nenhum, entao a busca ampla e' o unico jeito de alcanca-los."""
    exc = " ".join(f"-site:{s}" for s in MARKETPLACES_COM_COBERTURA_DEDICADA)
    return [f"{item.nome} comprar {exc}"]


def gerar_queries_fornecedores(categoria: str) -> list[str]:
    """Bloco C, CAMADA 2 (correcao do usuario, 20/08): busca por tipo de
    FORNECEDOR, SEM o nome do produto - descobre o NEGOCIO por categoria; o
    casamento com o produto da busca principal acontece so' depois,
    visitando cada pagina encontrada ("entrar em cada pagina e procurar o
    item da busca principal" - ver `sourcing/adapters/apify_source.py::
    ApifyBroadSource` e `domain/extracao_pagina.py`). So' os grupos de
    `PONTOS_VENDA` validos pra ESSA categoria entram aqui (ver
    `pontos_venda_amostra_fornecedor`/`GRUPOS_CAMADA2_POR_CATEGORIA`) -
    "supermercado" faz sentido pra achar arroz, nao faz sentido pra achar
    fornecedor de componente eletronico (achado em teste real, 20/08: a
    query "supermercado Sul Brasil" trouxe rede de supermercado, nao
    fornecedor de componente). Cruzado com as 5 regioes do Brasil - a busca
    NAO se restringe a uma regiao por padrao; restringir a uma so' regiao
    e' pendencia (so' acontece por pedido explicito do usuario, ver
    ARQUITETURA.md)."""
    pvs = pontos_venda_amostra_fornecedor(categoria, por_grupo=1)
    exc = " ".join(f"-site:{s}" for s in MARKETPLACES_COM_COBERTURA_DEDICADA)
    queries: list[str] = []
    for regiao in REGIOES_BR:
        for pv in pvs:
            queries.append(f"{pv} {regiao} Brasil {exc}")
    return queries


def gerar_queries_locais(item: ItemProduto, loc: Localizacao, categoria: str) -> list[str]:
    onde = loc.cidade or loc.cep or "Brasil"
    return [f"{pv} {onde} raio {loc.raio_km}km" for pv in pontos_venda_de(categoria)[:4]]


# EUA: mouser/digikey/newark ja' existiam; jameco/arrow/sparkfun/adafruit/
# sweetwater/bhphotovideo sao "sites proprios" (exportador, nao marketplace)
# adicionados em 19/08 a pedido do usuario; ebay/amazon.com continuam
# (marketplace, mas ainda vale o site: aqui - e' Google, nao o actor Apify
# que ja' cobre esses dois separadamente em Bloco D).
SITES_INTERNACIONAIS_EUA = [
    "mouser.com", "digikey.com", "newark.com", "jameco.com", "arrow.com",
    "sparkfun.com", "adafruit.com", "sweetwater.com", "bhphotovideo.com",
    "ebay.com", "amazon.com",
]

# China: sites proprios de exportador/distribuidor (nao marketplace generico
# tipo alibaba.com/aliexpress.com/made-in-china.com - trocados em 19/08 a
# pedido do usuario pelos sites proprios reais de componente eletronico).
SITES_INTERNACIONAIS_CHINA = [
    "1688.com", "taobao.com", "lcsc.com", "sunsky-online.com",
    "jlcpcb.com", "winsource.com",
]


def gerar_queries_internacionais(item: ItemProduto, termo_en: str, termo_zh: str) -> list[str]:
    """`termo_en` busca nos sites dos EUA, `termo_zh` (chines) busca nos
    sites da China - sao termos DIFERENTES, nao o mesmo valor duplicado (ver
    `domain.roteamento.EscopoEfetivo` e `domain.nomenclatura_chinesa`)."""
    q = [f"{termo_en} buy price site:{s}" for s in SITES_INTERNACIONAIS_EUA]
    q += [f"{termo_zh} site:{s}" for s in SITES_INTERNACIONAIS_CHINA]
    return q


def montar_consulta_produto(
    item: ItemProduto,
    escopo: Escopo,
    *,
    termo_internacional: str | None = None,
    termo_zh: str | None = None,
) -> ConsultaProduto:
    """`termo_internacional` (EN) e `termo_zh` sobrescrevem os termos usados
    nas queries de Bloco D (EUA e China respectivamente) - vem de
    `domain.roteamento.montar_escopo_efetivo`, que adapta nomenclatura
    PT->internacional quando necessario (ver ali o porque). Sem
    `termo_zh`, cai no MESMO termo em ingles (melhor que nada, mas nao busca
    em chines de verdade - ver `domain.nomenclatura_chinesa`)."""
    categoria = classificar(item.nome)
    queries = gerar_queries_nacionais(item)
    if escopo is Escopo.INTERNACIONAL:
        termo_en = termo_internacional or item.nome
        queries += gerar_queries_internacionais(item, termo_en, termo_zh or termo_en)
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
