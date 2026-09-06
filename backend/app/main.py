"""
GasFlow — Sistema operacional para depósitos de gás e água.

Arquitetura: Domain-Driven Design (DDD)
- Domain: Entidades e interfaces de repositório
- Application: Casos de uso (Use Cases)
- Infrastructure: Implementações SQLAlchemy
- Presentation: API Routes e Schemas
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.infrastructure.database.init_db import init_db
from app.presentation.api.health import router as health_router
from app.presentation.api.clients import router as client_router
from app.presentation.api.orders import router as orders_router
from app.presentation.api.products import router as products_router
from app.presentation.api.delivery import router as delivery_router
from app.presentation.api.whatsapp import router as whatsapp_router
from app.presentation.api.inventory import router as inventory_router
from app.presentation.api.finance import router as finance_router
from app.presentation.api.ai import router as ai_router
from app.presentation.api.whatsapp_gateway import router as whatsapp_gateway_router
from app.presentation.api.audio import router as audio_router
from app.presentation.api.automation import router as automation_router
from app.presentation.api.auth import router as auth_router
from app.presentation.api.delivery_ops import router as delivery_ops_router
from app.presentation.api.dashboard import router as dashboard_router
from app.presentation.api.driver_api import router as driver_api_router
from app.presentation.api.printer import router as printer_router
from app.presentation.api.payments import router as payments_router
from app.presentation.api.reports import router as reports_router
from app.presentation.api.dispatch import router as dispatch_router
from app.presentation.api.operations import router as operations_router
from app.presentation.api.communication import router as communication_router
from app.presentation.api.segmentation import router as segmentation_router
from app.presentation.api.reorder import router as reorder_router
from app.presentation.api.whatsapp_automation import router as whatsapp_automation_router
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.logging import LoggingMiddleware, setup_logging
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.rate_limit import RateLimitMiddleware
from app.core.metrics import MetricsMiddleware, render_metrics

# Setup structured logging
logger = setup_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    setup_realtime_bridge()
    _ws_listener_task = None
    if settings.realtime_backend == "redis":
        from app.infrastructure.realtime.websocket import (
            start_cross_worker_listener,
        )

        _ws_listener_task, _ = start_cross_worker_listener(url=settings.realtime_redis_url)
    yield
    if _ws_listener_task is not None:
        _ws_listener_task.cancel()
        try:
            await _ws_listener_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Sistema operacional para depósitos de gás e água — API + WhatsApp Automation",
    lifespan=lifespan,
)

# Security headers (applied first = outermost)
app.add_middleware(SecurityHeadersMiddleware)

# Prometheus metrics (requisições + latência)
app.add_middleware(MetricsMiddleware)

# Request logging
app.add_middleware(LoggingMiddleware)

# Rate limiting
app.add_middleware(RateLimitMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)

# Initialize database (creates tables if not using migrations)
init_db()

logger.info(f"GasFlow backend starting — env={settings.environment}", extra={"service": "gasflow-backend"})


@app.get("/metrics")
def metrics_endpoint():
    """Prometheus metrics (formato text/plain)."""
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)


@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "online",
        "architecture": "Domain-Driven Design (DDD)",
        "services": {
            "api": "http://localhost:8000",
            "whatsapp": "http://localhost:3001",
            "docs": "http://localhost:8000/docs",
            "whatsapp_connect": "http://localhost:3001/connect",
        },
    }


# Root-level routers (backward compatibility)
app.include_router(health_router)
app.include_router(client_router)
app.include_router(orders_router)
app.include_router(products_router)
app.include_router(delivery_router)
app.include_router(whatsapp_router)
app.include_router(inventory_router)
app.include_router(finance_router)
app.include_router(ai_router)
app.include_router(whatsapp_gateway_router)
app.include_router(audio_router)
app.include_router(automation_router)
app.include_router(auth_router)
app.include_router(delivery_ops_router)
app.include_router(driver_api_router)
app.include_router(printer_router)
app.include_router(payments_router)
app.include_router(reports_router)
app.include_router(dashboard_router)
app.include_router(dispatch_router)
app.include_router(operations_router)
app.include_router(communication_router)
app.include_router(segmentation_router)
app.include_router(reorder_router)
app.include_router(whatsapp_automation_router)

# WebSocket realtime
from app.infrastructure.realtime.websocket import router as realtime_ws_router, setup_realtime_bridge

app.include_router(realtime_ws_router)

# Unified v1 API (same routers, /api/v1 prefix)
app.include_router(api_v1_router)
