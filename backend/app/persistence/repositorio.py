"""Implementacao de RepositorioBusca (persistencia — ETAPA 6)."""
from __future__ import annotations

from datetime import UTC, datetime

from app.domain.classificacao import normalizar
from app.domain.models import Oferta
from app.persistence.db import sessao
from app.persistence.orm import HistoricoPreco, ResultadoBusca


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
            dias = (datetime.now(UTC) - ant.coletado_em).days
            return {"variacao_pct": round(pct, 2), "dias": dias}
