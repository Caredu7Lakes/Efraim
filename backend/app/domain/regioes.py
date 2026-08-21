"""Clusters regionais - classificacao de RESULTADO, nao parametro de busca
(ETAPA 1 - extensao, 20/08/2026, redesenhado no mesmo dia apos correcao do
usuario).

Correcao do usuario: "as regioes devem ser apresentadas apos a coleta dos
dados, nao tem sentido separar pesquisa por regiao do brasil. a pesquisa
deve ser ampla e profunda dentro do brasil, recebido o retorno o agente
deve ser capaz de identificar e separar cada dado por regiao - isso e'
diferente de pesquisa por regiao." Ou seja: a lista de cidades abaixo
(`TODAS_CIDADES`) e' so' um conjunto de ancoras geograficas pra alimentar a
busca ampla no Google Maps (Maps exige algum vies de localizacao pra
devolver algo util) - o "cluster" de cada RESULTADO nao vem de qual cidade
gerou a query, vem do endereco real que a loja devolveu (`cluster_da_uf`,
usado em `brightdata_unlocker.py` depois de extrair o UF do endereco com
`extrair_uf_e_cidade`). Uma busca ancorada em Curitiba pode legitimamente
devolver uma loja em Santa Catarina - o endereco decide o cluster, nao a
cidade da query.

Lista de cidades e' a que o usuario especificou (20/08) - "Norte +
Nordeste" so' veio com 6 das 12 capitais citadas explicitamente ("Salvador,
Recife, Fortaleza, Belem, Manaus, Natal, etc."); as 6 restantes (Joao
Pessoa/PB, Maceio/AL, Aracaju/SE, Sao Luis/MA, Teresina/PI, Porto Velho/RO)
foram adicionadas aqui pra cobrir os 12 estados que o usuario listou - nao
e' escolha silenciosa, e' a extrapolacao razoavel do "etc." dado o resto do
padrao (uma capital por estado listado).
"""
from __future__ import annotations

import re

CLUSTERS_REGIONAIS: dict[str, dict[str, list[str]]] = {
    "Sul": {
        "estados": ["PR", "SC", "RS"],
        "cidades": [
            "Curitiba", "Porto Alegre", "Blumenau", "Joinville",
            "Florianopolis", "Londrina", "Caxias do Sul", "Pelotas",
            "Maringa", "Chapeco",
        ],
    },
    "Sudeste e Centro-Oeste": {
        "estados": ["SP", "MG", "RJ", "ES", "GO", "MT", "MS", "DF"],
        "cidades": [
            # Santa Ifigenia e' o bairro/polo de componentes eletronicos de
            # SP - escolha deliberada do usuario, nao erro (mais preciso
            # pra Bloco B de eletronico que "Sao Paulo" generico).
            "Santa Ifigenia, Sao Paulo", "Campinas", "Belo Horizonte",
            "Uberlandia", "Rio de Janeiro", "Vitoria", "Brasilia",
            "Goiania", "Cuiaba",
        ],
    },
    "Norte e Nordeste": {
        "estados": ["BA", "PE", "CE", "PA", "AM", "RN", "PB", "AL", "SE", "MA", "PI", "RO"],
        "cidades": [
            "Salvador", "Recife", "Fortaleza", "Belem", "Manaus", "Natal",
            "Joao Pessoa", "Maceio", "Aracaju", "Sao Luis", "Teresina", "Porto Velho",
        ],
    },
}

# lista PLANA - a busca nao trata "cluster" como parametro, so' usa cidades
# como ancora geografica pra alimentar o Google Maps (ver docstring acima).
TODAS_CIDADES: list[str] = [
    cidade for dados in CLUSTERS_REGIONAIS.values() for cidade in dados["cidades"]
]

# UF -> cluster, pra CLASSIFICAR o resultado depois de coletado (nao pra
# decidir onde buscar).
_UF_PARA_CLUSTER: dict[str, str] = {
    uf: cluster for cluster, dados in CLUSTERS_REGIONAIS.items() for uf in dados["estados"]
}


def cluster_da_uf(uf: str | None) -> str | None:
    if not uf:
        return None
    return _UF_PARA_CLUSTER.get(uf.upper())


# endereco BR tipico: "Av. Sete de Setembro, 3561 - Centro, Curitiba - PR,
# 80250-250" - cidade e UF ficam entre o penultimo " - " e a virgula do CEP.
_ENDERECO_RE = re.compile(r",\s*([^,-]+?)\s*-\s*([A-Z]{2})\b")


def extrair_uf_e_cidade(endereco: str | None) -> tuple[str | None, str | None]:
    """Extrai (uf, cidade) de um endereco brasileiro no formato que o Maps
    devolve. Retorna (None, None) quando o endereco nao bate o padrao
    esperado (loja sem endereco formatado, resultado de outro pais etc.) -
    o chamador decide o fallback."""
    if not endereco:
        return None, None
    m = _ENDERECO_RE.search(endereco)
    if not m:
        return None, None
    cidade, uf = m.group(1).strip(), m.group(2)
    return uf, cidade
