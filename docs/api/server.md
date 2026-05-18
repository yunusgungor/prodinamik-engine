# HTTP Server

Prodinamik Engine v1.1 — HTTP Server

Built-in HTTP server exposing health checks, Prometheus-format metrics, and a
RESTful API for run management, state transitions, profile discovery, and audit
log queries. Includes middleware for API key authentication (Bearer or X-API-Key)
and token-bucket rate limiting.

The server runs in a background thread by default, allowing the engine to
continue operating while serving HTTP requests. A blocking (foreground) mode
is also available for direct control.

**Module:** `engine/server.py` (307 lines, 2 classes, 19 functions)

---

## Endpoints Overview

| Method | Path              | Auth Required | Description                          |
|--------|-------------------|---------------|--------------------------------------|
| GET    | `/healthz`        | No            | Health check (alias: `/health`)      |
| GET    | `/metrics`        | No            | Prometheus-format metrics            |
| GET    | `/api/v1/health`  | Yes           | Authenticated health details         |
| GET    | `/api/v1/runs`    | Yes           | List all runs                        |
| GET    | `/api/v1/runs/{slug}` | Yes        | Get single run details               |
| POST   | `/api/v1/runs`    | Yes           | Create a new run                     |
| POST   | `/api/v1/runs/{slug}` | Yes        | Transition run state                 |
| GET    | `/api/v1/profiles`| Yes           | List registered profiles             |
| GET    | `/api/v1/audit`   | Yes           | Query audit log                      |
| GET    | `/api/v1/metrics` | Yes           | Authenticated metrics                |

---

## Classes

### `ProdinamikHandler(BaseHTTPRequestHandler)`

HTTP request handler for Prodinamik Engine. Subclasses Python's
`http.server.BaseHTTPRequestHandler` and dispatches incoming requests
to typed handlers based on path and HTTP method.

**Class-level references (set by `ProdinamikServer` on startup):**

| Attribute           | Type             | Description                              |
|---------------------|------------------|------------------------------------------|
| `engine`            | `AsyncEngine`    | Reference to the running engine instance |
| `auth_manager`      | `AuthManager`    | API key authentication manager           |
| `rate_limiter`      | `RateLimiter`    | Token-bucket rate limiter                |
| `server_started_at` | `float`          | `time.time()` timestamp of server start  |

**Methods:**

#### `do_GET()`

Route incoming GET requests by path:

- `/healthz` or `/health` → `_handle_health()`
- `/metrics` → `_handle_metrics()`
- `/api/v1/...` → `_handle_api(path)`
- All other paths → 404 JSON response

#### `do_POST()`

Route incoming POST requests:

- `/api/v1/...` → `_handle_api(path)`
- All other paths → 404 JSON response

#### `_handle_health()`

Health check endpoint (unauthenticated).

**Response:** `200 OK`

Builds a health dictionary by calling `engine.health_snapshot` (if engine is
available). Adds:
- `server_uptime`: seconds since server started
- `timestamp`: ISO 8601 current time
- `status`: `"ok"` if `health_score > 0`, otherwise `"degraded"`

If the engine is unavailable, returns a partial response with
`"error": "engine unavailable"`.

**Example response:**
```json
{
  "health_score": 95,
  "active_runs": 3,
  "total_runs": 27,
  "server_uptime": 3600,
  "timestamp": "2026-05-18T14:51:00",
  "status": "ok"
}
```

#### `_handle_metrics()`

Prometheus-format metrics endpoint (unauthenticated).

**Response:** `200 OK` with `Content-Type: text/plain; version=0.0.4`

If engine is available:
1. Imports `metrics` and `EngineMetrics` from `.metrics`
2. Creates an `EngineMetrics` instance bound to the engine
3. Calls `em.poll()` to collect current metrics
4. Calls `metrics.render_prometheus()` to produce Prometheus text output
5. Returns the output as `text/plain`

If engine is unavailable: `503 Service Unavailable`

On error during metric collection: `500 Internal Server Error` with error
details.

#### `_handle_api(path: str)`

Authenticated API handler — central dispatch for all /api/v1/ endpoints.

**Flow:**

1. **Authentication:** Calls `get_auth_from_header(self.headers, self.auth_manager)` from `.auth`. Supports both `Authorization: Bearer pdmk_...` and `X-API-Key: pdmk_...` header styles.

   - If authentication fails (invalid or missing key), returns `401 Unauthorized` with error details.

