"""
WhatsApp API Bridge — FastAPI endpoints that proxy to WhatsApp Service.

FASE 4.1 — Architecture Boundary:
- Frontend → FastAPI Backend → WhatsApp Service (Node.js)
- Frontend NEVER talks to WhatsApp Service directly
- WhatsApp Service NEVER accesses backend database

Service Authentication:
- Backend sends MARCOS_GAS_API_KEY as Bearer token to WhatsApp Service
- WhatsApp Service validates the token
"""

import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

import httpx


router = APIRouter(
    prefix="/whatsapp",
    tags=["WhatsApp"]
)


# ── Config ────────────────────────────────────────────────

WHATSAPP_SERVICE_URL = os.getenv("WHATSAPP_SERVICE_URL", "http://localhost:3001")
WHATSAPP_SERVICE_KEY = os.getenv("MARCOS_GAS_API_KEY", "")


# ── Helpers ───────────────────────────────────────────────

def _get_headers() -> dict:
    """Build headers for service-to-service authentication."""
    headers = {"Content-Type": "application/json"}
    if WHATSAPP_SERVICE_KEY:
        headers["Authorization"] = f"Bearer {WHATSAPP_SERVICE_KEY}"
    return headers


async def _proxy_get(path: str) -> dict:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{WHATSAPP_SERVICE_URL}/api{path}",
                headers=_get_headers(),
                timeout=10,
            )
            return response.json()
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail="Serviço WhatsApp não está acessível."
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


async def _proxy_post(path: str, data: Optional[dict] = None) -> dict:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{WHATSAPP_SERVICE_URL}/api{path}",
                json=data or {},
                headers=_get_headers(),
                timeout=10,
            )
            return response.json()
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail="Serviço WhatsApp não está acessível."
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


# ── Schemas ───────────────────────────────────────────────



class WhatsAppCampaignCreateRequest(BaseModel):
    name: str
    message: str
    list_id: int


# ═══════════════════════════════════════════════════════════
# Multi-Account Endpoints (FASE 4.1)
# ═══════════════════════════════════════════════════════════

@router.get("/accounts")
async def list_accounts():
    """List all WhatsApp accounts with status."""
    return await _proxy_get("/whatsapp/accounts")


@router.get("/accounts/{account_id}")
async def get_account(account_id: str):
    """Get single account status."""
    return await _proxy_get(f"/whatsapp/accounts/{account_id}")


@router.post("/accounts/{account_id}/start")
async def start_account(account_id: str):
    """Start a specific WhatsApp account."""
    return await _proxy_post(f"/whatsapp/accounts/{account_id}/start")


@router.post("/accounts/{account_id}/stop")
async def stop_account(account_id: str):
    """Stop a specific WhatsApp account."""
    return await _proxy_post(f"/whatsapp/accounts/{account_id}/stop")


@router.post("/accounts/{account_id}/logout")
async def logout_account(account_id: str):
    """Logout a specific WhatsApp account."""
    return await _proxy_post(f"/whatsapp/accounts/{account_id}/logout")


@router.get("/accounts/{account_id}/qr")
async def get_account_qr(account_id: str):
    """Get QR code for a specific account."""
    return await _proxy_get(f"/whatsapp/accounts/{account_id}/qr")


@router.get("/accounts/{account_id}/health")
async def account_health(account_id: str):
    """Health check for a specific account."""
    return await _proxy_get(f"/whatsapp/accounts/{account_id}/health")


# ═══════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════
# FASE 5: Message Sending
# ═══════════════════════════════════════════════════════════

class WhatsAppSendMessageRequest(BaseModel):
    """Request to send a WhatsApp message."""
    recipient: str
    message: str
    idempotency_key: Optional[str] = None


@router.post("/accounts/{account_id}/messages")
async def send_message(account_id: str, data: WhatsAppSendMessageRequest):
    """Send a message via a specific WhatsApp account."""
    payload = data.model_dump()
    if not payload.get("idempotency_key"):
        import uuid
        payload["idempotency_key"] = str(uuid.uuid4())
    return await _proxy_post(f"/whatsapp/accounts/{account_id}/messages", payload)


@router.get("/accounts/{account_id}/messages")
async def list_messages(account_id: str, limit: int = 50, offset: int = 0):
    """List sent messages for an account."""
    return await _proxy_get(f"/whatsapp/accounts/{account_id}/messages?limit={limit}&offset={offset}")

# Legacy Endpoints (backward compat)
# ═══════════════════════════════════════════════════════════

@router.get("/status")
async def get_status():
    return await _proxy_get("/whatsapp/status")


@router.get("/health")
async def health_check():
    return await _proxy_get("/whatsapp/health")


@router.get("/qr")
async def get_qr_code():
    return await _proxy_get("/whatsapp/qr")


@router.post("/start")
async def start_session():
    return await _proxy_post("/whatsapp/start")


@router.post("/logout")
async def logout_session():
    return await _proxy_post("/whatsapp/logout")


# ── Contacts ──────────────────────────────────────────────

@router.get("/contacts")
async def list_contacts(limit: int = 50, offset: int = 0):
    return await _proxy_get(f"/contacts?limit={limit}&offset={offset}")


@router.post("/contacts/sync")
async def sync_contacts():
    return await _proxy_post("/contacts/sync")


# ── Customers ─────────────────────────────────────────────

@router.get("/customers")
async def list_customers(limit: int = 50, offset: int = 0):
    return await _proxy_get(f"/customers?limit={limit}&offset={offset}")


@router.post("/customers/{contact_id}/promote")
async def promote_to_customer(contact_id: int, status: str = "UNKNOWN"):
    return await _proxy_post(f"/customers/{contact_id}/promote", {"status": status})


@router.post("/customers/{customer_id}/opt-in")
async def opt_in_customer(customer_id: int):
    return await _proxy_post(f"/customers/{customer_id}/opt-in", {"source": "api"})


@router.post("/customers/{customer_id}/opt-out")
async def opt_out_customer(customer_id: int):
    return await _proxy_post(f"/customers/{customer_id}/opt-out", {"source": "api"})


# ── Lists ─────────────────────────────────────────────────

@router.get("/lists")
async def list_lists():
    return await _proxy_get("/lists")


@router.post("/lists")
async def create_list(name: str, description: Optional[str] = None):
    return await _proxy_post("/lists", {"name": name, "description": description})


@router.post("/lists/seed")
async def seed_lists():
    return await _proxy_post("/lists/seed")


# ── Campaigns ─────────────────────────────────────────────

@router.get("/campaigns")
async def list_campaigns():
    return await _proxy_get("/campaigns")


@router.post("/campaigns")
async def create_campaign(data: WhatsAppCampaignCreateRequest):
    return await _proxy_post("/campaigns", data.model_dump())


@router.post("/campaigns/{campaign_id}/start")
async def start_campaign(campaign_id: int):
    return await _proxy_post(f"/campaigns/{campaign_id}/start")


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(campaign_id: int):
    return await _proxy_post(f"/campaigns/{campaign_id}/pause")


@router.post("/campaigns/{campaign_id}/cancel")
async def cancel_campaign(campaign_id: int):
    return await _proxy_post(f"/campaigns/{campaign_id}/cancel")


@router.get("/campaigns/{campaign_id}/results")
async def get_campaign_results(campaign_id: int):
    return await _proxy_get(f"/campaigns/{campaign_id}/results")
