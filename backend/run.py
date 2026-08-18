"""CLI de enforcement/utilidades — compativel com a concepcao do agente.

    python run.py '{"acao":"filtrar_top7","resultados":[...]}'
    python run.py '{"acao":"extrair_contatos","html":"<html>"}'

Mantido como interface estavel para o agente; a logica vive em app.sourcing.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime

from app.domain.models import Condicao, Disponibilidade, Oferta
from app.sourcing.contatos import extrair_contatos
from app.sourcing.filtro import filtrar_top7


def _oferta_de_dict(d: dict) -> Oferta:
    return Oferta(
        produto=d.get("produto", ""), local=d.get("local", ""),
        link=d.get("link", ""), fonte=d.get("fonte", "cli"),
        coletado_em=datetime.now(UTC), marca=d.get("marca"),
        preco_centavos=d.get("preco_centavos"), moeda=d.get("moeda", "BRL"),
        pagamento=d.get("pagamento"),
        disponibilidade=Disponibilidade(d.get("disponibilidade", "desconhecida")),
        condicao=Condicao(d.get("condicao", "desconhecida")),
        frete_centavos=d.get("frete_centavos", 0),
    )


def main(raw: str) -> None:
    pedido = json.loads(raw)
    acao = pedido.get("acao")

    if acao == "filtrar_top7":
        ofertas = [_oferta_de_dict(x) for x in pedido.get("resultados", [])]
        r = filtrar_top7(ofertas)
        print(json.dumps({
            "top7_online": [_serial(o) for o in r.top7_online],
            "sem_preco": [_serial(o) for o in r.sem_preco],
            "total_descartados": r.total_descartados,
        }, ensure_ascii=False))
    elif acao == "extrair_contatos":
        c = extrair_contatos(pedido.get("html", ""))
        print(json.dumps(asdict(c), ensure_ascii=False))
    else:
        raise SystemExit(f"acao desconhecida: {acao!r}")


def _serial(o: Oferta) -> dict:
    return {
        "produto": o.produto, "marca": o.marca, "preco_centavos": o.preco_centavos,
        "moeda": o.moeda, "local": o.local, "link": o.link,
        "disponibilidade": o.disponibilidade.value, "fonte": o.fonte,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("uso: python run.py '<json>'")
    main(sys.argv[1])
