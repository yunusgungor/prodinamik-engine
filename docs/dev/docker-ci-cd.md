# Docker & CI/CD

## Multi-Stage Docker Build

```
Stage        Size      Description
──────────────────────────────────────
base         ~120MB    python:3.11-slim foundation
dev          ~270MB    + dev dependencies, source code
test         ~332MB    + tests (165/165 passed as build step)
production   ~231MB    CLI entrypoint (prodinamik --help)
```

**Key pattern:** The test stage runs `pytest -x` INSIDE the Docker build.
If tests fail, the build fails — enforcing testing at build time.

```bash
# Build production image
make docker
# or: docker build --target production -t prodinamik-engine:latest .

# Build + test in Docker
make docker-test
# or: docker compose --profile ci run --rm ci

# Interactive shell
make docker-shell
# or: docker compose --profile dev run --rm shell
```

## CI Pipeline (ci.yml)

Trigger: push to main/PR, tags `v*.*.*`

```
push/PR → test (matrix: 3.11, 3.12) → lint → docker build & push to GHCR
```

## Release Pipeline (release.yml)

Trigger: `git tag v*.*.*`

```
tag push → version check → test → PyPI publish → GHCR push → GitHub Release
```

## Makefile Targets

| Category | Targets |
|----------|---------|
| **Dev** | `install`, `test`, `test-all`, `test-coverage`, `lint`, `clean`, `full-ci` |
| **Docker** | `docker`, `docker-test`, `docker-lint`, `docker-all`, `docker-shell`, `docker-push` |
| **Release** | `build`, `publish`, `publish-test` |
