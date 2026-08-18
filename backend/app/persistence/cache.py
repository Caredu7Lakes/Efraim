"""Cache TTL simples em memoria (v1). Serve a latencia de buscas repetidas E
reduz chamadas pagas ao MCP pela mesma consulta. Redis entra depois pelo
mesmo contrato, sem tocar o dominio.

TTL e' uma decisao de custo x qualidade, nao so de latencia: TTL curto gasta
mais chamada MCP mas mantem preco fresco (o que importa pra um produto que
recomenda "mais barato"); TTL longo economiza chamada as custas de preco
desatualizado. O padrao (`Settings.cache_ttl_s`) favorece frescor sobre
economia — ver `app/config.py`.
"""

from __future__ import annotations

import time
from typing import Any


class CacheTTL:
    def __init__(self, ttl_segundos: int = 900) -> None:
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

    def invalidar(self, chave: str) -> None:
        """Invalidacao manual/pontual (ex.: admin marcou um preco como errado).

        Invalidacao automatica por variacao de preco (via HistoricoPreco) fica
        para quando `RepositorioSQL.salvar` estiver de fato conectado ao fluxo
        de /buscas — hoje esse ponto de persistencia nao e' chamado por
        ninguem no caminho vivo (achado separado, fora deste escopo).
        """
        self._store.pop(chave, None)
