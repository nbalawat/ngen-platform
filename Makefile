.PHONY: help bootstrap install lint test test-integration test-e2e test-all coverage \
       infra-up infra-down docker-build kind-up kind-down deploy-local clean

SHELL := /bin/bash
UV := uv
PYTHON := $(UV) run python
PYTEST := $(UV) run pytest

# Default target
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

bootstrap: ## One-command setup: install deps, verify tooling, run tests
	@echo "==> Bootstrapping NGEN Platform..."
	@command -v uv >/dev/null 2>&1 || { echo "Error: uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
	$(MAKE) install
	$(MAKE) lint
	$(MAKE) test
	@echo "==> Bootstrap complete! All tests passing."

install: ## Install all Python dependencies
	$(UV) sync --all-packages --extra dev

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------

lint: ## Run linters (ruff + mypy)
	$(UV) run ruff check .
	$(UV) run ruff format --check .

lint-fix: ## Fix linting issues
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

typecheck: ## Run type checking
	$(UV) run mypy libs/ services/ adapters/ cli/ --ignore-missing-imports

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

test: ## Run all unit tests
	$(PYTEST) libs/ adapters/ services/ cli/ -v --tb=short

test-cov: ## Run tests with coverage
	$(PYTEST) libs/ adapters/ services/ cli/ -v --tb=short \
		--cov=libs --cov=adapters --cov=services --cov=cli \
		--cov-report=term-missing --cov-report=html

test-integration: ## Run integration tests (requires Docker Compose infra)
	$(PYTEST) tests/integration/ -v --tb=short

test-e2e: ## Run end-to-end tests (requires Kind cluster)
	$(PYTEST) tests/e2e/ -v --tb=short

test-load: ## Run load tests (requires Kind cluster)
	@echo "Load tests not yet configured"

test-all: test test-integration test-e2e ## Run all test levels

coverage: test-cov ## Generate coverage report and enforce minimum

# ---------------------------------------------------------------------------
# Local infrastructure (Docker Compose)
# ---------------------------------------------------------------------------

infra-up: ## Start local infrastructure (PostgreSQL, Redis, NATS)
	docker compose -f infrastructure/docker-compose/docker-compose.yaml up -d
	@echo "==> Waiting for services to be healthy..."
	@sleep 3
	@docker compose -f infrastructure/docker-compose/docker-compose.yaml ps

infra-down: ## Stop local infrastructure
	docker compose -f infrastructure/docker-compose/docker-compose.yaml down -v

infra-status: ## Show infrastructure status
	docker compose -f infrastructure/docker-compose/docker-compose.yaml ps

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

SERVICES := tenant-service model-registry model-gateway workflow-engine

docker-build: ## Build Docker images for all services
	@for svc in $(SERVICES); do \
		echo "==> Building $$svc..."; \
		docker build -t ngen/$$svc:latest -f services/$$svc/Dockerfile .; \
	done
	@echo "==> Building mock-llm..."
	@docker build -t ngen/mock-llm:latest -f libs/ngen-mock-llm/Dockerfile .
	@echo "==> All images built."

# ---------------------------------------------------------------------------
# Kubernetes (Kind)
# ---------------------------------------------------------------------------

kind-up: ## Create Kind cluster with ingress
	bash scripts/kind-up.sh

kind-down: ## Destroy Kind cluster
	bash scripts/kind-down.sh

kind-load: ## Load Docker images into Kind cluster
	@for svc in $(SERVICES) mock-llm; do \
		echo "==> Loading ngen/$$svc:latest into Kind..."; \
		kind load docker-image ngen/$$svc:latest --name ngen-platform; \
	done
	@echo "==> All images loaded into Kind."

deploy-infra: ## Deploy PostgreSQL and Redis to Kind cluster
	@echo "==> Deploying PostgreSQL..."
	@helm upgrade --install postgres infrastructure/helm/charts/postgres \
		--namespace ngen-system --create-namespace
	@echo "==> Deploying Redis..."
	@helm upgrade --install redis infrastructure/helm/charts/redis \
		--namespace ngen-system --create-namespace
	@echo "==> Waiting for infra pods..."
	@kubectl wait --for=condition=ready pod -l app=postgres -n ngen-system --timeout=120s
	@kubectl wait --for=condition=ready pod -l app=redis -n ngen-system --timeout=120s
	@echo "==> Infrastructure deployed."

deploy-local: deploy-infra ## Deploy all services to local Kind cluster via Helm
	@for svc in $(SERVICES) mock-llm; do \
		echo "==> Deploying $$svc..."; \
		helm upgrade --install $$svc infrastructure/helm/charts/$$svc \
			--namespace ngen-system --create-namespace; \
	done
	@echo "==> Deploying ingress..."
	@helm upgrade --install ngen-ingress infrastructure/helm/charts/ingress \
		--namespace ngen-system --create-namespace
	@echo "==> All services deployed."
	@kubectl get pods -n ngen-system

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

clean: ## Remove build artifacts and caches
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage coverage.xml dist/ build/
