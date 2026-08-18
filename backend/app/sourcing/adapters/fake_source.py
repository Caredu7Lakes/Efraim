"""Fakes deterministicos: rodam o pipeline inteiro sem rede.
Usados em dev (EFRAIM_FONTE=fake) e nos testes.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.domain.models import (
    Condicao,
    ConsultaLocal,
    ConsultaProduto,
    Contato,
    Disponibilidade,
    Oferta,
)


def _agora() -> datetime:
    return datetime.now(UTC)


class FakePriceSource:
    nome = "fake-price"

    async def buscar(self, consulta: ConsultaProduto) -> list[Oferta]:
        n = consulta.item.nome
        return [
            Oferta(produto=n, marca="ACME", preco_centavos=1990, local="Loja Alpha",
                   link="https://exemplo.com/a", fonte=self.nome, coletado_em=_agora(),
                   disponibilidade=Disponibilidade.EM_ESTOQUE, condicao=Condicao.NOVO,
                   pagamento="pix/cartao"),
            Oferta(produto=n, marca="ACME", preco_centavos=1550, local="Loja Beta",
                   link="https://exemplo.com/b", fonte=self.nome, coletado_em=_agora(),
                   disponibilidade=Disponibilidade.EM_ESTOQUE, condicao=Condicao.NOVO),
            Oferta(produto=n, marca="ACME", preco_centavos=1200, local="Loja Gama (usado)",
                   link="https://exemplo.com/c", fonte=self.nome, coletado_em=_agora(),
                   disponibilidade=Disponibilidade.EM_ESTOQUE, condicao=Condicao.USADO),
        ]


class FakeLocalSource:
    nome = "fake-local"

    async def buscar(self, consulta: ConsultaLocal) -> list[Oferta]:
        n = consulta.item.nome
        return [
            Oferta(produto=n, preco_centavos=None, local="Distribuidora Local",
                   link="https://exemplo.com/dist", fonte=self.nome, coletado_em=_agora(),
                   contato=Contato(whatsapp=("5511999998888",), email=("vendas@dist.com.br",))),
        ]
