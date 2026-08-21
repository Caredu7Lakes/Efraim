from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.domain.models import Escopo


class RegistroIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    senha: str = Field(min_length=8, max_length=255)


class LoginIn(BaseModel):
    email: str
    senha: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UsuarioOut(BaseModel):
    id: int
    email: str


class ItemIn(BaseModel):
    nome: str
    marca: str | None = None
    quantidade: float = 1
    unidade: str = "un"
    qualidade: str | None = None


class BuscaIn(BaseModel):
    produtos: list[ItemIn]
    # Escopo e' o enum de dominio (nao uma string solta): um valor invalido
    # vira 422 direto do FastAPI, em vez de estourar 500 dentro da task
    # (Escopo(payload["escopo"]) so' seria validado ali, tarde demais).
    escopo: Escopo = Escopo.NACIONAL
    cidade: str | None = None
    cep: str | None = None
    lista_id: int | None = None

    @model_validator(mode="after")
    def _cep_obrigatorio_no_local(self) -> BuscaIn:
        # busca local sem CEP nao tem raio de busca preciso pra ancorar -
        # cidade sozinha e' informacao redundante/vaga demais (nao tinhamos
        # criterio nenhum antes; isto fecha a lacuna).
        if self.escopo is Escopo.LOCAL and not self.cep:
            raise ValueError("cep e' obrigatorio quando escopo='local'")
        return self


class ContatoOut(BaseModel):
    whatsapp: list[str] = []
    email: list[str] = []
    telefone: list[str] = []
    form_url: str | None = None


class OfertaOut(BaseModel):
    produto: str
    marca: str | None
    preco_centavos: int | None
    moeda: str
    local: str
    link: str
    pagamento: str | None
    disponibilidade: str
    condicao: str
    frete_centavos: int
    coletado_em: str
    fonte: str
    # None quando a oferta nao tem nenhum contato (a maioria das ofertas com
    # preco publico) - so' preenche pra "sem_preco" tipicamente.
    contato: ContatoOut | None = None
    # preenchido so' pelo Bloco B/local (Google Maps) - None nas demais.
    regiao: str | None = None
    cidade: str | None = None
    uf: str | None = None


class ResultadoProdutoOut(BaseModel):
    produto: str
    categoria: str
    idioma_detectado: str
    # sempre inclui "nacional" (ou "local"); ganha "internacional" quando o
    # roteamento por categoria/idioma decidiu rodar tambem o Bloco D - ver
    # domain/roteamento.py.
    escopo_efetivo: list[str]
    # termo (possivelmente adaptado de portugues) usado nas queries
    # internacionais - None quando este produto nao rodou Bloco D.
    termo_busca_internacional: str | None
    # termo em chines, derivado de termo_busca_internacional - usado nas
    # queries dos sites da China (ver domain/nomenclatura_chinesa.py).
    termo_busca_zh: str | None
    top7_online: list[OfertaOut]
    sem_preco: list[OfertaOut]
    # sem_preco agrupado por regiao (Bloco B) - a busca cobre as 5 regioes
    # do Brasil sem restringir a nenhuma por padrao; a apresentacao divide
    # por regiao pra o usuario comparar (ver domain/classificacao.REGIOES_BR).
    # So' tem chave pras regioes que de fato acharam algo.
    sem_preco_por_regiao: dict[str, list[OfertaOut]] = {}
    total_descartados: int


class ResultadoOut(BaseModel):
    resultados: list[ResultadoProdutoOut]
