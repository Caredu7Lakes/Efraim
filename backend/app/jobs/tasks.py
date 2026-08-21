"""Task Celery que executa o pipeline de busca (ETAPA 1-5), substituindo o
runner in-process de v1.

Recebe e devolve SOMENTE dados serializaveis (dict) - nunca um objeto de
dominio (`Oferta`, `ConsultaProduto`...) nem uma coroutine. E' essa fronteira
que torna a fila trocavel de broker e escalavel: um worker Celery rodando em
outro processo/maquina so' consegue receber o `payload` se ele for JSON.

Processa TODOS os produtos da lista (nao so' o primeiro) - cada produto tem
seu proprio escopo efetivo, decidido por `domain.roteamento` (categoria +
idioma do nome), independente do escopo pedido pra busca inteira.
"""
from __future__ import annotations

import asyncio
import logging

from app.config import Settings, get_settings
from app.domain.classificacao import montar_consulta_local, montar_consulta_produto
from app.domain.models import Contato, Escopo, ItemProduto, Localizacao, Oferta, ResultadoFiltro
from app.domain.roteamento import montar_escopo_efetivo
from app.jobs.celery_app import celery_app
from app.persistence.repositorio import RepositorioSQL
from app.sourcing.busca_mercadolivre import buscar_mercadolivre
from app.sourcing.busca_shopee import buscar_shopee
from app.sourcing.factory import montar_orquestrador
from app.sourcing.filtro import filtrar_top7
from app.sourcing.orcamento import OrcamentoMCP
from app.sourcing.variacoes_busca import buscar_e_aprender

log = logging.getLogger("efraim.tasks")


def _contato_para_dict(c: Contato | None) -> dict | None:
    if c is None or c.vazio():
        return None
    return {
        "whatsapp": list(c.whatsapp), "email": list(c.email),
        "telefone": list(c.telefone), "form_url": c.form_url,
    }


def oferta_para_dict(o: Oferta) -> dict:
    return {
        "produto": o.produto, "marca": o.marca, "preco_centavos": o.preco_centavos,
        "moeda": o.moeda, "local": o.local, "link": o.link, "pagamento": o.pagamento,
        "disponibilidade": o.disponibilidade.value, "condicao": o.condicao.value,
        "frete_centavos": o.frete_centavos, "coletado_em": o.coletado_em.isoformat(),
        "fonte": o.fonte, "contato": _contato_para_dict(o.contato), "regiao": o.regiao,
        "cidade": o.cidade, "uf": o.uf,
    }


def _sem_preco_por_regiao(ofertas: list[Oferta]) -> dict[str, list[dict]]:
    """Agrupa as ofertas do Bloco B (regional) por regiao - a busca ja'
    cobre as 5 regioes sem restringir a nenhuma (ver domain/roteamento e
    ApifyRegionalSource); isto so' organiza a APRESENTACAO. Ofertas sem
    regiao (marketplace, Bloco C) nao entram aqui - ja' estao em sem_preco
    normal."""
    grupos: dict[str, list[dict]] = {}
    for o in ofertas:
        if o.regiao is None:
            continue
        grupos.setdefault(o.regiao, []).append(oferta_para_dict(o))
    return grupos


def resultado_para_dict(r: ResultadoFiltro) -> dict:
    return {
        "top7_online": [oferta_para_dict(o) for o in r.top7_online],
        "sem_preco": [oferta_para_dict(o) for o in r.sem_preco],
        "sem_preco_por_regiao": _sem_preco_por_regiao(r.sem_preco),
        "total_descartados": r.total_descartados,
    }


def _item_de(p: dict) -> ItemProduto:
    return ItemProduto(
        nome=p["nome"], marca=p.get("marca"), quantidade=p.get("quantidade", 1),
        unidade=p.get("unidade", "un"), qualidade=p.get("qualidade"),
    )


