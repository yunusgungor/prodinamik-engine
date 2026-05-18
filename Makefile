# ──────────────────────────────────────────────────
# Prodinamik Engine — Makefile
# ──────────────────────────────────────────────────
# Usage:
#   make          # dev install (default)
#   make test     # run tests
#   make lint     # ruff check
#   make docker   # build production image
#   make ci       # Docker CI pipeline
# ──────────────────────────────────────────────────

.DEFAULT_GOAL := install

PACKAGE := prodinamik-engine
IMAGE   := ghcr.io/yunusgungor/$(PACKAGE)
TAG     := latest

# ── Development ──

install:  ## 📦 Install package in dev mode
	pip install -e ".[dev]"

test:  ## 🧪 Run test suite
	python -m pytest tests/ -v --tb=short -x --no-header

test-all:  ## 🧪 Run all tests (no fail-fast)
	python -m pytest tests/ -v --tb=short --no-header

test-coverage:  ## 📊 Run tests with coverage report
	pip install -e ".[dev]"
	python -m pytest tests/ --tb=short -x --no-header \
		--cov=engine --cov=profiles --cov=adapters --cov-report=term-missing

lint:  ## 🔍 Run ruff linter
	pip install ruff
	python -m ruff check engine/ profiles/ adapters/
	python -m ruff format --check engine/ profiles/ adapters/ || echo "⚠️ Format check warnings"

clean:  ## 🧹 Clean build artifacts
	rm -rf dist/ build/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true

full-ci: test lint  ## 🔄 Run full CI pipeline locally

# ── Docker ──

docker:  ## 🐳 Build production image
	docker build --target production -t $(IMAGE):$(TAG) .

docker-test:  ## 🐳 Build and run tests in Docker
	docker compose --profile ci build
	docker compose --profile ci run --rm ci

docker-lint:  ## 🐳 Build and run lint in Docker
	docker compose --profile ci run --rm lint

docker-all: docker docker-test docker-lint  ## 🐳 Full Docker pipeline

docker-shell:  ## 🐳 Start interactive shell in container
	docker compose --profile dev run --rm shell

docker-push: docker  ## 📤 Push image to registry
	docker push $(IMAGE):$(TAG)

docker-tag-version:  ## 🏷️ Tag version from pyproject.toml
	docker tag $(IMAGE):$(TAG) $(IMAGE):$(shell python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")

# ── Release ──

build: clean  ## 📦 Build distribution packages
	pip install build
	python -m build

publish: build  ## 📤 Publish to PyPI (requires API token)
	pip install twine
	twine upload dist/*

publish-test: build  ## 📤 Publish to TestPyPI
	pip install twine
	twine upload --repository testpypi dist/*

# ── Help ──

help:  ## 📖 Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: install test test-all test-coverage lint clean full-ci \
	docker docker-test docker-lint docker-all docker-shell docker-push docker-tag-version \
	build publish publish-test help
