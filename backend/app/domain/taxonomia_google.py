"""Taxonomia oficial de produtos do Google (pt-BR + en-US) - ETAPA 1,
extensao 20/08/2026.

Fonte: https://www.google.com/basepages/producttype/taxonomy-with-ids.<pt-BR
|en-US>.txt (versao 2021-09-21, baixada em 20/08/2026, salva em `data/
google_taxonomy_pt_br.txt` e `data/google_taxonomy_en_us.txt`). 5594
categorias reais por idioma, 21 raizes, ate' 7 niveis de profundidade - o
mesmo padrao que o Google Shopping (e boa parte do mercado de e-commerce)
usa pra classificar produto. Decisao do usuario (20/08): "usar o google
product taxonomy - o efraim precisa aprender a explorar ele."

"Explorar" aqui significa: dado um nome de produto, percorrer a arvore
inteira (nao um dict fixo de ~20 entradas como `classificacao.py` tinha
antes) e achar o(s) caminho(s) de categoria mais relevante(s) via busca
lexica - deterministico (sem LLM/embedding), mesmo padrao do resto do
dominio.

Dois problemas reais achados testando com produtos de verdade desta sessao
(20/08), ambos corrigidos:

1) Substring solta gera falso positivo: `"cimento" in "aquecimento"` e
   `"red" in "rede"` batiam porque a palavra da busca aparecia DENTRO de
   uma palavra maior e nao relacionada. Corrigido comparando PALAVRA
   INTEIRA (tokens), com uma variacao simples de plural (adiciona/remove
   "s" final) pra nao perder "cimento" x "Cimentos" - sem isso, exigir
   igualdade exata tambem quebrava (nome do produto quase sempre vem no
   singular, a taxonomia usa plural).

2) Nome de produto em ingles (ex.: "LED... red") buscado contra a
   taxonomia em PORTUGUES colide por coincidencia lexica ("red" e' cor em
   ingles, mas e' substring/quase-palavra de termos portugueses sem
   relacao). Corrigido escolhendo o ARQUIVO certo (pt-BR ou en-US) pelo
   idioma detectado do termo (`domain.idioma.detectar_idioma`), em vez de
   sempre buscar so' na taxonomia em portugues.

Isso substitui/enriquece `classificar()` (categoria ampla, usada hoje pra
escolher `PONTOS_VENDA`) com uma classificacao MUITO mais fina - mas
`PONTOS_VENDA` continua curado nos ~20 grupos amplos (quem vende/fabrica/
distribui e' um eixo DIFERENTE de "o que e' o produto", a taxonomia do
Google nao carrega esse eixo).

3o problema real, sem correcao simples de regex/plural: quando so' UMA
palavra da busca tem cobertura na taxonomia (ex.: "conector jack p10
stereo" - nem "jack" nem "stereo"/"estereo" existem na taxonomia em
portugues, so' "conector" bate), varias categorias de dominios totalmente
diferentes empatam na pontuacao ("Conectores de correntes" de ferragem,
"Conectores para encanamento", "Conectores de componentes eletronicos") -
nenhum desempate lexico razoavel (densidade, profundidade) resolve isso de
forma confiavel, porque lexicamente elas SAO igualmente validas. A saida
NAO e' inventar mais heuristica lexica - e' usar o `classificar()` JA'
EXISTENTE (keyword-based, ~20 categorias, ja' testado e correto pra este
caso: "conector"/"jack" ja' classificam como "eletronico") como sinal de
QUAL RAIZ da taxonomia do Google priorizar (`categoria_dominio` em
`explorar`/`RAIZ_GOOGLE_POR_CATEGORIA`) - os dois sistemas se completam:
`classificar()` acerta o DOMINIO amplo com poucas palavras-chave
confiaveis, a taxonomia do Google da' a FOLHA fina dentro desse dominio.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.domain.idioma import detectar_idioma

_DIR_DADOS = Path(__file__).parent / "data"
_ARQUIVOS_POR_IDIOMA = {
    "pt": _DIR_DADOS / "google_taxonomy_pt_br.txt",
    "en": _DIR_DADOS / "google_taxonomy_en_us.txt",
}

# categoria de `classificacao.classificar()` -> raiz da taxonomia do
# Google, por idioma (a raiz certa muda de nome conforme o arquivo). Usado
# como boost em `explorar` (ver item 3 da docstring do modulo) - nao
# substitui a busca lexica, so' desempata categorias igualmente validas em
# dominios diferentes a favor do dominio que `classificar()` ja' acertou.
RAIZ_GOOGLE_POR_CATEGORIA: dict[str, dict[str, str]] = {
    "eletronico": {"pt": "Eletrônicos", "en": "Electronics"},
    "informatica": {"pt": "Eletrônicos", "en": "Electronics"},
    "alimento": {"pt": "Alimentos, bebidas e tabaco", "en": "Food, Beverages & Tobacco"},
    "hortifruti": {"pt": "Alimentos, bebidas e tabaco", "en": "Food, Beverages & Tobacco"},
    "carne": {"pt": "Alimentos, bebidas e tabaco", "en": "Food, Beverages & Tobacco"},
    "bebida": {"pt": "Alimentos, bebidas e tabaco", "en": "Food, Beverages & Tobacco"},
    "padaria": {"pt": "Alimentos, bebidas e tabaco", "en": "Food, Beverages & Tobacco"},
    "pet": {
        "pt": "Animais e suprimentos para animais de estimação",
        "en": "Animals & Pet Supplies",
    },
    "construcao": {"pt": "Ferragens", "en": "Hardware"},
    "ferramenta": {"pt": "Ferragens", "en": "Hardware"},
    "limpeza": {"pt": "Casa e jardim", "en": "Home & Garden"},
    "floricultura_jardinagem": {"pt": "Casa e jardim", "en": "Home & Garden"},
    "eletrodomesticos": {"pt": "Casa e jardim", "en": "Home & Garden"},
    "higiene": {"pt": "Saúde e beleza", "en": "Health & Beauty"},
    "farmacia": {"pt": "Saúde e beleza", "en": "Health & Beauty"},
    "vestuario": {"pt": "Vestuário e acessórios", "en": "Apparel & Accessories"},
    "papelaria": {"pt": "Materiais de escritório", "en": "Office Supplies"},
    "brinquedo": {"pt": "Brinquedos e jogos", "en": "Toys & Games"},
    "livro": {"pt": "Mídia", "en": "Media"},
    "moveis": {"pt": "Móveis", "en": "Furniture"},
}

_BOOST_RAIZ_CORRETA = 0.5


@dataclass(frozen=True)
class CategoriaGoogle:
    id: int
    caminho: str  # "Eletrônicos > Componentes > Conectores de componentes eletrônicos"

    @property
    def raiz(self) -> str:
        return self.caminho.split(">")[0].strip()

    @property
    def folha(self) -> str:
        return self.caminho.split(">")[-1].strip()

    @property
    def profundidade(self) -> int:
        return self.caminho.count(">") + 1


def _normalizar_termo(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto)
    t = t.encode("ascii", "ignore").decode("ascii").lower()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _com_variacao_plural(palavras: set[str]) -> set[str]:
    """Adiciona a forma com/sem plural de cada palavra - o nome do produto
    normalmente vem no singular ("cimento", "conector"), a taxonomia usa
    plural ("Cimentos", "Conectores"). Portugues pluraliza palavra
    terminada em r/s/z com "+es" ("conector" -> "conectores"), nao so' "+s"
    como ingles ("cimento" -> "cimentos") - sem cobrir os dois padroes,
    "conector" nunca batia contra "Conectores" (achado em teste real,
    20/08, com o produto mais usado nesta sessao pra validar o modulo). So'
    mexe no final de uma palavra JA' tokenizada (nao e' substring solta) -
    por isso nao reintroduz o bug de "cimento" casar dentro de
    "aquecimento"."""
    variacoes = set(palavras)
    for p in palavras:
        variacoes.add(p + "s")
        variacoes.add(p + "es")
        if p.endswith("es") and len(p) > 4:
            variacoes.add(p[:-2])
        elif p.endswith("s") and len(p) > 3:
            variacoes.add(p[:-1])
    return variacoes


@lru_cache(maxsize=2)
def _carregar_taxonomia(idioma: str) -> tuple[CategoriaGoogle, ...]:
    arquivo = _ARQUIVOS_POR_IDIOMA[idioma]
    categorias: list[CategoriaGoogle] = []
    with arquivo.open(encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            id_str, caminho = linha.split(" - ", 1)
            categorias.append(CategoriaGoogle(id=int(id_str), caminho=caminho))
    return tuple(categorias)


def explorar(
    termo: str, top_n: int = 5, *, categoria_dominio: str | None = None,
) -> list[CategoriaGoogle]:
    """Percorre toda a taxonomia (~5600 categorias, no idioma detectado do
    `termo` - ver `domain.idioma.detectar_idioma`) e devolve as `top_n`
    mais relevantes, ordenadas por relevancia. Pontuacao: conta quantas
    PALAVRAS INTEIRAS (com variacao simples de plural) do termo aparecem no
    caminho da categoria, com peso extra pra match na FOLHA (ultimo nivel,
    mais especifico) e um boost pra categorias na RAIZ certa quando
    `categoria_dominio` e' passado (ver `RAIZ_GOOGLE_POR_CATEGORIA` e item 3
    da docstring do modulo - resolve empate entre dominios que a densidade/
    profundidade sozinhas nao resolvem, tipo "conector" batendo em
    Ferragens/Encanamento/Eletronicos igualmente). Desempate final: maior
    densidade (fracao da folha que casou) e depois caminho mais FUNDO
    (mais especifico) - testado contra "furadeira eletrica" real: preferir
    raso fazia "Manuais de produtos > Manuais de... furadeiras eletricas"
    (categoria sobre DOCUMENTACAO) ganhar de "Furadeiras eletricas
    portateis" (a certa, mais funda) so' por ter menos niveis."""
    idioma = detectar_idioma(termo)
    palavras = [p for p in _normalizar_termo(termo).split() if len(p) >= 3]
    if not palavras:
        return []

    raiz_alvo = None
    if categoria_dominio:
        raiz_alvo = RAIZ_GOOGLE_POR_CATEGORIA.get(categoria_dominio, {}).get(idioma)

    pontuadas: list[tuple[float, float, CategoriaGoogle]] = []
    for cat in _carregar_taxonomia(idioma):
        palavras_folha_brutas = _normalizar_termo(cat.folha).split()
        palavras_caminho = _com_variacao_plural(set(_normalizar_termo(cat.caminho).split()))
        palavras_folha = _com_variacao_plural(set(palavras_folha_brutas))
        pontos = 0.0
        acertos_na_folha = 0
        for p in palavras:
            if p in palavras_caminho:
                pontos += 1.0
                if p in palavras_folha:
                    pontos += 1.5
                    acertos_na_folha += 1
        if pontos > 0:
            if raiz_alvo and cat.raiz == raiz_alvo:
                pontos += _BOOST_RAIZ_CORRETA
            # densidade: fracao da FOLHA que casou com a busca - desempate
            # pra "conector" (uma so' palavra da busca bate) nao empatar
            # "Conectores de componentes eletronicos" (folha curta, no
            # topico) com "Conectores drop forward para armas de
            # paintball" (folha longa, "conector" e' so' 1 de 6 palavras
            # sem relacao nenhuma com o resto da busca) - achado em teste
            # real, 20/08: preferir so' profundidade dava a categoria
            # errada (paintball) por ser mais funda.
            densidade = acertos_na_folha / max(1, len(palavras_folha_brutas))
            pontuadas.append((pontos, densidade, cat))

    pontuadas.sort(key=lambda par: (-par[0], -par[1], -par[2].profundidade))
    return [cat for _, _, cat in pontuadas[:top_n]]


def melhor_categoria(termo: str, *, categoria_dominio: str | None = None) -> CategoriaGoogle | None:
    resultados = explorar(termo, top_n=1, categoria_dominio=categoria_dominio)
    return resultados[0] if resultados else None
