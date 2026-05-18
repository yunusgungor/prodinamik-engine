# Authentication & Authorization

Prodinamik Engine provides a complete authentication and authorization system built on API keys with role-based access control (RBAC). The system manages token issuance, validation, revocation, and integrates with HTTP middleware, rate limiting, and CLI commands. Source modules: `engine/auth.py`, `engine/ratelimit.py`.

## Architecture Overview

The auth system has four layers:

1. **AuthManager** — API key creation, validation, listing, and revocation. Keys are stored as SHA-256 hashes; raw keys are shown only once at creation (like GitHub personal access tokens).
2. **RBAC (Role-Based Access Control)** — Three roles with a hierarchy: `admin` > `user` > `readonly`.
3. **AuthRateLimiter** — Composite middleware that combines authentication with token-bucket rate limiting per key.
4. **HTTP Integration** — Bearer token extraction from `Authorization` headers with fallback to `X-API-Key`.

## API Key Authentication

### Key Format

All API keys follow the format:

```
pdmk_<48-hex-characters>
```

Example:
```
pdmk_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4
```

The `pdmk_` prefix identifies the key as a Prodinamik Engine token. The remaining 48 characters are cryptographically random (generated via `secrets.token_hex(24)`).

### Key Storage

Keys are stored in a directory structure:

```
data/auth/
└── keys/
    ├── deploy-bot-a1b2.json
    └── ci-pipeline-c3d4.json
```

Each key file contains the full `APIKey` record:

```json
{
  "key_id": "deploy-bot-a1b2c3d4",
  "key_hash": "sha256hex...",
  "name": "deploy-bot",
  "role": "admin",
  "created_at": "2026-05-18T12:00:00+00:00",
  "expires_at": "2026-08-18T12:00:00+00:00",
  "last_used_at": "2026-05-18T14:32:15+00:00",
  "enabled": true,
  "metadata": {
    "team": "platform",
    "environment": "production"
  }
}
```

**Important**: The `key_hash` is the SHA-256 hash of the raw key. The raw key itself is **never stored** — only the hash is persisted. This follows password-security best practices.

## Role-Based Access Control (RBAC)

### Roles

| Role | Hierarchy Level | Permissions |
|------|----------------|-------------|
| **admin** | 2 (highest) | Full read/write access. Can create and revoke API keys, manage runs, view all data, modify configurations. |
| **user** | 1 | Standard access. Can create runs, transition states, view metrics and audit logs. Cannot manage API keys or modify system configuration. |
| **readonly** | 0 | Read-only access. Can list runs, view state, inspect metrics and audit logs. Cannot create runs, transition states, or modify any resource. |

### Role Enforcement

Roles are enforced through the `require_role` decorator:

```python
from engine.auth import AuthManager

class RunController:
    @AuthManager.require_role("admin")
    def delete_run(self, slug: str, auth_result=None):
        # Only admin can delete runs
        ...

    @AuthManager.require_role("user")
    def create_run(self, title: str, auth_result=None):
        # Users and admins can create runs
        ...

    @AuthManager.require_role("readonly")
    def list_runs(self, auth_result=None):
        # All authenticated users can list runs
        ...
```

The decorator extracts `AuthResult` from keyword arguments or positional arguments. If the caller's role hierarchy level is below the minimum required role, a `PermissionError` is raised.

### Auth Scopes

Roles can be further refined through the `metadata` field on API keys. For example, you can attach metadata to restrict a key to a specific profile:

```python
key_id, raw_key = auth.create_key(
    name="hardware-ci",
    role="user",
    metadata={"profile": "hardware"}
)
```

Application code can then check these metadata scopes to enforce fine-grained access:

```python
if auth_result.key_id == "hardware-ci-..." and run.meta.profile != "hardware":
    raise PermissionError("Key scoped to hardware profile only")
```

## Token Management

### Creating API Keys

**CLI:**
```bash
prodinamik auth create deploy-bot --role admin
# ✅ API key created
# Key ID:  deploy-bot-a1b2c3d4
# Raw key: pdmk_a1b2c3d4e5f6a7b8c9d0e1f...
# ⚠️  Save this key — it will not be shown again.
```

**With expiration and metadata:**
```bash
prodinamik auth create ci-pipeline --role user --expires-in 90 --metadata team=ci
```

