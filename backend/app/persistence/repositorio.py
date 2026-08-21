"""Implementacao de RepositorioBusca (persistencia — ETAPA 6)."""
from __future__ import annotations

from datetime import UTC, datetime

from app.domain.classificacao import normalizar
from app.domain.models import Oferta
from app.persistence.db import sessao
from app.persistence.orm import HistoricoPreco, ListaCompra, ResultadoBusca, VariacaoBusca


def _obs(o: Oferta) -> str | None:
    if not o.contato:
        return None
    partes = []
    if o.contato.whatsapp:
        partes.append("wpp:" + ",".join(o.contato.whatsapp))
    if o.contato.email:
        partes.append("email:" + ",".join(o.contato.email))
    if o.contato.telefone:
        partes.append("tel:" + ",".join(o.contato.telefone))
    return " | ".join(partes) or None


class RepositorioSQL:
    async def criar_lista(
        self, *, escopo: str, localizacao: str | None, usuario_id: int | None = None
    ) -> int:
        """Cria a ListaCompra que ancora `ResultadoBusca.lista_id` (FK NOT NULL).

        Chamado quando o pedido de busca nao veio com `lista_id` existente
        (hoje o caminho unico, ja' que nao ha' autenticacao de morador/usuario
        conectada ao endpoint `/buscas` ainda — `usuario_id` fica None).
        """
        with sessao() as s:
            lista = ListaCompra(usuario_id=usuario_id, escopo=escopo, localizacao=localizacao)
            s.add(lista)
            s.flush()
            return lista.id

    async def salvar(self, lista_id: int, ofertas: list[Oferta]) -> None:
        with sessao() as s:
            for o in ofertas:
                s.add(ResultadoBusca(
                    lista_id=lista_id,             # OBRIGATORIO
                    produto=o.produto, marca=o.marca,
                    preco_centavos=o.preco_centavos, moeda=o.moeda,
                    local=o.local, link=o.link, fonte=o.fonte,
                    disponibilidade=o.disponibilidade.value,
                    observacoes=_obs(o), coletado_em=o.coletado_em,
                ))
                if o.tem_preco:
                    var = await self.variacao(normalizar(o.produto), o.local, o.preco_centavos)
                    s.add(HistoricoPreco(
                        produto_normalizado=normalizar(o.produto), local=o.local,
                        preco_centavos=o.preco_centavos,
                        variacao_pct=(var or {}).get("variacao_pct"),
                        dias_desde_ultima=(var or {}).get("dias"),
                    ))

    async def variacao(self, produto_normalizado: str, local: str,
                       preco_atual_centavos: int) -> dict | None:
        with sessao() as s:
            ant = (
                s.query(HistoricoPreco)
                .filter_by(produto_normalizado=produto_normalizado, local=local)
                .order_by(HistoricoPreco.coletado_em.desc())
                .first()
            )
            if not ant:
                return None
            base = ant.preco_centavos or 1
            pct = (preco_atual_centavos - base) / base * 100
            # sqlite nao preserva tzinfo na volta (mesmo com DateTime(timezone=True));
            # Postgres preserva. Trata os dois casos assumindo UTC quando naive.
            coletado_em = ant.coletado_em
            if coletado_em.tzinfo is None:
                coletado_em = coletado_em.replace(tzinfo=UTC)
            dias = (datetime.now(UTC) - coletado_em).days
            return {"variacao_pct": round(pct, 2), "dias": dias}

    async def salvar_variacoes_busca(self, categoria: str, variacoes: list[str]) -> None:
        """Upsert por (categoria, variacao) - reaparecer incrementa
        `vezes_encontrada` em vez de duplicar linha (e' o que da' o "as que
        mais aparecem" pedido pelo usuario, 20/08)."""
        with sessao() as s:
            for v in variacoes:
                existente = (
                    s.query(VariacaoBusca).filter_by(categoria=categoria, variacao=v).first()
                )
                if existente:
                    existente.vezes_encontrada += 1
                    existente.atualizado_em = datetime.now(UTC)
                else:
                    s.add(VariacaoBusca(categoria=categoria, variacao=v))

    async def variacoes_mais_frequentes(self, categoria: str, limite: int = 5) -> list[str]:
        with sessao() as s:
            linhas = (
                s.query(VariacaoBusca)
                .filter_by(categoria=categoria)
                .order_by(VariacaoBusca.vezes_encontrada.desc())
                .limit(limite)
                .all()
            )
            return [linha.variacao for linha in linhas]
