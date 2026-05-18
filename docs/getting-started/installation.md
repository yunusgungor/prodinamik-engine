# Installation

## Requirements

- Python 3.11 or later
- pip

## Install from PyPI

```bash
pip install prodinamik-engine
```

## Install from source

```bash
git clone https://github.com/yunusgungor/prodinamik-engine.git
cd prodinamik-engine
pip install -e ".[dev]"
```

## Install with Docker

```bash
docker pull ghcr.io/yunusgungor/prodinamik-engine:latest
docker run --rm ghcr.io/yunusgungor/prodinamik-engine:latest --help
```

Or build locally:

```bash
make docker
# or
docker build --target production -t prodinamik-engine:latest .
```

## Verify installation

```bash
prodinamik --version
prodinamik --help
```
