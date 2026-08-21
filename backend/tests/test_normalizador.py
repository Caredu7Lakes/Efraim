from app.domain.normalizador import normalizar, normalizar_nome


def test_normalizar_nome_remove_acento_e_unidade():
    assert normalizar_nome("Café Torrado 500g") == "cafe torrado 500g"
    assert normalizar_nome("Cimento CP-II") == "cimento cp ii"


def test_normalizar_converte_preco_br():
    o = normalizar({"produto": "X", "preco": "R$ 1.299,90"}, fonte="t")
    assert o.preco_centavos == 129990
    assert o.moeda == "BRL"


def test_normalizar_sem_preco():
    o = normalizar({"produto": "X", "preco": None}, fonte="t")
    assert o.preco_centavos is None


def test_normalizar_converte_preco_us():
    o = normalizar({"produto": "X", "preco": "19.99"}, fonte="t")
    assert o.preco_centavos == 1999


def test_normalizar_sem_frete_nao_quebra_custo_total():
    """Achado ao ligar o adapter Apify (primeiro chamador real): sem 'frete'
    no raw, frete_centavos virava None (nao 0) e custo_total_centavos
    (preco + frete) quebrava com TypeError."""
    o = normalizar({"produto": "X", "preco": "10,00"}, fonte="t")
    assert o.frete_centavos == 0
    assert o.custo_total_centavos == 1000


def test_normalizar_infere_unidades_do_lote_a_partir_do_nome_do_produto():
    """Correcao do usuario (20/08): "so' pode descartar apos fazer a
    conversao" - quem chama nao precisa passar `unidades_no_lote`
    explicito, `normalizar` infere do proprio nome/titulo (cobre Mercado
    Livre/Shopee/actors, cujos titulos reais dizem "Kit 6 Conectores...")."""
    o = normalizar({"produto": "Kit 6 Conectores P10 Trs Femea Painel", "preco": "69,00"},
                    fonte="t")
    assert o.unidades_no_lote == 6
    assert o.custo_unitario_centavos == 1150  # 6900 / 6


def test_normalizar_unidades_no_lote_explicito_tem_prioridade():
    o = normalizar({"produto": "conector jack p10", "preco": "60,00", "unidades_no_lote": 3},
                    fonte="t")
    assert o.unidades_no_lote == 3
    assert o.custo_unitario_centavos == 2000


def test_normalizar_sem_sinal_de_lote_unidade_e_1():
    o = normalizar({"produto": "conector jack p10", "preco": "10,00"}, fonte="t")
    assert o.unidades_no_lote == 1