**Programmatic:**
```python
from engine.auth import AuthManager

auth = AuthManager(base_path="./data/auth")

# Create with defaults (role=user, no expiration)
key_id, raw_key = auth.create_key("deploy-bot")

# Create with custom options
key_id, raw_key = auth.create_key(
    name="ci-pipeline",
    role="user",
    expires_in_days=90,
    metadata={"environment": "production", "team": "platform"},
)

print(f"Key ID: {key_id}")
print(f"Raw key: {raw_key}")  # ⚠️ Show once, then discard
```

### Listing API Keys

**CLI:**
```bash
prodinamik auth list
```

Output shows key ID, name, role, creation date, expiration, and enabled status. Key hashes are never exposed.

**Programmatic:**
```python
keys = auth.list_keys()
for k in keys:
    print(f"{k['key_id']} — {k['name']} ({k['role']}) {'🔒' if not k['enabled'] else ''}")
```

### Getting Key Details

```bash
prodinamik auth info deploy-bot-a1b2c3d4
```

Shows full key metadata (without hash):

```python
info = auth.get_key("deploy-bot-a1b2c3d4")
# {
#     "key_id": "deploy-bot-a1b2c3d4",
#     "name": "deploy-bot",
#     "role": "admin",
#     "created_at": "2026-05-18T12:00:00+00:00",
#     "expires_at": "2026-08-18T12:00:00+00:00",
#     "enabled": true,
#     "last_used_at": "2026-05-18T14:32:15+00:00",
#     "metadata": {"team": "platform"}
# }
```

### Revoking API Keys

**CLI:**
```bash
prodinamik auth revoke deploy-bot-a1b2c3d4
# ✅ Key 'deploy-bot-a1b2c3d4' revoked
```

**Programmatic:**
```python
success = auth.revoke_key("deploy-bot-a1b2c3d4")
if success:
    print("Key revoked")
```

Revocation sets `enabled=False` on the stored key. The key remains in the key store but `validate_key()` will return `AuthResult(valid=False, error="Key disabled")` for any request using it.

## Key Validation

### Validation Flow

When a raw API key is presented, the validation process works as follows:

1. **Format check** — Must start with `pdmk_`. Returns "Invalid key format" if not.
2. **Hash lookup** — Compute SHA-256 hash of the raw key, then search the cache for a matching `key_hash`.
3. **Expiry check** — If the key has an `expires_at`, validate it's still in the future.
4. **Enabled check** — Verify the key's `enabled` flag is `true`.
5. **Usage tracking** — Update `last_used_at` timestamp on the stored key record.
6. **Return result** — `AuthResult` with `valid`, `role`, `name`, `key_id` fields.

### AuthResult

```python
@dataclass
class AuthResult:
    valid: bool = False
    role: str = ""
    name: str = ""
    key_id: str = ""
    error: str = ""
```

Check `result.valid` to determine if the key is acceptable. For invalid keys, `result.error` contains the reason.

### Programmatic Validation

```python
from engine.auth import AuthManager

auth = AuthManager()

raw_key = "pdmk_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4"
result = auth.validate_key(raw_key)

if result.valid:
    print(f"Authenticated as {result.name} ({result.role})")
else:
    print(f"Auth failed: {result.error}")
```

## HTTP Integration

### Bearer Token Authentication

Include the API key in the `Authorization` HTTP header:

```bash
curl -H "Authorization: Bearer pdmk_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4" \
     http://localhost:8080/api/runs
```

### X-API-Key Header (Fallback)

The system also accepts the key via the `X-API-Key` header:

```bash
curl -H "X-API-Key: pdmk_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4" \
     http://localhost:8080/api/runs
```

### Header Extraction Utility

```python
from engine.auth import get_auth_from_header

headers = {
    "Authorization": "Bearer pdmk_a1b2c3d4..."
}
result = get_auth_from_header(headers, auth_manager)
```

Priority order: `Authorization: Bearer` > `X-API-Key`.

## Rate Limiting

The rate limiter (`engine/ratelimit.py`) uses the **token bucket algorithm** for per-key traffic shaping.

### Token Bucket Algorithm

Each client is assigned a bucket containing tokens. Tokens are consumed at a cost per request. Tokens are refilled at a constant rate (tokens per second). If the bucket has enough tokens, the request is allowed; otherwise it's denied with a wait time.

