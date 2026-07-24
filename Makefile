.PHONY: install lint format typecheck test test-docker verify-gold schema check help

##@ Setup

install: ## Install the package with dev dependencies
	pip install -e ".[dev]"

##@ Quality

lint: ## Run ruff lint
	ruff check src tests

format: ## Format code with ruff
	ruff format src tests

typecheck: ## Run mypy
	mypy

test: ## Run unit tests (no Docker)
	pytest -m "not docker" -q

test-docker: ## Run integration tests (requires Docker)
	pytest -m docker -q

check: lint typecheck test ## Run lint, typecheck, and unit tests

##@ reforge

verify-gold: ## Self-verify the tiny sample task
	reforge verify-gold tests/fixtures/tiny-task

schema: ## Write the task JSON Schema to docs/task.schema.json
	reforge schema --output docs/task.schema.json

##@ Help

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make <target>\n"} /^[a-zA-Z_\/-]+:.*?##/ { printf "  %-14s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
