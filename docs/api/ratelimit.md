# Rate Limiter

Prodinamik Engine v1.1 — Rate Limiter

Token bucket rate limiter with per-key tracking, burst support,
and degradation integration.

Usage:
    limiter = RateLimiter(rate=10, burst=20)
    allowed, wait = limiter.check("key-123")
    # (True, 0.0) if allowed, (False, 1.5) if rate limited

**Module:** `engine.ratelimit.py`

## Classes

### `Bucket`

Token bucket state

### `RateLimiter`

Token bucket rate limiter — thread-safe, per-key tracking.

rate:     tokens per second (long-term average)
burst:    max burst size (default = rate, meaning no burst)

**Methods:**

- `__init__(rate, burst)`
- `check(key, cost)`
  — Check if request is allowed.
- `reset(key)`
  — Reset rate limiter for a key (or all keys)
- `stats(key)`
  — Get rate limiter statistics
- `__repr__()`

### `AuthRateLimiter`

Combined authentication + rate limiting middleware.

Applicable for HTTP server integration.

**Methods:**

- `__init__(auth_manager, rate_limiter)`
- `check_request(api_key, cost)`
  — Full request check: auth + rate limit.
