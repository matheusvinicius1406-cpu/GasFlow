"""
Rate Limiting Middleware — FastAPI

Configurable rate limiting per endpoint category.
Uses in-memory sliding window (adequate for single-worker dev;
multi-worker production should use Redis-backed implementation).

Categories:
- LOGIN: 5 requests / 5 minutes (brute force protection)
- MUTATION: 60 requests / minute (create/update/delete)
- READ: 120 requests / minute (list/get)
- ADMIN: 30 requests / minute (admin operations)
- DRIVER: 30 requests / minute (driver app)
- PUBLIC: 120 requests / minute (health, root)
"""

import time
import threading
from typing import Dict, Tuple, Optional
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SlidingWindowRateLimiter:
    """Thread-safe sliding window rate limiter."""

    def __init__(self):
        self._buckets: Dict[str, list] = {}
        self._lock = threading.Lock()

    def check(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, Dict]:
        """Check rate limit. Returns (allowed, info_dict)."""
        now = time.time()
        with self._lock:
            bucket = self._buckets.get(key, [])
            cutoff = now - window_seconds
            bucket = [t for t in bucket if t > cutoff]

            if len(bucket) >= max_requests:
                retry_after = int(bucket[0] - cutoff) + 1
                self._buckets[key] = bucket
                return False, {
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(cutoff + window_seconds)),
                    "Retry-After": str(retry_after),
                }

            bucket.append(now)
            self._buckets[key] = bucket
            remaining = max_requests - len(bucket)
            return True, {
                "X-RateLimit-Limit": str(max_requests),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(int(cutoff + window_seconds)),
            }


# Global rate limiter instance
_limiter = SlidingWindowRateLimiter()

# Rate limit policies: (max_requests, window_seconds)
RATE_LIMIT_POLICIES = {
    "login": (5, 300),        # 5 per 5 minutes
    "mutation": (60, 60),     # 60 per minute
    "read": (120, 60),        # 120 per minute
    "admin": (30, 60),        # 30 per minute
    "driver": (30, 60),       # 30 per minute
    "public": (120, 60),      # 120 per minute
}

# Path → policy mapping
PATH_POLICIES = {
    "/auth/login": "login",
    "/auth/logout": "mutation",
    "/auth/users": "admin",
    "/auth/tenants": "admin",
    "/auth/roles": "admin",
    "/auth/audit": "admin",
    "/payment": "mutation",
    "/delivery": "mutation",
    "/dispatch": "admin",
    "/driver": "driver",
    "/whatsapp": "mutation",
    "/ai": "mutation",
    "/audio": "mutation",
    "/inventory": "mutation",
    "/finance": "read",
    "/reports": "read",
    "/products": "read",
    "/clients": "read",
    "/orders": "read",
    "/health": "public",
}


def _get_policy(path: str) -> Tuple[int, int]:
    """Determine rate limit policy for a path."""
    # Check exact match first, then prefix match
    for prefix, policy_name in sorted(PATH_POLICIES.items(), key=lambda x: -len(x[0])):
        if path.startswith(prefix):
            return RATE_LIMIT_POLICIES.get(policy_name, RATE_LIMIT_POLICIES["read"])
    return RATE_LIMIT_POLICIES["read"]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting."""

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for docs and OpenAPI
        path = request.url.path
        if path.startswith("/docs") or path.startswith("/openapi") or path == "/":
            return await call_next(request)

        # Get client identifier (IP or token)
        client_id = request.client.host if request.client else "unknown"
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            client_id = auth[7:27]  # Use first 20 chars of token as identifier

        # Get policy
        max_requests, window = _get_policy(path)
        key = f"{client_id}:{path.split('/')[1] if '/' in path else 'root'}"

        allowed, info = _limiter.check(key, max_requests, window)

        if not allowed:
            return Response(
                content='{"error": "Too many requests. Please try again later."}',
                status_code=429,
                media_type="application/json",
                headers=info,
            )

        response = await call_next(request)
        for header, value in info.items():
            response.headers[header] = value
        return response
