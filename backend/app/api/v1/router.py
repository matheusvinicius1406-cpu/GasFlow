"""
GasFlow API v1 — Unified Router

Aggregates all module routers under /api/v1 prefix.
Existing root-level endpoints remain for backward compatibility.
"""

from fastapi import APIRouter

from app.presentation.api.core.health import router as health_router
from app.presentation.api.clients import router as client_router
from app.presentation.api.orders import router as orders_router
from app.presentation.api.catalog.products import router as products_router
from app.presentation.api.logistics.delivery import router as delivery_router
from app.presentation.api.whatsapp.accounts import router as whatsapp_router
from app.presentation.api.catalog.inventory import router as inventory_router
from app.presentation.api.finance.finance import router as finance_router
from app.presentation.api.ai import router as ai_router
from app.presentation.api.whatsapp.gateway import router as whatsapp_gateway_router
from app.presentation.api.whatsapp.cloud_webhook import router as whatsapp_cloud_webhook_router
from app.presentation.api.alerts_webhook import router as alerts_webhook_router
from app.presentation.api.audio import router as audio_router
from app.presentation.api.automation import router as automation_router
from app.presentation.api.core.auth import router as auth_router
from app.presentation.api.logistics.delivery_ops import router as delivery_ops_router
from app.presentation.api.logistics.driver_v1 import router as driver_v1_router
from app.presentation.api.logistics.driver_relay import router as driver_relay_router
from app.presentation.api.logistics.driver_mobile_auth import router as driver_mobile_router
from app.presentation.api.logistics.dispatch import router as dispatch_router
from app.presentation.api.operations import router as operations_router
from app.presentation.api.communication import router as communication_router
from app.presentation.api.printer import router as printer_router
from app.presentation.api.finance.payments import router as payments_router
from app.presentation.api.finance.reports import router as reports_router
from app.presentation.api.core.settings import router as settings_router
from app.presentation.api.core.admin import router as admin_router
from app.presentation.api.coupons import router as coupons_router
from app.presentation.api.leads import router as leads_router
from app.presentation.api.integrations import router as integrations_router
from app.presentation.api.whatsapp.contacts import router as contacts_crm_router
from app.presentation.api.purchase_notes import router as purchase_notes_router
from app.presentation.api.mobile_version import router as mobile_version_router

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
api_v1_router.include_router(whatsapp_cloud_webhook_router, tags=["WhatsApp Cloud API"])
api_v1_router.include_router(alerts_webhook_router, tags=["Alerts"])
api_v1_router.include_router(ai_router, tags=["AI"])
api_v1_router.include_router(audio_router, tags=["Audio"])
api_v1_router.include_router(automation_router, tags=["Automation"])
api_v1_router.include_router(driver_v1_router, tags=["Driver"])
api_v1_router.include_router(
    driver_relay_router, tags=["Driver Relay"]
)  # /internal/*: service-to-service (relay → desktop → backend)
api_v1_router.include_router(driver_mobile_router, tags=["Driver Mobile"])
api_v1_router.include_router(dispatch_router, tags=["Dispatch"])
api_v1_router.include_router(operations_router, tags=["Operations"])
api_v1_router.include_router(communication_router, tags=["Communication"])
api_v1_router.include_router(printer_router, tags=["Printer"])
api_v1_router.include_router(payments_router, tags=["Payments"])
api_v1_router.include_router(reports_router, tags=["Reports"])
api_v1_router.include_router(settings_router, tags=["Settings"])
api_v1_router.include_router(admin_router, tags=["Admin"])
api_v1_router.include_router(coupons_router, tags=["Coupons"])
from app.presentation.api.public_signup import router as public_signup_router  # F10.1: público (sem auth)

api_v1_router.include_router(public_signup_router, tags=["Public Signup"])
api_v1_router.include_router(leads_router, tags=["Leads"])
api_v1_router.include_router(integrations_router, tags=["Integrations"])
api_v1_router.include_router(contacts_crm_router, tags=["Contacts CRM"])
api_v1_router.include_router(purchase_notes_router, tags=["Purchase Notes"])
api_v1_router.include_router(mobile_version_router, tags=["Mobile Update"])
