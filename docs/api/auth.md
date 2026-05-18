# Authentication

Prodinamik Engine v1.1 — Authentication & Access Control

API key management with role-based access control (RBAC).
Supports admin, user, and readonly roles with decorator-based protection.

Usage:
    from engine.auth import AuthManager
    auth = AuthManager(base_path="./data/auth")
    key = auth.create_key("deploy-bot", role="admin")
    result = auth.validate_key(key)
    # result.valid=True, result.role="admin", result.name="deploy-bot"

**Module:** `engine.auth.py`

## Classes

### `APIKey`

API key with metadata

**Methods:**

- `to_dict()`
- `from_dict(cls, d)`

### `AuthResult`

Result of a key validation

### `AuthManager`

API key store and validation engine.

Stores keys as JSON in base_path/keys/{key_id}.json.
Raw keys are only shown once on creation (like GitHub tokens).

**Methods:**

- `__init__(base_path)`
- `create_key(name, role, expires_in_days, metadata)`
  — Generate a new API key.
- `validate_key(raw_key)`
  — Validate a raw API key. Returns AuthResult.
- `list_keys()`
  — List all keys (without hashes)
- `revoke_key(key_id)`
  — Revoke (disable) a key
- `get_key(key_id)`
  — Get key info (without hash)
- `require_role(min_role)`
  — Decorator: requires minimum role level to call function.
- `_generate_id(name)`
  — Generate a unique key ID
- `_generate_key()`
  — Generate a raw API key (pdmk_ prefix)
- `_hash_key(raw_key)`
  — SHA-256 hash of raw key
- `_save_key(key)`
  — Persist key to disk
- `_load_cache()`
  — Load all keys from disk into cache

## Functions

### `get_auth_from_header(headers, auth_manager)`

Extract and validate API key from HTTP Authorization header