async def _executar_pipeline(payload: dict) -> dict:
    cfg = get_settings()
    escopo_pedido = Escopo(payload["escopo"])
    repo = RepositorioSQL()
    lista_id = await _lista_id_da_busca(repo, escopo_pedido, payload)

    resultados = []
    for p in payload["produtos"]:
        item = _item_de(p)
        efetivo = montar_escopo_efetivo(item, escopo_pedido)

        orq = montar_orquestrador(cfg)
        cp = montar_consulta_produto(
            item, efetivo.escopo,
            termo_internacional=efetivo.termo_internacional,
            termo_zh=efetivo.termo_zh,
        )
        cl = None
        if efetivo.escopo is Escopo.LOCAL:
            loc = Localizacao(cep=payload.get("cep"), cidade=payload.get("cidade"))
            cl = montar_consulta_local(item, loc)

        resultado_orquestrado = await orq.executar(cp, cl)
        ofertas_aprendidas = await _aprender_variacoes(cfg, item, efetivo.categoria, repo)
        # reprocessa TUDO junto (resultado original + Google + Mercado
        # Livre) pelo mesmo ponto unico de decisao (`filtrar_top7`) -
        # correcao do usuario (20/08): antes o aprendizado so' era despejado
        # em sem_preco, sem competir pelas 7 melhores ofertas nem passar
        # pela deduplicacao por contato entre fontes.
        resultado = filtrar_top7(
            resultado_orquestrado.top7_online
            + resultado_orquestrado.sem_preco
            + ofertas_aprendidas,
        )
        await _persistir(repo, lista_id, resultado)

        # escopo_efetivo sempre inclui "nacional" (gerar_queries_nacionais
        # roda incondicionalmente) + "internacional" quando aplicavel - ver
        # domain/roteamento.py.
        rotulo_escopo = ["nacional"] if efetivo.escopo is not Escopo.LOCAL else ["local"]
        if efetivo.escopo is Escopo.INTERNACIONAL:
            rotulo_escopo.append("internacional")

        resultados.append({
            "produto": item.nome,
            "categoria": efetivo.categoria,
            "idioma_detectado": efetivo.idioma_detectado,
            "escopo_efetivo": rotulo_escopo,
            "termo_busca_internacional": (
                efetivo.termo_internacional if efetivo.escopo is Escopo.INTERNACIONAL else None
            ),
            "termo_busca_zh": (
                efetivo.termo_zh if efetivo.escopo is Escopo.INTERNACIONAL else None
            ),
            **resultado_para_dict(resultado),
        })

    return {"resultados": resultados}


async def _lista_id_da_busca(
    repo: RepositorioSQL, escopo_pedido: Escopo, payload: dict,
) -> int | None:
    """Uma ListaCompra por busca (nao por produto) - todos os produtos do
    mesmo pedido compartilham a mesma lista, como o modelo de dados prescreve
    (LISTA_COMPRA 1:N RESULTADO_BUSCA). Falha aqui e' resiliente: sem
    lista_id, a busca segue e so' a persistencia desse job fica de fora."""
    try:
        lista_id = payload.get("lista_id")
        if lista_id is not None:
            return lista_id
        localizacao = payload.get("cidade") or payload.get("cep")
        return await repo.criar_lista(
            escopo=escopo_pedido.value, localizacao=localizacao,
            usuario_id=payload.get("usuario_id"),
        )
    except Exception:  # noqa: BLE001 - resiliencia proposital, ver docstring de _persistir
        log.exception("falha ao criar lista de compra (resposta ao usuario segue normal)")
        return None