2. **Rate limiting:** If a `rate_limiter` is configured, calls `rate_limiter.check(auth_result.key_id)`.

   - If rate limited, returns `429 Too Many Requests` with a `Retry-After` header and JSON body including `retry_after_seconds`.

3. **Routing:** Dispatches based on the normalized path:

   | Path Pattern                     | Handler               |
   |----------------------------------|------------------------|
   | `/api/v1/runs`                   | `_api_list_runs()`     |
   | `/api/v1/runs/{slug}` (GET)      | `_api_get_run(slug)`   |
   | `/api/v1/health`                 | `_handle_health()`     |
   | `/api/v1/profiles`               | `_api_list_profiles()` |
   | `/api/v1/audit`                  | `_api_audit_query()`   |
   | `/api/v1/metrics`                | `_handle_metrics()`    |

   Any unmatched path returns `404 Not Found`.

4. **Error handling:** All route handlers are wrapped in a `try/except Exception` block. Unhandled exceptions return `500 Internal Server Error` with the exception message.

#### `_api_list_runs(auth_result)`

List all runs (non-archived).

**Response:** `200 OK`

Calls `engine.list_runs(include_archived=False)` and returns a JSON array of
run summaries. Each run object contains:
- `slug`: unique identifier
- `profile`: profile name
- `state`: current state machine state
- `title`: human-readable title
- `status`: run status

Returns `503 Service Unavailable` if engine is not available.

**Example response:**
```json
{
  "runs": [
    {
      "slug": "flux-release-001",
      "profile": "software",
      "state": "review",
      "title": "Implement CRDT merge",
      "status": "active"
    }
  ],
  "count": 1
}
```

#### `_api_get_run(slug: str, auth_result)`

Get detailed information about a specific run.

**Response:** `200 OK`

Calls `engine.get_run(slug)` and `engine.run_manager.get_state_elapsed(slug)`.
Returns a JSON object with all run metadata including:
- `slug`, `profile`, `state`, `title`, `status`, `version`
- `created_at`, `updated_at` (ISO 8601)
- `elapsed_seconds`: time spent in current state (nullable)

Returns `404 Not Found` if the run does not exist.
Returns `503 Service Unavailable` if engine is not available.

#### `_api_list_profiles(auth_result)`

List all registered profiles.

**Response:** `200 OK`

Fetches `engine.health_snapshot` and returns the `profiles` array from it.

**Example response:**
```json
{
  "profiles": ["software", "content", "research"]
}
```

#### `_api_audit_query(auth_result)`

Query the append-only audit log with optional filters.

**Query parameters** (from URL query string):
- `since` (optional): ISO 8601 timestamp — return entries after this time
- `type` (optional): Filter by event type (e.g., `state_transition`, `run_created`)
- `limit` (optional): Maximum entries to return (default: 20)

**Response:** `200 OK`

Loads the `AuditLog` from the configured `data_dir/audit/` directory, applies
filters, and returns matching entries. Each entry is serialized via `to_dict()`.

**Example response:**
```json
{
  "entries": [
    {
      "sequence": 42,
      "run_slug": "flux-release-001",
      "timestamp": "2026-05-18T14:00:00",
      "event_type": "state_transition",
      "data": {"from": "active", "to": "review"}
    }
  ],
  "count": 1
}
```

#### `_json_response(status: int, data: dict)`

Send a JSON response with the given HTTP status code.

- Serializes `data` with `json.dumps(ensure_ascii=False, default=str)`
- Sets `Content-Type: application/json`
- Sets `Access-Control-Allow-Origin: *` for CORS support
- Writes the JSON body to the response stream

#### `_text_response(status: int, text: str, content_type: str = "text/plain")`

Send a plain text response.

- `text`: The response body string
- `content_type`: MIME type (default `text/plain`)
- Used for the `/metrics` endpoint which serves Prometheus text format

#### `log_message(format, *args)`

Override of the default `BaseHTTPRequestHandler.log_message`.

Suppresses the default stderr HTTP logging and instead routes log entries
through the engine's structured logger at DEBUG level.

**Log format:** `HTTP: {method} {path} {status_code}`

---

### `ProdinamikServer`

HTTP server for Prodinamik Engine. Manages lifecycle (start/stop) of an
`HTTPServer` running in a background daemon thread.

**Constructor:**

```python
def __init__(self, engine=None, host="127.0.0.1", port=8080,
             auth_manager=None, rate_limiter=None)
```

