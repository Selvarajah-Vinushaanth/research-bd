# ============================================
# Makefile - AI Research Assistant Backend
# ============================================

.PHONY: help install dev test lint format docker-up docker-down db-push db-generate migrate clean

PYTHON := python3

help: ## Show this help message
	@echo "AI Research Assistant - Backend"
	@echo "=============================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---- Setup ----

install: ## Install production dependencies
	poetry install --only main

install-dev: ## Install all dependencies (incl. dev)
	poetry install

setup: install-dev db-generate ## Full local setup (install + generate Prisma)
	@echo "✅ Setup complete. Copy .env.example to .env and update values."

# ---- Development ----

dev: ## Run dev server with auto-reload
	poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-worker: ## Run Celery worker in dev mode
	poetry run celery -A app.workers.celery_worker:celery_app worker --loglevel=info --pool=solo -Q celery,paper_processing,embedding,ai_tasks

dev-beat: ## Run Celery beat scheduler in dev mode
	poetry run celery -A app.workers.celery_worker:celery_app beat --loglevel=info

dev-flower: ## Run Flower monitoring dashboard
	poetry run celery -A app.workers.celery_worker:celery_app flower --port=5555

# ---- Database ----

db-generate: ## Generate Prisma client
	poetry run prisma generate

db-push: ## Push schema to database (dev only)
	poetry run prisma db push

db-migrate: ## Create and apply migration
	poetry run prisma migrate dev --name $(name)

db-deploy: ## Apply migrations (production)
	poetry run prisma migrate deploy

db-studio: ## Open Prisma Studio
	npx prisma studio

db-reset: ## Reset database (WARNING: destroys data)
	poetry run prisma migrate reset --force

db-seed: ## Seed database with sample data
	poetry run python scripts/seed.py

# ---- Testing ----

test: ## Run all tests
	poetry run pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage
	poetry run pytest tests/ -v --cov=app --cov-report=html --cov-report=term-missing

test-unit: ## Run unit tests only
	poetry run pytest tests/unit/ -v --tb=short

test-integration: ## Run integration tests only
	poetry run pytest tests/integration/ -v --tb=short

test-api: ## Run API tests only
	poetry run pytest tests/api/ -v --tb=short

# ---- Code Quality ----

lint: ## Run linter
	poetry run ruff check app/ tests/

lint-fix: ## Fix linting issues
	poetry run ruff check --fix app/ tests/

format: ## Format code
	poetry run ruff format app/ tests/

type-check: ## Run type checking
	poetry run mypy app/ --ignore-missing-imports

quality: lint type-check ## Run all quality checks

# ---- Docker ----

docker-up: ## Start all services with Docker Compose
	docker compose up -d --build

docker-down: ## Stop all services
	docker compose down

docker-logs: ## View logs from all services
	docker compose logs -f

docker-logs-backend: ## View backend logs
	docker compose logs -f backend

docker-logs-worker: ## View worker logs
	docker compose logs -f celery_worker

docker-restart: ## Restart all services
	docker compose restart

docker-clean: ## Stop and remove volumes (WARNING: destroys data)
	docker compose down -v --remove-orphans

docker-rebuild: ## Rebuild and restart
	docker compose down
	docker compose up -d --build

# ---- Production ----

prod-build: ## Build production Docker image
	docker build -t research-assistant-backend:latest .
	docker build -t research-assistant-worker:latest -f Dockerfile.worker .

prod-run: ## Run production server
	poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --loop uvloop

# ---- GCP ----

gcp-build: ## Build and push to GCP Artifact Registry
	gcloud builds submit --tag gcr.io/$$(gcloud config get-value project)/research-backend:latest .

gcp-deploy: ## Deploy to Cloud Run
	gcloud run deploy research-backend \
		--image gcr.io/$$(gcloud config get-value project)/research-backend:latest \
		--platform managed \
		--region us-central1 \
		--allow-unauthenticated \
		--memory 2Gi \
		--cpu 2 \
		--max-instances 10 \
		--set-env-vars "APP_ENV=production"

# ---- Utilities ----

clean: ## Clean generated files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage .mypy_cache dist build *.egg-info

logs-clean: ## Clean log files
	find . -name "*.log" -delete 2>/dev/null || true

env-check: ## Verify environment setup
	@echo "Python: $$($(PYTHON) --version)"
	@echo "Poetry: $$(poetry --version 2>/dev/null || echo 'Not installed')"
	@echo "Prisma: $$(poetry run prisma --version 2>/dev/null || echo 'Not installed')"
	@echo "Docker: $$(docker --version 2>/dev/null || echo 'Not installed')"
	@echo "Redis: $$(redis-cli --version 2>/dev/null || echo 'Not installed')"