async def _aprender_variacoes(
    cfg: Settings, item: ItemProduto, categoria: str, repo: RepositorioSQL,
) -> list[Oferta]:
    """Bloco C, enriquecimento (pedido do usuario, 20/08: "ligar e rodar
    a busca, extrair variacoes, guardar pra proxima" - depois expandido pra
    "entrar em cada link existente na pagina", e mais tarde pra "mercado
    livre nao e' o unico marketplace que deve ser visitado" - a relacao
    real esta' em `docs/ARQUITETURA.md` §6: ML, Magalu, Shopee, Americanas.
    Magalu e Americanas ficaram FORA (achado real, 20/08: as 2 renderizam a
    lista de produtos so' client-side via JS - o HTML cru devolvido pelo
    Web Unlocker nao tem nenhum produto, so' o shell da pagina - confirmado
    inspecionando o payload `__NEXT_DATA__`/embutido de cada uma; sem um
    modo de renderizacao JS no Web Unlocker desta conta, nao ha' dado real
    pra' extrair). Busca ampla e profunda no Google (shopping + organico
    paginado, visitando cada link - `sourcing.variacoes_busca.
    buscar_e_aprender`), no Mercado Livre (`sourcing.busca_mercadolivre.
    buscar_mercadolivre`) e na Shopee (`sourcing.busca_shopee.
    buscar_shopee`), persiste as variacoes de busca do Google achadas e
    devolve TODAS as ofertas aprendidas pro chamador combinar com o
    resultado original antes de rodar `filtrar_top7` de novo (ver
    `_executar_pipeline`) - assim elas competem pelas 7 melhores em vez de
    so' cair em sem_preco. Orcamento proprio pra CADA fonte (bem mais
    generoso que o resto do pipeline - decisao explicita do usuario foi
    "tempo nao importa, o que importa e' a qualidade do retorno"), NAO
    compartilhado entre elas - achado real (20/08): com 1 orcamento so'
    dividido entre as 3, o Google (que agora sempre pagina ate' a pagina 18
    e visita cada link novo, desde a correcao de nao parar por duplicidade)
    consumia o orcamento inteiro antes da vez do Mercado Livre/Shopee,
    zerando os dois mesmo com credenciais validas - confirmado comparando
    um job real (0 ofertas de `mercadolivre-direto`) contra a mesma busca
    isolada (60 ofertas reais). Cada fonte com seu proprio orcamento
    elimina essa disputa; nenhum deles compete com o orcamento principal
    (Bloco A/B/C/D)."""
    ofertas_google = await buscar_e_aprender(
        item.nome, categoria,
        zone=cfg.brightdata_web_unlocker_zone, token=cfg.brightdata_web_unlocker_token,
        repo=repo, orcamento=OrcamentoMCP(limite_por_job=400),
    )
    ofertas_ml = await buscar_mercadolivre(
        item.nome,
        zone=cfg.brightdata_web_unlocker_zone, token=cfg.brightdata_web_unlocker_token,
        orcamento=OrcamentoMCP(limite_por_job=400),
    )
    ofertas_shopee = await buscar_shopee(
        item.nome,
        zone=cfg.brightdata_web_unlocker_zone, token=cfg.brightdata_web_unlocker_token,
        orcamento=OrcamentoMCP(limite_por_job=400),
    )
    return ofertas_google + ofertas_ml + ofertas_shopee


async def _persistir(
    repo: RepositorioSQL, lista_id: int | None, resultado: ResultadoFiltro,
) -> None:
    """Grava ResultadoBusca/HistoricoPreco (ETAPA 6). Falha aqui NUNCA derruba
    a resposta ao usuario - o resultado ja' foi calculado e e' o que importa
    pra quem pediu a busca; persistencia e' registro historico, nao o produto
    principal (mesma filosofia de resiliencia do orquestrador: uma parte
    degradada nao trava o todo)."""
    if lista_id is None:
        return
    try:
        await repo.salvar(lista_id, resultado.top7_online + resultado.sem_preco)
    except Exception:  # noqa: BLE001 - resiliencia proposital, ver docstring
        log.exception("falha ao persistir resultado da busca (resposta ao usuario segue normal)")


@celery_app.task(name="efraim.executar_busca")
def executar_busca_task(payload: dict) -> dict:
    return asyncio.run(_executar_pipeline(payload))
