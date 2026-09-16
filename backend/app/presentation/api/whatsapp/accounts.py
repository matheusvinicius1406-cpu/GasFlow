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
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

import httpx

from app.infrastructure.database.dependencies import get_db


router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])


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
        except httpx.ConnectError as exc:
            raise HTTPException(status_code=503, detail="Serviço WhatsApp não está acessível.") from exc
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e


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
        except httpx.ConnectError as exc:
            raise HTTPException(status_code=503, detail="Serviço WhatsApp não está acessível.") from exc
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e


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
async def send_message(account_id: str, data: WhatsAppSendMessageRequest, db: Session = Depends(get_db)):
    """Send a message via a specific WhatsApp account.

    Persiste o envio na thread do CRM (direction=OUTGOING, sender=human)
    para que mensagens manuais/API apareçam nas Conversas (fix D1 — ver
    docs/whatsapp-fix-spec.md). Falha de persistência NUNCA bloqueia o envio.
    """
    payload = data.model_dump()
    if not payload.get("idempotency_key"):
        import uuid

        payload["idempotency_key"] = str(uuid.uuid4())
    result = await _proxy_post(f"/whatsapp/accounts/{account_id}/messages", payload)

    # ── Persistência CRM (outbound) — tolerante a falhas ─────────────
    if isinstance(result, dict) and result.get("success"):
        try:
            import re as _re

            from app.domain.whatsapp.conversation import Conversation, ConversationMessage, ConversationState
            from app.infrastructure.whatsapp.repositories import (
                SQLAlchemyConversationMessageRepository,
                SQLAlchemyConversationRepository,
            )

            # Mesma regra de normalização do gateway (dígitos, lstrip 0, min 8).
            digits = _re.sub(r"\D", "", payload["recipient"]).lstrip("0")
            if len(digits) >= 8:
                conv_repo = SQLAlchemyConversationRepository(db)
                msg_repo = SQLAlchemyConversationMessageRepository(db)
                conv = conv_repo.find_by_phone_and_account(digits, account_id)
                if not conv:
                    conv = conv_repo.create(
                        Conversation(
                            account_id=account_id,
                            customer_phone=digits,
                            state=ConversationState.IDLE,
                        )
                    )
                msg_repo.create(
                    ConversationMessage(
                        conversation_id=conv.id,
                        direction="OUTGOING",
                        sender="human",
                        content=payload["message"],
                        message_type="TEXT",
                        metadata={
                            "provider_message_id": result.get("messageId"),
                            "idempotency_key": payload["idempotency_key"],
                            "origin": "api_send",
                        },
                    )
                )  # repo.create já atualiza last_message/last_message_at da conversa
        except Exception:
            import logging

            logging.getLogger("gasflow.whatsapp.bridge").warning("falha ao persistir outbound no CRM", exc_info=True)
    return result


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
# Reorg F5: os endpoints de CONTATOS do CRM mudaram de namespace.
#   GET/POST /whatsapp/contacts/* → app.presentation.api.whatsapp.contacts
# (listagem do CRM, sync, sync-batch, VCF, reativação, enrich).
# Mantidos aqui apenas os proxies de serviço WhatsApp sem conflito de rota.


@router.post("/crm-sync")
async def trigger_crm_sync(account_id: str = "primary"):
    """Dispara o push de contatos (Node → POST /clients/contacts/sync-batch).

    O serviço WhatsApp coleta os contatos 1:1 da conta e envia ao CRM em
    lotes com X-GasFlow-Key. Útil após conectar/parear para popular o CRM
    sem esperar o push automático do boot.
    """
    return await _proxy_post("/whatsapp/crm-sync", {"accountId": account_id})


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


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: int):
    """Proxy: detalhe de campanha (o FE consome em CampaignResultsPage)."""
    return await _proxy_get(f"/campaigns/{campaign_id}")


@router.get("/campaigns/{campaign_id}/recipients")
async def get_campaign_recipients(campaign_id: int):
    """Proxy: destinatários de campanha (o FE consome em CampaignResultsPage)."""
    return await _proxy_get(f"/campaigns/{campaign_id}/recipients")


@router.get("/lists/{list_id}")
async def get_list_detail(list_id: int):
    """Proxy: detalhe de lista (o FE consome no wizard de campanha)."""
    return await _proxy_get(f"/lists/{list_id}")
