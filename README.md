# Efraim — moshe1.8

Agente de pesquisa de preços e fornecedores para qualquer usuário no Brasil
(nacional), com bloco internacional (EUA + China) previsto. Web data via
**MCP (Bright Data)** atrás de portas; enforcement do ranking em Python.

Arquitetura completa e organograma: [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md).

## Requisitos
- Python 3.11+
- (opcional) Docker, para o Postgres de produção
- VSCode com as extensões recomendadas (`.vscode/extensions.json`)

## Setup rápido
```bash
make setup                 # cria .venv e instala dependências
cp backend/.env.example backend/.env
make seed                  # papéis, admin e categorias (idempotente)
make test                  # suíte de testes (roda com fontes fake, sem rede)
make run                   # API em http://localhost:8000  (/docs para o Swagger)
```

Sem `make` (Windows PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
copy backend\.env.example backend\.env
cd backend
..\.venv\Scripts\python -m scripts.seed_dev
..\.venv\Scripts\pytest -q
..\.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

## Fluxo de uso da API
`/buscas` exige autenticação — cada busca e cada resultado ficam presos ao
usuário que os criou (isolamento lógico, não banco separado por usuário).

```bash
# registra o usuário (uma vez)
curl -X POST localhost:8000/auth/registrar -H 'content-type: application/json' \
  -d '{"email":"voce@exemplo.com","senha":"uma-senha-com-8+"}'

# loga -> devolve access_token (JWT, válido por JWT_EXPIRA_MINUTOS)
TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"email":"voce@exemplo.com","senha":"uma-senha-com-8+"}' | jq -r .access_token)

# dispara uma busca (job assíncrono) -> devolve job_id
curl -X POST localhost:8000/buscas -H 'content-type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"produtos":[{"nome":"conector jack P10 estereo"}],"escopo":"nacional"}'

# consulta o resultado (Top 7 + sem preço) — só o dono do job vê (404 pra outro usuário)
curl localhost:8000/buscas/<job_id> -H "Authorization: Bearer $TOKEN"
```

## Estrutura
```
efraim/
├─ .vscode/                 # settings, launch, extensões
├─ docs/ARQUITETURA.md      # documentação + organograma (Mermaid)
├─ docker-compose.yml       # Postgres
├─ Makefile
└─ backend/
   ├─ app/
   │  ├─ domain/            # Oferta (DTO único), classificação + queries
   │  ├─ sourcing/          # ports, orquestrador, filtro (enforcement), contatos
   │  │  └─ adapters/       # bright data, whatsapp, fakes, factory
   │  ├─ persistence/       # orm, db, repositório
   │  ├─ jobs/              # runner assíncrono
   │  └─ api/               # rotas FastAPI
   ├─ scripts/seed_dev.py   # seed idempotente (admin/RBAC/categorias)
   ├─ migrations/           # Alembic
   ├─ tests/                # filtro, contatos, orquestrador
   └─ run.py                # CLI: filtrar_top7 / extrair_contatos
```

## Trocar fake -> Bright Data
1. Instale o CLI: `curl -fsSL https://cli.brightdata.com/install.sh | bash` e `bdata login`.
2. No `.env`: `EFRAIM_FONTE=brightdata` (e `BRIGHTDATA_API_KEY` se usar o MCP remoto).
3. Implemente os `TODO(bright-data)` em `app/sourcing/adapters/brightdata_mcp.py`
   (mapa Bloco→ferramenta na docstring). O restante do pipeline não muda.

## Convenções
- **Nada de admin/RBAC por SQL ad-hoc** — só via `scripts/seed_dev.py` (idempotente, versionado).
- **`filtrar_top7` é o ponto único de ranking.** Não reordenar fora dele.
- **Todo adapter devolve `Oferta`.** Normalização mora no adapter.
