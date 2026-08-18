"""Cache TTL simples em memoria (v1). Serve a latencia de buscas repetidas.
Redis entra depois pelo mesmo contrato, sem tocar o dominio.
"""

from __future__ import annotations

import time
from typing import Any


class CacheTTL:
    def __init__(self, ttl_segundos: int = 3600) -> None:
        self._ttl = ttl_segundos
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, chave: str) -> Any | None:
        item = self._store.get(chave)
        if not item:
            return None
        expira_em, valor = item
        if time.monotonic() > expira_em:
            self._store.pop(chave, None)
            return None
        return valor

    def set(self, chave: str, valor: Any) -> None:
        self._store[chave] = (time.monotonic() + self._ttl, valor)
