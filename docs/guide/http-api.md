# HTTP API

The HTTP API server provides RESTful endpoints for run management, monitoring, and audit.

## Starting the Server

```bash
# Start on default port 8080
prodinamik serve

# Custom port
prodinamik serve --port 8000

# Bind to all interfaces
prodinamik serve --bind 0.0.0.0
```

## Authentication

API endpoints require an API key. Create one with:

```bash
prodinamik auth create my-key --role admin
# → Key: pdmk_<48 hex chars> (shown once, save it!)
```

Authenticate via header:

```
Authorization: Bearer pdmk_<48 hex chars>
X-API-Key: pdmk_<48 hex chars>
```

## Endpoints

### Health (unauthenticated)

```
GET /healthz    → Health check
GET /metrics    → Prometheus metrics (text/plain)
```

### API v1 (authenticated)

```
GET    /api/v1/health       → Detailed health
GET    /api/v1/runs          → List all runs
POST   /api/v1/runs          → Create a new run
GET    /api/v1/runs/{slug}   → Run details
POST   /api/v1/runs/{slug}   → Transition run state
GET    /api/v1/profiles      → List profiles
GET    /api/v1/audit         → Query audit log
```

### Example: Create a run

```bash
curl -X POST http://localhost:8080/api/v1/runs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer pdmk_..." \
  -d '{"profile": "software", "title": "Implement FFT"}'
```

### Example: Query audit log

```bash
curl "http://localhost:8080/api/v1/audit?type=state_transition&limit=10" \
  -H "Authorization: Bearer pdmk_..."
```

## Rate Limiting

Rate-limited requests receive HTTP 429 with `Retry-After` header:

```json
{
  "error": "Rate limit exceeded",
  "detail": "Try again in 0.5 seconds"
}
```

## Full API Spec

See [OpenAPI Spec](https://yunusgungor.github.io/prodinamik-engine/openapi.yaml) for complete schema definitions.
