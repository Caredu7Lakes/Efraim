from app.domain.classificacao import (
    PONTOS_VENDA,
    REGIOES_BR,
    SITES_INTERNACIONAIS_CHINA,
    SITES_INTERNACIONAIS_EUA,
    classificar,
    gerar_queries_fornecedores,
    gerar_queries_internacionais,
    gerar_queries_produto,
    pontos_venda_amostra,
    pontos_venda_amostra_fornecedor,
)
from app.domain.models import ItemProduto


def test_agua_pura_cai_no_fallback_geral():
    """Agua sozinha nao e' produto de limpeza - nao deve casar com a
    keyword composta 'agua sanitaria' (substring exige a frase inteira)."""
    assert classificar("agua") == "geral"
    assert classificar("água") == "geral"
    assert classificar("agua mineral com gas") == "geral"


def test_agua_sanitaria_classifica_como_limpeza():
    assert classificar("agua sanitaria") == "limpeza"
    assert classificar("água sanitária") == "limpeza"
    assert classificar("agua sanitaria 5L") == "limpeza"
    assert classificar("candida agua sanitaria") == "limpeza"  # marca + produto


def test_pontos_venda_amostra_cobre_todos_os_6_grupos():
    """Achado em revisao (19/08): `pontos_venda_de(cat)[:3]` so' pegava o
    grupo "primarios" (varejo), porque ele vem primeiro no dict e ja' tem 3
    itens sozinho - a busca nunca alcancava distribuidor/importador/
    atacadista/representante. `pontos_venda_amostra` pega de CADA grupo."""
    amostra = pontos_venda_amostra("eletronico", por_grupo=1)
    assert len(amostra) == 6  # 1 de cada um dos 6 grupos
    texto = " ".join(amostra).lower()
    assert "distribuidora" in texto or "atacadista" in texto or "representante" in texto
    assert "importadora" in texto


def test_queries_camada1_buscam_so_o_produto_sem_qualificar_loja():
    """Correcao do usuario (20/08): a camada 1 busca so' pelo produto -
    "a busca se inicia apenas pelo produto" - sem termo de categoria/loja
    misturado na query."""
    item = ItemProduto(nome="conector jack p10")
    queries = gerar_queries_produto(item)
    assert all("conector jack p10" in q for q in queries)
    assert all("-site:mercadolivre.com.br" in q for q in queries)
    texto = " ".join(queries).lower()
    assert "loja" not in texto and "distribuidora" not in texto and "fabricante" not in texto


def test_queries_fornecedores_cobrem_todas_as_5_regioes_sem_restringir():
    """Bloco C (camada 2) nao restringe a uma regiao por padrao - so' por
    pedido explicito do usuario (pendencia, ainda nao codada)."""
    queries = gerar_queries_fornecedores("eletronico")
    for regiao in REGIOES_BR:
        assert any(regiao in q for q in queries), f"regiao {regiao} ausente das queries"


def test_queries_fornecedores_excluem_marketplaces_e_nao_incluem_produto():
    """Correcao do usuario (20/08): a camada 2 busca por CATEGORIA de
    fornecedor (loja/distribuidor/importador/fabricante), NUNCA pelo nome
    do produto - o casamento com o produto acontece depois, visitando cada
    pagina encontrada (ver `sourcing/adapters/apify_source.py`)."""
    queries = gerar_queries_fornecedores("eletronico")
    assert all("conector jack p10" not in q for q in queries)
    assert all("-site:mercadolivre.com.br" in q for q in queries)


def test_queries_internacionais_usam_termo_en_nos_sites_dos_eua_e_termo_zh_na_china():
    item = ItemProduto(nome="conector jack p10 stereo")
    termo_en, termo_zh = "3.5mm stereo jack connector", "3.5mm立体声插孔连接器"
    queries = gerar_queries_internacionais(item, termo_en, termo_zh)
    for site in SITES_INTERNACIONAIS_EUA:
        q = next(q for q in queries if f"site:{site}" in q)
        assert "3.5mm stereo jack connector" in q
    for site in SITES_INTERNACIONAIS_CHINA:
        q = next(q for q in queries if f"site:{site}" in q)
        assert "3.5mm立体声插孔连接器" in q
        assert "3.5mm stereo jack connector" not in q  # nao vaza o termo em ingles pro lado chines


def test_categorias_expandidas_tem_6_grupos_de_pontos_de_venda():
    """As 12 categorias novas portadas do prototipo Base44 (19/08) devem ter
    os mesmos 6 grupos que 'eletronico' ja' tinha, nao so' os 3 originais do
    prototipo (primarios/secundarios/cruzados) - ver pontos_venda_amostra."""
    novas = [
        "floricultura_jardinagem", "carne", "bebida", "higiene", "padaria",
        "vestuario", "papelaria", "farmacia", "brinquedo", "livro",
        "eletrodomesticos", "moveis",
    ]
    for categoria in novas:
        grupos = PONTOS_VENDA[categoria]
        assert set(grupos.keys()) == {
            "primarios", "secundarios", "cruzados",
            "fabricantes", "distribuidores", "importadoras",
        }
        assert all(grupos[g] for g in grupos)  # nenhum grupo vazio


def test_bebida_nao_inclui_agua_generica_como_keyword():
    """'agua mineral com gas' deve continuar caindo no fallback 'geral' -
    ver test_agua_pura_cai_no_fallback_geral. Adicionar a categoria 'bebida'
    nao pode quebrar isso (o prototipo Base44 original incluia 'agua
    mineral'/'agua com gas' em bebida; aqui ficam de fora de proposito)."""
    assert classificar("agua mineral com gas") == "geral"
    assert classificar("cerveja artesanal") == "bebida"


def test_eletronico_restringe_camada2_a_fabricante_distribuidor_importador():
    """Correcao do usuario (20/08): pra eletronico/componente, a busca de
    FORNECEDOR (camada 2) nao deve incluir "supermercado"/"loja de
    celulares"/"marketplace online" - achado em teste real, a query
    "supermercado Sul Brasil" trouxe rede de supermercado, nao fornecedor
    de componente eletronico."""
    amostra = pontos_venda_amostra_fornecedor("eletronico", por_grupo=1)
    assert amostra == [
        "fabricante de eletronicos", "distribuidora de eletronicos", "importadora de eletronicos",
    ]
    assert "supermercado" not in amostra
    assert "loja de celulares" not in amostra


def test_alimento_continua_usando_todos_os_6_grupos_camada2():
    """Correcao do usuario (20/08): a curadoria e' POR CATEGORIA, nao um
    valor fixo universal - "supermercado"/"atacarejo"/"minimercado" SAO
    pontos de venda legitimos pra arroz, diferente de eletronico."""
    amostra_completa = pontos_venda_amostra("alimento", por_grupo=1)
    amostra_fornecedor = pontos_venda_amostra_fornecedor("alimento", por_grupo=1)
    assert amostra_fornecedor == amostra_completa  # sem override - usa os 6 grupos
    assert "supermercado" in amostra_fornecedor
