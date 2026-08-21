"""Tipos de dominio do Efraim.

`Oferta` e o schema unico: TODO adapter/fonte normaliza seu resultado
para este DTO antes de qualquer comparacao. E o que elimina duplicacao
de logica de extracao por site.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Escopo(str, Enum):
    LOCAL = "local"
    NACIONAL = "nacional"
    INTERNACIONAL = "internacional"


class Disponibilidade(str, Enum):
    EM_ESTOQUE = "em_estoque"
    INDISPONIVEL = "indisponivel"
    DESCONHECIDA = "desconhecida"


class Condicao(str, Enum):
    NOVO = "novo"
    USADO = "usado"
    RECONDICIONADO = "recondicionado"
    DESCONHECIDA = "desconhecida"


@dataclass(frozen=True)
class Contato:
    whatsapp: tuple[str, ...] = ()
    email: tuple[str, ...] = ()
    telefone: tuple[str, ...] = ()
    form_url: str | None = None

    def vazio(self) -> bool:
        return not (self.whatsapp or self.email or self.telefone or self.form_url)


@dataclass(frozen=True)
class Oferta:
    """Resultado normalizado de uma fonte de preco ou de comercio local."""
    produto: str
    local: str
    link: str
    fonte: str                        # nome do adapter (auditoria)
    coletado_em: datetime
    marca: str | None = None
    preco_centavos: int | None = None  # None => vai para a secao de cotacao
    moeda: str = "BRL"
    pagamento: str | None = None
    contato: Contato | None = None
    disponibilidade: Disponibilidade = Disponibilidade.DESCONHECIDA
    condicao: Condicao = Condicao.DESCONHECIDA
    frete_centavos: int = 0
    # preenchido pelo Bloco B (regional/Google Maps) - a busca cobre as 5
    # regioes do Brasil sem restringir a nenhuma por padrao; None quando a
    # oferta nao veio de uma busca regional (ex.: marketplace, Bloco C).
    regiao: str | None = None
    cidade: str | None = None
    uf: str | None = None
    # id estavel do anuncio NA FONTE de origem (ex.: "MLB3882572605" no
    # Mercado Livre) - None quando a fonte nao expoe um id assim ou nao foi
    # extraido. Usado pra deduplicar o MESMO anuncio quando ele chega por 2
    # caminhos diferentes (ex.: actor Apify E busca direta do mesmo
    # marketplace - achado 20/08, revisao pedida pelo usuario). Generico
    # (nao amarrado a "MLB") pra' servir qualquer fonte que tenha id
    # proprio no futuro (ASIN da Amazon, itemId do eBay etc.).
    id_externo: str | None = None
    # quantas unidades `preco_centavos` realmente cobre - 1 (preco unitario)
    # por padrao; > 1 quando a oferta e' um kit/lote (ex.: "Kit 6
    # Conectores"). Correcao do usuario (20/08): comparar/descartar ofertas
    # pelo preco BRUTO do anuncio deixava um kit barato vencer um preco
    # unitario real so' por ter numero absoluto menor - a comparacao tem
    # que ser por CUSTO POR UNIDADE (ver `custo_unitario_centavos` abaixo e
    # `sourcing.filtro.filtrar_top7`).
    unidades_no_lote: int = 1

    @property
    def tem_preco(self) -> bool:
        return self.preco_centavos is not None

    @property
    def custo_total_centavos(self) -> int | None:
        if self.preco_centavos is None:
            return None
        return self.preco_centavos + self.frete_centavos

    @property
    def custo_unitario_centavos(self) -> int | None:
        """Custo total (preco + frete) dividido pelas unidades do lote -
        base real de comparacao entre ofertas (ver `unidades_no_lote`)."""
        total = self.custo_total_centavos
        if total is None:
            return None
        return round(total / self.unidades_no_lote)


@dataclass(frozen=True)
class ItemProduto:
    nome: str
    marca: str | None = None
    quantidade: float = 1
    unidade: str = "un"
    qualidade: str | None = None


@dataclass(frozen=True)
class Localizacao:
    cep: str | None = None
    cidade: str | None = None
    uf: str | None = None
    raio_km: int = 36


@dataclass(frozen=True)
class ConsultaProduto:
    """Entrada de uma PriceSource."""
    item: ItemProduto
    escopo: Escopo
    categoria: str
    queries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConsultaLocal:
    """Entrada de uma LocalBusinessSource."""
    item: ItemProduto
    categoria: str
    pontos_venda: list[str]
    localizacao: Localizacao
    queries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Fornecedor:
    nome: str
    cidade_regiao: str | None = None
    contato: Contato | None = None
    link: str | None = None


@dataclass(frozen=True)
class ResultadoFiltro:
    """Saida do enforcement filtrar_top7."""
    top7_online: list[Oferta]
    sem_preco: list[Oferta]
    total_descartados: int
