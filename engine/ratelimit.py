"""Prodinamik Engine v1.1 — Rate Limiter

Token bucket rate limiter with per-key tracking, burst support,
and degradation integration.

Usage:
    limiter = RateLimiter(rate=10, burst=20)
    allowed, wait = limiter.check("key-123")
    # (True, 0.0) if allowed, (False, 1.5) if rate limited
"""

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional
from datetime import datetime


@dataclass
class Bucket:
    """Token bucket state"""
    tokens: float
    last_refill: float
    burst: float = 0.0


class RateLimiter:
    """Token bucket rate limiter — thread-safe, per-key tracking.

    rate:     tokens per second (long-term average)
    burst:    max burst size (default = rate, meaning no burst)
    """

    def __init__(self, rate: float = 10.0, burst: Optional[float] = None):
        self.rate = rate
        self.burst = burst or rate  # Default: no burst (burst = rate)
        self._lock = threading.Lock()
        self._buckets: Dict[str, Bucket] = {}
        self._stats: Dict[str, dict] = defaultdict(lambda: {
            "allowed": 0, "denied": 0, "last": 0.0
        })

    def check(self, key: str, cost: float = 1.0) -> Tuple[bool, float]:
        """Check if request is allowed.

        Returns (allowed, wait_seconds).
        If allowed=False, wait_seconds is how long to wait before retrying.
        """
        now = time.monotonic()

        with self._lock:
            bucket = self._buckets.get(key)

            if bucket is None:
                # First request: full bucket
                bucket = Bucket(tokens=max(0, self.burst - cost),
                                last_refill=now, burst=self.burst)
                self._buckets[key] = bucket
                self._stats[key]["allowed"] += 1
                self._stats[key]["last"] = now
                return True, 0.0

            # Refill tokens
            elapsed = now - bucket.last_refill
            new_tokens = min(self.burst, bucket.tokens + elapsed * self.rate)
            bucket.last_refill = now

            if new_tokens >= cost:
                bucket.tokens = new_tokens - cost
                self._stats[key]["allowed"] += 1
                self._stats[key]["last"] = now
                return True, 0.0
            else:
                bucket.tokens = new_tokens
                wait = (cost - new_tokens) / self.rate
                self._stats[key]["denied"] += 1
                self._stats[key]["last"] = now
                return False, wait

    def reset(self, key: str = None):
        """Reset rate limiter for a key (or all keys)"""
        with self._lock:
            if key:
                self._buckets.pop(key, None)
                self._stats.pop(key, None)
            else:
                self._buckets.clear()
                self._stats.clear()

    def stats(self, key: str = None) -> dict:
        """Get rate limiter statistics"""
        with self._lock:
            if key:
                s = self._stats.get(key, {})
                bucket = self._buckets.get(key)
                return {
                    "key": key,
                    "allowed": s.get("allowed", 0),
                    "denied": s.get("denied", 0),
                    "tokens": bucket.tokens if bucket else self.burst,
                    "burst": self.burst,
                    "rate": self.rate,
                }
            total_allowed = sum(s["allowed"] for s in self._stats.values())
            total_denied = sum(s["denied"] for s in self._stats.values())
            return {
                "total_keys": len(self._buckets),
                "total_allowed": total_allowed,
                "total_denied": total_denied,
                "rate": self.rate,
                "burst": self.burst,
            }

    def __repr__(self) -> str:
        s = self.stats()
        return (f"RateLimiter(rate={self.rate}/s, burst={self.burst}, "
                f"keys={s['total_keys']}, "
                f"allowed={s['total_allowed']}, "
                f"denied={s['total_denied']})")


# ──────────────────────────────────────────────
# Composite: Auth + Rate Limit
# ──────────────────────────────────────────────

class AuthRateLimiter:
    """Combined authentication + rate limiting middleware.

    Applicable for HTTP server integration.
    """

    def __init__(self, auth_manager=None, rate_limiter=None):
        from .auth import AuthManager
        self.auth = auth_manager or AuthManager()
        self.limiter = rate_limiter or RateLimiter(rate=10, burst=20)

    def check_request(self, api_key: str, cost: float = 1.0) -> dict:
        """Full request check: auth + rate limit.

        Returns dict with:
            allowed: bool
            status: "ok" | "auth_error" | "rate_limited"
            auth_result: AuthResult
            wait: float (seconds to wait if rate limited)
        """
        from .auth import get_auth_from_header

        # Validate key
        auth_result = self.auth.validate_key(api_key)

        result = {
            "allowed": False,
            "status": "auth_error",
            "auth_result": auth_result,
            "wait": 0.0,
        }

        if not auth_result.valid:
            result["error"] = auth_result.error
            return result

        # Check rate limit
        rate_allowed, wait = self.limiter.check(auth_result.key_id, cost=cost)
        if not rate_allowed:
            result["status"] = "rate_limited"
            result["wait"] = wait
            result["error"] = f"Rate limited. Wait {wait:.1f}s"
            return result

        result["allowed"] = True
        result["status"] = "ok"
        return result
