"""Erros especificos de fontes MCP, distintos de falha generica (ETAPA 2 - extensao).

O TIPO do erro importa pro orquestrador: rate limit (429) pede backoff e nova
tentativa respeitando o `Retry-After` do provedor, nao a abertura imediata do
circuit breaker como uma falha de rede comum faria.
"""
from __future__ import annotations


class MCPRateLimitError(Exception):
    """A fonte respondeu com rate limit (HTTP 429 ou equivalente do CLI/MCP).

    `retry_after_s`, quando o provedor informa, e' respeitado antes da proxima
    tentativa; quando ausente, o orquestrador aplica backoff proprio.
    """

    def __init__(self, fonte: str, retry_after_s: float | None = None) -> None:
        self.fonte = fonte
        self.retry_after_s = retry_after_s
        super().__init__(f"rate limit em '{fonte}' (retry_after={retry_after_s}s)")
