# Convenience targets. Run from the dashboard/ folder: `make dev`, `make demo`, `make test`.
.PHONY: dev demo stop test test-backend test-frontend test-integration build

dev:            ## start with real data (dashboard/.env)
	./start.sh

demo:           ## start with synthetic data
	DEMO=1 ./start.sh

stop:
	./stop.sh

test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/pip install -q -r requirements-dev.txt && .venv/bin/pytest

test-integration: ## needs Docker
	cd backend && ./scripts/integration-test.sh

test-frontend:
	cd frontend && npm ci --no-audit --no-fund && npx tsc --noEmit && npx vitest run

build:
	cd frontend && npm run build
