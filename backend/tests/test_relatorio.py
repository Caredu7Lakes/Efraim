from app.domain.relatorio import renderizar_relatorio_markdown


def _resultado_exemplo() -> dict:
    return {
        "produto": "conector jack p10 stereo",
        "top7_online": [
            # ja' vem ordenado por preco (garantia do filtrar_top7) - o
            # fixture precisa respeitar isso, nao e' o renderizador que ordena.
            {"produto": "P10 Jack Stereo Aberto", "marca": "Mac Cabos", "preco_centavos": 138,
             "moeda": "BRL", "local": "Enterlight", "link": "https://enterlight.example.com/x",
             "regiao": "Sudeste"},
            {"produto": "Conector Jack P10", "marca": "Daier", "preco_centavos": 140,
             "moeda": "BRL", "local": "Alibaba", "link": "https://alibaba.example.com/x",
             "regiao": None},
        ],
        "sem_preco": [
            {"local": "MD Componentes Eletrônicos", "cidade": "Curitiba", "uf": "PR",
             "regiao": "Sul", "link": "https://mdcomp.example.com",
             "contato": {"whatsapp": ["554130240022"], "telefone": [], "email": []}},
        ],
        "sem_preco_por_regiao": {
            "Sul": [{"local": "MD Componentes Eletrônicos", "cidade": "Curitiba"}],
        },
    }


def test_relatorio_inclui_titulo_e_secoes():
    md = renderizar_relatorio_markdown(_resultado_exemplo())
    assert "# Relatório de Busca — conector jack p10 stereo" in md
    assert "SEÇÃO 1 — TOP 7 MENORES PREÇOS ONLINE" in md
    assert "SEÇÃO 2 — TODOS OS FORNECEDORES SEM PREÇO ONLINE" in md


def test_relatorio_estatisticas_batem_com_os_dados():
    md = renderizar_relatorio_markdown(_resultado_exemplo())
    assert "Menor preço:** R$ 1,38" in md  # o de 138 centavos, nao o de 140
    assert "Fornecedores com preço:** 2" in md
    assert "Sem preço online:** 1" in md
    assert "Regiões cobertas:** 1" in md


def test_relatorio_formata_preco_e_link_por_linha():
    md = renderizar_relatorio_markdown(_resultado_exemplo())
    assert "| 1 | P10 Jack Stereo Aberto | Mac Cabos | R$ 1,38 | Enterlight | Sudeste |" in md
    assert "| 2 | Conector Jack P10 | Daier | R$ 1,40 | Alibaba | — |" in md
    assert "[abrir](https://alibaba.example.com/x)" in md


def test_relatorio_secao_2_com_contato_e_cidade():
    md = renderizar_relatorio_markdown(_resultado_exemplo())
    assert "| MD Componentes Eletrônicos | Curitiba/PR | Sul | 554130240022 | — |" in md


def test_relatorio_cobertura_por_regiao():
    md = renderizar_relatorio_markdown(_resultado_exemplo())
    assert "### Cobertura da busca profunda" in md
    assert "**Sul:** Curitiba" in md


def test_relatorio_sem_ofertas_nao_quebra():
    vazio = {
        "produto": "produto sem resultado", "top7_online": [], "sem_preco": [],
        "sem_preco_por_regiao": {},
    }
    md = renderizar_relatorio_markdown(vazio)
    assert "Nenhuma oferta com preço encontrada" in md
    assert "Nenhum fornecedor sem preço encontrado" in md
