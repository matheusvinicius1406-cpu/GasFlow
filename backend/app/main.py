"""
GasFlow — Sistema operacional para depósitos de gás e água.

Arquitetura: Domain-Driven Design (DDD)
- Domain: Entidades e interfaces de repositório
- Application: Casos de uso (Use Cases)
- Infrastructure: Implementações SQLAlchemy
- Presentation: API Routes e Schemas
"""

import asyncio
import os
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
from app.presentation.api.settings import router as settings_router
from app.presentation.api.admin import router as admin_router
from app.presentation.api.coupons import router as coupons_router
from app.presentation.api.leads import router as leads_router
from app.presentation.api.integrations import router as integrations_router
from app.presentation.api.contacts_crm import router as contacts_crm_router
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

    # ── Executor de automações em background (opt-in) ────────
    # Processa executions PENDING/APPROVED (incl. reativação) sem depender de
    # chamada manual a POST /whatsapp-automation/process-pending. Desligado
    # por padrão (AUTOMATION_POLL_SECONDS=0) — compose/cron externo continua
    # sendo alternativa. Em multi-worker, qualquer worker pode processar:
    # as executions são marcadas antes do envio (sem duplo envio).
    _automation_poll_task = None
    _automation_poll_seconds = int(os.getenv("AUTOMATION_POLL_SECONDS", "0"))

    # ── Snapshot diário de estoque (P0 3.7) ─────────────────
    # Garante o snapshot do dia no boot (idempotente) e agenda o job
    # diário. Usa o mesmo intervalo do poller de automação (o job é
    # no-op se já existir snapshot do dia). Desligado em TESTING.
    if not os.getenv("TESTING"):
        try:
            import sqlalchemy.orm

            from app.application.inventory.snapshot_service import StockDailySnapshotService
            from app.infrastructure.database.init_db import engine as _snap_engine

            _snap_session = sqlalchemy.orm.Session(bind=_snap_engine)
            try:
                _snap_count = StockDailySnapshotService(_snap_session, "default").ensure_initial_snapshot()
                if _snap_count:
                    logger.info(
                        f"snapshot diário de estoque criado ({_snap_count} produtos)",
                        extra={"service": "gasflow-backend"},
                    )
            finally:
                _snap_session.close()
        except Exception as exc:  # pragma: no cover — nunca derruba a API
            logger.warning(f"snapshot diário de estoque falhou no boot: {exc}")

    _snapshot_poll_task = None
    if _automation_poll_seconds > 0 and not os.getenv("TESTING"):

        async def _snapshot_poller():
            import sqlalchemy.orm

            from app.application.inventory.snapshot_service import StockDailySnapshotService
            from app.infrastructure.database.init_db import engine as _snap_engine

            while True:
                try:
                    session = sqlalchemy.orm.Session(bind=_snap_engine)
                    try:
                        StockDailySnapshotService(session, "default").run_daily_snapshot()
                    finally:
                        session.close()
                except Exception as exc:  # pragma: no cover — nunca derruba a API
                    logger.warning(f"snapshot poller falhou: {exc}")
                await asyncio.sleep(_automation_poll_seconds)

        _snapshot_poll_task = asyncio.create_task(_snapshot_poller())
        logger.info(
            f"snapshot poller iniciado (intervalo={_automation_poll_seconds}s)",
            extra={"service": "gasflow-backend"},
        )

    if _automation_poll_seconds > 0 and not os.getenv("TESTING"):

        async def _automation_poller():
            import sqlalchemy.orm

            from app.infrastructure.database.init_db import engine as _poll_engine
            from app.infrastructure.repositories.whatsapp_automation_repository import (
                SQLAlchemyAutomationRepository,
            )
            from app.application.whatsapp_automation.executor import ExecutionProcessor

            while True:
                try:
                    session = sqlalchemy.orm.Session(bind=_poll_engine)
                    try:
                        repo = SQLAlchemyAutomationRepository(session, "default")
                        processor = ExecutionProcessor(repo)
                        await processor.process_pending_executions(limit=10)
                    finally:
                        session.close()
                except Exception as exc:  # pragma: no cover — nunca derruba a API
                    logger.warning(f"automation poller falhou: {exc}")
                await asyncio.sleep(_automation_poll_seconds)

        _automation_poll_task = asyncio.create_task(_automation_poller())
        logger.info(
            f"automation poller iniciado (intervalo={_automation_poll_seconds}s)",
            extra={"service": "gasflow-backend"},
        )

    yield
    if _ws_listener_task is not None:
        _ws_listener_task.cancel()
        try:
            await _ws_listener_task
        except asyncio.CancelledError:
            pass
    if _automation_poll_task is not None:
        _automation_poll_task.cancel()
        try:
            await _automation_poll_task
        except asyncio.CancelledError:
            pass
    if _snapshot_poll_task is not None:
        _snapshot_poll_task.cancel()
        try:
            await _snapshot_poll_task
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
    # Desktop: FRONTEND_DIST setado → a raiz serve o app React original.
    if _frontend_dist and (_Path(_frontend_dist) / "index.html").is_file():
        return _FileResponse(_Path(_frontend_dist) / "index.html")
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
app.include_router(settings_router)
app.include_router(admin_router)
app.include_router(coupons_router)
app.include_router(leads_router)
app.include_router(integrations_router)
app.include_router(contacts_crm_router)

