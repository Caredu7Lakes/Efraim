"""Extracao de preco/contato/produto a partir de HTML de pagina de
fornecedor (ETAPA 1 - extensao, 20/08/2026).

Ponto UNICO dessas regexes - antes viviam duplicadas dentro de
`brightdata_unlocker.py` (Bloco B) e agora tambem sao usadas por
`apify_source.py` (Bloco C, camada 2 - "pente fino" apos visitar a pagina
de um distribuidor/importador/fabricante descoberto por categoria). Ver
`domain.regioes`/correcao do usuario (20/08) sobre o modelo de 2 camadas:
camada 1 busca so' pelo produto; camada 2 descobre o FORNECEDOR por
categoria e so' depois confirma, visitando a pagina dele, se o item da
busca principal esta' la'.
"""
from __future__ import annotations

import re

from app.domain.classificacao import normalizar

_TELEFONE_RE = re.compile(r"\(?\d{2}\)?\s?\d{4,5}-?\d{4}")
_WHATSAPP_RE = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=)(\d+)")
_PRECO_RE = re.compile(r"R\$\s?[\d.]+,\d{2}")

# preco anunciado pode ser por LOTE ("kit com 50", "pacote de 100 pecas"),
# nao por unidade - achado real (20/08): o carrossel de Shopping do Google
# mostra "R$ 0,19" pro LED, mas isso costuma ser preco de kit/lote, nao de
# 1 peca sozinha - pedido do usuario foi "checar se esse preco e' por
# quantas unidades" antes de aceitar o valor como comparavel.
_QUANTIDADE_RE = re.compile(
    r"\b(kit|pacote|combo|caixa|lote)\s+(?:com|de)\s+(\d+)\s*"
    r"(unidades?|pe[cç]as?|un\.?|pcs?)\b|\b(\d+)\s*(unidades?|pe[cç]as?|pcs?)\b",
    re.IGNORECASE,
)

# versao NUMERICA, mais permissiva - usada pra CONVERTER o preco (nao so'
# anotar) antes de comparar ofertas (correcao do usuario, 20/08: "so' pode
# descartar apos fazer a conversao" - filtrar_top7 estava comparando preco
# bruto do anuncio, deixando um "kit de 6" ganhar de um preco unitario real
# so' por ter numero menor). Cobre titulos reais de marketplace que a versao
# de anotacao acima nao cobre - "Kit 6 Conectores..." (sem "com"/"de" entre
# "kit" e o numero), "Kit 10x ..." - confirmado contra titulos reais do
# Mercado Livre/Shopee capturados ao vivo (20/08). So' entra no branch de
# numero solto quando ha' palavra de unidade explicita logo depois (evita
# pegar "6 Terminais"/"10 Jacks" como se fosse quantidade de lote - mais
# seguro presumir preco unitario quando o sinal e' ambiguo do que inflar um
# "kit" falso e distorcer a comparacao pra baixo).
_QUANTIDADE_NUMERICA_RE = re.compile(
    r"\bkit\s*(?:com|de)?\s*(\d+)\s*x?\b"
    r"|\b(\d+)\s*(?:unidades?|pe[cç]as?|un\.?|pcs?)\b",
    re.IGNORECASE,
)

# sinais textuais de que um fornecedor de fora do Brasil de fato exporta/
# atende o Brasil - substring simples, case-insensitive via `normalizar`.
_SINAIS_EXPORTA_BRASIL = (
    "brasil", "brazil", "shipping to brazil", "ships to brazil",
    "international shipping", "worldwide shipping", "envio internacional",
    "worldwide delivery", "we ship worldwide", "export to brazil",
)


def extrair_preco(html: str) -> str | None:
    m = _PRECO_RE.search(html)
    return m.group(0) if m else None


def extrair_whatsapp(html: str) -> str | None:
    m = _WHATSAPP_RE.search(html)
    return m.group(1) if m else None


def extrair_telefone(html: str) -> str | None:
    m = _TELEFONE_RE.search(html)
    return m.group(0) if m else None


def extrair_quantidade_unidades(html: str) -> str | None:
    """Devolve a frase que indica quantidade/lote do preco ("kit com 50
    unidades", "100 pecas") quando encontrada perto do texto da pagina -
    None quando nao ha' sinal de lote (presume-se preco unitario nesse
    caso, mas SEM confirmar - quem chama decide como tratar a ausencia).
    Pedido do usuario (20/08): nao aceitar preco de carrossel/anuncio como
    "por unidade" sem checar - o valor exibido costuma ser de kit/lote."""
    texto = re.sub(r"<[^>]+>", " ", html)
    m = _QUANTIDADE_RE.search(texto)
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else None


def extrair_quantidade_numerica(texto: str) -> int:
    """Devolve QUANTAS unidades o preco anunciado cobre de verdade - 1
    (preco unitario) quando nao ha' sinal de lote/kit. Usado pra CONVERTER
    `Oferta.preco_centavos` pro custo por unidade real antes de qualquer
    comparacao/descarte (`Oferta.unidades_no_lote`, `sourcing.filtro.
    filtrar_top7`) - correcao do usuario (20/08): "so' pode descartar apos
    fazer a conversao" - sem isso um "kit de 6" barato vencia um preco
    unitario real so' por ter numero absoluto menor."""
    texto_sem_tag = re.sub(r"<[^>]+>", " ", texto)
    m = _QUANTIDADE_NUMERICA_RE.search(texto_sem_tag)
    if not m:
        return 1
    numero = m.group(1) or m.group(2)
    return int(numero) if numero else 1


def exporta_para_brasil(html: str) -> bool:
    """Correcao do usuario (20/08): um fornecedor internacional (Bloco B
    encontrou lojas no Peru, EAU etc. mesmo buscando com ancora no Brasil -
    a API de discovery da Bright Data nao restringe 100% por pais) NAO e'
    "lixo" so' por nao ser brasileiro - "se o preco do Peru for menor e o
    site conter informacao que exporta para o Brasil entao nao e' lixo, e'
    o tipo de resultado que esperamos, isso e' minerar". Esta funcao e' o
    criterio: so' considera valido pra comparacao de preco quando a propria
    pagina sinaliza que atende/envia pro Brasil - sem esse sinal, o
    resultado fica de fora da comparacao (nao classificado como lixo, so'
    nao confirmado)."""
    texto = normalizar(html)
    return any(normalizar(sinal) in texto for sinal in _SINAIS_EXPORTA_BRASIL)


def produto_aparece(html: str, produto: str) -> bool:
    """Exige que quase todas as palavras significativas (len>=3) do nome do
    produto apareçam no texto da pagina - tolera 1 faltando (variacao de
    descricao), mas evita que qualquer "R$" solto no site (frete, produto
    diferente, rodape) vire falso positivo de preco. E' o "pente fino" da
    camada 2: a descoberta foi por categoria de fornecedor, so' a visita
    confirma se ELE tem o item da busca principal."""
    texto = normalizar(re.sub(r"<[^>]+>", " ", html))
    palavras = [p for p in normalizar(produto).split() if len(p) >= 3]
    if not palavras:
        return True
    encontradas = sum(1 for p in palavras if p in texto)
    return encontradas >= max(1, len(palavras) - 1)
