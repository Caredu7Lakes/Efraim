from app.domain.models import Escopo, ItemProduto
from app.domain.roteamento import montar_escopo_efetivo


def test_eletronico_em_ingles_ganha_internacional_com_termo_original():
    item = ItemProduto(nome="LED 3MM round Long lead diffused red")
    efetivo = montar_escopo_efetivo(item, Escopo.NACIONAL)
    assert efetivo.escopo is Escopo.INTERNACIONAL
    assert efetivo.idioma_detectado == "en"
    assert efetivo.categoria == "eletronico"
    # ja' em ingles - usa como veio, nao traduz
    assert efetivo.termo_internacional == "LED 3MM round Long lead diffused red"


def test_eletronico_em_portugues_ganha_internacional_com_termo_adaptado():
    item = ItemProduto(nome="conector jack p10 stereo profissional")
    efetivo = montar_escopo_efetivo(item, Escopo.NACIONAL)
    assert efetivo.escopo is Escopo.INTERNACIONAL
    assert efetivo.idioma_detectado == "pt"
    assert efetivo.categoria == "eletronico"
    assert efetivo.termo_internacional == "3.5mm stereo jack connector"


def test_termo_zh_deriva_do_termo_internacional_ja_adaptado():
    item = ItemProduto(nome="conector jack p10 stereo profissional")
    efetivo = montar_escopo_efetivo(item, Escopo.NACIONAL)
    assert efetivo.termo_zh == "3.5mm立体声插孔连接器"


def test_termo_zh_tambem_e_gerado_quando_nome_ja_veio_em_ingles():
    item = ItemProduto(nome="black connector cable")
    efetivo = montar_escopo_efetivo(item, Escopo.INTERNACIONAL)
    assert efetivo.idioma_detectado == "en"
    # sem match de frase (nao tem "3.5mm") - cai no glossario palavra-a-palavra
    assert "连接器" in efetivo.termo_zh  # connector
    assert "电缆" in efetivo.termo_zh  # cable
    assert "黑色" in efetivo.termo_zh  # black


def test_categoria_nao_internacional_fica_so_nacional():
    item = ItemProduto(nome="arroz tipo 1 5kg")
    efetivo = montar_escopo_efetivo(item, Escopo.NACIONAL)
    assert efetivo.escopo is Escopo.NACIONAL
    assert efetivo.categoria == "alimento"


def test_escopo_local_nao_e_sobrescrito_por_categoria():
    item = ItemProduto(nome="LED 3MM round Long lead diffused red")
    efetivo = montar_escopo_efetivo(item, Escopo.LOCAL)
    assert efetivo.escopo is Escopo.LOCAL


def test_escopo_internacional_pedido_explicitamente_e_respeitado():
    item = ItemProduto(nome="arroz tipo 1 5kg")  # categoria nao-eletronico
    efetivo = montar_escopo_efetivo(item, Escopo.INTERNACIONAL)
    assert efetivo.escopo is Escopo.INTERNACIONAL
