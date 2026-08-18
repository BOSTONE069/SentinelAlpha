.PHONY: api web test build seed alpaca-test migrate migration-check stack

api:
	cd apps/api && uvicorn app.main:app --reload

web:
	cd apps/web && npm run dev

test:
	cd apps/api && pytest -q
	cd apps/web && npm run typecheck

build:
	cd apps/web && npm run build

seed:
	cd apps/api && python ../../scripts/seed_demo.py

alpaca-test:
	python scripts/test_alpaca.py

migrate:
	cd apps/api && alembic upgrade head

migration-check:
	cd apps/api && alembic check

stack:
	docker compose up --build
