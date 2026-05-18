# HTTP Server

Prodinamik Engine v1.1 — HTTP Server

Built-in HTTP server with:
- /metrics      → Prometheus format metrics
- /healthz      → Health check endpoint
- /api/v1/*     → RESTful API (authenticated)
- Rate limiting + authentication middleware

Usage:
    from engine.server import ProdinamikServer
    server = ProdinamikServer(engine, port=8080)
    server.start()  # background thread

**Module:** `engine.server.py`

## Classes

### `ProdinamikHandler`(BaseHTTPRequestHandler)

HTTP request handler for Prodinamik Engine

**Methods:**

- `do_GET()`
- `do_POST()`
- `_handle_health()`
  — Health check endpoint
- `_handle_metrics()`
  — Prometheus metrics endpoint
- `_handle_api(path)`
  — Authenticated API handler
- `_api_list_runs(auth_result)`
- `_api_get_run(slug, auth_result)`
- `_api_list_profiles(auth_result)`
- `_api_audit_query(auth_result)`
- `_json_response(status, data)`
- `_text_response(status, text, content_type)`
- `log_message(format)`
  — Suppress default HTTP log (use engine logger instead)

### `ProdinamikServer`

HTTP server for Prodinamik Engine.

Runs in a background thread. Supports start/stop lifecycle.

**Methods:**

- `__init__(engine, host, port, auth_manager, rate_limiter)`
- `start()`
  — Start HTTP server in background thread
- `start_blocking()`
  — Start HTTP server in foreground (blocking)
- `stop()`
  — Stop HTTP server
- `_serve()`
  — Background thread target
- `is_running()`
- `__repr__()`
