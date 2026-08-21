"""Testa a exploracao da taxonomia real do Google (arquivo de verdade,
baixado em 20/08 - nao e' mock, e' o mesmo dado que vai pra producao).
Cada teste aqui corresponde a um bug real achado testando com produtos
reais desta sessao, ver docstring de `taxonomia_google.py`."""
from app.domain.taxonomia_google import explorar, melhor_categoria


def test_conector_bate_eletronicos_com_boost_de_dominio():
    """3o bug achado (20/08): sem o produto ter cobertura lexica em mais
    de 1 palavra ("jack"/"stereo" nao existem na taxonomia), "conector"
    sozinho empata entre Ferragens/Encanamento/Eletronicos - o boost pelo
    dominio ja' classificado por `classificacao.classificar()` resolve."""
    cat = melhor_categoria("conector jack p10 stereo", categoria_dominio="eletronico")
    assert cat is not None
    assert cat.raiz == "Eletrônicos"
    assert "conector" in cat.folha.lower() or "conectores" in cat.folha.lower()


def test_cimento_nao_confunde_com_aquecimento():
    """1o bug achado (20/08): substring solta - "cimento" batia dentro de
    "aquecimento" (a-que-CIMENTO). Corrigido comparando palavra inteira."""
    cat = melhor_categoria("cimento 50kg", categoria_dominio="construcao")
    assert cat is not None
    assert "cimento" in cat.caminho.lower()
    assert "aquecimento" not in cat.caminho.lower()


def test_conector_no_plural_bate_com_termo_no_singular():
    """2o bug achado (20/08): portugues pluraliza "conector" -> "conectores"
    com "+es", nao "+s" como ingles - sem cobrir os dois padroes, o termo
    no singular (como o produto normalmente vem) nunca batia contra a
    taxonomia (que usa plural)."""
    resultados = explorar("conector", top_n=20)
    assert any("conectores" in r.folha.lower() for r in resultados)


def test_furadeira_eletrica_prefere_categoria_da_ferramenta_nao_manual():
    """Desempate por profundidade: "Manuais de produtos > Manuais de...
    furadeiras eletricas" (documentacao) empatava com "Furadeiras
    eletricas portateis" (a ferramenta em si) - preferir mais fundo
    corrigiu, "manual" nao pode ganhar da categoria real do produto."""
    cat = melhor_categoria("furadeira eletrica", categoria_dominio="ferramenta")
    assert cat is not None
    assert "manual" not in cat.caminho.lower()
    assert "furadeira" in cat.folha.lower()


def test_racao_gato_nao_racao_cachorro():
    cat = melhor_categoria("racao para gato", categoria_dominio="pet")
    assert cat is not None
    assert "gato" in cat.caminho.lower()
    assert "cachorro" not in cat.caminho.lower() and "cão" not in cat.caminho.lower()


def test_termo_em_ingles_usa_taxonomia_em_ingles():
    """Nome de produto em ingles busca na taxonomia en-US, nao pt-BR -
    evita colisao lexica tipo "red" (cor, ingles) batendo em "rede"
    (portugues) por coincidencia."""
    resultados = explorar("black connector cable", top_n=5)
    assert resultados  # tem que achar algo
    # taxonomia en-US usa "&" em vez de acentos - confirma que carregou o arquivo certo
    assert any("&" in r.caminho or r.raiz.isascii() for r in resultados)


def test_termo_sem_palavra_reconhecida_devolve_vazio():
    assert explorar("xyzabc123qwerty") == []


def test_arroz_bate_categoria_de_graos():
    cat = melhor_categoria("arroz tipo 1 5kg", categoria_dominio="alimento")
    assert cat is not None
    assert "arroz" in cat.caminho.lower()
