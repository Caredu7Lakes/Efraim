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
