"""ETAPA 3 — extracao de contatos (fallback deterministico do run.py).

O adapter Bright Data prefere `extract` (IA) para contatos; esta funcao
regex e o fallback local, sem rede, e a base dos testes.
"""
from __future__ import annotations

import re

from app.domain.models import Contato

_WHATSAPP = [
    re.compile(r"wa\.me/(\+?\d{10,15})"),
    re.compile(r"api\.whatsapp\.com/send\?phone=(\+?\d{10,15})"),
    re.compile(r"whatsapp[:\s]*\+?(?:55)?\s*(\(?\d{2}\)?\s*9?\d{4}[-\s]?\d{4})", re.I),
]
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_TEL = re.compile(r"\(?\d{2}\)?[\s-]?9?\d{4}[\s-]?\d{4}")
_FORM = re.compile(r'<form[^>]*action=["\']([^"\']+)["\']', re.I)


def _limpar_num(s: str) -> str:
    return re.sub(r"\D", "", s)


def extrair_contatos(html: str) -> Contato:
    whats: set[str] = set()
    for pat in _WHATSAPP:
        for m in pat.findall(html):
            num = _limpar_num(m if isinstance(m, str) else "".join(m))
            if 10 <= len(num) <= 15:
                whats.add(num)

    emails = {e.lower() for e in _EMAIL.findall(html)}
    tels = {_limpar_num(t) for t in _TEL.findall(html)}
    tels = {t for t in tels if 10 <= len(t) <= 11}

    form_m = _FORM.search(html)
    return Contato(
        whatsapp=tuple(sorted(whats)),
        email=tuple(sorted(emails)),
        telefone=tuple(sorted(tels)),
        form_url=form_m.group(1) if form_m else None,
    )
