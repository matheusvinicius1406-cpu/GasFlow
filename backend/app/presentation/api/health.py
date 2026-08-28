"""
Health & Readiness Endpoints — FASE 16

/health — Liveness: is the process alive?
/ready — Readiness: can the service accept traffic?
"""

import time
from fastapi import APIRouter
from sqlalchemy import text

from app.infrastructure.database.connection import engine

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

    # Determine overall status
    all_ok = all(v == "ok" for v in checks.values())
    status = "ready" if all_ok else "degraded"

    result = {
        "status": status,
        "checks": checks,
        "uptime_seconds": round(time.time() - _start_time, 1),
    }

    return result
