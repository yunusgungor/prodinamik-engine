# Contributing

Welcome to the Prodinamik Engine project! We appreciate your interest in contributing. This guide covers everything you need to know to set up your development environment, write code, run tests, and submit changes.

**Project:** Prodinamik Engine v1.3  
**Repository:** <https://github.com/yunusgungor/prodinamik-engine>  
**License:** See [LICENSE](../license.md)

---

## Table of Contents

- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Code Style & Linting](#code-style-linting)
- [Pull Request Workflow](#pull-request-workflow)
- [Documentation](#documentation)
- [Release Process](#release-process)

---

## Development Setup

### Prerequisites

- Python 3.10+
- Git
- Make (optional, for convenience targets)
- Virtual environment tool (venv, virtualenv, or conda)

### Step 1: Clone the Repository

```bash
git clone https://github.com/yunusgungor/prodinamik-engine.git
cd prodinamik-engine
```

### Step 2: Create a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows
```

### Step 3: Install Development Dependencies

```bash
# Core dependencies
pip install -e .

# Development dependencies
pip install -e ".[dev]"

# Or use the Makefile shortcut
make install-dev
```

The `[dev]` extras include:

| Package | Version | Purpose |
|---------|---------|---------|
| pytest | ≥7.0 | Test runner |
| pytest-asyncio | ≥0.21 | Async test support |
| pytest-cov | ≥4.0 | Code coverage |
| black | ≥23.0 | Code formatter |
| isort | ≥5.12 | Import sorter |
| ruff | ≥0.1 | Fast Python linter |
| tox | ≥4.0 | Multi-env test runner |
| mkdocs | ≥1.5 | Documentation builder |
| mkdocs-material | ≥9.0 | Documentation theme |

### Step 4: Verify Setup

```bash
python -c "import engine; print(engine.__version__)"
# Should print version without errors

make test  # or python -m pytest tests/ -v
```

---

## Running Tests

### Test Structure

Tests are located in the `tests/` directory, organized by development phase:

| File | Test Count | Coverage Area |
|------|-----------|---------------|
| `test_integration.py` | 7 | Core engine fundamentals |
| `test_phase2.py` | 8 | EventStore, Degradation, Safety, Cache |
| `test_phase3.py` | 6 | Cost, Budget, Raft, CRDT |
| `test_phase4.py` | 6 | DebugCLI, Registry, Health Dashboard |
| `test_phase5.py` | 6 | Profiles, Migration, Cross-Profile |
| `test_phase6.py` | 8 | AsyncEngine, Hooks, Timeout, Shutdown |
| `test_phase7.py` | 27 | Shell, Scaffold, Benchmarks, CLI |
| `test_phase8.py` | 31 | Metrics, Dashboard, Audit, CLI |
| `test_phase9.py` | 35 | Auth, Rate Limiter, Server, Raft, CLI |
| `test_phase10.py` | 53 | Chaos + Monitoring + Alert |
| **Total** | **~177** | **All features** |

### Running Tests

```bash
# Run all tests
make test
# or
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_phase10.py -v

# Run a specific test
python -m pytest tests/test_phase10.py::test_chaos_run -v

# Run with verbose output and no capture
python -m pytest tests/ -v -s

# Run tests matching a keyword
python -m pytest tests/ -k "chaos"
```

### Code Coverage

```bash
# Run with coverage
make test-coverage
# or
python -m pytest tests/ --cov=engine --cov-report=term-missing

# Generate HTML report
python -m pytest tests/ --cov=engine --cov-report=html
open htmlcov/index.html
```

Target coverage: **80%+** for new code.

### Testing with Tox

Tox runs tests across multiple Python versions:

```bash
# Run all environments
tox

# Run a specific environment
tox -e py311

# List available environments
tox list
```

### Writing Tests

Tests use `pytest` with `pytest-asyncio` for async test support.

```python
import pytest
from engine.validators import (
    RegexValidator, LengthValidator, ValidatorPipeline,
    ContentAddressableCache, CachePolicy,
)
from engine.profile import ValidatorDef, ValidatorTier

@pytest.mark.asyncio
async def test_regex_validator_detects_slop():
    """T1 regex validator should flag promotional language."""
    patterns = [
        ("promo_language", r"(harika|mükemmel)", "error"),
    ]
    validator = RegexValidator(
        ValidatorDef("SlopScanT1", ValidatorTier.T1, critical=True),
        patterns,
    )

    result = await validator.validate("Bu harika bir ürün!")
    assert not result.passed
    assert "promo_language" in str(result.details)
```

Key fixtures are available in `tests/conftest.py`:

```python
@pytest.fixture
def chaos_engine(tmp_path):
    """Chaos engine with temp directory for isolation."""
    return ChaosEngine(base_path=str(tmp_path))
```

---

## Code Style & Linting

The project uses a three-tool formatting and linting pipeline:

### Black (Code Formatter)

```bash
# Format all Python files
black engine/ tests/

# Check formatting without changes
black --check engine/ tests/
```

Configuration in `pyproject.toml`:

```toml
[tool.black]
line-length = 100
target-version = ["py310"]
```

### isort (Import Sorter)

```bash
# Sort imports
isort engine/ tests/

# Check without changes
isort --check-only engine/ tests/
```

Configuration:

```toml
[tool.isort]
profile = "black"
line_length = 100
```

### Ruff (Linter)

```bash
# Run linter
ruff check engine/ tests/

# Auto-fix issues
ruff check --fix engine/ tests/
```

### Pre-commit Hook (Recommended)

```bash
# Install pre-commit
pip install pre-commit
pre-commit install

# Run on all files
pre-commit run --all-files
```

Add a `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.12.0
    hooks:
      - id: black
  - repo: https://github.com/PyCQA/isort
    rev: 5.12.0
    hooks:
      - id: isort
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.8
    hooks:
      - id: ruff
        args: [--fix]
```

### One-Command Formatting

```bash
make format
# Runs: black engine/ tests/ && isort engine/ tests/
```

---

## Pull Request Workflow

### Branch Naming

```
feature/<short-description>     # New feature
fix/<short-description>         # Bug fix
docs/<short-description>        # Documentation only
refactor/<short-description>    # Code restructuring
test/<short-description>        # Adding/improving tests
chore/<short-description>       # Tooling, CI, dependencies
```

Example: `feature/raft-leader-election`, `fix/cache-ttl-bug`

### Workflow Steps

```bash
# 1. Create a feature branch
git checkout -b feature/my-feature

# 2. Make changes and commit
git add .
git commit -m "feat: add Raft leader election timeout"

# 3. Keep branch up to date
git fetch origin
git rebase origin/main

# 4. Run tests locally
make test
make lint

# 5. Push and create PR
git push origin feature/my-feature
```

### Commit Message Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <description>

[optional body]
```

| Type | Usage |
|------|-------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation changes |
| `refactor` | Code restructuring (no functional change) |
| `test` | Adding or updating tests |
| `chore` | Tooling, CI, dependencies |
| `perf` | Performance improvement |
| `style` | Formatting, linting (no code change) |

Examples:

```
feat: add 3-tier validator pipeline with content-addressable cache
fix: handle empty artifact in SchemaValidator
docs: add chaos engineering guide
test: add integration test for degradation transitions
```

### Pull Request Checklist

Before submitting a PR:

- [ ] Code compiles and tests pass (`make test`)
- [ ] Code is formatted (`make format`)
- [ ] Linter passes (`ruff check .`)
- [ ] New tests added for new functionality
- [ ] Coverage has not decreased significantly
- [ ] Documentation updated (if applicable)
- [ ] Commit messages follow conventional commits
- [ ] Branch is rebased on latest `main`

### Review Process

1. **Open a draft PR** early for feedback on approach
2. **Request review** from maintainers when ready
3. **Address review comments** with additional commits
4. **Squash commits** before merge (optional, done by maintainers)
5. **Merge** via squash-merge to keep history clean

---

## Documentation

### Building Documentation Locally

```bash
# Install docs dependencies
pip install mkdocs mkdocs-material

# Build and serve
mkdocs serve
# Open http://127.0.0.1:8000

# Build static site
mkdocs build
# Output in site/
```

### Documentation Structure

```
docs/
├── index.md                          # Home page
├── getting-started/
│   ├── installation.md
│   ├── quickstart.md
│   ├── configuration.md
│   └── profiles.md
├── guide/
│   ├── cli.md
│   ├── http-api.md
│   ├── state-machine.md
│   ├── runs.md
│   ├── monitoring.md
│   ├── auth.md
│   ├── chaos.md                      # ← Chaos engineering guide
│   ├── plugin-ecosystem.md
│   └── ai-native.md
├── dev/
│   ├── architecture.md
│   ├── modules.md
│   ├── testing.md
│   ├── docker-ci-cd.md
│   └── contributing.md               # ← This file
├── api/                              # API reference (one per module)
│   ├── engine.md
│   ├── validators.md
│   ├── chaos.md
│   └── ...
├── changelog.md
└── license.md
```

### Docstring Style

All public modules, classes, and functions should have Google-style docstrings:

```python
def validate(self, artifact: Any) -> ValidationResult:
    """Run all regex patterns against the artifact.

    Scans content for forbidden patterns and collects findings.
    Fails on any "error"-severity match.

    Args:
        artifact: Input content (string, object with .content/.text, or any).

    Returns:
        ValidationResult with passed/failed status, message, and details.

    Raises:
        ValueError: If artifact cannot be converted to string.
    """
```

### Adding a New Page

1. Create `.md` file in the appropriate `docs/` subdirectory
2. Add the page to `mkdocs.yml` under the `nav` section
3. Build and verify with `mkdocs serve`

---

## Release Process

### Version Numbering

Prodinamik Engine follows [Semantic Versioning](https://semver.org/):

```
MAJOR.MINOR.PATCH
```

- **MAJOR** — incompatible API changes
- **MINOR** — backward-compatible new features
- **PATCH** — backward-compatible bug fixes

Current version: **v1.3**

### Release Steps

```bash
# 1. Update version in engine/__init__.py
#    (and any other version references)

# 2. Update changelog
#    Edit docs/changelog.md with new version entry

# 3. Commit version bump
git add engine/__init__.py docs/changelog.md
git commit -m "chore: bump version to v1.4.0"

# 4. Create and push tag
git tag v1.4.0
git push origin v1.4.0

# 5. Build distribution packages
python -m build

# 6. Upload to PyPI (if applicable)
python -m twine upload dist/*

# 7. Create GitHub Release
#    - Title: "v1.4.0"
#    - Description: Copy changelog entry
#    - Attach: dist/*.tar.gz, dist/*.whl
```

### Changelog Format

```markdown
## [v1.4.0] - 2026-06-15

### Added
- New chaos scenario: disk-corruption with byte-level file mutation
- Predictive degradation cost optimizer

### Changed
- Validator timeout defaults adjusted (BuildValidator: 300s → 180s)

### Fixed
- ContentAddressableCache invalidation now clears disk cache correctly
- SchemaValidator handles empty content without crash

### Removed
- Deprecated `engine.legacy` module
```

---

## Getting Help

- **GitHub Issues** — Bug reports and feature requests
- **Discussions** — Questions and community support
- **Pull Requests** — Code contributions

Thank you for contributing to the Prodinamik Engine!
