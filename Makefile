.PHONY: setup env test lint run worker seed db-up db-down redis-up migrate

PY=.venv/bin/python
PIP=.venv/bin/pip

setup:            ## cria venv e instala dependencias
	python3 -m venv .venv
	$(PIP) install -U pip
	$(PIP) install -r backend/requirements.txt
	@echo "OK. Ative com: source .venv/bin/activate"

test:             ## roda os testes
	cd backend && ../.venv/bin/pytest -q

lint:             ## ruff
	.venv/bin/ruff check backend

run:              ## sobe a API em http://localhost:8000
	cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000

worker:           ## sobe o worker Celery (precisa de CELERY_TASK_EAGER=false + redis-up)
	cd backend && ../.venv/bin/celery -A app.jobs.celery_app worker --loglevel=info

seed:             ## seed idempotente (papeis, admin, categorias)
	cd backend && ../.venv/bin/python -m scripts.seed_dev

db-up:            ## sobe o Postgres via docker
	docker compose up -d db

redis-up:         ## sobe o Redis (broker/backend do Celery) via docker
	docker compose up -d redis

db-down:
	docker compose down

migrate:          ## gera revisao alembic (autogenerate)
	cd backend && ../.venv/bin/alembic revision --autogenerate -m "$(m)"
