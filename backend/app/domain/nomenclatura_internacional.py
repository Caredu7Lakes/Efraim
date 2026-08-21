"""Adaptacao de nomenclatura tecnica PT->internacional (ETAPA 1 - extensao).

Glossario termo-a-termo, deterministico - NAO e' tradutor generico, e'
mapeamento de vocabulario tecnico conhecido (eletronica/conectores por
enquanto). Cresce por extensao do dicionario.

Por que isso existe: um nome de produto em portugues pode descrever um item
vendido internacionalmente, mas anunciado la' fora com nomenclatura tecnica
DIFERENTE (ex.: "conector jack P10 estereo" -> "3.5mm stereo jack
connector"). Sem essa adaptacao, a busca internacional (Mouser/DigiKey/
eBay/Alibaba) com o termo em portugues nao encontra nada - o produto existe
la' fora, so' que ninguem anuncia com esse termo.
"""
from __future__ import annotations

from app.domain.classificacao import normalizar

# frase completa (mais precisa que palavra-a-palavra) -> termo internacional
_FRASES_PT_EN: dict[str, str] = {
    "conector jack p10 estereo": "3.5mm stereo jack connector",
    "conector jack p10 stereo": "3.5mm stereo jack connector",
    "jack p10 estereo": "3.5mm stereo jack",
    "jack p10 stereo": "3.5mm stereo jack",
}

# fallback palavra-a-palavra quando a frase completa nao esta' mapeada -
# termos sem entrada aqui (siglas, codigos tecnicos) ficam como estao.
_PALAVRAS_PT_EN: dict[str, str] = {
    "conector": "connector", "cabo": "cable", "fio": "wire",
    "resistor": "resistor", "capacitor": "capacitor", "bateria": "battery",
    "fonte": "power supply", "chave": "switch", "furadeira": "drill",
    "parafusadeira": "screwdriver", "estereo": "stereo", "profissional": "professional",
    "preto": "black", "branco": "white", "vermelho": "red", "azul": "blue",
    "verde": "green", "grande": "large", "pequeno": "small",
}


def nomenclatura_internacional(nome: str) -> str:
    """Termo pronto pra busca internacional a partir de um nome em
    portugues. Tenta a frase tecnica conhecida primeiro, como SUBSTRING (nao
    igualdade exata) - nome real de produto tem descritores extras
    ("profissional", "importado"...) que nao fazem parte da especificacao
    tecnica buscavel la' fora e nao devem impedir o match. Sem nenhuma frase
    conhecida, traduz palavra a palavra pelo glossario, preservando termos
    tecnicos sem mapeamento (ex.: "p10") como vieram."""
    n = normalizar(nome)
    for frase, termo in _FRASES_PT_EN.items():
        if frase in n:
            return termo
    palavras = [_PALAVRAS_PT_EN.get(p, p) for p in n.split()]
    return " ".join(palavras)
