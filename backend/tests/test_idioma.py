from app.domain.idioma import detectar_idioma


def test_detecta_ingles():
    assert detectar_idioma("LED 3MM round Long lead diffused red") == "en"


def test_detecta_portugues():
    assert detectar_idioma("conector jack p10 stereo profissional") == "pt"
    assert detectar_idioma("conector jack p10 estéreo profissional") == "pt"


def test_nome_neutro_sem_sinal_lexico_desempata_portugues():
    assert detectar_idioma("P10") == "pt"
    assert detectar_idioma("XYZ123") == "pt"
