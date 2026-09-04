"""
SC-01 — Testes do rate limiter com Redis (e do fallback in-memory).

Deterministic: exercises RedisSlidingWindowRateLimiter against an in-memory
fake client (dict-backed zsets) — no Redis server required. Also covers the
middleware fallback when Redis is unavailable.
"""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.core.rate_limit as rate_limit_module
from app.core.rate_limit import RateLimitMiddleware
from app.core.rate_limit_redis import RedisSlidingWindowRateLimiter


class FakeRedis:
    """Dict-backed fake covering the zset surface the limiter uses."""

    def __init__(self):
        self.zsets = {}
        self.ping_fails = False
        self.ping_count = 0

    def ping(self):
        self.ping_count += 1
        if self.ping_fails:
            raise ConnectionError("connection refused")
        return True

    def zremrangebyscore(self, key, min_score, max_score):
        import math

        zs = self.zsets.setdefault(key, {})
        lo = -math.inf if min_score == "-inf" else float(min_score)
        hi = math.inf if max_score == "+inf" else float(max_score)
        removed = 0
        for member, score in list(zs.items()):
            if lo <= score <= hi:
                del zs[member]
                removed += 1
        return removed

    def zcard(self, key):
        return len(self.zsets.get(key, {}))

    def zadd(self, key, mapping):
        zs = self.zsets.setdefault(key, {})
        for member, score in mapping.items():
            zs[member] = float(score)
        return len(mapping)

    def zrange(self, key, start, end, withscores=False):
        zs = sorted(self.zsets.get(key, {}).items(), key=lambda kv: kv[1])
        window = zs[start : end + 1 if end >= 0 else None]
        if not withscores:
            return [m for m, _ in window]
        return [[m, s] for m, s in window]

    def pexpire(self, key, ms):
        return True


@pytest.fixture()
def fake_redis():
    return FakeRedis()


@pytest.fixture()
def limiter(fake_redis):
    return RedisSlidingWindowRateLimiter(client=fake_redis)


class TestRedisSlidingWindowRateLimiter:
    def test_allows_until_limit(self, limiter, fake_redis):
        for i in range(5):
            allowed, _ = limiter.check("k", 5, 60)
            assert allowed is True, f"request {i+1} should be allowed"

    def test_blocks_after_limit(self, limiter, fake_redis):
        for _ in range(5):
            limiter.check("k", 5, 60)
        allowed, info = limiter.check("k", 5, 60)
        assert allowed is False
        assert info["X-RateLimit-Limit"] == "5"
        assert info["X-RateLimit-Remaining"] == "0"
        assert "Retry-After" in info

    def test_remaining_count_header(self, limiter, fake_redis):
        allowed, info = limiter.check("k", 10, 60)
        assert allowed is True
        assert info["X-RateLimit-Remaining"] == "9"

    def test_expired_window_allows_again(self, limiter, fake_redis):
        for _ in range(5):
            limiter.check("k", 5, 60)
        # Simulate window passage: timestamps now older than the window.
        for member in list(fake_redis.zsets.get("k", {})):
            fake_redis.zsets["k"][member] = time.time() - 120
        allowed, _ = limiter.check("k", 5, 60)
        assert allowed is True

    def test_keys_are_independent(self, limiter, fake_redis):
        for _ in range(3):
            limiter.check("a", 3, 60)
        allowed, _ = limiter.check("b", 3, 60)
        assert allowed is True
        allowed, _ = limiter.check("a", 3, 60)
        assert allowed is False

    def test_available_true_when_redis_ok(self, limiter):
        assert limiter.available is True

    def test_available_false_when_ping_fails(self, fake_redis):
        fake_redis.ping_fails = True
        rl = RedisSlidingWindowRateLimiter(client=fake_redis)
        assert rl.available is False
        # Circuit breaker: stays unavailable without re-pinging every call.
        fake_redis.ping_fails = False
        assert rl.available is False


