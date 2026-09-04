"""
Health & Readiness Endpoints — FASE 16

/health — Liveness: is the process alive?
/ready — Readiness: can the service accept traffic?
"""

import time

import httpx
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.infrastructure.database.connection import engine
from app.core.rate_limit_redis import RedisSlidingWindowRateLimiter

router = APIRouter()

_start_time = time.time()


@router.get("/health")
def health():
    """Liveness probe — is the process alive?"""
    return {
        "status": "healthy",
        "service": "gasflow-backend",
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


@router.get("/ready")
def ready():
    """Readiness probe — can the service accept traffic?"""
    checks = {}

    # Database check
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:100]}"

    # Redis check — only when Redis is the active rate-limit backend.
    # Fail-open: if Redis is down, the limiter already degrades to in-memory,
    # so /ready reports degraded instead of crashing the probe.
    if settings.rate_limit_mode == "redis":
        try:
            limiter = RedisSlidingWindowRateLimiter(url=settings.rate_limit_redis_url)
            checks["redis"] = "ok" if limiter.available else "unavailable"
        except Exception as e:
            checks["redis"] = f"error: {str(e)[:100]}"

    # WhatsApp service check — informational only; a missing WhatsApp must
    # not take the whole backend out of the load balancer.
    try:
        url = settings.whatsapp_service_url.rstrip("/") + "/api/health"
        resp = httpx.get(url, timeout=2.0)
        checks["whatsapp"] = "ok" if resp.status_code == 200 else f"error: HTTP {resp.status_code}"
    except Exception as e:
        checks["whatsapp"] = f"error: {str(e)[:100]}"

    # Overall status: database is critical; redis only when it is the active
    # rate-limit backend; whatsapp is informational (see comment above).
    critical = {"database"}
    if settings.rate_limit_mode == "redis":
        critical.add("redis")
    ready = all(checks.get(k) == "ok" for k in critical)
    status = "ready" if ready else "degraded"

    result = {
        "status": status,
        "checks": checks,
        "uptime_seconds": round(time.time() - _start_time, 1),
    }

    return result
