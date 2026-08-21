from app.domain.extracao_pagina import (
    exporta_para_brasil,
    extrair_quantidade_numerica,
    extrair_quantidade_unidades,
    produto_aparece,
)


def test_exporta_para_brasil_detecta_mencao_explicita():
    assert exporta_para_brasil("<html>We ship worldwide, including Brazil.</html>")
    assert exporta_para_brasil("<html>Enviamos para todo o Brasil</html>")
    assert exporta_para_brasil("<html>International shipping available.</html>")


def test_exporta_para_brasil_sem_sinal_e_falso():
    """Correcao do usuario (20/08): um resultado internacional sem sinal de
    que atende o Brasil nao e' "lixo" automaticamente, mas tambem nao entra
    na comparacao de preco sem esse sinal - o site so' vender localmente
    (Peru, EAU etc.) sem mencionar exportacao nao confirma que atende o
    Brasil."""
    html = "<html>Loja de eletronicos em Lima, Peru. Entrega so' na cidade.</html>"
    assert not exporta_para_brasil(html)


def test_produto_aparece_continua_funcionando():
    assert produto_aparece("<html>Conector Jack P10 em estoque</html>", "conector jack p10")
    assert not produto_aparece("<html>Frete gratis acima de R$ 100</html>", "conector jack p10")


def test_extrai_quantidade_de_kit():
    assert extrair_quantidade_unidades("<html>Kit com 50 unidades por R$ 9,90</html>") == (
        "Kit com 50 unidades"
    )


def test_extrai_quantidade_solta_sem_kit():
    assert extrair_quantidade_unidades("<html>Pacote 100 pecas - promocao</html>") == "100 pecas"


def test_sem_sinal_de_quantidade_devolve_none():
    assert extrair_quantidade_unidades("<html>Preco: R$ 9,90 a vista</html>") is None


def test_quantidade_numerica_kit_sem_com_ou_de():
    """Titulo real do Mercado Livre (20/08): "Kit 6 Conectores..." - sem
    "com"/"de" entre "kit" e o numero, que a versao de anotacao (acima)
    exige."""
    assert extrair_quantidade_numerica("Kit 6 Conectores P10 Trs Femea Painel") == 6


def test_quantidade_numerica_kit_com_x():
    assert extrair_quantidade_numerica("Kit 10x Ls-2039 Conector P10 Jack Stereo") == 10


def test_quantidade_numerica_kit_com_de_continua_funcionando():
    assert extrair_quantidade_numerica("Kit com 50 unidades por R$ 9,90") == 50


def test_quantidade_numerica_ignora_numero_que_nao_e_quantidade():
    """"6 Terminais" nao e' quantidade de lote - so' "10 Pecas" (unidade
    explicita) deve contar aqui."""
    assert extrair_quantidade_numerica("Conector 6 Terminais Com Rosca 10 Pecas") == 10


def test_quantidade_numerica_sem_sinal_presume_unidade():
    assert extrair_quantidade_numerica("Conector Jack P10 Stereo Femea De Painel") == 1
