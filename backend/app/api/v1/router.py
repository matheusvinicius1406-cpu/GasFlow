"""
GasFlow API v1 — Unified Router

Aggregates all module routers under /api/v1 prefix.
Existing root-level endpoints remain for backward compatibility.
"""

from fastapi import APIRouter

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
from app.presentation.api.driver_api import router as driver_api_router
from app.presentation.api.printer import router as printer_router
from app.presentation.api.payments import router as payments_router
from app.presentation.api.reports import router as reports_router

api_v1_router = APIRouter(prefix="/api/v1")

# Include all module routers (original routers already have their own prefixes)
api_v1_router.include_router(health_router, tags=["Health"])
api_v1_router.include_router(auth_router, tags=["Auth"])
api_v1_router.include_router(client_router, tags=["Clients"])
api_v1_router.include_router(orders_router, tags=["Orders"])
api_v1_router.include_router(products_router, tags=["Products"])
api_v1_router.include_router(inventory_router, tags=["Inventory"])
api_v1_router.include_router(finance_router, tags=["Finance"])
api_v1_router.include_router(delivery_router, tags=["Drivers"])
api_v1_router.include_router(delivery_ops_router, tags=["Delivery"])
api_v1_router.include_router(whatsapp_router, tags=["WhatsApp"])
api_v1_router.include_router(whatsapp_gateway_router, tags=["WhatsApp Gateway"])
api_v1_router.include_router(ai_router, tags=["AI"])
api_v1_router.include_router(audio_router, tags=["Audio"])
api_v1_router.include_router(automation_router, tags=["Automation"])
api_v1_router.include_router(printer_router, tags=["Printer"])
api_v1_router.include_router(payments_router, tags=["Payments"])
api_v1_router.include_router(reports_router, tags=["Reports"])
