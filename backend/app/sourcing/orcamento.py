"""Orcamento de chamadas MCP por job (ETAPA 2 - extensao).

Nao e' rate limiting do lado do provedor (isso o circuit breaker + backoff de
429 em `orquestrador.py` cobrem) - e' controle de CUSTO: um teto que corta a
busca antes dela continuar gastando, mesmo que a fonte esteja saudavel e
respondendo rapido. Sem isso, uma categoria com muitos pontos de venda pode
gerar dezenas de chamadas pagas sem nenhum freio.

O teto e' por execucao de job (uma instancia de `OrcamentoMCP` por chamada a
`Orquestrador.executar`), nao global/singleton - jobs concorrentes nao
disputam o mesmo contador.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class OrcamentoExcedidoError(Exception):
    """Levantado quando uma chamada extra estouraria o teto do job.

    Nao e' falha da fonte (o circuit breaker nao deve abrir por causa disso -
    foi uma decisao nossa de parar, nao um problema do provedor).
    """

    def __init__(self, bloco: str, limite: int) -> None:
        self.bloco = bloco
        self.limite = limite
        super().__init__(
            f"orcamento de chamadas MCP esgotado no bloco '{bloco}' (limite={limite}/job)"
        )


@dataclass
class OrcamentoMCP:
    """Contador de chamadas MCP gastas nesta execucao, com teto configuravel."""

    limite_por_job: int
    _usadas: dict[str, int] = field(default_factory=dict)

    def total_usado(self) -> int:
        return sum(self._usadas.values())

    def usadas_no_bloco(self, bloco: str) -> int:
        return self._usadas.get(bloco, 0)

    def registrar_chamada(self, bloco: str) -> None:
        """Conta uma chamada contra o teto. Levanta se isso estourasse o limite."""
        if self.total_usado() >= self.limite_por_job:
            raise OrcamentoExcedidoError(bloco, self.limite_por_job)
        self._usadas[bloco] = self._usadas.get(bloco, 0) + 1