```python
from engine.ratelimit import RateLimiter

limiter = RateLimiter(rate=10.0, burst=20.0)
# rate: 10 tokens/second refill
# burst: max 20 tokens (allows short bursts above the average rate)
```

### Checking Rate Limits

```python
# Returns (allowed, wait_seconds)
allowed, wait = limiter.check("client-key-123", cost=1.0)

if allowed:
    print("Request allowed")
else:
    print(f"Rate limited. Wait {wait:.1f}s")
```

### Per-Key Statistics

```python
stats = limiter.stats("client-key-123")
# {
#     "key": "client-key-123",
#     "allowed": 42,
#     "denied": 3,
#     "tokens": 8.5,
#     "burst": 20,
#     "rate": 10
# }

global_stats = limiter.stats()
# {
#     "total_keys": 15,
#     "total_allowed": 4523,
#     "total_denied": 87,
#     "rate": 10,
#     "burst": 20
# }
```

### Resetting Limiter State

```python
limiter.reset("client-key-123")   # Reset specific key
limiter.reset()                   # Reset all keys
```

## Composite Auth + Rate Limit Middleware

The `AuthRateLimiter` class combines authentication and rate limiting into a single check:

```python
from engine.ratelimit import AuthRateLimiter

guard = AuthRateLimiter(auth_manager=auth, rate_limiter=limiter)

result = guard.check_request("pdmk_a1b2c3d4...", cost=2.0)
# {
#     "allowed": True/False,
#     "status": "ok" | "auth_error" | "rate_limited",
#     "auth_result": <AuthResult>,
#     "wait": 0.0,
#     "error": "..."
# }
```

This is the recommended middleware for HTTP servers — it validates the key first, then applies rate limiting only for valid keys.

## CLI Reference

| Command | Description |
|---------|-------------|
| `prodinamik auth create <name>` | Create a new API key with default role (user) |
| `prodinamik auth create <name> --role admin` | Create with admin role |
| `prodinamik auth create <name> --expires-in 30` | Create with 30-day expiration |
| `prodinamik auth create <name> --metadata key=val` | Create with custom metadata |
| `prodinamik auth list` | List all API keys (without hashes) |
| `prodinamik auth revoke <key-id>` | Revoke (disable) a key by ID |
| `prodinamik auth info <key-id>` | Show key details |

## Security Best Practices

### Token Rotation

- Rotate API keys regularly. Use the `--expires-in` flag to set automatic expiration — 90 days is a reasonable default for CI/CD pipelines.
- For production deployments, rotate keys at least every 180 days.
- Use the `last_used_at` field to identify stale keys and revoke them proactively.

```bash
# Identify keys not used in 30+ days
prodinamik auth list | grep -v "$(date -d '30 days ago' +%Y-%m-%d)"
```

### Least Privilege

- Assign the minimum role needed. Prefer `readonly` for monitoring tools, `user` for CI/CD pipelines, and reserve `admin` for human operators.
- Use metadata to scope keys to specific profiles or environments.
- Never embed admin keys in configuration files or environment variables that are checked into version control.

### Environment Variable Conventions

```bash
export PRODINAMIK_API_KEY="pdmk_a1b2c3d4..."
# OR
export PRODINAMIK_ADMIN_KEY="pdmk_..."
export PRODINAMIK_RO_USER_KEY="pdmk_..."
```

### Key Generation Security

- Keys are generated using Python's `secrets.token_hex()` (CSPRNG). Do not replace with `random` or deterministic generators.
- The raw key is shown exactly once at creation time. Log this securely or display it to the user for immediate capture.
- Store hashes only. The `key_hash` is a SHA-256 digest that cannot be reversed.

### Monitoring Authentication Events

Combined with the monitoring system, track authentication failures:

```bash
prodinamik audit query --type "auth.failure"
prodinamik metrics  # Shows auth failure rate
```

The Prometheus alert rule `AuthFailureRate` fires when authentication failures exceed 5 per second over 5 minutes, which may indicate a brute-force attack.

### Rate Limit Tuning

- Default rate: 10 requests/second with burst of 20 — suitable for most CI/CD workloads.
- For API integrations, lower to 5 requests/second to protect shared engine instances.
- For internal CLI usage, increase to 50+ requests/second with burst of 100.
- Monitor rate limit hits via the `RateLimitHit` Prometheus alert rule.
