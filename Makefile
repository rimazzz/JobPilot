# JobPilot developer tasks.
# Usage: `make <target>`. Requires Python 3.11+ and a POSIX shell (Git Bash/WSL on Windows).

.DEFAULT_GOAL := help
PYTHON ?= python

.PHONY: help install install-browsers dev lint format typecheck test test-cov run cli docker-build docker-up docker-down clean

help: ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Install the package with dev + openai extras (editable).
	$(PYTHON) -m pip install -e ".[dev,openai]"

install-browsers: ## Download the Playwright Chromium browser.
	$(PYTHON) -m playwright install chromium

dev: install install-browsers ## Full local dev setup.

lint: ## Run ruff lint checks.
	ruff check src tests

format: ## Auto-format with ruff.
	ruff format src tests
	ruff check --fix src tests

typecheck: ## Run mypy static type checks.
	mypy src

test: ## Run the test suite.
	pytest

test-cov: ## Run tests with a coverage report.
	pytest --cov=jobpilot --cov-report=term-missing

run: ## Start the FastAPI server (reload).
	uvicorn jobpilot.main:app --reload --host 0.0.0.0 --port 8000

cli: ## Run a demo application end-to-end from the CLI (uses sample data).
	jobpilot run --candidate data/sample_candidate.json --goal "Senior Python engineer, remote"

docker-build: ## Build the Docker image.
	docker build -t jobpilot:latest .

docker-up: ## Start the stack with docker-compose.
	docker compose up --build

docker-down: ## Stop the docker-compose stack.
	docker compose down

clean: ## Remove caches and build artifacts.
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
