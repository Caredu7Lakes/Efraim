import pytest


@pytest.fixture
def html_com_contatos() -> str:
    return """
    <html><body>
      <a href="https://wa.me/5511988887777">WhatsApp</a>
      <a href="https://api.whatsapp.com/send?phone=551133224455">fale</a>
      contato: vendas@loja.com.br / suporte@loja.com.br
      Tel: (11) 3322-4455
      <form action="/enviar-cotacao" method="post"></form>
    </body></html>
    """
