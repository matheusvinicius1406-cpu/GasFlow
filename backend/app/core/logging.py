"""
Structured Logging Configuration — FASE 16

Provides JSON-structured logs for production observability.
Never logs: passwords, tokens, secrets.
"""

import logging
import json
import sys
import time
import uuid
from datetime import datetime
from typing import Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service": "gasflow-backend",
            "message": record.getMessage(),
        }

        if hasattr(record, "endpoint"):
            log_entry["endpoint"] = record.endpoint
        if hasattr(record, "status_code"):
            log_entry["status_code"] = record.status_code
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        if hasattr(record, "client_ip"):
            log_entry["client_ip"] = record.client_ip

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])

        return json.dumps(log_entry, default=str)


def setup_logging(level: str = "INFO"):
    """Configure structured logging."""
    root_logger = logging.getLogger("gasflow")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Console handler with structured format
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    return root_logger


logger = setup_logging()


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs every request with structured data."""

    # Paths to exclude from logging (health checks, etc.)
    EXCLUDE_PATHS = {"/health", "/ready", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        # Skip logging for health/readiness probes
        if request.url.path in self.EXCLUDE_PATHS:
            return await call_next(request)

        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        client_ip = request.client.host if request.client else "unknown"

        # Attach request_id to request state
        request.state.request_id = request_id

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.time() - start_time) * 1000, 1)
            logger.error(
                f"Request failed: {request.method} {request.url.path}",
                extra={
                    "endpoint": f"{request.method} {request.url.path}",
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "request_id": request_id,
                    "client_ip": client_ip,
                },
                exc_info=True,
            )
            raise

        duration_ms = round((time.time() - start_time) * 1000, 1)

        # Log level based on status code
        log_fn = logger.info
        if response.status_code >= 500:
            log_fn = logger.error
        elif response.status_code >= 400:
            log_fn = logger.warning

        log_fn(
            f"{request.method} {request.url.path} -> {response.status_code}",
            extra={
                "endpoint": f"{request.method} {request.url.path}",
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "request_id": request_id,
                "client_ip": client_ip,
            },
        )

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        return response
