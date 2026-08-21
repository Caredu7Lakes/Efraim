from app.domain.nomenclatura_internacional import nomenclatura_internacional


def test_adapta_conector_jack_p10_estereo():
    """Exemplo motivador: sem essa adaptacao, a busca internacional por
    'conector jack p10 estereo' voltaria vazia - ninguem anuncia nesse
    termo fora do Brasil."""
    assert nomenclatura_internacional("conector jack p10 estéreo") == "3.5mm stereo jack connector"
    assert nomenclatura_internacional("conector jack p10 stereo") == "3.5mm stereo jack connector"


def test_fallback_palavra_a_palavra_preserva_termos_desconhecidos():
    # "resistor" traduz, "10k" (codigo tecnico) fica como veio
    assert nomenclatura_internacional("resistor 10k") == "resistor 10k"
