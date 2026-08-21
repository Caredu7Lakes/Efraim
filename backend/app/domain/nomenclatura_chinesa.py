"""Adaptacao de nomenclatura tecnica -> chines (ETAPA 1 - extensao Bloco D).

Mesmo padrao de `nomenclatura_internacional.py`: glossario termo-a-termo
deterministico, NAO tradutor generico. A diferenca e' a ENTRADA: aqui o
glossario e' chaveado em INGLES, nao portugues - o pipeline sempre traduz
PT/EN -> termo_en (canonico, ja' resolvido por `nomenclatura_internacional`
+ `roteamento.montar_escopo_efetivo`) e so' DEPOIS deriva o termo em chines
a partir desse termo_en unico. Isso evita manter dois glossarios paralelos
(um pra PT->ZH, outro pra EN->ZH) com o mesmo vocabulario tecnico duplicado
em dois lugares - ha' um unico ponto de verdade (termo_en) do qual tanto as
queries dos EUA quanto as da China derivam.
"""
from __future__ import annotations

from app.domain.classificacao import normalizar

# frase completa (mais precisa que palavra-a-palavra) -> termo em chines
_FRASES_EN_ZH: dict[str, str] = {
    "3.5mm stereo jack connector": "3.5mm立体声插孔连接器",
    "3.5mm stereo jack": "3.5mm立体声插孔",
}

# fallback palavra-a-palavra quando a frase completa nao esta' mapeada -
# termos sem entrada aqui (siglas, codigos tecnicos, nomes de marca) ficam
# como estao.
_PALAVRAS_EN_ZH: dict[str, str] = {
    "connector": "连接器", "cable": "电缆", "wire": "电线",
    "resistor": "电阻器", "capacitor": "电容器", "battery": "电池",
    "power": "电源", "supply": "电源", "switch": "开关", "drill": "电钻",
    "screwdriver": "电动螺丝刀", "stereo": "立体声", "jack": "插孔",
    "plug": "插头", "professional": "专业", "black": "黑色", "white": "白色",
    "red": "红色", "blue": "蓝色", "green": "绿色", "large": "大",
    "small": "小",
}


def nomenclatura_chinesa(termo_en: str) -> str:
    """Termo pronto pra busca em sites chineses (1688/Taobao/LCSC/...) a
    partir do termo em ingles JA' RESOLVIDO (nao do nome original em
    portugues - ver docstring do modulo). Tenta a frase tecnica conhecida
    primeiro, como SUBSTRING; sem match, traduz palavra a palavra pelo
    glossario, preservando termos sem mapeamento (numeros, siglas, marca)
    como vieram."""
    n = normalizar(termo_en)
    for frase, termo in _FRASES_EN_ZH.items():
        if normalizar(frase) in n:
            return termo
    palavras = [_PALAVRAS_EN_ZH.get(p, p) for p in n.split()]
    return " ".join(palavras)