# Seed das configurações padrão (idempotente)
from sqlalchemy.orm import Session as DBSession
from app.infrastructure.database.init_db import engine as _engine
from app.application.settings.settings_service import SettingsService as _SettingsSvc

_settings_seed_session = _SettingsSvc(DBSession(bind=_engine))
try:
    _created = _settings_seed_session.seed_defaults()
    if _created:
        logger.info(f"system_settings seeded: {_created} defaults criados")
except Exception as _e:  # pragma: no cover
    logger.warning(f"settings seed skipped: {_e}")

# WebSocket realtime
from app.infrastructure.realtime.websocket import router as realtime_ws_router, setup_realtime_bridge

app.include_router(realtime_ws_router)

# Unified v1 API (same routers, /api/v1 prefix)
app.include_router(api_v1_router)

# ── Frontend embutido (GasFlow Desktop) ─────────────────
# Quando FRONTEND_DIST aponta para o build do React (frontend/dist), o
# backend serve o frontend na raiz e espelha TODOS os routers raiz sob
# /api (mesmo contrato do proxy do vite: baseURL '/api' → path sem /api).
# Desligado por padrão — docker/nginx continuam como estavam.
from pathlib import Path as _Path
from fastapi.staticfiles import StaticFiles as _StaticFiles
from fastapi.responses import FileResponse as _FileResponse

_frontend_dist = os.getenv("FRONTEND_DIST", "")
if _frontend_dist and _Path(_frontend_dist).is_dir():
    _root_routers = [
        client_router,
        orders_router,
        products_router,
        delivery_router,
        whatsapp_router,
        inventory_router,
        finance_router,
        ai_router,
        whatsapp_gateway_router,
        audio_router,
        automation_router,
        auth_router,
        delivery_ops_router,
        driver_api_router,
        printer_router,
        payments_router,
        reports_router,
        dashboard_router,
        dispatch_router,
        operations_router,
        communication_router,
        segmentation_router,
        reorder_router,
        whatsapp_automation_router,
        settings_router,
        coupons_router,
        leads_router,
        integrations_router,
        contacts_crm_router,
    ]
    for _r in _root_routers:
        app.include_router(_r, prefix="/api")

    _dist = _Path(_frontend_dist)
    if (_dist / "assets").is_dir():
        app.mount("/assets", _StaticFiles(directory=str(_dist / "assets")), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            from fastapi import HTTPException as _HTTPException

            raise _HTTPException(status_code=404, detail="Not Found")
        candidate = (_dist / full_path).resolve()
        # segurança: nunca servir fora de dist/
        if full_path and candidate.is_file() and str(candidate).startswith(str(_dist.resolve())):
            return _FileResponse(candidate)
        return _FileResponse(_dist / "index.html")
