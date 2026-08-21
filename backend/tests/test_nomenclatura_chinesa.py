from app.domain.nomenclatura_chinesa import nomenclatura_chinesa


def test_frase_tecnica_conhecida_bate_como_substring():
    assert nomenclatura_chinesa("3.5mm stereo jack connector") == "3.5mm立体声插孔连接器"
    # descritor extra nao impede o match da frase tecnica
    esperado = "3.5mm立体声插孔连接器"
    assert nomenclatura_chinesa("professional 3.5mm stereo jack connector") == esperado


def test_sem_frase_conhecida_cai_no_glossario_palavra_a_palavra():
    termo = nomenclatura_chinesa("black connector cable")
    assert "黑色" in termo
    assert "连接器" in termo
    assert "电缆" in termo


def test_termo_sem_mapeamento_fica_como_veio():
    termo = nomenclatura_chinesa("arduino uno r3")
    assert "arduino" in termo
    assert "uno" in termo
    assert "r3" in termo
