from __future__ import annotations

from datetime import UTC, datetime

from app.domain.deduplicacao import deduplicar_ofertas
from app.domain.models import Contato, Oferta


def _oferta(
    fonte: str, preco: int | None, contato: Contato | None = None, local: str = "loja",
    id_externo: str | None = None,
) -> Oferta:
    return Oferta(
        produto="conector jack p10", local=local, link=f"http://{fonte}",
        fonte=fonte, coletado_em=datetime.now(UTC), preco_centavos=preco, contato=contato,
        id_externo=id_externo,
    )


def test_mesmo_whatsapp_em_fontes_diferentes_e_deduplicado():
    """Correcao do usuario (20/08): "a exclusao de duplicidade... devem ser
    excluidas usando o contato do fornecedor como comparativo" - URLs
    diferentes (Google, Bright Data) do mesmo fornecedor nao podem virar 2
    ofertas."""
    a = _oferta("google-serp-direto", 1500, Contato(whatsapp=("11999998888",)))
    b = _oferta("brightdata-regional", 1800, Contato(whatsapp=("11999998888",)))
    resultado = deduplicar_ofertas([a, b])
    assert len(resultado) == 1
    assert resultado[0].fonte == "google-serp-direto"  # mais barata vence


def test_whatsapp_com_e_sem_codigo_do_pais_e_o_mesmo_contato():
    a = _oferta("fonte-a", 1500, Contato(whatsapp=("5511999998888",)))
    b = _oferta("fonte-b", 1200, Contato(whatsapp=("11999998888",)))
    resultado = deduplicar_ofertas([a, b])
    assert len(resultado) == 1
    assert resultado[0].fonte == "fonte-b"  # mais barata vence, apesar do formato diferente


def test_oferta_com_preco_vence_oferta_sem_preco_mesmo_contato():
    com_preco = _oferta("fonte-a", 1500, Contato(telefone=("1133334444",)))
    sem_preco = _oferta("fonte-b", None, Contato(telefone=("1133334444",)))
    resultado = deduplicar_ofertas([sem_preco, com_preco])
    assert len(resultado) == 1
    assert resultado[0].tem_preco


def test_ofertas_sem_contato_nunca_sao_deduplicadas_entre_si():
    a = _oferta("fonte-a", 1500, None)
    b = _oferta("fonte-b", 1500, None)
    resultado = deduplicar_ofertas([a, b])
    assert len(resultado) == 2


def test_contatos_diferentes_nao_sao_deduplicados():
    a = _oferta("fonte-a", 1500, Contato(whatsapp=("11999998888",)))
    b = _oferta("fonte-b", 1200, Contato(whatsapp=("11988887777",)))
    resultado = deduplicar_ofertas([a, b])
    assert len(resultado) == 2


def test_mesmo_id_externo_em_fontes_diferentes_e_deduplicado():
    """Correcao do usuario (20/08): "voce utilizou scraper do mercado livre
    ontem" - o actor Apify (`apify-price`) e a busca direta
    (`mercadolivre-direto`) cobrem o MESMO Mercado Livre por 2 caminhos e
    podem trazer o MESMO anuncio (mesmo id MLB) duas vezes."""
    do_actor = _oferta("apify-price", 6925, id_externo="MLB3882572605")
    da_busca_direta = _oferta(
        "mercadolivre-direto", 6500, id_externo="MLB3882572605",
    )
    resultado = deduplicar_ofertas([do_actor, da_busca_direta])
    assert len(resultado) == 1
    assert resultado[0].fonte == "mercadolivre-direto"  # mais barata vence


def test_id_externo_tem_prioridade_sobre_contato():
    """Mesmo id_externo mas contatos DIFERENTES (ex.: um lado extraiu um
    whatsapp de rodape por engano) - ainda e' o MESMO anuncio, id_externo
    decide, nao o contato."""
    a = _oferta("fonte-a", 1500, Contato(whatsapp=("11999998888",)), id_externo="MLB1")
    b = _oferta("fonte-b", 1200, Contato(whatsapp=("11988887777",)), id_externo="MLB1")
    resultado = deduplicar_ofertas([a, b])
    assert len(resultado) == 1


def test_id_externo_diferente_nao_e_deduplicado_mesmo_com_mesmo_contato():
    a = _oferta("fonte-a", 1500, Contato(whatsapp=("11999998888",)), id_externo="MLB1")
    b = _oferta("fonte-b", 1200, Contato(whatsapp=("11999998888",)), id_externo="MLB2")
    resultado = deduplicar_ofertas([a, b])
    assert len(resultado) == 2


def test_sem_id_externo_cai_para_dedup_por_contato():
    a = _oferta("fonte-a", 1500, Contato(whatsapp=("11999998888",)))
    b = _oferta("fonte-b", 1200, Contato(whatsapp=("11999998888",)))
    resultado = deduplicar_ofertas([a, b])
    assert len(resultado) == 1