| Parameter       | Type           | Default        | Description                                    |
|-----------------|----------------|----------------|------------------------------------------------|
| `engine`        | `AsyncEngine`  | `None`         | The engine instance to serve                   |
| `host`          | `str`          | `"127.0.0.1"`  | Bind address (use `"0.0.0.0"` for all interfaces) |
| `port`          | `int`          | `8080`         | TCP port to listen on                          |
| `auth_manager`  | `AuthManager`  | `AuthManager()`| Authentication manager for API key validation  |
| `rate_limiter`  | `RateLimiter`  | `RateLimiter(rate=20, burst=40)` | Token-bucket rate limiter |

**Behavior:**

1. Stores engine, host, port references.
2. Initializes `_server` and `_thread` as `None`, `_running` as `False`.
3. Creates default `AuthManager` and `RateLimiter` instances if none provided.
4. Wires the `ProdinamikHandler` class with:
   - `engine` reference
   - `auth_manager` reference
   - `rate_limiter` reference
   - `server_started_at` timestamp

**Methods:**

#### `start()`

Start the HTTP server in a background daemon thread.

1. Returns immediately if already running.
2. Creates an `HTTPServer((host, port), handler_class)`.
3. Creates and starts a daemon `threading.Thread` named `"prodinamik-http"`.
4. Sets `_running = True`.
5. Logs an info message: `"HTTP server started on http://{host}:{port}"`.

The server runs until `stop()` is called or the process exits (daemon thread).

**Usage:**
```python
server = ProdinamikServer(engine, port=8080)
server.start()  # non-blocking, returns immediately
```

#### `start_blocking()`

Start the HTTP server in the current thread (foreground/blocking).

1. Creates an `HTTPServer((host, port), handler_class)`.
2. Logs an info message including `"(blocking)"` suffix.
3. Calls `server.serve_forever()` — blocks indefinitely.
4. On `KeyboardInterrupt`, calls `stop()` to clean up.

**Usage:**
```python
server = ProdinamikServer(engine, port=8080)
server.start_blocking()  # blocks until Ctrl+C
```

#### `stop()`

Stop the HTTP server gracefully.

1. Sets `_running = False`.
2. If `_server` exists: calls `server.shutdown()` and `server.server_close()`.
3. Sets `_server = None`.
4. Logs an info message: `"HTTP server stopped"`.

Safe to call multiple times (second call is a no-op since `_server` is `None`).

#### `_serve()`

Background thread target. Calls `self._server.serve_forever()` to start
accepting connections. This method is the `target` for the daemon thread
created in `start()`.

#### `is_running -> bool`

Property that returns `True` if the server is currently running and the
background thread is alive.

```python
if server.is_running:
    print(f"Server alive on {server.host}:{server.port}")
```

#### `__repr__() -> str`

Returns a string representation of the server:

```
ProdinamikServer(host=127.0.0.1, port=8080, running=True)
```

---

## Usage Examples

### Basic — background thread

```python
from engine.engine import AsyncEngine
from engine.config import ProdinamikConfig
from engine.server import ProdinamikServer

cfg = ProdinamikConfig.load()
engine = AsyncEngine(cfg)

server = ProdinamikServer(engine, host="0.0.0.0", port=8080)
server.start()

# Engine continues working in main thread
engine.run_forever()
```

### With custom authentication and rate limiting

```python
from engine.auth import AuthManager
from engine.ratelimit import RateLimiter
from engine.server import ProdinamikServer

auth = AuthManager(base_path="./data/auth")
limiter = RateLimiter(rate=10, burst=30)

server = ProdinamikServer(engine, port=8080,
                          auth_manager=auth,
                          rate_limiter=limiter)
server.start()
```

### Blocking mode (for testing or simple deployments)

```python
server = ProdinamikServer(engine, port=8080)
try:
    server.start_blocking()  # Ctrl+C to stop
except KeyboardInterrupt:
    server.stop()
```

---

## Security & Rate Limiting

- **Authentication:** All `/api/v1/*` endpoints require a valid API key sent
  via `Authorization: Bearer pdmk_...` or `X-API-Key: pdmk_...` header.
  Keys are managed via `AuthManager` (see [auth.md](auth.md)).
- **Rate limiting:** Default configuration allows 20 requests/second with a
  burst of 40. The limit is applied per API key ID. When exceeded, the
  server responds with HTTP 429 and a `Retry-After` header.
- **CORS:** The `Access-Control-Allow-Origin: *` header is set on all JSON
  responses, enabling cross-origin requests from browser-based clients.
- **Health/Metrics endpoints** (`/healthz`, `/health`, `/metrics`) are
  intentionally unauthenticated for integration with load balancers,
  monitoring systems (Prometheus), and orchestration platforms.
