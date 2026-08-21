"""Renderiza o resultado de uma busca como relatorio em markdown (ETAPA 5).

Formato: SEÇÃO 1 (top7 com preço, ordenado) + SEÇÃO 2 (sem preço, contato
pra cotação) + estatísticas + cobertura da busca regional. Pura formatação,
sem I/O — opera sobre o dict que `jobs/tasks.py::resultado_para_dict` já
produz (mais os campos extras que `_executar_pipeline` acrescenta por
produto: produto/categoria/idioma_detectado/escopo_efetivo/...).
"""
from __future__ import annotations

_SIMBOLO_MOEDA = {"BRL": "R$", "USD": "US$"}


def _preco_fmt(preco_centavos: int | None, moeda: str) -> str:
    if preco_centavos is None:
        return "—"
    valor = preco_centavos / 100
    texto = f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    simbolo = _SIMBOLO_MOEDA.get(moeda, f"{moeda} ")
    return f"{simbolo} {texto}"


def _contato_fmt(contato: dict | None) -> tuple[str, str]:
    if not contato:
        return "—", "—"
    whats_tel = list(contato.get("whatsapp") or []) + list(contato.get("telefone") or [])
    email = contato.get("email") or []
    return (", ".join(whats_tel) or "—", ", ".join(email) or "—")


def _link_md(url: str | None, rotulo: str = "abrir") -> str:
    return f"[{rotulo}]({url})" if url else "—"


def _cidade_uf(oferta: dict) -> str:
    partes = [p for p in [oferta.get("cidade"), oferta.get("uf")] if p]
    return "/".join(partes) if partes else "—"


def renderizar_relatorio_markdown(resultado_produto: dict) -> str:
    """`resultado_produto` e' um item de `resultado["resultados"]` (a saida
    de `_executar_pipeline`/`GET /buscas/{job_id}`), nao o payload inteiro."""
    produto = resultado_produto["produto"]
    top7 = resultado_produto["top7_online"]
    sem_preco = resultado_produto["sem_preco"]
    por_regiao = resultado_produto.get("sem_preco_por_regiao", {})

    linhas = [f"# Relatório de Busca — {produto}", ""]

    menor_preco = _preco_fmt(top7[0]["preco_centavos"], top7[0]["moeda"]) if top7 else "—"
    linhas.append(
        f"**Menor preço:** {menor_preco} | **Fornecedores com preço:** {len(top7)} | "
        f"**Sem preço online:** {len(sem_preco)} | **Regiões cobertas:** {len(por_regiao)}"
    )
    linhas.append("")

    linhas.append("## SEÇÃO 1 — TOP 7 MENORES PREÇOS ONLINE")
    linhas.append(
        "Ordenado por menor preço unitário. Inclui marketplaces, distribuidores, "
        "lojas próprias e sites internacionais."
    )
    linhas.append("")
    if top7:
        linhas.append("| # | Produto | Marca | Preço | Local | Região | Link |")
        linhas.append("|---|---|---|---|---|---|---|")
        for i, o in enumerate(top7, start=1):
            preco = _preco_fmt(o["preco_centavos"], o["moeda"])
            marca = o["marca"] or "—"
            regiao = o.get("regiao") or "—"
            linhas.append(
                f"| {i} | {o['produto']} | {marca} | {preco} | {o['local']} | "
                f"{regiao} | {_link_md(o['link'])} |"
            )
    else:
        linhas.append("_Nenhuma oferta com preço encontrada._")
    linhas.append("")

    linhas.append("## SEÇÃO 2 — TODOS OS FORNECEDORES SEM PREÇO ONLINE (WhatsApp/Email)")
    linhas.append(
        "Comércios com site mas sem preço online. Contatos para cotação direta. "
        "Sem limite de listagem."
    )
    linhas.append("")
    if sem_preco:
        linhas.append("| Comércio | Cidade/UF | Região | WhatsApp/Telefone | Email | Link |")
        linhas.append("|---|---|---|---|---|---|")
        for o in sem_preco:
            regiao = o.get("regiao") or "—"
            whats_tel, email = _contato_fmt(o.get("contato"))
            linhas.append(
                f"| {o['local']} | {_cidade_uf(o)} | {regiao} | {whats_tel} | {email} | "
                f"{_link_md(o['link'], 'site')} |"
            )
    else:
        linhas.append("_Nenhum fornecedor sem preço encontrado._")
    linhas.append("")

    if por_regiao:
        linhas.append("### Cobertura da busca profunda")
        for regiao in sorted(por_regiao.keys()):
            cidades = sorted({o["cidade"] for o in por_regiao[regiao] if o.get("cidade")})
            texto = ", ".join(cidades) if cidades else "(cidade não identificada pelo actor)"
            linhas.append(f"**{regiao}:** {texto}")
        linhas.append("")

    return "\n".join(linhas)
