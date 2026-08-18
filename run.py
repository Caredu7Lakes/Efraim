#!/usr/bin/env python3
"""CLI de enforcement/extracao (compat com a concepcao original).

Uso:
  python run.py '{"acao":"extrair_contatos","html":"<html>"}'
  python run.py '{"acao":"filtrar_top7","resultados":[...]}'
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.domain.enforcement import filtrar_top7  # noqa: E402
from app.domain.normalizador import normalizar  # noqa: E402
from app.sourcing.adapters.regex_fallback import extrair_contatos  # noqa: E402


def main(payload: dict) -> dict:
    acao = payload.get("acao")
    if acao == "extrair_contatos":
        return asdict(extrair_contatos(payload.get("html", "")))
    if acao == "filtrar_top7":
        ofertas = [normalizar(r, fonte=r.get("fonte", "cli")) for r in payload["resultados"]]
        filtro = filtrar_top7(ofertas)
        return {
            "top7_online": [asdict(o) for o in filtro.top7_online],
            "sem_preco": [asdict(o) for o in filtro.sem_preco],
            "total_descartados": filtro.total_descartados,
        }
    return {"erro": f"acao desconhecida: {acao}"}


if __name__ == "__main__":
    entrada = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(main(entrada), default=str, ensure_ascii=False, indent=2))
