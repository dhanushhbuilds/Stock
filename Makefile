PY := backend/.venv/bin

.PHONY: services backend frontend migrate test test-backend test-frontend lint up down

services:          ## start Postgres + Redis containers
	docker compose up -d postgres redis

backend: migrate   ## run API with reload on :8000
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:          ## run Vite dev server on :5173
	cd frontend && npm run dev

migrate:
	cd backend && .venv/bin/alembic upgrade head

test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/pytest -v

test-frontend:
	cd frontend && npm test

lint:
	cd backend && .venv/bin/ruff check app tests alembic/env.py
	cd frontend && npm run lint

up:                ## full stack in Docker (frontend on :5173, API on :8000)
	docker compose --profile app up -d --build

down:
	docker compose --profile app down
