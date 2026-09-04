"""
Redis-backed sliding window rate limiter.

Same interface as the in-memory ``SlidingWindowRateLimiter``
(``check(key, max_requests, window_seconds) -> (allowed, headers)``) so the
middleware can switch backends without changing call sites.

Implementation: one Redis ZSET per key; members are request timestamps.
- ZREMRANGEBYSCORE removes entries older than the window
- ZCARD is the current request count
- ZADD appends the current request; PEXPIRE bounds the key lifetime

Note: the read (zcard) and write (zadd) are not atomic — under high
concurrency the counter can overshoot slightly. Bounded and acceptable for
this tier; a Lua script or pipeline could make it exact later.

``redis`` is imported lazily (constructor) so dev/tests run without it —
the default backend remains in-memory.
"""

import itertools
import logging
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger("app.core.rate_limit_redis")


def _build_headers(
    max_requests: int,
    remaining: int,
    reset_ts: float,
    retry_after: Optional[int] = None,
) -> Dict[str, str]:
    headers = {
        "X-RateLimit-Limit": str(max_requests),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(int(reset_ts)),
    }
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return headers


class RedisSlidingWindowRateLimiter:
    """Sliding window rate limiter backed by Redis (shared across workers)."""

    def __init__(
        self,
        client=None,
        url: str = "redis://localhost:6379/0",
        socket_timeout: float = 1.5,
    ):
        self._client = client
        self._url = url
        self._socket_timeout = socket_timeout
        # Circuit breaker: skip Redis for a while after a failure instead of
        # pinging it on every request. Availability is also cached on success
        # (probe at most once every few seconds), so a healthy Redis is not
        # pinged per-request.
        self._unavailable_until = 0.0
        self._available_until = 0.0
        self._seq = itertools.count()

    def _connect(self):
        """Lazy client creation (avoids importing redis until actually used)."""
        if self._client is None:
            import redis

            self._client = redis.Redis.from_url(
                self._url,
                socket_connect_timeout=self._socket_timeout,
                socket_timeout=self._socket_timeout,
            )
        return self._client

    @property
    def available(self) -> bool:
        """True when Redis responds; caches both success and failure briefly."""
        now = time.time()
        if now < self._unavailable_until:
            return False
        if now < self._available_until:
            return True
        try:
            self._connect().ping()
            self._available_until = now + 5
            return True
        except Exception:
            self._unavailable_until = now + 30
            logger.warning("Redis unreachable — rate limiter falling back to in-memory")
            return False

    def check(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, Dict]:
        """Check rate limit. Returns (allowed, info_dict) — same contract as in-memory."""
        client = self._connect()
        now = time.time()
        cutoff = now - window_seconds
        reset_ts = now + window_seconds

        client.zremrangebyscore(key, "-inf", cutoff)
        count = client.zcard(key)

        if count >= max_requests:
            oldest = client.zrange(key, 0, 0, withscores=True)
            oldest_score = oldest[0][1] if oldest else now
            retry_after = int(oldest_score + window_seconds - now) + 1
            return False, _build_headers(max_requests, 0, reset_ts, retry_after)

        # Unique member per request so same-second collisions don't overwrite.
        member = f"{now:.6f}|{next(self._seq)}"
        client.zadd(key, {member: now})
        client.pexpire(key, int(window_seconds * 1000))

        return True, _build_headers(max_requests, max_requests - count - 1, reset_ts)