class TestMiddlewareFallback:
    """The middleware must never 500 because the rate limiter fails."""

    @pytest.fixture()
    def app(self, monkeypatch):
        app = FastAPI()

        @app.get("/ping")
        def ping():
            return {"ok": True}

        app.add_middleware(RateLimitMiddleware)

        # Force small public policy so tests don't need 120 requests.
        monkeypatch.setitem(
            rate_limit_module.RATE_LIMIT_POLICIES,
            "read",
            (3, 60),
        )
        monkeypatch.setitem(
            rate_limit_module.RATE_LIMIT_POLICIES,
            "public",
            (3, 60),
        )
        return app

    def test_blocks_after_policy_limit(self, app):
        client = TestClient(app)
        for _ in range(3):
            r = client.get("/ping")
            assert r.status_code == 200
        r = client.get("/ping")
        assert r.status_code == 429
        assert "X-RateLimit-Limit" in r.headers

    def test_redis_down_falls_back_to_memory(self, app, monkeypatch, fake_redis):
        fake_redis.ping_fails = True
        redis_limiter = RedisSlidingWindowRateLimiter(client=fake_redis)

        monkeypatch.setattr(rate_limit_module, "_limiter_backend", "redis")
        monkeypatch.setattr(rate_limit_module, "_limiter", redis_limiter)
        monkeypatch.setattr(
            rate_limit_module,
            "_fallback_limiter",
            rate_limit_module.SlidingWindowRateLimiter(),
        )

        client = TestClient(app)
        # Even with Redis down, requests must succeed (in-memory fallback).
        for _ in range(3):
            r = client.get("/ping")
            assert r.status_code == 200
        r = client.get("/ping")
        assert r.status_code == 429

    def test_limiter_exception_fails_open(self, app, monkeypatch):
        class ExplodingLimiter:
            def available(self):
                return True

            def check(self, key, max_requests, window_seconds):
                raise RuntimeError("boom")

        monkeypatch.setattr(rate_limit_module, "_limiter_backend", "redis")
        monkeypatch.setattr(rate_limit_module, "_limiter", ExplodingLimiter())

        client = TestClient(app)
        # Rate limiter exploding must not break the API request.
        r = client.get("/ping")
        assert r.status_code == 200


class TestRedisLimiterWiring:
    """GOLDEN — o limiter Redis de produção deve apontar para o Redis
    configurado (RATE_LIMIT_REDIS_URL), não para o default localhost.

    Regressão: rate_limit.py construía ``RedisSlidingWindowRateLimiter()``
    sem URL — o default ``redis://localhost:6379/0`` não alcançava o Redis
    em container (host ``redis``), o circuit breaker caía sempre no fallback
    in-memory e o rate limit compartilhado entre workers nunca existia.
    """

    def test_module_limiter_uses_configured_url(self, monkeypatch):
        import importlib

        from app.core.config import settings

        monkeypatch.setattr(settings, "rate_limit_mode", "redis")
        monkeypatch.setattr(
            settings, "rate_limit_redis_url", "redis://my-redis:7777/3"
        )
        importlib.reload(rate_limit_module)
        try:
            assert rate_limit_module._limiter_backend == "redis"
            assert isinstance(
                rate_limit_module._limiter, RedisSlidingWindowRateLimiter
            )
            assert rate_limit_module._limiter._url == "redis://my-redis:7777/3"
        finally:
            # Restaura o estado do módulo para os demais testes.
            monkeypatch.setattr(settings, "rate_limit_mode", "memory")
            importlib.reload(rate_limit_module)

    def test_module_limiter_is_memory_when_mode_memory(self, monkeypatch):
        import importlib

        from app.core.config import settings

        monkeypatch.setattr(settings, "rate_limit_mode", "memory")
        importlib.reload(rate_limit_module)
        try:
            assert rate_limit_module._limiter_backend == "memory"
            assert isinstance(
                rate_limit_module._limiter,
                rate_limit_module.SlidingWindowRateLimiter,
            )
        finally:
            importlib.reload(rate_limit_module)