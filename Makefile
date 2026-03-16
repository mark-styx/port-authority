.PHONY: help install dev test lint format check clean build release

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install the package
	pip install -e .

dev: ## Install development dependencies
	pip install -e ".[dev]"
	pre-commit install

test: ## Run tests
	pytest

test-cov: ## Run tests with coverage report
	pytest --cov=port_authority --cov-report=term-missing --cov-report=html

lint: ## Run linting
	ruff check

format: ## Format code
	ruff format

type-check: ## Run type checking
	mypy src

check: lint type-check test ## Run all checks (lint, type-check, test)

pre-commit: ## Run pre-commit hooks on all files
	pre-commit run --all-files

clean: ## Remove build artifacts and cache files
	rm -rf build/
	rm -rf dist/
	rm -rf .eggs/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf coverage.xml
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete
	find . -type f -name '*.egg' -delete
	find . -type f -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true

build: clean ## Build the package
	python -m build

release: check build ## Run checks and build for release
	@echo "Package built successfully. Ready to publish to PyPI."
	@echo "To publish: twine upload dist/*"

serve: ## Start the port-authority server
	port-authority serve

status: ## Show server status
	port-authority status
