"""Extracao da categoria REAL que o Mercado Livre atribui a um produto, via
o breadcrumb da pagina de busca dele (ETAPA 1 - extensao, 20/08/2026).

Confirmado ao vivo (Web Unlocker, 20/08): a pagina de resultados de busca
do ML (`lista.mercadolivre.com.br/<termo>`) carrega o breadcrumb de
categoria com marcacao schema.org/BreadcrumbList real (`itemprop="name"`
por nivel). Pra "led 3mm round long lead diffused red", devolveu:
['Eletrônicos, Áudio e Vídeo', 'Componentes Eletrônicos', 'Semicondutores',
'Chips Leds'] - uma classificacao MUITO mais fina do que a taxonomia
publica do Google tem pra esse item (Google so' tem "LED Signs"/"LED Light
Bulbs" - produto acabado, nao componente bruto solto - ver
`taxonomia_google.py`, item 3 da docstring). O Mercado Livre e' um sinal de
classificacao REAL do mercado brasileiro, curado por eles mesmos - onde a
taxonomia do Google (generica, internacional) nao cobre bem um item tecnico
de nicho, o breadcrumb do ML frequentemente cobre.

Este modulo so' PARSEIA o HTML (sem I/O) - quem busca a pagina (Web
Unlocker, `sourcing/adapters/brightdata_unlocker.py::_chamar_unlocker`, ja'
validado nesta sessao pra contornar o 403 que o ML devolve em fetch
direto) fica de fora daqui de proposito, mesma separacao que
`extracao_pagina.py` ja' segue.
"""
from __future__ import annotations

import re

_BREADCRUMB_RE = re.compile(r'itemprop="name">([^<]+)</span>')


def extrair_categoria_ml(html: str) -> list[str]:
    """Devolve a cadeia de categorias (do mais amplo ao mais especifico)
    que o Mercado Livre atribuiu a pagina de busca - lista vazia se a
    pagina nao tiver o breadcrumb esperado (layout mudou, pagina de erro,
    termo sem resultado, etc - nao assume que o breadcrumb sempre existe)."""
    return _BREADCRUMB_RE.findall(html)


def montar_url_busca_ml(termo: str) -> str:
    """Monta a URL de busca do ML a partir de um termo - mesmo padrao de
    slug (espacos viram traco) que o proprio site usa nos links de busca."""
    slug = re.sub(r"\s+", "-", termo.strip().lower())
    return f"https://lista.mercadolivre.com.br/{slug}"
