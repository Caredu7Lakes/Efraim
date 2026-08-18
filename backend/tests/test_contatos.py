from app.sourcing.contatos import extrair_contatos


def test_extrai_whatsapp_email_telefone_form(html_com_contatos):
    c = extrair_contatos(html_com_contatos)
    assert "5511988887777" in c.whatsapp
    assert "551133224455" in c.whatsapp
    assert "vendas@loja.com.br" in c.email
    assert "suporte@loja.com.br" in c.email
    assert any(t.endswith("33224455") for t in c.telefone)
    assert c.form_url == "/enviar-cotacao"


def test_html_vazio():
    c = extrair_contatos("<html></html>")
    assert c.vazio()


def test_whatsapp_rotulado_como_texto():
    c = extrair_contatos("<p>Fale conosco no whatsapp: (11) 99999-8888</p>")
    assert "11999998888" in c.whatsapp
