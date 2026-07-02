# PhishGuard — developer convenience commands
# Usage: make <target>

# Image name used across all docker targets
IMAGE  := phishguard
TAG    := latest

.PHONY: install lint lint-fix format format-check check test test-fast \
        train train-fast run run-prod clean \
        docker-build docker-run docker-stop docker-logs \
        docker-test docker-train docker-shell docker-clean

# ============================================================================
# Local development
# ============================================================================

## Install the package in editable mode with dev dependencies
install:
	pip install -e ".[dev]"

## Lint with ruff
lint:
	ruff check src/ app/ tests/ scripts/

## Auto-fix lint issues
lint-fix:
	ruff check --fix src/ app/ tests/ scripts/

## Format with black
format:
	black src/ app/ tests/ scripts/

## Check formatting (CI mode — does not modify files)
format-check:
	black --check src/ app/ tests/ scripts/

## Run all checks (lint + format) — mirrors CI
check: lint format-check

## Run full test suite with coverage
test:
	pytest tests/ -v --cov --cov-report=term-missing

## Run only fast unit tests (skips integration tests)
test-fast:
	pytest tests/ --fast -v

## Run only integration tests
test-integration:
	pytest tests/ -m integration -v

## Full training pipeline (downloads data)
train:
	python scripts/train_pipeline.py

## Training pipeline — reuse existing URL files
train-fast:
	python scripts/train_pipeline.py --skip-download

## Start development server
run:
	python run.py

## Start production server (requires SECRET_KEY env var)
run-prod:
	python run.py --prod

## Generate a new SECRET_KEY
secret-key:
	python scripts/generate_secret_key.py

## Remove generated artefacts
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov .coverage
	rm -rf dist build *.egg-info src/*.egg-info

# ============================================================================
# Docker
# ============================================================================

## Build the Docker image
docker-build:
	docker build \
		-f docker/Dockerfile \
		-t $(IMAGE):$(TAG) \
		.

## Run the production container (requires models/ volume populated)
## Usage: make docker-run SECRET_KEY=your-secret
docker-run:
	docker run -d \
		--name phishguard \
		-p 5005:5005 \
		-e SECRET_KEY=$(SECRET_KEY) \
		-v "$(PWD)/models:/app/models" \
		$(IMAGE):$(TAG)
	@echo "PhishGuard running → http://localhost:5005"
	@echo "Logs: make docker-logs"

## Stop and remove the running container
docker-stop:
	docker stop phishguard 2>/dev/null || true
	docker rm phishguard 2>/dev/null || true

## Follow container logs
docker-logs:
	docker logs -f phishguard

## Run the full test suite inside the container
docker-test:
	docker compose \
		-f docker/docker-compose.test.yml \
		run --rm test

## Run the training pipeline inside a container
## Output model is written to the phishguard_models named volume
docker-train:
	docker compose \
		-f docker/docker-compose.yml \
		run --rm train

## Open a shell inside the running container (for debugging)
docker-shell:
	docker exec -it phishguard /bin/bash

## Start dev service with compose (hot-reload)
docker-dev:
	docker compose -f docker/docker-compose.yml up dev

## Start prod service with compose
docker-prod:
	docker compose -f docker/docker-compose.yml up prod

## Remove all PhishGuard images and volumes
docker-clean:
	docker compose -f docker/docker-compose.yml down -v 2>/dev/null || true
	docker rmi $(IMAGE):$(TAG) $(IMAGE):dev 2>/dev/null || true
	@echo "PhishGuard images and volumes removed."
