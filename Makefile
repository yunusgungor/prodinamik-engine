# ──────────────────────────────────────────────────
# Prodinamik Engine — Makefile
# ──────────────────────────────────────────────────
# Usage:
#   make          # Dev install (default target)
#   make help     # Show all available targets
#   make install  # pip install -e ".[dev]"
#   make test     # Run test suite
#   make lint     # Ruff check + format check
#   make all      # Full pipeline: lint → typecheck → test → coverage
# ──────────────────────────────────────────────────

.DEFAULT_GOAL := install

PACKAGE := prodinamik-engine
IMAGE   := ghcr.io/yunusgungor/$(PACKAGE)
TAG     := latest

# ── Variables ──

PYTHON   := python3
PIP      := $(PYTHON) -m pip
PYTEST   := $(PYTHON) -m pytest
RUFF     := $(PYTHON) -m ruff
MYPY     := $(PYTHON) -m mypy
BLACK    := $(PYTHON) -m black
MKDOCS   := $(PYTHON) -m mkdocs

# Source directories to check — update when adding new packages
SRC_DIRS := engine profiles adapters validators

# ── Help ──

help:  ## 📖 Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Installation ──

install:  ## 📦 Install package in development mode
	$(PIP) install -e ".[dev]"

# ── Testing ──

test:  ## 🧪 Run test suite with verbose output
	$(PYTEST) tests/ -v --tb=short -x --no-header

test-all:  ## 🧪 Run all tests (no fail-fast)
	$(PYTEST) tests/ -v --tb=short --no-header

test-coverage:  ## 📊 Run tests with coverage report
	$(PIP) install -e ".[dev]"
	$(PYTEST) tests/ --tb=short -x --no-header \
		--cov=engine --cov=profiles --cov=adapters --cov-report=term-missing

# ── Linting & Formatting ──

lint:  ## 🔍 Run ruff linter and format check
	$(RUFF) check $(SRC_DIRS)

format:  ## ✨ Auto-format code with black
	$(BLACK) $(SRC_DIRS)

format-check:  ## 🔍 Check formatting without modifying
	$(BLACK) --check $(SRC_DIRS) || (echo "⚠️  Run 'make format' to fix"; exit 1)

typecheck:  ## 🧹 Run mypy type checker
	$(MYPY) $(SRC_DIRS) || echo "⚠️  Type checking found issues"

# ── Cleanup ──

clean:  ## 🧹 Clean build artifacts, caches, and temporary files
	rm -rf dist/ build/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .coverage -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	rm -f .coverage coverage.xml

# ── Documentation ──

docs:  ## 📚 Build MkDocs documentation
	$(MKDOCS) build --clean

# ── Docker ──

docker:  ## 🐳 Build production Docker image
	docker build --target production -t $(IMAGE):$(TAG) .

docker-test:  ## 🐳 Build and run tests in Docker
	docker compose --profile ci build
	docker compose --profile ci run --rm ci

docker-lint:  ## 🐳 Run lint in Docker
	docker compose --profile ci run --rm lint

docker-all: docker docker-test docker-lint  ## 🐳 Full Docker pipeline

docker-shell:  ## 🐳 Start interactive shell in container
	docker compose --profile dev run --rm shell

docker-push: docker  ## 📤 Push image to container registry
	docker push $(IMAGE):$(TAG)

docker-tag-version:  ## 🏷️ Tag image with version from pyproject.toml
	docker tag $(IMAGE):$(TAG) $(IMAGE):$(shell $(PYTHON) -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])" 2>/dev/null || echo "unknown")

# ── Release ──

build: clean  ## 📦 Build distribution packages
	$(PIP) install build
	$(PYTHON) -m build

publish: build  ## 📤 Publish to PyPI (requires API token)
	$(PIP) install twine
	twine upload dist/*

publish-test: build  ## 📤 Publish to TestPyPI
	$(PIP) install twine
	twine upload --repository testpypi dist/*

# ── Full Pipeline ──

all:  ## 🔄 Run full CI pipeline: lint → typecheck → test → coverage
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) test
	$(MAKE) test-coverage

# ── Legacy alias (backward compatibility) ──

full-ci: test lint  ## 🔄 (legacy) Run full CI pipeline locally

# ── Phony targets ──

.PHONY: help install test test-all test-coverage \
	lint format format-check typecheck clean docs \
	docker docker-test docker-lint docker-all docker-shell \
	docker-push docker-tag-version \
	build publish publish-test all full-ci
