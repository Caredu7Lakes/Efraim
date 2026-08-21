"""Deteccao de idioma do nome do produto: PT vs EN (ETAPA 1 - extensao).

Heuristica lexica por contagem de palavras-funcao/adjetivos comuns de cada
idioma no nome normalizado (sem acento, minusculo) - sem chamada externa,
sem LLM, deterministica e testavel. Termos tecnicos/sigla (LED, USB, P10...)
nao aparecem em nenhuma lista: nao decidem sozinhos o idioma.

Por que isso importa pro pipeline: um nome de produto em ingles e' sinal de
peca/componente tipicamente importado (eletronica, ferragem tecnica) - vale
a pena rodar tambem os blocos internacionais (EUA/China) mesmo quando o
escopo pedido pela busca e' "nacional". Ver `montar_escopo_efetivo` em
`jobs/tasks.py`.
"""
from __future__ import annotations

from app.domain.classificacao import normalizar

_PALAVRAS_PT = {
    "de", "da", "do", "das", "dos", "com", "para", "sem", "e", "ou",
    "profissional", "estereo", "stereo", "conector", "cabo", "fio",
    "preto", "branco", "vermelho", "azul", "verde", "grande", "pequeno",
    "novo", "usado", "furadeira", "parafusadeira", "chave", "torneira",
}

_PALAVRAS_EN = {
    "the", "with", "for", "without", "and", "or", "round", "long",
    "short", "lead", "diffused", "red", "blue", "green", "black", "white",
    "large", "small", "new", "used", "professional", "connector", "cable",
    "wire", "wired", "wireless", "diffuse", "clear",
}


def detectar_idioma(nome: str) -> str:
    """Retorna 'en' ou 'pt'. Empate (incl. nenhuma palavra reconhecida em
    nenhuma lista) desempata para 'pt' - mercado padrao e' nacional, so'
    desvia pra ingles com sinal lexico claro."""
    tokens = set(normalizar(nome).split())
    pt_hits = len(tokens & _PALAVRAS_PT)
    en_hits = len(tokens & _PALAVRAS_EN)
    return "en" if en_hits > pt_hits else "pt"
